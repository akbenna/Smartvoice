"""
VitaScribe Cloud API - Speech-to-Text Service

Pluggable STT with support for:
  - Groq Whisper (free tier, fast)
  - Deepgram Nova-3 (best Dutch accuracy, default)
  - OpenAI Whisper API

All providers return a unified TranscriptResult.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import os

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import httpx
import structlog

from .config import get_config

logger = structlog.get_logger()


@dataclass
class TranscriptSegment:
    """A single segment of transcribed speech."""
    text: str
    start: float
    end: float
    speaker: str = ""
    confidence: float = 0.0


@dataclass
class TranscriptResult:
    """Unified transcription result across all providers."""
    raw_text: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    language: str = "nl"
    duration_secs: float = 0.0
    provider: str = ""


def met_sprekers(transcript: TranscriptResult) -> str:
    """Het transcript per spreker, zoals het taalmodel het moet lezen.

    Deepgram scheidt de stemmen (diarize) en geeft per uiting een spreker.
    Zonder die labels krijgt het model een lap tekst en moet het raden wie
    de klacht vertelt en wie onderzoekt; met de labels kan het klachten in S
    en bevindingen in O zetten. Opeenvolgende uitingen van dezelfde spreker
    worden een alinea. Er staat bewust "Spreker 1" en niet "arts": wie de
    arts is, leidt het model af uit wat er gezegd wordt, want de
    sprekerherkenning weet dat niet en kan zich vergissen.

    Is er maar een spreker, of geven de segmenten geen spreker (Groq,
    OpenAI), dan blijft het de gewone tekst.
    """
    segmenten = getattr(transcript, "segments", None)
    if not isinstance(segmenten, list):
        return transcript.raw_text
    bruikbaar = [s for s in segmenten if getattr(s, "speaker", "") and (s.text or "").strip()]
    if len({s.speaker for s in bruikbaar}) < 2:
        return transcript.raw_text

    nummers: dict = {}
    alineas: List[List[str]] = []
    vorige = None
    for s in bruikbaar:
        if s.speaker not in nummers:
            nummers[s.speaker] = len(nummers) + 1
        if s.speaker != vorige:
            alineas.append([f"Spreker {nummers[s.speaker]}:"])
            vorige = s.speaker
        alineas[-1].append(s.text.strip())
    return "\n".join(" ".join(a) for a in alineas)


async def transcribe(audio_path: Path, provider: str = None,
                     deepgram_key: Optional[str] = None) -> TranscriptResult:
    """Transcribe audio file using the specified or default provider.

    deepgram_key: the practice's own Deepgram key, if it has one."""
    config = get_config()
    provider = provider or config.stt.default_provider

    logger.info("stt.start", provider=provider, file=str(audio_path))

    if provider == "groq":
        return await _transcribe_groq(audio_path)
    elif provider == "deepgram":
        return await _transcribe_deepgram(audio_path, deepgram_key)
    elif provider == "openai":
        return await _transcribe_openai(audio_path)
    else:
        raise ValueError(f"Onbekende STT provider: {provider}")


async def _transcribe_groq(audio_path: Path) -> TranscriptResult:
    """Transcribe using Groq's free Whisper API."""
    config = get_config()
    api_key = config.stt.groq_api_key
    if not api_key:
        raise ValueError("GROQ_API_KEY niet geconfigureerd.")

    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(audio_path, "rb") as f:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (audio_path.name, f, "audio/webm")},
                data={
                    "model": config.stt.groq_model,
                    "language": "nl",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
            )
        response.raise_for_status()
        data = response.json()

    segments = []
    for seg in data.get("segments", []):
        segments.append(TranscriptSegment(
            text=seg.get("text", "").strip(),
            start=seg.get("start", 0.0),
            end=seg.get("end", 0.0),
            confidence=seg.get("avg_logprob", 0.0),
        ))

    return TranscriptResult(
        raw_text=data.get("text", ""),
        segments=segments,
        language=data.get("language", "nl"),
        duration_secs=data.get("duration", 0.0),
        provider="groq",
    )


