"""
Tests voor de zelflerende vocabulaire-lus (services/learning/vocabulary_learner.py).

De pure aggregatie/promotie wordt direct getest; de volledige run() wordt getest
met een in-memory FakeSession, zodat geen echte database nodig is.
"""

import asyncio
import json

from services.learning.vocabulary_learner import (
    AggregatedCandidate,
    LearnerConfig,
    VocabularyLearner,
    aggregate_candidates,
    select_promotions,
)


def test_aggregate_counts_confirmations_across_consults():
    pairs = [
        ("patient gebruikt metaformien", "patient gebruikt metformine"),
        ("start met metaformien", "start met metformine"),
        ("metaformien verhoogd", "metformine verhoogd"),
        ("amlodiepine gegeven", "amlodipine gegeven"),
    ]
    cands = {c.wrong: c for c in aggregate_candidates(pairs)}
    assert cands["metaformien"].confirmations == 3
    assert cands["metaformien"].correct == "metformine"
    assert cands["amlodiepine"].confirmations == 1


def test_select_promotions_respects_threshold():
    cfg = LearnerConfig()
    cfg.min_confirmations = 3
    cfg.min_dominance = 0.6
    cands = [
        AggregatedCandidate("metaformien", "metformine", 3, 3, 1.0),
        AggregatedCandidate("amlodiepine", "amlodipine", 1, 1, 1.0),
    ]
    promoted = {c.wrong for c in select_promotions(cands, cfg)}
    assert promoted == {"metaformien"}


def test_select_promotions_respects_dominance():
    cfg = LearnerConfig()
    cfg.min_confirmations = 3
    cfg.min_dominance = 0.6
    # 3 bevestigingen maar slechts 50% dominant -> niet promoten
    cands = [AggregatedCandidate("teststring", "varianta", 3, 6, 0.5)]
    assert select_promotions(cands, cfg) == []


# ── End-to-end run() met FakeSession ──────────────────────────────────

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Minimalistische async sessie die de drie SQL-stappen nabootst."""

    def __init__(self, feedback_pairs):
        self._feedback = feedback_pairs
        self.upserts = {}   # (wrong, correct) -> {"conf":.., "active":..}
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM consultation_feedback" in sql:
            return _FakeResult(list(self._feedback))
        if sql.strip().upper().startswith("INSERT INTO VOCABULARY_CORRECTIONS"):
            self.upserts[(params["wrong"], params["correct"])] = {
                "conf": params["conf"], "active": params["active"],
            }
            return _FakeResult([])
        if "FROM vocabulary_corrections" in sql:
            rows = [
                (w, c) for (w, c), v in self.upserts.items() if v["active"]
            ]
            return _FakeResult(rows)
        return _FakeResult([])

    async def commit(self):
        self.committed = True


def test_full_run_promotes_and_exports(tmp_path):
    out = tmp_path / "custom_vocabulary.json"
    cfg = LearnerConfig()
    cfg.min_confirmations = 3
    cfg.min_dominance = 0.6
    cfg.persist_floor = 2
    cfg.custom_vocab_path = str(out)

    feedback = [
        ("patient gebruikt metaformien", "patient gebruikt metformine"),
        ("start met metaformien", "start met metformine"),
        ("metaformien verhoogd", "metformine verhoogd"),
        ("amlodiepine gegeven", "amlodipine gegeven"),  # te weinig bevestigd
    ]
    session = _FakeSession(feedback)
    learner = VocabularyLearner(cfg)

    report = asyncio.run(learner.run(session))

    assert session.committed is True
    assert report.feedback_rows == 4
    assert ("metaformien", "metformine") in report.promoted_pairs
    assert report.promoted == 1                 # alleen metformine
    # amlodiepine (conf 1) valt onder persist_floor -> niet eens opgeslagen
    assert ("amlodiepine", "amlodipine") not in session.upserts

    # Het exportbestand bevat de actieve term in het juiste formaat
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"metaformien": "metformine"}


def test_full_run_exported_file_loads_into_vocabulary(tmp_path):
    """De geëxporteerde lijst moet door de transcriptieservice leesbaar zijn
    (zelfde formaat als shared.vocabulary.load_custom_vocabulary verwacht)."""
    from shared.vocabulary import load_custom_vocabulary, correct_transcript_full

    out = tmp_path / "custom_vocabulary.json"
    cfg = LearnerConfig()
    cfg.min_confirmations = 2
    cfg.persist_floor = 2
    cfg.custom_vocab_path = str(out)
    # Nieuwe term die NIET in de ingebouwde lijst staat (eigen verwijslocatie)
    feedback = [
        ("verwijzing fysiocentum", "verwijzing fysiocentrum"),
        ("naar fysiocentum", "naar fysiocentrum"),
    ]
    learner = VocabularyLearner(cfg)
    asyncio.run(learner.run(_FakeSession(feedback)))

    n = load_custom_vocabulary(out)
    assert n >= 1
    corrected, _ = correct_transcript_full("patient naar fysiocentum")
    assert "fysiocentrum" in corrected
