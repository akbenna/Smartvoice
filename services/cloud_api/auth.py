"""
SmartVoice Cloud API - Authentication

Simple API key authentication via X-API-Key header.
Dev mode: no keys configured = allow all requests.
"""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from .config import get_config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str = Security(api_key_header),
) -> str:
    """Validate API key. No keys configured = dev mode (allow all)."""
    config = get_config()
    valid_keys = {k.strip() for k in config.api_keys.split(",") if k.strip()}

    # Dev mode: no keys configured, allow everything
    if not valid_keys:
        return "dev-mode"

    if not api_key:
        raise HTTPException(status_code=401, detail="API sleutel ontbreekt.")

    if api_key not in valid_keys:
        raise HTTPException(status_code=403, detail="Ongeldige API sleutel.")

    return api_key
