"""
Tests voor de gedeelde medische woordenlijst (shared/vocabulary.py).
"""

from shared.vocabulary import (
    correct_transcript_full,
    get_hotwords,
    get_initial_prompt,
    PRIORITY_TERMS,
)


def test_postcorrect_fixes_common_stt_errors():
    text = "patient gebruikt metaformien en amlodiepine"
    corrected, stats = correct_transcript_full(text)
    assert "metformine" in corrected
    assert "amlodipine" in corrected
    assert stats.total_corrections >= 2


def test_postcorrect_empty_is_safe():
    corrected, stats = correct_transcript_full("")
    assert corrected == ""
    assert stats.total_corrections == 0


def test_word_boundaries_respected():
    # "lo" mag niet binnenin "bloeddruk" worden vervangen
    corrected, _ = correct_transcript_full("de bloeddruk is hoog")
    assert "bloeddruk" in corrected


def test_initial_prompt_compact_and_contextual():
    prompt = get_initial_prompt()
    assert "huisartsconsult" in prompt.lower()
    # Compact houden i.v.m. Whisper's 224-token venster
    assert len(prompt) < 1200
    # Bevat kerntermen
    assert "metformine" in prompt


def test_initial_prompt_accepts_extra_terms():
    prompt = get_initial_prompt(extra_terms=["smartvoiceterm"])
    assert "smartvoiceterm" in prompt


def test_hotwords_nonempty_and_deduplicated():
    hw = get_hotwords().split(",")
    assert len(hw) > 50
    assert len(hw) == len(set(hw))  # geen duplicaten


def test_priority_terms_are_known_good_spellings():
    # Steekproef: priority-termen moeten correct gespeld zijn
    assert "hypertensie" in PRIORITY_TERMS
    assert "nitrofurantoïne" in PRIORITY_TERMS
