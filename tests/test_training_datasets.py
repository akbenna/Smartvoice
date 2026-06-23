"""
Tests voor de trainingsdata-export (services/learning/training/).
"""

import asyncio
import json

from services.learning.training.asr_correction_dataset import (
    ASRDatasetBuilder,
    build_asr_pairs,
)
from services.learning.training.soep_dpo_dataset import (
    SoepDPODatasetBuilder,
    build_dpo_pairs,
)


# ── ASR-postcorrectie SFT ─────────────────────────────────────────────

def test_build_asr_pairs_filters_and_dedupes():
    pairs = [
        ("patient gebruikt metaformien", "patient gebruikt metformine"),  # ok
        ("zelfde tekst hier ongewijzigd", "zelfde tekst hier ongewijzigd"),  # identiek -> weg
        ("kort", "lang"),  # te kort
        ("patient gebruikt metaformien", "patient gebruikt metformine"),  # duplicaat
        ("hij heeft griep", "een volledig andere zin zonder gelijkenis hier"),  # te ongelijk
    ]
    recs = build_asr_pairs(pairs)
    assert len(recs) == 1
    assert recs[0] == {"input": "patient gebruikt metaformien", "target": "patient gebruikt metformine"}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt, params=None):
        return _FakeResult(self._rows)


def test_asr_builder_writes_jsonl(tmp_path):
    out = tmp_path / "asr.jsonl"
    rows = [
        ("patient gebruikt metaformien", "patient gebruikt metformine"),
        ("bloeddruk hoge tensie gemeten", "bloeddruk hypertensie gemeten"),
    ]
    builder = ASRDatasetBuilder(out_path=str(out), min_pairs=5)
    report = asyncio.run(builder.run(_FakeSession(rows)))

    assert report.feedback_rows == 2
    assert report.records == 2
    assert report.sufficient is False  # < min_pairs=5
    lines = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert all("input" in r and "target" in r for r in lines)


# ── SOEP DPO ──────────────────────────────────────────────────────────

def test_build_dpo_pairs_requires_change_and_fields():
    rows = [
        # geldig: arts wijzigde de S
        ("transcript a",
         {"S": "hoofpijn", "O": "", "E": "spanningshoofdpijn", "P": "paracetamol"},
         {"S": "hoofdpijn sinds 3 dagen", "O": "", "E": "spanningshoofdpijn", "P": "paracetamol"}),
        # ongewijzigd -> geen voorkeurssignaal
        ("transcript b",
         {"S": "x", "O": "", "E": "y", "P": "z"},
         {"S": "x", "O": "", "E": "y", "P": "z"}),
        # corrected mist E -> overslaan
        ("transcript c",
         {"S": "a", "E": "b"},
         {"S": "alleen s"}),
    ]
    recs = build_dpo_pairs(rows)
    assert len(recs) == 1
    r = recs[0]
    assert "transcript a" in r["prompt"]
    assert "hoofdpijn sinds 3 dagen" in r["chosen"]
    assert "hoofpijn" in r["rejected"]


def test_dpo_builder_handles_dict_and_string_jsonb(tmp_path):
    out = tmp_path / "dpo.jsonl"
    rows = [
        ("transcript 1",
         {"S": "klacht", "O": "", "E": "diag", "P": "plan"},
         {"S": "klacht verbeterd", "O": "geen LO", "E": "diag", "P": "plan zn"}),
        ("transcript 2",
         json.dumps({"S": "a", "O": "", "E": "e", "P": "p"}),
         json.dumps({"S": "a beter", "O": "", "E": "e", "P": "p"})),
    ]
    builder = SoepDPODatasetBuilder(out_path=str(out), min_pairs=1)
    report = asyncio.run(builder.run(_FakeSession(rows)))

    assert report.records == 2
    assert report.sufficient is True
    lines = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert all({"prompt", "chosen", "rejected"} <= set(r) for r in lines)
