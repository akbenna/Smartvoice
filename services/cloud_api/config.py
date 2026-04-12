"""
SmartVoice Cloud API — Configuratie
====================================
Alle settings via environment variabelen met sensible defaults.
Ondersteunt meerdere STT en LLM providers.
"""

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class STTConfig:
    """Speech-to-Text provider configuratie."""
    default_provider: str = os.getenv("STT_PROVIDER", "groq")

    # Groq (gratis tier: 14.400 sec/dag)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

    # Deepgram (beste Nederlands, ~$0.0043/min)
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
    deepgram_model: str = os.getenv("DEEPGRAM_MODEL", "nova-2")
    deepgram_language: str = os.getenv("DEEPGRAM_LANGUAGE", "nl")

    # OpenAI Whisper (~$0.006/min)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_STT_MODEL", "whisper-1")


@dataclass
class LLMConfig:
    """LLM provider configuratie."""
    default_provider: str = os.getenv("LLM_PROVIDER", "mistral")

    # Mistral (EU-gevestigd, ~$0.001/1K tokens)
    mistral_api_key: str = os.getenv("MISTRAL_API_KEY", "")
    mistral_model: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

    # Anthropic Claude Haiku (~$0.00025/1K input)
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    # Google Gemini Flash (~$0.000075/1K tokens)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


@dataclass
class APIConfig:
    """API server configuratie."""
    host: str = os.getenv("API_HOST", "0.0.0.0")
    port: int = int(os.getenv("API_PORT", "8002"))
    api_keys: list = field(default_factory=lambda: [
        k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()
    ])
    cors_origins: list = field(default_factory=lambda: [
        o.strip() for o in os.getenv(
            "CORS_ORIGINS",
            "chrome-extension://,http://localhost:3000"
        ).split(",") if o.strip()
    ])
    max_audio_mb: int = int(os.getenv("MAX_AUDIO_MB", "50"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


@dataclass
class CloudConfig:
    """Root configuratie."""
    api: APIConfig = field(default_factory=APIConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


config = CloudConfig()
