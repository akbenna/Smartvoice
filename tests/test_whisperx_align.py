"""
Tests voor de pure WhisperX-mapper (services/transcription/whisperx_align.py).
"""

from services.transcription.whisperx_align import apply_aligned_words


def test_apply_aligned_words_replaces_words():
    whisper_segments = [
        {"start": 0.0, "end": 3.0, "text": "hoe gaat het", "words": [
            {"start": 0.0, "end": 1.0, "text": "hoe"},
        ]},
    ]
    aligned = [
        {"words": [
            {"word": "hoe", "start": 0.1, "end": 0.5, "score": 0.9},
            {"word": "gaat", "start": 0.5, "end": 1.0, "score": 0.9},
            {"word": "het", "start": 1.0, "end": 1.4, "score": 0.9},
        ]},
    ]
    out = apply_aligned_words(whisper_segments, aligned)
    assert len(out[0]["words"]) == 3
    assert out[0]["words"][0] == {"start": 0.1, "end": 0.5, "text": "hoe"}


def test_apply_aligned_words_skips_invalid_times():
    whisper_segments = [{"start": 0, "end": 2, "text": "x", "words": [{"start": 0, "end": 2, "text": "x"}]}]
    aligned = [{"words": [
        {"word": "geldig", "start": 0.0, "end": 0.5},
        {"word": "ongeldig", "start": None, "end": None},
    ]}]
    out = apply_aligned_words(whisper_segments, aligned)
    assert [w["text"] for w in out[0]["words"]] == ["geldig"]


def test_apply_aligned_words_empty_keeps_original():
    seg = [{"start": 0, "end": 1, "text": "x", "words": [{"start": 0, "end": 1, "text": "x"}]}]
    assert apply_aligned_words(seg, []) == seg


def test_apply_aligned_words_segment_without_alignment_kept():
    seg = [
        {"start": 0, "end": 1, "text": "a", "words": [{"start": 0, "end": 1, "text": "a"}]},
        {"start": 1, "end": 2, "text": "b", "words": [{"start": 1, "end": 2, "text": "b"}]},
    ]
    aligned = [{"words": [{"word": "a", "start": 0.0, "end": 0.4}]}]  # alleen segment 0
    out = apply_aligned_words(seg, aligned)
    assert out[0]["words"][0]["text"] == "a"
    assert out[1]["words"][0]["text"] == "b"  # ongewijzigd
