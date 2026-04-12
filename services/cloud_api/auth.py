"""
SmartVoice Cloud API — Authenticatie
=====================================
Simpele API key authenticatie via X-API-Key header.
Multi-tenant: elke praktijk krijgt een eigen key.
"""

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from services.cloud_api.config import config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Valideer de API key.
    Als er geen keys geconfigureerd zijn (development), sta alles toe.
    """
    # Development mode: geen keys geconfigureerd → alles toelaten
    if not config.api.api_keys:
        return "dev-mode"

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key ontbreekt. Stuur een X-API-Key header mee.",
        )

    if api_key not in config.api.api_keys:
        raise HTTPException(
            status_code=403,
            detail="Ongeldige API key.",
        )

    return api_key