async def _transcribe_deepgram(audio_path: Path, api_key: Optional[str] = None) -> TranscriptResult:
    """Transcribe using Deepgram (best Dutch accuracy), with speaker diarization."""
    config = get_config()
    api_key = api_key or config.stt.deepgram_api_key
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY niet geconfigureerd.")

    # Detect content type from extension
    ext = audio_path.suffix.lower()
    content_types = {
        ".webm": "audio/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
    }
    content_type = content_types.get(ext, "audio/webm")

    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        logger.info(
            "deepgram.request",
            audio_size_bytes=len(audio_data),
            audio_size_kb=round(len(audio_data) / 1024, 1),
            content_type=content_type,
            file_ext=ext,
            model=config.stt.deepgram_model,
            language=config.stt.deepgram_language,
        )

        response = await client.post(
            # EU endpoint: processing stays in the EU.
            os.getenv("DEEPGRAM_URL", "https://api.eu.deepgram.com/v1/listen"),
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": content_type,
            },
            params={
                "model": config.stt.deepgram_model,
                "language": config.stt.deepgram_language,
                "punctuate": "true",
                "diarize": "true",
                "smart_format": "true",
                "utterances": "true",
                # AVG: not kept, not used for training.
                "mip_opt_out": "true",
            },
            content=audio_data,
        )

        logger.info("deepgram.response_status", status_code=response.status_code)

        if response.status_code != 200:
            logger.error("deepgram.error", status=response.status_code, body=response.text[:500])

        response.raise_for_status()
        data = response.json()

    # Log full Deepgram response for debugging
    metadata = data.get("metadata", {})
    logger.info(
        "deepgram.result",
        duration=metadata.get("duration", 0),
        channels_count=len(data.get("results", {}).get("channels", [])),
        model_info=metadata.get("model_info", {}),
        request_id=metadata.get("request_id", ""),
    )

    result = data.get("results", {})
    channels = result.get("channels", [{}])
    alternatives = channels[0].get("alternatives", [{}]) if channels else [{}]
    transcript_text = alternatives[0].get("transcript", "") if alternatives else ""

    logger.info(
        "deepgram.transcript",
        text_length=len(transcript_text),
        text_preview=transcript_text[:200] if transcript_text else "(LEEG)",
        confidence=alternatives[0].get("confidence", 0) if alternatives else 0,
    )

    segments = []
    for utt in result.get("utterances", []):
        segments.append(TranscriptSegment(
            text=utt.get("transcript", "").strip(),
            start=utt.get("start", 0.0),
            end=utt.get("end", 0.0),
            speaker=f"spreker_{utt.get('speaker', 0)}",
            confidence=utt.get("confidence", 0.0),
        ))

    metadata = data.get("metadata", {})
    duration = metadata.get("duration", 0.0)

    return TranscriptResult(
        raw_text=transcript_text,
        segments=segments,
        language="nl",
        duration_secs=duration,
        provider="deepgram",
    )


async def _transcribe_openai(audio_path: Path) -> TranscriptResult:
    """Transcribe using OpenAI Whisper API."""
    config = get_config()
    api_key = config.stt.openai_api_key
    if not api_key:
        raise ValueError("OPENAI_API_KEY niet geconfigureerd.")

    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(audio_path, "rb") as f:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (audio_path.name, f, "audio/webm")},
                data={
                    "model": config.stt.openai_model,
                    "language": "nl",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
            )
        response.raise_for_status()
        data = response.json()

    segments = []
    for seg in data.get("segments", []):
        segments.append(TranscriptSegment(
            text=seg.get("text", "").strip(),
            start=seg.get("start", 0.0),
            end=seg.get("end", 0.0),
            confidence=seg.get("avg_logprob", 0.0),
        ))

    return TranscriptResult(
        raw_text=data.get("text", ""),
        segments=segments,
        language=data.get("language", "nl"),
        duration_secs=data.get("duration", 0.0),
        provider="openai",
    )
