"""
SmartVoice Cloud API — Speech-to-Text Service
===============================================
Pluggable STT met Groq (gratis), Deepgram (best NL), en OpenAI Whisper.
Elke provider implementeert dezelfde interface: transcribe(audio_bytes) -> str.
"""

import io
import logging
from abc import ABC, abstractmethod

import httpx

from services.cloud_api.config import config

logger = logging.getLogger("smartvoice.stt")


class STTProvider(ABC):
    """Basis-interface voor alle STT providers."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Transcribeer audio bytes naar tekst."""
        ...


class GroqSTT(STTProvider):
    """
    Groq Whisper — gratis tier: 14.400 seconden/dag.
    Snelste optie, goede kwaliteit voor Nederlands.
    """

    API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        api_key = config.stt.groq_api_key
        if not api_key:
            raise ValueError("GROQ_API_KEY niet geconfigureerd")

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_bytes, "audio/webm")},
                data={
                    "model": config.stt.groq_model,
                    "language": "nl",
                    "response_format": "text",
                    "prompt": (
                        "Dit is een huisartsconsult in het Nederlands. "
                        "Medische termen: anamnese, tractus, auscultatie, "
                        "palpatie, percussie, bloeddruk, saturatie, ECG, "
                        "lab, BSE, CRP, glucose, HbA1c, TSH, creatinine."
                    ),
                },
            )

        if resp.status_code != 200:
            logger.error("Groq STT fout %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Groq STT fout: {resp.status_code} — {resp.text}")

        transcript = resp.text.strip()
        logger.info("Groq transcriptie voltooid: %d tekens", len(transcript))
        return transcript


class DeepgramSTT(STTProvider):
    """
    Deepgram Nova-2 — beste Nederlandse herkenning (~€0,0043/min).
    Ondersteunt diarisation en smart formatting.
    """

    API_URL = "https://api.deepgram.com/v1/listen"

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        api_key = config.stt.deepgram_api_key
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY niet geconfigureerd")

        params = {
            "model": config.stt.deepgram_model,
            "language": config.stt.deepgram_language,
            "smart_format": "true",
            "punctuate": "true",
            "diarize": "true",
            "paragraphs": "true",
        }

        content_type = "audio/webm"
        if filename.endswith(".wav"):
            content_type = "audio/wav"
        elif filename.endswith(".mp3"):
            content_type = "audio/mpeg"

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self.API_URL,
                params=params,
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type": content_type,
                },
                content=audio_bytes,
            )

        if resp.status_code != 200:
            logger.error("Deepgram STT fout %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Deepgram STT fout: {resp.status_code} — {resp.text}")

        data = resp.json()
        transcript = (
            data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
        )

        logger.info("Deepgram transcriptie voltooid: %d tekens", len(transcript))
        return transcript


class OpenAISTT(STTProvider):
    """
    OpenAI Whisper API (~€0,006/min).
    Betrouwbare fallback, brede taalondersteuning.
    """

    API_URL = "https://api.openai.com/v1/audio/transcriptions"

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        api_key = config.stt.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY niet geconfigureerd")

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_bytes, "audio/webm")},
                data={
                    "model": config.stt.openai_model,
                    "language": "nl",
                    "response_format": "text",
                    "prompt": (
                        "Huisartsconsult, Nederlandse medische terminologie: "
                        "anamnese, lichamelijk onderzoek, differentiaaldiagnose, "
                        "SOEP, verwijzing, recept, bloeddruk, saturatie."
                    ),
                },
            )

        if resp.status_code != 200:
            logger.error("OpenAI STT fout %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"OpenAI STT fout: {resp.status_code} — {resp.text}")

        transcript = resp.text.strip()
        logger.info("OpenAI transcriptie voltooid: %d tekens", len(transcript))
        return transcript


# ── Provider registry ──────────────────────────────────────────────

_PROVIDERS: dict[str, type[STTProvider]] = {
    "groq": GroqSTT,
    "deepgram": DeepgramSTT,
    "openai": OpenAISTT,
}


def get_stt_provider(name: str | None = None) -> STTProvider:
    """
    Haal een STT provider op basis van naam.
    Zonder naam: gebruik de geconfigureerde default.
    """
    provider_name = (name or config.stt.default_provider).lower()
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(
            f"Onbekende STT provider: '{provider_name}'. "
            f"Kies uit: {', '.join(_PROVIDERS.keys())}"
        )
    return cls()
