"""
Tests voor de evaluatie-meetlat (shared/evaluation.py).
"""

from shared.evaluation import (
    medical_term_error_rate,
    normalize_text,
    soep_edit_distance,
    word_error_rate,
)


def test_wer_perfect_match():
    assert word_error_rate("de patient heeft koorts", "de patient heeft koorts") == 0.0


def test_wer_counts_word_errors():
    # 1 substitutie op 4 woorden = 0.25
    wer = word_error_rate("de patient heeft koorts", "de patient heeft hoofdpijn")
    assert abs(wer - 0.25) < 1e-9


def test_wer_ignores_punctuation_and_case():
    assert word_error_rate("Koorts, hoesten.", "koorts hoesten") == 0.0


def test_wer_empty_reference():
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("", "iets") == 1.0


def test_medical_term_error_rate_detects_miss():
    terms = ["metformine", "hypertensie"]
    # referentie noemt beide; hypothese mist metformine
    res = medical_term_error_rate(
        reference="patient met hypertensie gebruikt metformine",
        hypothesis="patient met hypertensie gebruikt metaformien",
        terms=terms,
    )
    assert res.total_terms == 2
    assert res.correct == 1
    assert "metformine" in res.missed_terms
    assert abs(res.error_rate - 0.5) < 1e-9


def test_medical_term_error_rate_multiword():
    terms = ["diabetes mellitus"]
    res = medical_term_error_rate(
        reference="bekend met diabetes mellitus type 2",
        hypothesis="bekend met diabetes melitus type 2",
        terms=terms,
    )
    assert res.total_terms == 1
    assert res.correct == 0


def test_soep_edit_distance_identical_is_zero():
    soep = {"S": "hoofdpijn", "O": "geen LO", "E": "spanningshoofdpijn", "P": "paracetamol"}
    res = soep_edit_distance(soep, soep)
    assert res.overall == 0.0
    assert all(v == 0.0 for v in res.per_field.values())


def test_soep_edit_distance_detects_change():
    gen = {"S": "hoofdpijn sinds 2 dagen", "O": "", "E": "", "P": ""}
    app = {"S": "hoofdpijn sinds drie dagen", "O": "", "E": "", "P": ""}
    res = soep_edit_distance(gen, app)
    assert res.overall > 0.0


def test_normalize_keeps_accents():
    assert normalize_text("Nitrofurantoïne!") == "nitrofurantoïne"
