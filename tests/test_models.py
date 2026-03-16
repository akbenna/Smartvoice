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
