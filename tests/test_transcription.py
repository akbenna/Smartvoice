"""
Transcription service tests (zonder GPU/modellen).
"""

import pytest

from services.transcription.service import TranscriptSegment, TranscriptResult


def test_transcript_segment():
    """TranscriptSegment dataclass."""
    seg = TranscriptSegment(
        spreker="arts",
        start=0.0,
        eind=5.0,
        tekst="Goedemorgen.",
        confidence=0.95,
    )
    assert seg.spreker == "arts"
    assert seg.eind == 5.0


def test_transcript_result_to_labeled_text():
    """Gelabeld transcript voor LLM input."""
    result = TranscriptResult(
        segments=[
            TranscriptSegment("arts", 0.0, 3.0, "Hallo, wat kan ik voor u doen?", 0.95),
            TranscriptSegment("patient", 3.5, 8.0, "Ik heb hoofdpijn.", 0.92),
            TranscriptSegment("arts", 8.5, 12.0, "Hoe lang al?", 0.94),
        ],
        raw_text="Hallo, wat kan ik voor u doen? Ik heb hoofdpijn. Hoe lang al?",
        model_version="test",
    )

    labeled = result.to_labeled_text()
    assert "arts: Hallo" in labeled
    assert "patient: Ik heb hoofdpijn." in labeled
    lines = labeled.strip().split("\n")
    assert len(lines) == 3


def test_transcript_result_to_dict():
    """TranscriptResult serialisatie."""
    result = TranscriptResult(
        segments=[
            TranscriptSegment("arts", 0.0, 3.0, "Test.", 0.9),
        ],
        raw_text="Test.",
        model_version="whisper-large-v3-turbo",
        language="nl",
        confidence_avg=0.9,
        duration_secs=3.0,
        word_count=1,
    )

    d = result.to_dict()
    assert d["model_version"] == "whisper-large-v3-turbo"
    assert d["language"] == "nl"
    assert d["segments"][0]["spreker"] == "arts"


def test_empty_transcript():
    """Leeg transcript."""
    result = TranscriptResult()
    assert result.to_labeled_text() == ""
    d = result.to_dict()
    assert d["segments"] == []
    assert d["word_count"] == 0
