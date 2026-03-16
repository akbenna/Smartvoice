"""
Pipeline Orchestrator
=====================
Verbindt alle services: Audio -> Transcript -> Extractie -> SOEP -> Detectie.
Slaat tussenresultaten op in de database.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.settings import config
from shared.models.consult import Consult, ConsultStatus
from shared.models.transcript import Transcript
from shared.models.extraction import Extraction
from shared.models.soep_concept import SoepConcept
from shared.models.detection_result import DetectionResult
from shared.models.patient_instruction import PatientInstruction

from services.transcription.service import TranscriptionService
from services.extraction.service import ExtractionService

logger = structlog.get_logger()


class PipelineOrchestrator:
    """
    Orkestreert de volledige verwerkingspipeline voor een consult.

    Flow:
        1. Audio transcriberen (Whisper + diarisatie)
        2. Medische extractie (LLM)
        3. SOEP-concept genereren (LLM)
        4. Rode vlaggen detectie (LLM)
        5. Patientinstructie genereren (LLM)
    """

    def __init__(self):
        self.transcription_service = TranscriptionService(config)
        self.extraction_service = ExtractionService(config)

    async def initialize(self):
        """Laad ML-modellen (eenmalig bij startup)."""
        await self.transcription_service.initialize()
        logger.info("Pipeline orchestrator geinitialiseerd")

    async def process_consult(
        self, db: AsyncSession, consult_id: uuid.UUID, audio_path: str
    ) -> dict:
        """
        Verwerk een volledig consult van audio tot SOEP.

        Args:
            db: Database sessie
            consult_id: UUID van het consult
            audio_path: Pad naar het audiobestand

        Returns:
            dict met alle resultaten
        """
        logger.info("Pipeline gestart", consult_id=str(consult_id))

        try:
            # === Stap 1: Transcriptie ===
            await self._update_status(db, consult_id, ConsultStatus.transcribing)

            transcript_result = await self.transcription_service.transcribe(audio_path)

            # Sla transcript op in database
            transcript = Transcript(
                consult_id=consult_id,
                raw_text=transcript_result.raw_text,
                segments=[s.__dict__ for s in transcript_result.segments],
                model_version=transcript_result.model_version,
                language=transcript_result.language,
                confidence_avg=transcript_result.confidence_avg,
                word_count=transcript_result.word_count,
                duration_secs=transcript_result.duration_secs,
            )
            db.add(transcript)
            await db.flush()

            logger.info("Transcriptie voltooid",
                        consult_id=str(consult_id),
                        word_count=transcript_result.word_count)

            # === Stap 2: Medische extractie ===
            await self._update_status(db, consult_id, ConsultStatus.extracting)

            labeled_text = transcript_result.to_labeled_text()
            extraction_data = await self.extraction_service.extract(labeled_text)

            extraction = Extraction(
                consult_id=consult_id,
                transcript_id=transcript.id,
                klachten=extraction_data.get("klachten", []),
                anamnese=extraction_data.get("anamnese", {}),
                lich_onderzoek=extraction_data.get("lichamelijk_onderzoek", {}),
                vitale_params=extraction_data.get("lichamelijk_onderzoek", {}).get("vitale_parameters", {}),
                medicatie=extraction_data.get("medicatie", {}),
                allergieen=extraction_data.get("allergieen", []),
                voorgeschiedenis=extraction_data.get("voorgeschiedenis", []),
                model_version=config.ollama.model,
                raw_response=extraction_data,
            )
            db.add(extraction)
            await db.flush()

            logger.info("Extractie voltooid", consult_id=str(consult_id))

            # === Stap 3: SOEP generatie ===
            soep_data = await self.extraction_service.generate_soep(extraction_data)

            soep = SoepConcept(
                consult_id=consult_id,
                extraction_id=extraction.id,
                s_text=soep_data.get("S", ""),
                o_text=soep_data.get("O", ""),
                e_text=soep_data.get("E", ""),
                p_text=soep_data.get("P", ""),
                icpc_code=soep_data.get("icpc_code"),
                icpc_titel=soep_data.get("icpc_titel"),
                model_version=config.ollama.model,
            )
            db.add(soep)
            await db.flush()

            logger.info("SOEP gegenereerd", consult_id=str(consult_id))

            # === Stap 4: Detectie ===
            detection_data = await self.extraction_service.detect_flags(
                extraction_data, soep_data
            )

            detection = DetectionResult(
                consult_id=consult_id,
                red_flags=detection_data.get("rode_vlaggen", []),
                missing_info=detection_data.get("ontbrekende_info", []),
            )
            db.add(detection)
            await db.flush()

            logger.info("Detectie voltooid",
                        consult_id=str(consult_id),
                        red_flags=len(detection_data.get("rode_vlaggen", [])))

            # === Stap 5: Patientinstructie ===
            instruction_text = await self.extraction_service.generate_patient_instruction(
                soep_data
            )

            instruction = PatientInstruction(
                consult_id=consult_id,
                instruction_text=instruction_text,
            )
            db.add(instruction)

            # === Status: klaar voor review ===
            await self._update_status(db, consult_id, ConsultStatus.reviewing)
            await db.commit()

            logger.info("Pipeline voltooid", consult_id=str(consult_id))

            return {
                "consult_id": str(consult_id),
                "status": "reviewing",
                "transcript": transcript_result.to_dict(),
                "soep": soep_data,
                "detection": detection_data,
                "patient_instruction": instruction_text,
            }

        except Exception as e:
            logger.error("Pipeline mislukt",
                        consult_id=str(consult_id), error=str(e))
            await self._update_status(db, consult_id, ConsultStatus.failed)
            await db.commit()
            raise

    async def _update_status(
        self, db: AsyncSession, consult_id: uuid.UUID, status: ConsultStatus
    ):
        """Update de status van een consult."""
        from sqlalchemy import update
        await db.execute(
            update(Consult)
            .where(Consult.id == consult_id)
            .values(status=status)
        )


# Singleton
pipeline = PipelineOrchestrator()
