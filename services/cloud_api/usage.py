"""
SmartVoice Cloud API - Gebruiksregel vanuit de extensie

Een handeling die volledig in de browser gebeurt, komt nergens in het
gebruikslog terecht. Het opzoeken van een Thuisarts-pagina is zo'n handeling:
dat loopt met opzet zonder server, omdat er dan ook geen patiëntgegeven de
browser uit hoeft. Maar de praktijk moet wel kunnen zien of een functie
gebruikt wordt. Vandaar dit ene kleine eindpunt.

  POST /api/v1/usage   {"action": "patient.thuisarts", "kind": "R78"}

Wat er NIET in mag, en waarom dat hier hard staat en niet in een afspraak:

- Geen URL. Een adres op thuisarts.nl zegt welke aandoening het is, en dat is
  een gezondheidsgegeven. Alleen de ICPC-hoofdrubriek gaat mee, en die staat
  toch al in het dossier.
- Geen vrije tekst. `kind` moet de vorm van een ICPC-code hebben; al het
  andere wordt geweigerd, niet stil afgekapt.
- Geen vrije naam voor de handeling. Een open `action` zou de extensie laten
  bepalen wat er in het log komt te staan, en daarmee het log onbetrouwbaar
  maken. Er is een lijst, en die is kort.

De regel zelf gaat door `audit.log_event`, dat al bewaakt dat er geen inhoud
in het log belandt.
"""

from __future__ import annotations

import re

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import audit
from .auth import verify_api_key

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["usage"])

# Actions the extension handles itself but that may still be counted.
TOEGESTAAN = {"patient.thuisarts"}

ICPC = re.compile(r"^[A-Z]\d{2}$")


class UsageEvent(BaseModel):
    """Exactly two fields. `model_config` rejects the rest instead of dropping
    it: whoever sends text by accident should notice."""

    model_config = {"extra": "forbid"}

    action: str = Field(..., max_length=40)
    kind: str = Field("", max_length=8)


@router.post("/usage")
async def log_usage(body: UsageEvent, user: str = Depends(verify_api_key)):
    if body.action not in TOEGESTAAN:
        raise HTTPException(status_code=400, detail="Deze handeling wordt hier niet gelogd.")
    if body.kind and not ICPC.match(body.kind):
        raise HTTPException(status_code=400, detail="kind moet een ICPC-hoofdrubriek zijn, bijvoorbeeld R78.")
    audit.log_event(user, body.action, kind=body.kind)
    return {"ok": True}
