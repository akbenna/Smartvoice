"""
Prometheus Metrics
==================
Applicatie-metrics voor monitoring en observability.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# Try to import prometheus_client, graceful fallback if not installed
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Info,
        generate_latest, CONTENT_TYPE_LATEST,
        CollectorRegistry,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.info("prometheus_client niet beschikbaar, metrics disabled")


if PROMETHEUS_AVAILABLE:
    # Custom registry (voorkomt conflicten met default collectors)
    REGISTRY = CollectorRegistry()

    # --- Consult Metrics ---
    CONSULTS_TOTAL = Counter(
        "ca_consults_total",
        "Totaal aantal consulten per status",
        ["status"],
        registry=REGISTRY,
    )
    CONSULTS_ACTIVE = Gauge(
        "ca_consults_active",
        "Aantal actieve consulten (in verwerking)",
        registry=REGISTRY,
    )

    # --- Pipeline Metrics ---
    PIPELINE_DURATION = Histogram(
        "ca_pipeline_duration_seconds",
        "Verwerkingstijd van pipeline stappen",
        ["step"],
        buckets=[1, 5, 10, 30, 60, 120, 300],
        registry=REGISTRY,
    )
    PIPELINE_ERRORS = Counter(
        "ca_pipeline_errors_total",
        "Aantal pipeline fouten per stap",
        ["step", "error_type"],
        registry=REGISTRY,
    )

    # --- LLM Metrics ---
    LLM_REQUESTS = Counter(
        "ca_llm_requests_total",
        "Totaal aantal LLM verzoeken",
        ["operation", "model"],
        registry=REGISTRY,
    )
    LLM_DURATION = Histogram(
        "ca_llm_duration_seconds",
        "LLM response tijd",
        ["operation"],
        buckets=[1, 5, 10, 30, 60, 120],
        registry=REGISTRY,
    )
    LLM_ERRORS = Counter(
        "ca_llm_errors_total",
        "LLM fouten per type",
        ["operation", "error_type"],
        registry=REGISTRY,
    )

    # --- Transcription Metrics ---
    TRANSCRIPTION_DURATION = Histogram(
        "ca_transcription_duration_seconds",
        "Whisper transcriptie tijd",
        buckets=[5, 10, 30, 60, 120, 300, 600],
        registry=REGISTRY,
    )
    TRANSCRIPTION_AUDIO_DURATION = Histogram(
        "ca_transcription_audio_duration_seconds",
        "Duur van getranscribeerde audio",
        buckets=[30, 60, 120, 300, 600, 1200, 3600],
        registry=REGISTRY,
    )

    # --- Auth Metrics ---
    AUTH_ATTEMPTS = Counter(
        "ca_auth_attempts_total",
        "Login pogingen",
        ["result"],  # success, failed, blocked
        registry=REGISTRY,
    )

    # --- System Info ---
    SYSTEM_INFO = Info(
        "ca_system",
        "Systeem informatie",
        registry=REGISTRY,
    )


class MetricsCollector:
    """
    Facade voor metrics collectie.
    Werkt als no-op als prometheus_client niet beschikbaar is.
    """

    def __init__(self):
        self.enabled = PROMETHEUS_AVAILABLE

    def record_consult_started(self):
        if self.enabled:
            CONSULTS_TOTAL.labels(status="started").inc()
            CONSULTS_ACTIVE.inc()

    def record_consult_completed(self, status: str):
        if self.enabled:
            CONSULTS_TOTAL.labels(status=status).inc()
            CONSULTS_ACTIVE.dec()

    def record_pipeline_step(self, step: str, duration: float):
        if self.enabled:
            PIPELINE_DURATION.labels(step=step).observe(duration)

    def record_pipeline_error(self, step: str, error_type: str):
        if self.enabled:
            PIPELINE_ERRORS.labels(step=step, error_type=error_type).inc()

    def record_llm_request(self, operation: str, model: str, duration: float):
        if self.enabled:
            LLM_REQUESTS.labels(operation=operation, model=model).inc()
            LLM_DURATION.labels(operation=operation).observe(duration)

    def record_llm_error(self, operation: str, error_type: str):
        if self.enabled:
            LLM_ERRORS.labels(operation=operation, error_type=error_type).inc()

    def record_transcription(self, processing_duration: float, audio_duration: float):
        if self.enabled:
            TRANSCRIPTION_DURATION.observe(processing_duration)
            TRANSCRIPTION_AUDIO_DURATION.observe(audio_duration)

    def record_auth_attempt(self, result: str):
        if self.enabled:
            AUTH_ATTEMPTS.labels(result=result).inc()

    def set_system_info(self, version: str, env: str, model: str):
        if self.enabled:
            SYSTEM_INFO.info({
                "version": version,
                "environment": env,
                "llm_model": model,
            })

    def get_metrics(self) -> bytes:
        """Genereer Prometheus metrics output."""
        if self.enabled:
            return generate_latest(REGISTRY)
        return b""

    def get_content_type(self) -> str:
        if self.enabled:
            return CONTENT_TYPE_LATEST
        return "text/plain"


# Singleton
metrics = MetricsCollector()
