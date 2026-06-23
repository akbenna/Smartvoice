"""
Tests voor de diarisatie-upgrade: woord-niveau alignment + rolherkenning.
"""

from types import SimpleNamespace

from services.transcription.diarization_align import (
    SpeakerTurn,
    Word,
    aggregate_speaker_text,
    assign_word_speaker,
    group_words_by_speaker,
)
from services.transcription.role_assignment import assign_roles
from services.transcription.service import TranscriptionService


# ── Woord-toewijzing ──────────────────────────────────────────────────

def test_assign_word_speaker_by_overlap():
    turns = [SpeakerTurn(0, 3, "A"), SpeakerTurn(3, 6, "B")]
    assert assign_word_speaker(Word(0.1, 0.9, "hallo"), turns) == "A"
    assert assign_word_speaker(Word(4.0, 4.5, "ja"), turns) == "B"


def test_assign_word_speaker_nearest_when_no_overlap():
    turns = [SpeakerTurn(0, 3, "A"), SpeakerTurn(10, 12, "B")]
    # Woord op 6.0 valt buiten beide -> dichtstbijzijnde turn (A op 0-3, mid 1.5;
    # B mid 11) -> 6.0 ligt dichter bij A
    assert assign_word_speaker(Word(5.9, 6.1, "tussenin"), turns) == "A"


def test_group_words_splits_on_speaker_change():
    turns = [SpeakerTurn(0, 3, "A"), SpeakerTurn(3, 6, "B")]
    words = [
        Word(0.0, 1.0, "hoe"), Word(1.0, 2.0, "gaat"), Word(2.0, 3.0, "het"),
        Word(3.0, 4.0, "ik"), Word(4.0, 5.0, "heb"), Word(5.0, 6.0, "pijn"),
    ]
    segs = group_words_by_speaker(words, turns)
    assert len(segs) == 2
    assert segs[0].speaker == "A" and segs[0].text == "hoe gaat het"
    assert segs[1].speaker == "B" and segs[1].text == "ik heb pijn"


def test_aggregate_speaker_text():
    turns = [SpeakerTurn(0, 2, "A"), SpeakerTurn(2, 4, "B"), SpeakerTurn(4, 6, "A")]
    words = [
        Word(0.0, 1.0, "vraag"), Word(2.5, 3.0, "antwoord"), Word(4.5, 5.0, "nog"),
    ]
    agg = aggregate_speaker_text(group_words_by_speaker(words, turns))
    assert agg["A"] == "vraag nog"
    assert agg["B"] == "antwoord"


# ── Rolherkenning ─────────────────────────────────────────────────────

def test_roles_identify_arts_by_cues_even_if_second():
    # Spreker B opent NIET, maar stelt vragen + medische taal -> arts
    texts = {
        "A": "ik heb al een week last van hoofdpijn en ik voel me moe",
        "B": "sinds wanneer heeft u dit? ik adviseer paracetamol en een controle",
    }
    roles = assign_roles(texts, speaker_order=["A", "B"])
    assert roles["B"] == "arts"
    assert roles["A"] == "patient"


def test_roles_single_speaker_is_arts():
    assert assign_roles({"X": "dictaat van de arts"}) == {"X": "arts"}


def test_roles_three_speakers():
    texts = {
        "A": "sinds wanneer heeft u klachten? ik onderzoek uw bloeddruk",  # arts
        "B": "ik heb pijn in mijn buik en ik voel me niet lekker",          # patient
        "C": "ja dat klopt hoor",                                          # derde
    }
    roles = assign_roles(texts, speaker_order=["A", "B", "C"])
    assert roles["A"] == "arts"
    assert roles["B"] == "patient"
    assert roles["C"].startswith("spreker_")


# ── End-to-end merge met fake diarisatie ──────────────────────────────

class _FakeTurn:
    def __init__(self, start, end):
        self.start = start
        self.end = end


class _FakeDiarization:
    """Bootst pyannote's itertracks(yield_label=True) na."""
    def __init__(self, segments):
        self._segments = segments  # list of (start, end, speaker)

    def itertracks(self, yield_label=False):
        for start, end, spk in self._segments:
            yield _FakeTurn(start, end), None, spk


def _dummy_service():
    # We hebben geen model nodig; alleen self.config.whisper.postcorrect_transcript
    cfg = SimpleNamespace(whisper=SimpleNamespace(postcorrect_transcript=False))
    svc = TranscriptionService.__new__(TranscriptionService)
    svc.config = cfg
    return svc


def test_merge_splits_segment_spanning_two_speakers():
    svc = _dummy_service()
    # Eén Whisper-segment 0-6s met woorden van twee sprekers
    whisper_segments = [{
        "start": 0.0, "end": 6.0, "text": "hoe lang heeft u dit ik heb al een week pijn",
        "avg_logprob": -0.2,
        "words": [
            {"start": 0.0, "end": 0.5, "text": "hoe"},
            {"start": 0.5, "end": 1.0, "text": "lang"},
            {"start": 1.0, "end": 1.5, "text": "heeft"},
            {"start": 1.5, "end": 2.0, "text": "u"},
            {"start": 2.0, "end": 2.5, "text": "dit"},
            {"start": 3.2, "end": 3.6, "text": "ik"},
            {"start": 3.6, "end": 4.0, "text": "heb"},
            {"start": 4.0, "end": 4.4, "text": "al"},
            {"start": 4.4, "end": 4.8, "text": "een"},
            {"start": 4.8, "end": 5.2, "text": "week"},
            {"start": 5.2, "end": 5.8, "text": "pijn"},
        ],
    }]
    diarization = _FakeDiarization([(0.0, 3.0, "S1"), (3.0, 6.0, "S2")])

    segs = svc._merge_with_diarization(whisper_segments, diarization)
    assert len(segs) == 2
    # S1 stelt de vraag -> arts; S2 beschrijft klacht in ik-vorm -> patient
    assert segs[0].spreker == "arts"
    assert segs[1].spreker == "patient"
    assert "pijn" in segs[1].tekst
