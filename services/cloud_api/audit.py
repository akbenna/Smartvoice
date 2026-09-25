"""
SmartVoice Cloud API - Usage log (NEN 7513)

Records WHO used WHICH function WHEN, and with which outcome; never the
content (no audio, text, names or dossier data). One JSON line per event on
stdout (Railway keeps it) and, when AUDIT_LOG_PATH is set, appended to that
file as well.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

logger = structlog.get_logger()

_ALLOWED_DETAIL = {"kind", "mode", "provider", "chars", "seconds", "status", "consent", "aanvrager", "sections"}


def log_event(user: str, action: str, **detail: Any) -> None:
    """Write one usage event. Only whitelisted, content-free details are kept."""
    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "user": user or "onbekend",
        "action": action,
    }
    for key, value in detail.items():
        if key in _ALLOWED_DETAIL and isinstance(value, (str, int, float, bool)) and len(str(value)) <= 40:
            event[key] = value
    logger.info("audit", **event)
    path = os.getenv("AUDIT_LOG_PATH")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError as exc:  # never let logging break care
            logger.error("audit.write_failed", error=str(exc))
