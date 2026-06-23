"""
Tests voor de few-shot koude start (services/learning/fewshot_seed.py)
en de integriteit van het seed-bestand.
"""

import json
import re

from services.learning.fewshot_bank import FewShotBank
from services.learning.fewshot_seed import (
    DEFAULT_SEED_PATH,
    load_seed_examples,
    seed_bank,
)

_ICPC_RE = re.compile(r"^[A-Z]\d{2}$")


def test_seed_file_is_valid_and_complete():
    data = json.loads(open(DEFAULT_SEED_PATH, encoding="utf-8").read())
    examples = data["examples"]
    assert len(examples) >= 12
    ids = [e["id"] for e in examples]
    assert len(ids) == len(set(ids))  # unieke id's
    for e in examples:
        soep = e["soep"]
        assert soep.get("S") and soep.get("E") and soep.get("P")
        assert _ICPC_RE.match(soep["icpc_code"])      # geldige ICPC-2 vorm
        assert e["id"].startswith("seed_")


def test_load_seed_examples_builds_index():
    examples = load_seed_examples()
    assert len(examples) >= 12
    # index_text moet klinische inhoud bevatten (uit S + E)
    cyst = next(e for e in examples if e.id == "seed_u71_cystitis")
    assert "cystitis" in cyst.index_text.lower()


def test_seed_bank_idempotent(tmp_path):
    bank_path = tmp_path / "bank.json"
    added1, total1 = seed_bank(str(bank_path))
    added2, total2 = seed_bank(str(bank_path))  # nogmaals
    assert added1 == added2
    assert total1 == total2  # upsert op id -> geen duplicaten


def test_seeded_bank_retrieves_relevant_example(tmp_path):
    bank_path = tmp_path / "bank.json"
    seed_bank(str(bank_path))
    bank = FewShotBank.load(str(bank_path))
    res = bank.select("patient met pijnlijke mictie en aandrang, urineweginfectie", k=1)
    assert res and res[0].id == "seed_u71_cystitis"


def test_seeded_bank_coexists_with_practice_examples(tmp_path):
    from services.learning.fewshot_bank import FewShotExample
    bank_path = tmp_path / "bank.json"
    # Praktijkvoorbeeld eerst
    bank = FewShotBank([FewShotExample("fb_1", "eigen praktijk", {"S": "x", "E": "y"})])
    bank.save(str(bank_path))
    seed_bank(str(bank_path))
    loaded = FewShotBank.load(str(bank_path))
    ids = {e.id for e in loaded.examples}
    assert "fb_1" in ids
    assert any(i.startswith("seed_") for i in ids)
