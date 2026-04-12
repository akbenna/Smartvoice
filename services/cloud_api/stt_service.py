"""
SmartVoice Cloud API - Speech-to-Text Service

Pluggable STT with support for:
  - Groq Whisper (free tier, fast)
  - Deepgram Nova-2 (best Dutch accuracy, default)
  - OpenAI Whisper API

All providers return a unified TranscriptResult.
Compatible with Python 3.9+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

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


async def transcribe(audio_path: Path, provider: str = None) -> TranscriptResult:
    """Transcribe audio file using the specified or default provider."""
    config = get_config()
    provider = provider or config.stt.default_provider

    logger.info("stt.start", provider=provider, file=str(audio_path))

    if provider == "groq":
        return await _transcribe_groq(audio_path)
    elif provider == "deepgram":
        return await _transcribe_deepgram(audio_path)
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


async def _transcribe_deepgram(audio_path: Path) -> TranscriptResult:
    """Transcribe using Deepgram Nova-2 (best Dutch accuracy)."""
    config = get_config()
    api_key = config.stt.deepgram_api_key
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
            "https://api.deepgram.com/v1/listen",
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
