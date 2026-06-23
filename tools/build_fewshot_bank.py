#!/usr/bin/env python3
"""
SmartVoice - Few-shot-bank builder (Fase 2, niveau 2)
=====================================================

Vult de few-shot-bank met door de arts goedgekeurde SOEP's uit
consultation_feedback. De bank wordt door de extractieservice gebruikt om bij
SOEP-generatie de meest gelijkende praktijkvoorbeelden mee te geven.

Gebruik:
    python tools/build_fewshot_bank.py
    python tools/build_fewshot_bank.py --path /data/fewshot/soep_examples.json

Periodiek draaien (cron/scheduler), bv. wekelijks. Volledig lokaal en
gepseudonimiseerd.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.learning.fewshot_builder import FewShotBankBuilder  # noqa: E402


async def _run(path: str | None, max_examples: int | None) -> int:
    from shared.database import async_session, close_db

    builder = FewShotBankBuilder(path=path, max_examples=max_examples)
    async with async_session() as session:
        report = await builder.run(session)
    await close_db()

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SmartVoice few-shot-bank builder")
    ap.add_argument("--path", default=None, help="Doelbestand voor de bank (override)")
    ap.add_argument("--max-examples", type=int, default=None, help="Maximale bankgrootte")
    args = ap.parse_args(argv)

    try:
        return asyncio.run(_run(args.path, args.max_examples))
    except Exception as e:  # pragma: no cover
        print(f"Job mislukt: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
