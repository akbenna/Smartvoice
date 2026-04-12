"""
SmartVoice Cloud API - Processing Pipeline

Orchestrates the full flow: Audio → STT → SOEP → Decisief Regel → Detection
Single entry point for the Chrome extension.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import structlog

from . import llm_service, stt_service
from .prompts import (
    DECISIEF_SYSTEM_PROMPT,
    DECISIEF_USER_TEMPLATE,
    DETECTION_SYSTEM_PROMPT,
    DETECTION_USER_TEMPLATE,
    SOEP_SYSTEM_PROMPT,
    SOEP_USER_TEMPLATE,
)

logger = structlog.get_logger()


@dataclass
class SOEPResult:
    s: str = ""
    o: str = ""
    e: str = ""
    p: str = ""
    icpc_code: str = ""
    icpc_titel: str = ""


@dataclass
class DetectionResult:
    rode_vlaggen: List[Dict] = field(default_factory=list)
    ontbrekende_info: List[Dict] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Complete result from a single consultation processing."""

    transcript: str = ""
    soep: SOEPResult = field(default_factory=SOEPResult)
    decisief: str = ""
    detection: DetectionResult = field(default_factory=DetectionResult)
    duration_secs: float = 0.0
    stt_provider: str = ""
    llm_provider: str = ""

    def to_dict(self) -> dict:
        return {
            "transcript": self.transcript,
            "soep": asdict(self.soep),
            "decisief": self.decisief,
            "detection": asdict(self.detection),
            "duration_secs": self.duration_secs,
            "stt_provider": self.stt_provider,
            "llm_provider": self.llm_provider,
        }


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


async def process_consultation(
    audio_path: Path,
    stt_provider: str = None,
    llm_provider: str = None,
) -> PipelineResult:
    """
    Process a consultation audio file through the full pipeline.

    Steps:
    1. Transcribe audio (STT)
    2. Generate SOEP note (LLM)
    3. Generate decisief regel (LLM)
    4. Detect red flags (LLM)
    """
    result = PipelineResult()

    # ── Step 1: Transcription ──
    logger.info("pipeline.step", step="transcription")
    transcript = await stt_service.transcribe(audio_path, provider=stt_provider)
    result.transcript = transcript.raw_text
    result.duration_secs = transcript.duration_secs
    result.stt_provider = transcript.provider

    if not transcript.raw_text.strip():
        logger.warning(
            "pipeline.empty_transcript",
            audio_path=str(audio_path),
            duration_secs=transcript.duration_secs,
            provider=transcript.provider,
        )
        result.decisief = (
            f"Geen spraak gedetecteerd. "
            f"Audio duur: {transcript.duration_secs:.1f}s, "
            f"Provider: {transcript.provider}, "
            f"Bestandsgrootte: {audio_path.stat().st_size / 1024:.1f} KB"
        )
        return result

    # ── Step 2: SOEP Generation ──
    logger.info("pipeline.step", step="soep_generation")
    try:
        soep_response = await llm_service.complete(
            system_prompt=SOEP_SYSTEM_PROMPT,
            user_prompt=SOEP_USER_TEMPLATE.format(transcript=transcript.raw_text),
            provider=llm_provider,
            json_mode=True,
        )
        soep_data = _parse_json_response(soep_response)
        result.soep = SOEPResult(
            s=soep_data.get("s", ""),
            o=soep_data.get("o", ""),
            e=soep_data.get("e", ""),
            p=soep_data.get("p", ""),
            icpc_code=soep_data.get("icpc_code", ""),
            icpc_titel=soep_data.get("icpc_titel", ""),
        )
        result.llm_provider = llm_provider or "default"
    except Exception as e:
        logger.error("pipeline.soep_error", error=str(e))
        result.soep = SOEPResult(s="Fout bij SOEP generatie.", e=str(e))

    # ── Step 3: Decisief Regel ──
    logger.info("pipeline.step", step="decisief")
    try:
        icpc_line = ""
        if result.soep.icpc_code:
            icpc_line = f"ICPC: {result.soep.icpc_code} - {result.soep.icpc_titel}"

        decisief_response = await llm_service.complete(
            system_prompt=DECISIEF_SYSTEM_PROMPT,
            user_prompt=DECISIEF_USER_TEMPLATE.format(
                s=result.soep.s,
                o=result.soep.o,
                e=result.soep.e,
                p=result.soep.p,
                icpc_line=icpc_line,
            ),
            provider=llm_provider,
        )
        result.decisief = decisief_response.strip().strip('"').strip("'")
    except Exception as e:
        logger.error("pipeline.decisief_error", error=str(e))
        result.decisief = "Fout bij generatie decisief regel."

    # ── Step 4: Red Flag Detection ──
    logger.info("pipeline.step", step="detection")
    try:
        detection_response = await llm_service.complete(
            system_prompt=DETECTION_SYSTEM_PROMPT,
            user_prompt=DETECTION_USER_TEMPLATE.format(
                s=result.soep.s,
                o=result.soep.o,
                e=result.soep.e,
                p=result.soep.p,
                icpc_code=result.soep.icpc_code or "-",
                icpc_titel=result.soep.icpc_titel or "-",
            ),
            provider=llm_provider,
            json_mode=True,
        )
        detection_data = _parse_json_response(detection_response)
        result.detection = DetectionResult(
            rode_vlaggen=detection_data.get("rode_vlaggen", []),
            ontbrekende_info=detection_data.get("ontbrekende_info", []),
        )
    except Exception as e:
        logger.error("pipeline.detection_error", error=str(e))

    return result
