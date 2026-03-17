"""
Pipeline orchestrator tests with mocked services.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.consult import Consult, ConsultStatus
from shared.models.user import User, UserRole
from services.pipeline.orchestrator import PipelineOrchestrator
from services.transcription.service import TranscriptResult, TranscriptSegment


@pytest.mark.asyncio
async def test_pipeline_process_consult_success(db: AsyncSession, test_user: User):
    """Mock both services, run pipeline, verify all DB records created."""
    # Create a consult in DB first
    consult = Consult(
        patient_hash="test_patient_hash",
        practitioner_id=test_user.id,
        status=ConsultStatus.recording,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.commit()
    consult_id = consult.id

    # Create pipeline
    pipeline = PipelineOrchestrator()

    # Mock transcription service
    mock_transcript_result = TranscriptResult(
        segments=[
            TranscriptSegment("arts", 0.0, 3.0, "Goedemorgen.", 0.95),
            TranscriptSegment("patient", 3.5, 8.0, "Ik heb hoofdpijn.", 0.92),
        ],
        raw_text="Goedemorgen. Ik heb hoofdpijn.",
        model_version="whisper-large-v3-turbo",
        language="nl",
        confidence_avg=0.935,
        duration_secs=8.0,
        word_count=5,
    )

    mock_extraction = {
        "klachten": ["Hoofdpijn"],
        "anamnese": {"duur": "2 dagen"},
        "lichamelijk_onderzoek": {"bloed_druk": "120/80"},
        "medicatie": [],
        "allergieen": [],
        "voorgeschiedenis": [],
    }

    mock_soep = {
        "S": "Patiënt klaagt over hoofdpijn",
        "O": "Bloed druk 120/80",
        "E": "Spanningstypische hoofdpijn",
        "P": "Paracetamol voorgeschreven",
        "icpc_code": "N01",
        "icpc_titel": "Hoofdpijn",
    }

    mock_detection = {
        "rode_vlaggen": [],
        "ontbrekende_info": ["Allergiën niet vastgesteld"],
    }

    mock_instruction = "Neem paracetamol en rust uit."

    # Patch services
    with patch.object(pipeline.transcription_service, 'transcribe', new_callable=AsyncMock) as mock_trans, \
         patch.object(pipeline.extraction_service, 'extract', new_callable=AsyncMock) as mock_extract, \
         patch.object(pipeline.extraction_service, 'generate_soep', new_callable=AsyncMock) as mock_soep_gen, \
         patch.object(pipeline.extraction_service, 'detect_flags', new_callable=AsyncMock) as mock_detect, \
         patch.object(pipeline.extraction_service, 'generate_patient_instruction', new_callable=AsyncMock) as mock_instr, \
         patch('services.pipeline.orchestrator.redis_client') as mock_redis:

        mock_trans.return_value = mock_transcript_result
        mock_extract.return_value = mock_extraction
        mock_soep_gen.return_value = mock_soep
        mock_detect.return_value = mock_detection
        mock_instr.return_value = mock_instruction
        mock_redis.add_to_stream = AsyncMock()

        # Run pipeline
        result = await pipeline.process_consult(db, consult_id, "/fake/audio.wav")

    # Verify result
    assert result["status"] == "reviewing"
    assert result["soep"]["E"] == "Spanningstypische hoofdpijn"
    assert len(result["detection"]["rode_vlaggen"]) == 0

    # Verify DB records were created
    from sqlalchemy import select
    from shared.models.transcript import Transcript
    from shared.models.extraction import Extraction
    from shared.models.soep_concept import SoepConcept
    from shared.models.detection_result import DetectionResult
    from shared.models.patient_instruction import PatientInstruction

    # Check transcript
    trans_result = await db.execute(
        select(Transcript).where(Transcript.consult_id == consult_id)
    )
    transcript = trans_result.scalar_one_or_none()
    assert transcript is not None
    assert "Goedemorgen" in transcript.raw_text

    # Check extraction
    extr_result = await db.execute(
        select(Extraction).where(Extraction.consult_id == consult_id)
    )
    extraction = extr_result.scalar_one_or_none()
    assert extraction is not None
    assert extraction.klachten == ["Hoofdpijn"]

    # Check SOEP
    soep_result = await db.execute(
        select(SoepConcept).where(SoepConcept.consult_id == consult_id)
    )
    soep_concept = soep_result.scalar_one_or_none()
    assert soep_concept is not None
    assert "Patiënt" in soep_concept.s_text

    # Check detection
    det_result = await db.execute(
        select(DetectionResult).where(DetectionResult.consult_id == consult_id)
    )
    detection = det_result.scalar_one_or_none()
    assert detection is not None

    # Check patient instruction
    instr_result = await db.execute(
        select(PatientInstruction).where(PatientInstruction.consult_id == consult_id)
    )
    instruction = instr_result.scalar_one_or_none()
    assert instruction is not None


@pytest.mark.asyncio
async def test_pipeline_status_transitions(db: AsyncSession, test_user: User):
    """Verify status goes recording -> transcribing -> extracting -> reviewing."""
    consult = Consult(
        patient_hash="test_hash",
        practitioner_id=test_user.id,
        status=ConsultStatus.recording,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.commit()
    consult_id = consult.id

    pipeline = PipelineOrchestrator()

    # Mock minimal responses
    mock_transcript_result = TranscriptResult(
        segments=[],
        raw_text="Test",
        model_version="test",
    )

    with patch.object(pipeline.transcription_service, 'transcribe', new_callable=AsyncMock) as mock_trans, \
         patch.object(pipeline.extraction_service, 'extract', new_callable=AsyncMock) as mock_extract, \
         patch.object(pipeline.extraction_service, 'generate_soep', new_callable=AsyncMock) as mock_soep_gen, \
         patch.object(pipeline.extraction_service, 'detect_flags', new_callable=AsyncMock) as mock_detect, \
         patch.object(pipeline.extraction_service, 'generate_patient_instruction', new_callable=AsyncMock) as mock_instr, \
         patch('services.pipeline.orchestrator.redis_client') as mock_redis:

        mock_trans.return_value = mock_transcript_result
        mock_extract.return_value = {"klachten": []}
        mock_soep_gen.return_value = {"S": "", "O": "", "E": "", "P": ""}
        mock_detect.return_value = {"rode_vlaggen": [], "ontbrekende_info": []}
        mock_instr.return_value = "Test instruction"
        mock_redis.add_to_stream = AsyncMock()

        result = await pipeline.process_consult(db, consult_id, "/fake/audio.wav")

    # Verify final status
    from sqlalchemy import select
    consult_result = await db.execute(
        select(Consult).where(Consult.id == consult_id)
    )
    final_consult = consult_result.scalar_one()
    assert final_consult.status == ConsultStatus.reviewing


@pytest.mark.asyncio
async def test_pipeline_failure_marks_failed(db: AsyncSession, test_user: User):
    """Mock transcription to raise, verify consult status is 'failed'."""
    consult = Consult(
        patient_hash="test_hash",
        practitioner_id=test_user.id,
        status=ConsultStatus.recording,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.commit()
    consult_id = consult.id

    pipeline = PipelineOrchestrator()

    # Mock transcription to fail
    with patch.object(
        pipeline.transcription_service,
        'transcribe',
        new_callable=AsyncMock,
        side_effect=Exception("Transcription failed")
    ) as mock_trans, \
         patch('services.pipeline.orchestrator.redis_client'):

        with pytest.raises(Exception):
            await pipeline.process_consult(db, consult_id, "/fake/audio.wav")

    # Verify status is failed
    from sqlalchemy import select
    consult_result = await db.execute(
        select(Consult).where(Consult.id == consult_id)
    )
    failed_consult = consult_result.scalar_one()
    assert failed_consult.status == ConsultStatus.failed
