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


# === Aanvullende tests ===

def test_transcript_segment_defaults():
    """Confidence defaults to 0.0."""
    seg = TranscriptSegment(
        spreker="patient",
        start=1.0,
        eind=3.5,
        tekst="Ja, dat klopt."
    )
    assert seg.confidence == 0.0
    assert seg.spreker == "patient"
    assert seg.tekst == "Ja, dat klopt."


def test_transcript_result_confidence_calculation():
    """Test confidence calculation with multiple segments."""
    segments = [
        TranscriptSegment("arts", 0.0, 2.0, "Goedemorgen.", 0.95),
        TranscriptSegment("patient", 2.5, 5.0, "Hallo doctor.", 0.88),
        TranscriptSegment("arts", 5.5, 8.0, "Wat brengt u hier?", 0.92),
    ]
    result = TranscriptResult(
        segments=segments,
        raw_text="Goedemorgen. Hallo doctor. Wat brengt u hier?",
        model_version="whisper-large-v3-turbo",
        confidence_avg=0.91667,
    )
    assert result.confidence_avg == pytest.approx(0.91667, rel=0.01)
    assert len(result.segments) == 3


def test_to_labeled_text_unknown_speaker():
    """Spreker 'onbekend' should appear."""
    result = TranscriptResult(
        segments=[
            TranscriptSegment("onbekend", 0.0, 3.0, "Ergens hoort iemand iets.", 0.8),
            TranscriptSegment("arts", 3.5, 6.0, "Wie was dat?", 0.9),
        ],
        raw_text="Ergens hoort iemand iets. Wie was dat?",
        model_version="test",
    )
    labeled = result.to_labeled_text()
    assert "onbekend: Ergens hoort iemand iets." in labeled
    assert "arts: Wie was dat?" in labeled


def test_to_labeled_text_mixed_speakers():
    """Arts, patient, and other speakers."""
    result = TranscriptResult(
        segments=[
            TranscriptSegment("arts", 0.0, 2.0, "Goedemorgen.", 0.95),
            TranscriptSegment("patient", 2.5, 4.5, "Hallo.", 0.92),
            TranscriptSegment("spreker_3", 5.0, 7.0, "Sorry, verkeerd nummer.", 0.85),
        ],
        raw_text="Goedemorgen. Hallo. Sorry, verkeerd nummer.",
        model_version="test",
    )
    labeled = result.to_labeled_text()
    assert "arts: Goedemorgen." in labeled
    assert "patient: Hallo." in labeled
    assert "onbekend: Sorry, verkeerd nummer." in labeled  # spreker_3 maps to onbekend


def test_to_dict_full_metadata():
    """All fields populate correctly in to_dict()."""
    result = TranscriptResult(
        segments=[
            TranscriptSegment("arts", 0.0, 2.0, "Test.", 0.95),
            TranscriptSegment("patient", 2.5, 5.0, "Okay.", 0.90),
        ],
        raw_text="Test. Okay.",
        model_version="whisper-large-v3-turbo",
        language="nl",
        confidence_avg=0.925,
        duration_secs=5.0,
        word_count=2,
    )
    d = result.to_dict()

    assert d["raw_text"] == "Test. Okay."
    assert d["model_version"] == "whisper-large-v3-turbo"
    assert d["language"] == "nl"
    assert d["confidence_avg"] == 0.925
    assert d["duration_secs"] == 5.0
    assert d["word_count"] == 2
    assert len(d["segments"]) == 2
    assert d["segments"][0]["spreker"] == "arts"
    assert d["segments"][1]["spreker"] == "patient"


def test_transcript_segment_long_text():
    """Handle very long segments."""
    long_text = "Dit is een zeer lang segment. " * 100
    seg = TranscriptSegment(
        spreker="arts",
        start=0.0,
        eind=60.0,
        tekst=long_text,
        confidence=0.85,
    )
    assert len(seg.tekst) > 1000
    assert seg.confidence == 0.85

    result = TranscriptResult(
        segments=[seg],
        raw_text=long_text,
        model_version="test",
        word_count=len(long_text.split()),
    )
    labeled = result.to_labeled_text()
    assert long_text in labeled


def test_transcript_result_single_segment():
    """Edge case with single segment."""
    result = TranscriptResult(
        segments=[
            TranscriptSegment("arts", 0.0, 10.0, "Alles goed met u?", 0.96),
        ],
        raw_text="Alles goed met u?",
        model_version="whisper-large-v3-turbo",
        word_count=4,
    )

    labeled = result.to_labeled_text()
    assert labeled == "arts: Alles goed met u?"

    d = result.to_dict()
    assert len(d["segments"]) == 1
    assert d["word_count"] == 4
