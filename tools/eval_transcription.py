#!/usr/bin/env python3
"""
SmartVoice - Evaluatie-CLI
==========================

Reken transcriptie- en SOEP-kwaliteit door op een vaste testset, zodat elke
upgrade (hotwords, ander model, fine-tune) gemeten en terugdraaibaar wordt.

Gebruik:
    # Transcriptie: WER + medische-term-foutmarge
    python tools/eval_transcription.py --mode transcription cases.json

    # SOEP: genormaliseerde edit-afstand gegenereerd vs. goedgekeurd
    python tools/eval_transcription.py --mode soep soep_cases.json

Inputformaten (JSON):
    transcription: [{"reference": "...", "hypothesis": "..."}, ...]
    soep:          [{"generated": {"S":..,"O":..,"E":..,"P":..},
                     "approved":  {"S":..,"O":..,"E":..,"P":..}}, ...]

De testset is gepseudonimiseerd en bevat geen herleidbare patiëntgegevens.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Maak shared/ importeerbaar
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.evaluation import (  # noqa: E402
    default_medical_terms,
    medical_term_error_rate,
    soep_edit_distance,
    word_error_rate,
)


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def eval_transcription(cases: list) -> dict:
    terms = default_medical_terms()
    wers, term_errs = [], []
    total_terms = correct_terms = 0
    all_missed: dict = {}

    for c in cases:
        ref, hyp = c.get("reference", ""), c.get("hypothesis", "")
        wers.append(word_error_rate(ref, hyp))
        tr = medical_term_error_rate(ref, hyp, terms)
        term_errs.append(tr.error_rate)
        total_terms += tr.total_terms
        correct_terms += tr.correct
        for t in tr.missed_terms:
            all_missed[t] = all_missed.get(t, 0) + 1

    overall_term_err = 1.0 - (correct_terms / total_terms) if total_terms else 0.0
    return {
        "n_cases": len(cases),
        "mean_wer": round(_mean(wers), 4),
        "mean_medical_term_error_rate": round(_mean(term_errs), 4),
        "micro_medical_term_error_rate": round(overall_term_err, 4),
        "medical_terms_total": total_terms,
        "medical_terms_correct": correct_terms,
        "top_missed_terms": sorted(all_missed.items(), key=lambda x: -x[1])[:15],
    }


def eval_soep(cases: list) -> dict:
    overalls = []
    field_sums = {"S": [], "O": [], "E": [], "P": []}
    for c in cases:
        r = soep_edit_distance(c.get("generated", {}), c.get("approved", {}))
        overalls.append(r.overall)
        for f, v in r.per_field.items():
            field_sums[f].append(v)
    return {
        "n_cases": len(cases),
        "mean_overall_edit_distance": round(_mean(overalls), 4),
        "mean_per_field": {f: round(_mean(v), 4) for f, v in field_sums.items()},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SmartVoice evaluatie-meetlat")
    ap.add_argument("cases", help="Pad naar JSON-bestand met testcases")
    ap.add_argument("--mode", choices=["transcription", "soep"], default="transcription")
    args = ap.parse_args(argv)

    path = Path(args.cases)
    if not path.exists():
        print(f"Bestand niet gevonden: {path}", file=sys.stderr)
        return 2

    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        print("Verwacht een JSON-lijst van testcases.", file=sys.stderr)
        return 2

    result = eval_transcription(cases) if args.mode == "transcription" else eval_soep(cases)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
