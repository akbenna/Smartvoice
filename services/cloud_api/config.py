"""
SmartVoice Cloud API - Configuration

All settings via environment variables. Supports multiple STT and LLM providers
with Deepgram + Mistral as defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class STTConfig:
    """Speech-to-text provider configuration."""

    default_provider: str = "deepgram"
    groq_api_key: str = ""
    groq_model: str = "whisper-large-v3-turbo"
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"
    deepgram_language: str = "nl"
    openai_api_key: str = ""
    openai_model: str = "whisper-1"


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration."""

    default_provider: str = "mistral"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    temperature: float = 0.1
    max_tokens: int = 2048


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    host: str = "0.0.0.0"
    port: int = 8002
    debug: bool = False
    cors_origins: str = "*"
    api_keys: str = ""
    max_audio_size_mb: int = 50
    temp_dir: str = "/tmp/smartvoice"

    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Load configuration from environment variables."""
    return AppConfig(
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", os.getenv("API_PORT", "8002"))),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        cors_origins=os.getenv("CORS_ORIGINS", "*"),
        api_keys=os.getenv("API_KEYS", ""),
        max_audio_size_mb=int(os.getenv("MAX_AUDIO_MB", "50")),
        temp_dir=os.getenv("TEMP_DIR", "/tmp/smartvoice"),
        stt=STTConfig(
            default_provider=os.getenv("STT_PROVIDER", "deepgram"),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            groq_model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo"),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            deepgram_model=os.getenv("DEEPGRAM_MODEL", "nova-2"),
            deepgram_language=os.getenv("DEEPGRAM_LANGUAGE", "nl"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_STT_MODEL", "whisper-1"),
        ),
        llm=LLMConfig(
            default_provider=os.getenv("LLM_PROVIDER", "mistral"),
            mistral_api_key=os.getenv("MISTRAL_API_KEY", ""),
            mistral_model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        ),
    )
