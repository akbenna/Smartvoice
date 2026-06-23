#!/usr/bin/env python3
"""
SmartVoice - Trainingsdata-export (Fase 3)
==========================================

Exporteert uit consultation_feedback:
  1. ASR-postcorrectie SFT-dataset  (transcript_original -> transcript_corrected)
  2. SOEP DPO-voorkeursdataset      (soep_original = rejected, soep_corrected = chosen)

Gebruik:
    python tools/build_training_data.py
    python tools/build_training_data.py --asr-out /data/training/asr.jsonl
    python tools/build_training_data.py --only dpo

Volledig lokaal. De datasets bevatten klinische tekst en vallen onder hetzelfde
bewaarregime als de consulten. Train op een GPU-machine; zie
docs/FASE3_FINETUNING.md.
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

from services.learning.training.asr_correction_dataset import ASRDatasetBuilder  # noqa: E402
from services.learning.training.soep_dpo_dataset import SoepDPODatasetBuilder  # noqa: E402


async def _run(args) -> int:
    from shared.database import async_session, close_db

    out = {}
    async with async_session() as session:
        if args.only in (None, "asr"):
            r = await ASRDatasetBuilder(out_path=args.asr_out, min_pairs=args.min_pairs).run(session)
            out["asr"] = r.to_dict()
        if args.only in (None, "dpo"):
            r = await SoepDPODatasetBuilder(out_path=args.dpo_out, min_pairs=args.min_pairs).run(session)
            out["dpo"] = r.to_dict()
    await close_db()

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SmartVoice trainingsdata-export")
    ap.add_argument("--only", choices=["asr", "dpo"], default=None,
                    help="Exporteer alleen deze dataset (default: beide)")
    ap.add_argument("--asr-out", default=None, help="Pad voor ASR SFT-dataset")
    ap.add_argument("--dpo-out", default=None, help="Pad voor SOEP DPO-dataset")
    ap.add_argument("--min-pairs", type=int, default=None,
                    help="Minimaal aantal paren voor 'sufficient' (waarschuwing)")
    args = ap.parse_args(argv)

    try:
        return asyncio.run(_run(args))
    except Exception as e:  # pragma: no cover
        print(f"Export mislukt: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
