"""
ORM model tests.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.user import User, UserRole
from shared.models.consult import Consult, ConsultStatus
from shared.models.transcript import Transcript
from shared.models.soep_concept import SoepConcept
from shared.models.extraction import Extraction
from shared.models.detection_result import DetectionResult
from shared.models.correction import Correction, SoepField
from shared.models.patient_instruction import PatientInstruction
from shared.models.audit_log import AuditLog


@pytest.mark.asyncio
async def test_create_user(db: AsyncSession):
    """Maak een gebruiker aan en lees terug."""
    user = User(
        username="test_arts",
        display_name="Dr. Test",
        role=UserRole.arts,
        password_hash="$2b$12$dummy_hash",
    )
    db.add(user)
    await db.commit()

    result = await db.execute(select(User).where(User.username == "test_arts"))
    found = result.scalar_one()
    assert found.display_name == "Dr. Test"
    assert found.role == UserRole.arts
    assert found.is_active is True


@pytest.mark.asyncio
async def test_create_consult(db: AsyncSession, test_user: User):
    """Maak een consult aan met relatie naar user."""
    consult = Consult(
        patient_hash="sha256_hash_of_bsn",
        practitioner_id=test_user.id,
        status=ConsultStatus.recording,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.commit()

    result = await db.execute(select(Consult))
    found = result.scalar_one()
    assert found.status == ConsultStatus.recording
    assert found.patient_hash == "sha256_hash_of_bsn"


@pytest.mark.asyncio
async def test_consult_status_transitions(db: AsyncSession, test_user: User):
    """Test status veranderingen van een consult."""
    consult = Consult(
        patient_hash="test_hash",
        practitioner_id=test_user.id,
        status=ConsultStatus.recording,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()

    # recording -> transcribing -> extracting -> reviewing
    for status in [ConsultStatus.transcribing, ConsultStatus.extracting, ConsultStatus.reviewing]:
        consult.status = status
        await db.flush()

    assert consult.status == ConsultStatus.reviewing


@pytest.mark.asyncio
async def test_transcript_consult_relation(db: AsyncSession, test_user: User):
    """Transcript hoort bij een consult."""
    consult = Consult(
        patient_hash="test",
        practitioner_id=test_user.id,
        status=ConsultStatus.transcribing,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()

    transcript = Transcript(
        consult_id=consult.id,
        raw_text="Arts: Hallo. Patient: Ik heb hoofdpijn.",
        segments=[
            {"spreker": "arts", "start": 0, "eind": 2, "tekst": "Hallo.", "confidence": 0.95},
        ],
        model_version="whisper-large-v3-turbo",
    )
    db.add(transcript)
    await db.commit()

    result = await db.execute(select(Transcript).where(Transcript.consult_id == consult.id))
    found = result.scalar_one()
    assert "hoofdpijn" in found.raw_text
    assert len(found.segments) == 1


@pytest.mark.asyncio
async def test_audit_log_creation(db: AsyncSession):
    """Audit log entry aanmaken."""
    log = AuditLog(
        user_id=None,
        action="user.login",
        resource_type="user",
        details={"username": "dr.test"},
    )
    db.add(log)
    await db.commit()

    result = await db.execute(select(AuditLog))
    found = result.scalar_one()
    assert found.action == "user.login"


# === Aanvullende tests ===

@pytest.mark.asyncio
async def test_create_poh_user(db: AsyncSession):
    """Create user with UserRole.poh."""
    user = User(
        username="poh_test",
        display_name="POH Test",
        role=UserRole.poh,
        password_hash="hash",
    )
    db.add(user)
    await db.commit()

    result = await db.execute(select(User).where(User.username == "poh_test"))
    found = result.scalar_one()
    assert found.role == UserRole.poh
    assert found.is_active is True


@pytest.mark.asyncio
async def test_create_beheerder_user(db: AsyncSession):
    """Create user with UserRole.beheerder."""
    user = User(
        username="admin_test",
        display_name="Admin Test",
        role=UserRole.beheerder,
        password_hash="hash",
    )
    db.add(user)
    await db.commit()

    result = await db.execute(select(User).where(User.username == "admin_test"))
    found = result.scalar_one()
    assert found.role == UserRole.beheerder


@pytest.mark.asyncio
async def test_user_unique_username(db: AsyncSession):
    """Verify that creating two users with same username raises IntegrityError."""
    user1 = User(
        username="unique_user",
        display_name="User 1",
        role=UserRole.arts,
        password_hash="hash1",
    )
    db.add(user1)
    await db.commit()

    # Try to create another with same username
    user2 = User(
        username="unique_user",
        display_name="User 2",
        role=UserRole.arts,
        password_hash="hash2",
    )
    db.add(user2)

    with pytest.raises(Exception):  # IntegrityError or similar
        await db.commit()


@pytest.mark.asyncio
async def test_consult_with_metadata(db: AsyncSession, test_user: User):
    """Create consult with metadata JSONB."""
    consult = Consult(
        patient_hash="test_hash",
        practitioner_id=test_user.id,
        status=ConsultStatus.recording,
        started_at=datetime.now(timezone.utc),
        metadata={
            "clinic_location": "Amsterdam",
            "patient_age_group": "40-50",
            "visit_type": "follow-up",
        },
    )
    db.add(consult)
    await db.commit()

    result = await db.execute(select(Consult))
    found = result.scalar_one()
    assert found.metadata["clinic_location"] == "Amsterdam"
    assert found.metadata["visit_type"] == "follow-up"


@pytest.mark.asyncio
async def test_soep_concept_full_lifecycle(db: AsyncSession, test_user: User):
    """Create extraction -> soep -> approval flow."""
    # Create consult
    consult = Consult(
        patient_hash="test",
        practitioner_id=test_user.id,
        status=ConsultStatus.extracting,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()

    # Create transcript
    transcript = Transcript(
        consult_id=consult.id,
        raw_text="Test transcript",
        segments=[],
        model_version="test",
    )
    db.add(transcript)
    await db.flush()

    # Create extraction
    extraction = Extraction(
        consult_id=consult.id,
        transcript_id=transcript.id,
        klachten=["Hoofdpijn"],
        model_version="llama3.1:8b",
    )
    db.add(extraction)
    await db.flush()

    # Create SOEP concept
    soep = SoepConcept(
        consult_id=consult.id,
        extraction_id=extraction.id,
        s_text="Patiënt klaagt over hoofdpijn",
        o_text="Geen bijzonderheden bevonden",
        e_text="Spanningstypische hoofdpijn",
        p_text="Paracetamol voorgeschreven",
        icpc_code="N01",
        icpc_titel="Hoofdpijn",
        model_version="llama3.1:8b",
        is_approved=False,
    )
    db.add(soep)
    await db.flush()

    # Approve SOEP
    soep.is_approved = True
    soep.approved_by = test_user.id
    soep.approved_at = datetime.now(timezone.utc)
    await db.flush()

    await db.commit()

    # Verify
    result = await db.execute(select(SoepConcept))
    found = result.scalar_one()
    assert found.is_approved is True
    assert found.approved_by == test_user.id
    assert "hoofdpijn" in found.s_text.lower()


@pytest.mark.asyncio
async def test_detection_result_with_flags(db: AsyncSession, test_user: User):
    """Create detection with red_flags and missing_info JSONB."""
    consult = Consult(
        patient_hash="test",
        practitioner_id=test_user.id,
        status=ConsultStatus.reviewing,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()

    detection = DetectionResult(
        consult_id=consult.id,
        red_flags=[
            {"flag": "Ernstig symptoom", "severity": "high"},
            {"flag": "Mogelijke bijwerking", "severity": "medium"},
        ],
        missing_info=[
            "Allergiën niet vastgesteld",
            "Geen medicatiehistorie opgenomen",
        ],
    )
    db.add(detection)
    await db.commit()

    result = await db.execute(select(DetectionResult))
    found = result.scalar_one()
    assert len(found.red_flags) == 2
    assert len(found.missing_info) == 2


@pytest.mark.asyncio
async def test_correction_on_soep(db: AsyncSession, test_user: User):
    """Create a correction record."""
    # Setup: Create consult, transcript, extraction, soep
    consult = Consult(
        patient_hash="test",
        practitioner_id=test_user.id,
        status=ConsultStatus.reviewing,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()

    transcript = Transcript(
        consult_id=consult.id,
        raw_text="Test",
        segments=[],
        model_version="test",
    )
    db.add(transcript)
    await db.flush()

    extraction = Extraction(
        consult_id=consult.id,
        transcript_id=transcript.id,
        model_version="test",
    )
    db.add(extraction)
    await db.flush()

    soep = SoepConcept(
        consult_id=consult.id,
        extraction_id=extraction.id,
        s_text="Originele tekst",
        model_version="test",
    )
    db.add(soep)
    await db.flush()

    # Create correction
    correction = Correction(
        soep_id=soep.id,
        field=SoepField.S,
        original_text="Originele tekst",
        corrected_text="Gecorrigeerde tekst",
        corrected_by=test_user.id,
    )
    db.add(correction)
    await db.commit()

    result = await db.execute(select(Correction))
    found = result.scalar_one()
    assert found.field == SoepField.S
    assert found.corrected_text == "Gecorrigeerde tekst"


@pytest.mark.asyncio
async def test_patient_instruction(db: AsyncSession, test_user: User):
    """Create patient instruction record."""
    consult = Consult(
        patient_hash="test",
        practitioner_id=test_user.id,
        status=ConsultStatus.reviewing,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()

    instruction = PatientInstruction(
        consult_id=consult.id,
        instruction_text="Neem paracetamol twee keer per dag. Drink veel water.",
        language="nl",
        readability="B1",
    )
    db.add(instruction)
    await db.commit()

    result = await db.execute(select(PatientInstruction))
    found = result.scalar_one()
    assert "paracetamol" in found.instruction_text
    assert found.readability == "B1"


@pytest.mark.asyncio
async def test_consult_cascade_delete(db: AsyncSession, test_user: User):
    """Deleting consult should cascade to transcript."""
    consult = Consult(
        patient_hash="test",
        practitioner_id=test_user.id,
        status=ConsultStatus.recording,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()
    consult_id = consult.id

    transcript = Transcript(
        consult_id=consult.id,
        raw_text="Test",
        segments=[],
        model_version="test",
    )
    db.add(transcript)
    await db.commit()

    # Enable FK enforcement for this connection, then delete
    from sqlalchemy import text
    await db.execute(text("PRAGMA foreign_keys=ON"))
    await db.execute(text("DELETE FROM consults WHERE id = :id"), {"id": str(consult_id)})
    await db.commit()

    # Verify transcript is deleted too (cascade)
    result = await db.execute(select(Transcript).where(Transcript.consult_id == consult_id))
    count = len(result.scalars().all())
    assert count == 0


@pytest.mark.asyncio
async def test_extraction_with_full_data(db: AsyncSession, test_user: User):
    """All JSONB fields populated."""
    consult = Consult(
        patient_hash="test",
        practitioner_id=test_user.id,
        status=ConsultStatus.extracting,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()

    transcript = Transcript(
        consult_id=consult.id,
        raw_text="Test",
        segments=[],
        model_version="test",
    )
    db.add(transcript)
    await db.flush()

    extraction = Extraction(
        consult_id=consult.id,
        transcript_id=transcript.id,
        klachten=["Hoofdpijn", "Koorts"],
        anamnese={"vorige_ziektes": ["Griep"], "allergieën": []},
        lich_onderzoek={"bloed_druk": "120/80"},
        vitale_params={"temp": 37.2, "pols": 72},
        medicatie=[{"naam": "Paracetamol", "dosis": "500mg"}],
        allergieen=[{"naam": "Penicilline"}],
        voorgeschiedenis=[{"diagnose": "Migraine"}],
        model_version="llama3.1:8b",
        confidence=0.92,
        raw_response={"status": "success"},
    )
    db.add(extraction)
    await db.commit()

    result = await db.execute(select(Extraction))
    found = result.scalar_one()
    assert len(found.klachten) == 2
    assert found.anamnese["vorige_ziektes"] == ["Griep"]
    assert found.vitale_params["temp"] == 37.2
    assert found.confidence == 0.92
