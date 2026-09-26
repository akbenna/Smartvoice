"""
VitaScribe Cloud API - Versleuteling van de eigen sleutels van praktijken

Een praktijk kan een eigen sleutel bij een AI-dienst opgeven (brieven: Anthropic
of OpenAI; spraak: Deepgram). Die staat in de database, versleuteld met een
sleutel die alleen in de omgeving van de server staat:

  SLEUTELKLUIS   een of meer Fernet-sleutels, kommagescheiden. De eerste
                 versleutelt; alle ontsleutelen. Zo kan de kluissleutel worden
                 vervangen zonder dat opgeslagen sleutels onleesbaar worden:
                 zet de nieuwe vooraan, laat de oude erachter staan.

Maak een kluissleutel met:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Zonder SLEUTELKLUIS kan een praktijk geen eigen sleutel opslaan; alles loopt
dan via de sleutels van de server.
"""

from __future__ import annotations

import os
from typing import Optional


class KluisFout(Exception):
    pass


def _fernet():
    ruw = [k.strip() for k in (os.getenv("SLEUTELKLUIS") or "").split(",") if k.strip()]
    if not ruw:
        return None
    from cryptography.fernet import Fernet, MultiFernet

    try:
        return MultiFernet([Fernet(k.encode("ascii")) for k in ruw])
    except (ValueError, TypeError) as exc:
        raise KluisFout("SLEUTELKLUIS is geen geldige Fernet-sleutel.") from exc


def actief() -> bool:
    try:
        return _fernet() is not None
    except KluisFout:
        return False


def versleutel(geheim: str) -> str:
    f = _fernet()
    if f is None:
        raise KluisFout("Eigen sleutels zijn op deze server niet ingeschakeld (SLEUTELKLUIS ontbreekt).")
    return f.encrypt(geheim.encode("utf-8")).decode("ascii")


def ontsleutel(versleuteld: str) -> Optional[str]:
    """None als de kluis ontbreekt of de sleutel niet meer te lezen is."""
    f = _fernet()
    if f is None:
        return None
    from cryptography.fernet import InvalidToken

    try:
        return f.decrypt(versleuteld.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None
