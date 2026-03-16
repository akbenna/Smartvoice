"""
Transcription Service
=====================
Whisper Large v3 Turbo (Faster-Whisper) + PyAnnote diarisatie.
Verwerkt audio lokaal op GPU, output: getimed en gediariseerd transcript.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()


@dataclass
class TranscriptSegment:
    """Enkel segment uit het transcript."""
    spreker: str           # "arts" of "patient"
    start: float           # Starttijd in seconden
    eind: float            # Eindtijd in seconden
    tekst: str
    confidence: float = 0.0


@dataclass
class TranscriptResult:
    """Volledig transcriptieresultaat."""
    segments: list[TranscriptSegment] = field(default_factory=list)
    raw_text: str = ""
    model_version: str = ""
    language: str = "nl"
    confidence_avg: float = 0.0
    duration_secs: float = 0.0
    word_count: int = 0

    def to_labeled_text(self) -> str:
        """Genereer gelabeld transcript voor LLM input."""
        lines = []
        for seg in self.segments:
            label = seg.spreker if seg.spreker in ("arts", "patient") else "onbekend"
            lines.append(f"{label}: {seg.tekst}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "segments": [
                {
                    "spreker": s.spreker,
                    "start": s.start,
                    "eind": s.eind,
                    "tekst": s.tekst,
                    "confidence": s.confidence,
                }
                for s in self.segments
            ],
            "model_version": self.model_version,
            "language": self.language,
            "confidence_avg": self.confidence_avg,
            "duration_secs": self.duration_secs,
            "word_count": self.word_count,
        }


class TranscriptionService:
    """
    Lokale speech-to-text met Whisper + sprekerdiarisatie.

    Gebruik:
        service = TranscriptionService(config)
        await service.initialize()  # Laad modellen (eenmalig)
        result = await service.transcribe("/pad/naar/audio.wav")
    """

    def __init__(self, config):
        self.config = config
        self.whisper_model = None
        self.diarizer = None
        self._initialized = False

    async def initialize(self):
        """Laad Whisper en diarisatie modellen. Duurt ~30s bij eerste keer."""
        if self._initialized:
            return

        logger.info("Whisper model laden...",
                     model=self.config.whisper.model,
                     device=self.config.whisper.device)

        # --- Whisper laden ---
        try:
            from faster_whisper import WhisperModel

            self.whisper_model = WhisperModel(
                self.config.whisper.model,
                device=self.config.whisper.device,
                compute_type=self.config.whisper.compute_type,
                download_root=self.config.whisper.model_path,
            )
            logger.info("Whisper model geladen")
        except Exception as e:
            logger.error("Whisper model laden mislukt", error=str(e))
            raise

        # --- Diarisatie laden (optioneel) ---
        if self.config.diarization.enabled:
            try:
                from pyannote.audio import Pipeline

                self.diarizer = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.config.diarization.hf_token,
                )
                # Verplaats naar GPU indien beschikbaar
                import torch
                if torch.cuda.is_available():
                    self.diarizer.to(torch.device("cuda"))
                logger.info("Diarisatie pipeline geladen")
            except Exception as e:
                logger.warning("Diarisatie laden mislukt, gaat verder zonder",
                              error=str(e))
                self.diarizer = None

        self._initialized = True

    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """
        Transcribeer een audiobestand.

        Args:
            audio_path: Pad naar WAV/MP3/M4A bestand

        Returns:
            TranscriptResult met segmenten, timestamps en confidence
        """
        if not self._initialized:
            await self.initialize()

        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audiobestand niet gevonden: {audio_path}")

        logger.info("Transcriptie gestart", audio_path=str(audio_path))

        # --- Stap 1: Whisper transcriptie ---
        segments_raw, info = self.whisper_model.transcribe(
            str(audio_path),
            language=self.config.whisper.language,
            beam_size=self.config.whisper.beam_size,
            word_timestamps=True,
            vad_filter=True,
        )

        # Verzamel segmenten
        whisper_segments = []
        all_text_parts = []
        total_confidence = 0.0

        for segment in segments_raw:
            whisper_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "avg_logprob": segment.avg_logprob,
            })
            all_text_parts.append(segment.text.strip())
            total_confidence += segment.avg_logprob

        raw_text = " ".join(all_text_parts)
        avg_confidence = (
            total_confidence / len(whisper_segments)
            if whisper_segments else 0.0
        )
        # Converteer log-prob naar 0-1 schaal (benadering)
        confidence_normalized = min(1.0, max(0.0, 1.0 + avg_confidence))

        logger.info("Whisper transcriptie voltooid",
                     segments=len(whisper_segments),
                     duration=info.duration,
                     confidence=round(confidence_normalized, 3))

        # --- Stap 2: Diarisatie (optioneel) ---
        if self.diarizer is not None:
            try:
                diarization = self.diarizer(str(audio_path))
                transcript_segments = self._merge_with_diarization(
                    whisper_segments, diarization
                )
            except Exception as e:
                logger.warning("Diarisatie mislukt, gebruik transcript zonder sprekerinfo",
                              error=str(e))
                transcript_segments = [
                    TranscriptSegment(
                        spreker="onbekend",
                        start=s["start"],
                        eind=s["end"],
                        tekst=s["text"],
                        confidence=min(1.0, max(0.0, 1.0 + s["avg_logprob"])),
                    )
                    for s in whisper_segments
                ]
        else:
            transcript_segments = [
                TranscriptSegment(
                    spreker="onbekend",
                    start=s["start"],
                    eind=s["end"],
                    tekst=s["text"],
                    confidence=min(1.0, max(0.0, 1.0 + s["avg_logprob"])),
                )
                for s in whisper_segments
            ]

        return TranscriptResult(
            segments=transcript_segments,
            raw_text=raw_text,
            model_version=self.config.whisper.model,
            language=info.language,
            confidence_avg=confidence_normalized,
            duration_secs=info.duration,
            word_count=len(raw_text.split()),
        )

    def _merge_with_diarization(
        self, whisper_segments: list[dict], diarization
    ) -> list[TranscriptSegment]:
        """
        Combineer Whisper-segmenten met diarisatie-output.
        Wijst elke Whisper-segment toe aan de spreker die het meeste overlapt.

        Aanname: eerste spreker = arts (start het consult), tweede = patient.
        Dit kan verfijnd worden met een spraakregistratie-stap.
        """
        # Map diarisatie-sprekers naar arts/patient
        speaker_map = {}
        speaker_order = []

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if speaker not in speaker_order:
                speaker_order.append(speaker)

        # Eerste spreker = arts (heuristiek: arts opent het consult)
        for i, spk in enumerate(speaker_order):
            if i == 0:
                speaker_map[spk] = "arts"
            elif i == 1:
                speaker_map[spk] = "patient"
            else:
                speaker_map[spk] = f"spreker_{i+1}"

        # Wijs elk Whisper-segment toe aan een spreker
        result = []
        for seg in whisper_segments:
            best_speaker = "onbekend"
            best_overlap = 0.0

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                overlap_start = max(seg["start"], turn.start)
                overlap_end = min(seg["end"], turn.end)
                overlap = max(0.0, overlap_end - overlap_start)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker_map.get(speaker, "onbekend")

            result.append(TranscriptSegment(
                spreker=best_speaker,
                start=seg["start"],
                eind=seg["end"],
                tekst=seg["text"],
                confidence=min(1.0, max(0.0, 1.0 + seg["avg_logprob"])),
            ))

        return result
