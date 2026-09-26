"""
VitaScribe Cloud API - Praktijkregister (PostgreSQL)

Het register houdt bij welke praktijken VitaScribe mogen gebruiken, met welke
gebruikers, tot wanneer, en met welke eigen sleutels. Het staat op de server en
niet in de extensie: VitaScribe werkt toch alleen via deze server, dus er komt
geen nieuwe gegevensstroom bij, en zo kan een praktijk of gebruiker direct
worden uitgezet in plaats van pas wanneer een code verloopt.

Zonder DATABASE_URL staat het register uit. De server werkt dan zoals voorheen,
met de sleutels uit API_USERS en API_KEYS. Zo breekt een uitrol zonder database
niets, en kan het register worden aangezet door op Railway een PostgreSQL toe te
voegen.

Het schema staat in register_schema.sql en wordt bij de eerste verbinding
uitgevoerd; elke opdracht daarin is idempotent.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger()

SCHEMA = (Path(__file__).parent / "register_schema.sql").read_text(encoding="utf-8")

_pool = None
_lock = asyncio.Lock()


def database_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def actief() -> bool:
    """Staat het register aan? Dan geldt het ook als er geen sleutels in de omgeving staan."""
    return bool(database_url())


async def pool():
    """De verbindingspool, bij de eerste aanroep gemaakt, met het schema erop."""
    global _pool
    if not actief():
        return None
    if _pool is not None:
        return _pool
    async with _lock:
        if _pool is None:
            import asyncpg  # alleen nodig als het register aan staat

            nieuw = await asyncpg.create_pool(
                database_url(), min_size=1, max_size=int(os.getenv("DATABASE_POOL_MAX", "5")),
                command_timeout=10,
            )
            async with nieuw.acquire() as conn:
                await conn.execute(SCHEMA)
            _pool = nieuw
            logger.info("register.verbonden")
    return _pool


async def sluit() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def fetch(query: str, *args: Any) -> list:
    p = await pool()
    async with p.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any):
    p = await pool()
    async with p.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args: Any) -> str:
    p = await pool()
    async with p.acquire() as conn:
        return await conn.execute(query, *args)


async def log(door: str, handeling: str, praktijk_id: Optional[int] = None, **details: Any) -> None:
    """Een regel in het beheerlog. Bewaar hier nooit een sleutel."""
    try:
        await execute(
            "INSERT INTO vs_beheerlog (door, handeling, praktijk_id, details) VALUES ($1, $2, $3, $4::jsonb)",
            door, handeling, praktijk_id, json.dumps(details, ensure_ascii=False, default=str),
        )
    except Exception as exc:  # het log mag nooit een handeling laten mislukken
        logger.error("register.log_mislukt", error=str(exc))
