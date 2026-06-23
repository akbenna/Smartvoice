"""
Tests voor de diff-miner (services/learning/diff_miner.py).
"""

from services.learning.diff_miner import mine_corrections


def _pairs(original, corrected):
    return {(c.wrong, c.correct) for c in mine_corrections(original, corrected)}


def test_mines_medication_misrecognition():
    got = _pairs(
        "patient gebruikt metaformien dagelijks",
        "patient gebruikt metformine dagelijks",
    )
    assert ("metaformien", "metformine") in got


def test_ignores_identical_text():
    assert mine_corrections("zelfde tekst hier", "zelfde tekst hier") == []


def test_ignores_pure_insertions_and_deletions():
    # Arts voegt inhoud toe -> geen woordenlijstcorrectie
    assert _pairs("koorts", "koorts en hoofdpijn") == set()
    # Arts schrapt inhoud -> ook niet
    assert _pairs("koorts en hoofdpijn", "koorts") == set()


def test_rejects_dissimilar_rewrites():
    # Inhoudelijke herschrijving (te ongelijk) wordt niet geleerd
    got = _pairs("patient heeft griep", "patient heeft verkoudheid")
    assert ("griep", "verkoudheid") not in got


def test_skips_terms_with_digits():
    got = _pairs("dosering 500 mg", "dosering 250 mg")
    assert all(not any(ch.isdigit() for ch in w) for w, _ in got)


def test_skips_short_and_stopword_changes():
    # "de" -> "het" is stopwoord/te kort: niet leren
    got = _pairs("de patient komt binnen", "het patient komt binnen")
    assert ("de", "het") not in got


def test_dedupe_within_pair():
    cands = mine_corrections(
        "metaformien en metaformien",
        "metformine en metformine",
    )
    keys = [(c.wrong, c.correct) for c in cands]
    assert len(keys) == len(set(keys))
