"""
SmartVoice Cloud API - Authentication

Simple API key authentication via X-API-Key header.
Supports multiple keys for multi-tenant SaaS.
"""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from .config import get_config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
) -> str:
    """Validate API key from request header. Returns the key on success."""
    if not api_key:
        raise HTTPException(status_code=401, detail="API sleutel ontbreekt.")

    config = get_config()
    valid_keys = {k.strip() for k in config.auth.api_keys.split(",") if k.strip()}

    # Also accept admin key
    if config.auth.admin_key:
        valid_keys.add(config.auth.admin_key)

    if api_key not in valid_keys:
        raise HTTPException(status_code=403, detail="Ongeldige API sleutel.")

    return api_key
