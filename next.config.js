"""
Gedeelde configuratie voor AI-Consultassistent services.
Laadt settings uit environment variabelen met sensible defaults.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatabaseConfig:
    host: str = os.getenv("POSTGRES_HOST", "localhost")
    port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    database: str = os.getenv("POSTGRES_DB", "consultassistent")
    user: str = os.getenv("POSTGRES_USER", "ca_app")
    password: str = os.getenv("POSTGRES_PASSWORD", "")
    encryption_key: str = os.getenv("DB_ENCRYPTION_KEY", "")

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def async_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class RedisConfig:
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    password: str = os.getenv("REDIS_PASSWORD", "")

    @property
    def url(self) -> str:
        return f"redis://:{self.password}@{self.host}:{self.port}/0"


@dataclass
class WhisperConfig:
    model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    model_path: str = os.getenv("WHISPER_MODEL_PATH", "/models/whisper")
    device: str = os.getenv("WHISPER_DEVICE", "cuda")
    compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    language: str = os.getenv("WHISPER_LANGUAGE", "nl")
    beam_size: int = int(os.getenv("WHISPER_BEAM_SIZE", "5"))


@dataclass
class DiarizationConfig:
    enabled: bool = os.getenv("DIARIZATION_ENABLED", "true").lower() == "true"
    hf_token: str = os.getenv("HF_TOKEN", "")


@dataclass
class OllamaConfig:
    host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model: str = os.getenv("OLLAMA_MODEL", "llama3.3:8b-instruct-q4_K_M")
    fallback_model: str = os.getenv("OLLAMA_FALLBACK_MODEL", "")
    timeout: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))


@dataclass
class CloudFallbackConfig:
    enabled: bool = os.getenv("CLOUD_FALLBACK_ENABLED", "false").lower() == "true"
    provider: str = os.getenv("CLOUD_FALLBACK_PROVIDER", "mistral")
    api_key: str = os.getenv("CLOUD_FALLBACK_API_KEY", "")
    api_url: str = os.getenv("CLOUD_FALLBACK_API_URL", "")
    confidence_threshold: float = float(os.getenv("CLOUD_FALLBACK_CONFIDENCE_THRESHOLD", "0.6"))


@dataclass
class AudioConfig:
    sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    format: str = os.getenv("AUDIO_FORMAT", "wav")
    max_duration_seconds: int = int(os.getenv("AUDIO_MAX_DURATION_SECONDS", "3600"))
    storage_path: Path = Path(os.getenv("AUDIO_STORAGE_PATH", "/data/audio"))


@dataclass
class AuditConfig:
    retention_years: int = int(os.getenv("AUDIT_LOG_RETENTION_YEARS", "5"))
    log_path: Path = Path(os.getenv("AUDIT_LOG_PATH", "/data/audit"))


@dataclass
class SecurityConfig:
    secret_key: str = os.getenv("APP_SECRET_KEY", "CHANGE_ME")
    cors_origins: list = field(default_factory=lambda: os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3000"
    ).split(","))
    session_timeout_minutes: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
    max_login_attempts: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))


@dataclass
class AppConfig:
    env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("APP_LOG_LEVEL", "INFO")
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    diarization: DiarizationConfig = field(default_factory=DiarizationConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    cloud_fallback: CloudFallbackConfig = field(default_factory=CloudFallbackConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    @property
    def is_development(self) -> bool:
        return self.env == "development"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


# Singleton
config = AppConfig()
