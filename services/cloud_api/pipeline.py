"""
SmartVoice Cloud API — Processing Pipeline
=============================================
Volledige verwerking: audio → transcript → SOEP → decisief regel → rode vlaggen.
Eén async functie die de Chrome Extension aanroept.
"""

import logging
import time
from dataclasses import dataclass, field

from services.cloud_api.stt_service import get_stt_provider
from services.cloud_api.llm_service import get_llm_provider
from services.cloud_api.prompts import (
    build_soep_prompt,
    build_decisief_prompt,
    build_red_flags_prompt,
)

logger = logging.getLogger("smartvoice.pipeline")


@dataclass
class PipelineResult:
    """Resultaat van de volledige verwerkingspipeline."""

    transcript: str = ""
    soep: dict = field(default_factory=lambda: {
        "S": "", "O": "", "E": "", "P": "",
    })
    decisief: str = ""
    red_flags: str = ""
    stt_provider: str = ""
    llm_provider: str = ""
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "transcript": self.transcript,
            "soep": self.soep,
            "decisief": self.decisief,
            "red_flags": self.red_flags,
            "meta": {
                "stt_provider": self.stt_provider,
                "llm_provider": self.llm_provider,
                "duration_ms": self.duration_ms,
            },
        }


def _parse_soep(raw_text: str) -> dict:
    """
    Parseer de SOEP-output van het LLM naar een dict.
    Verwacht formaat:
        S: ...
        O: ...
        E: ...
        P: ...
    """
    result = {"S": "", "O": "", "E": "", "P": ""}
    current_key = None

    for line in raw_text.strip().splitlines():
        stripped = line.strip()

        # Detecteer sectie-header
        for key in ("S", "O", "E", "P"):
            if stripped.upper().startswith(f"{key}:") or stripped.upper().startswith(f"{key} :"):
                current_key = key
                # Pak de tekst na "S:" of "S :"
                after_colon = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
                result[key] = after_colon
                break
        else:
            # Vervolgregel: voeg toe aan huidige sectie
            if current_key and stripped:
                if result[current_key]:
                    result[current_key] += " " + stripped
                else:
                    result[current_key] = stripped

    return result


async def process_consultation(
    audio_bytes: bytes,
    filename: str = "audio.webm",
    stt_provider_name: str | None = None,
    llm_provider_name: str | None = None,
    skip_red_flags: bool = False,
) -> PipelineResult:
    """
    Verwerk een consultatie-opname door de volledige pipeline.

    Stappen:
    1. Audio → transcript (STT)
    2. Transcript → SOEP-verslag (LLM)
    3. SOEP → decisiefe regel (LLM)
    4. Transcript + SOEP → rode vlaggen (LLM, optioneel)
    """
    start = time.monotonic()
    result = PipelineResult()

    try:
        # ── Stap 1: Transcriptie ───────────────────────────────────
        stt = get_stt_provider(stt_provider_name)
        result.stt_provider = stt_provider_name or "default"
        logger.info("Pipeline stap 1/4: STT via %s", type(stt).__name__)

        result.transcript = await stt.transcribe(audio_bytes, filename)

        if not result.transcript.strip():
            result.error = "Lege transcriptie — geen spraak gedetecteerd in de audio."
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result

        # ── Stap 2: SOEP-generatie ─────────────────────────────────
        llm = get_llm_provider(llm_provider_name)
        result.llm_provider = llm_provider_name or "default"
        logger.info("Pipeline stap 2/4: SOEP via %s", type(llm).__name__)

        sys_prompt, usr_prompt = build_soep_prompt(result.transcript)
        soep_raw = await llm.generate(sys_prompt, usr_prompt)
        result.soep = _parse_soep(soep_raw)

        # ── Stap 3: Decisiefe regel ────────────────────────────────
        logger.info("Pipeline stap 3/4: Decisiefe regel")
        soep_text = "\n".join(f"{k}: {v}" for k, v in result.soep.items())
        sys_prompt, usr_prompt = build_decisief_prompt(soep_text)
        result.decisief = (await llm.generate(sys_prompt, usr_prompt)).strip()

        # ── Stap 4: Rode vlaggen (optioneel) ───────────────────────
        if not skip_red_flags:
            logger.info("Pipeline stap 4/4: Rode vlaggen detectie")
            sys_prompt, usr_prompt = build_red_flags_prompt(
                result.transcript, soep_text
            )
            result.red_flags = (await llm.generate(sys_prompt, usr_prompt)).strip()
        else:
            logger.info("Pipeline stap 4/4: Rode vlaggen overgeslagen")
            result.red_flags = ""

    except Exception as exc:
        logger.exception("Pipeline fout: %s", exc)
        result.error = str(exc)

    result.duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "Pipeline voltooid in %d ms (stt=%s, llm=%s)",
        result.duration_ms,
        result.stt_provider,
        result.llm_provider,
    )
    return result
