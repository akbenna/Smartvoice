#!/usr/bin/env python3
"""
SmartVoice - Zelflerende vocabulaire-job (Fase 2, niveau 1)
==========================================================

Draait de zelflerende lus: leert (fout -> goed)-correcties uit artsfeedback,
promoveert ze na een bevestigingsdrempel en exporteert de actieve woordenlijst
naar het bestand dat de transcriptieservice inleest (hotwords + naberekening).

Gebruik:
    python tools/learn_vocabulary.py
    python tools/learn_vocabulary.py --min-confirmations 5 --min-dominance 0.7
    python tools/learn_vocabulary.py --json-out /data/vocabulary/custom_vocabulary.json

Bedoeld om periodiek te draaien (cron / scheduler), bv. dagelijks of wekelijks.
Volledig lokaal; verwerkt geen herleidbare patiëntgegevens buiten de praktijk.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Maak project-root importeerbaar
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.learning.vocabulary_learner import (  # noqa: E402
    LearnerConfig,
    VocabularyLearner,
)


async def _run(cfg: LearnerConfig) -> int:
    from shared.database import async_session, close_db

    learner = VocabularyLearner(cfg)
    async with async_session() as session:
        report = await learner.run(session)
    await close_db()

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SmartVoice zelflerende vocabulaire-job")
    ap.add_argument("--min-confirmations", type=int, default=None,
                    help="Aantal onafhankelijke bevestigingen voor activatie")
    ap.add_argument("--min-dominance", type=float, default=None,
                    help="Minimaal aandeel van de dominante 'goed'-variant (0..1)")
    ap.add_argument("--json-out", type=str, default=None,
                    help="Pad voor de geëxporteerde woordenlijst (override)")
    args = ap.parse_args(argv)

    cfg = LearnerConfig()
    if args.min_confirmations is not None:
        cfg.min_confirmations = args.min_confirmations
    if args.min_dominance is not None:
        cfg.min_dominance = args.min_dominance
    if args.json_out:
        cfg.custom_vocab_path = args.json_out

    try:
        return asyncio.run(_run(cfg))
    except Exception as e:  # pragma: no cover - operationele fout
        print(f"Job mislukt: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
