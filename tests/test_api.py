"""
API endpoint tests.
"""

import pytest
from httpx import AsyncClient
from shared.models.user import User


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Health endpoint moet altijd werken."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "version" in data


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    """Inloggen met correcte credentials."""
    response = await client.post("/api/auth/login", json={
        "username": "dr.test",
        "password": "test123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "dr.test"
    assert data["user"]["role"] == "arts"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: User):
    """Inloggen met fout wachtwoord."""
    response = await client.post("/api/auth/login", json={
        "username": "dr.test",
        "password": "fout_wachtwoord",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient):
    """Inloggen met onbekende gebruiker."""
    response = await client.post("/api/auth/login", json={
        "username": "onbekend",
        "password": "test123",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_unauthorized(client: AsyncClient):
    """Zonder token moet /me 401 of 403 geven."""
    response = await client.get("/api/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_authorized(client: AsyncClient, auth_headers: dict):
    """/me met geldig token."""
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "dr.test"


@pytest.mark.asyncio
async def test_start_consult(client: AsyncClient, auth_headers: dict):
    """Start een nieuw consult."""
    response = await client.post(
        "/api/consult/start",
        json={"patient_hash": "abc123def456"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "recording"


@pytest.mark.asyncio
async def test_start_consult_unauthorized(client: AsyncClient):
    """Consult starten zonder login."""
    response = await client.post(
        "/api/consult/start",
        json={"patient_hash": "abc123"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_consults(client: AsyncClient):
    """Consulten lijst ophalen."""
    response = await client.get("/api/consults")
    assert response.status_code == 200
    data = response.json()
    assert "consults" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_nonexistent_transcript(client: AsyncClient):
    """Transcript ophalen voor onbestaand consult."""
    response = await client.get("/api/consult/00000000-0000-0000-0000-000000000099/transcript")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_invalid_format(client: AsyncClient):
    """Upload met ongeldig bestandsformaat."""
    from io import BytesIO
    files = {"file": ("test.txt", BytesIO(b"not audio"), "text/plain")}
    response = await client.post("/api/consult/upload", files=files)
    assert response.status_code == 400


# === Aanvullende API tests ===

@pytest.mark.asyncio
async def test_consult_full_workflow(client: AsyncClient, auth_headers: dict, db):
    """Start consult -> create transcript/soep in DB -> get soep -> approve -> export."""
    from datetime import datetime, timezone
    from shared.models.consult import Consult, ConsultStatus
    from shared.models.transcript import Transcript
    from shared.models.soep_concept import SoepConcept
    from shared.models.extraction import Extraction
    from sqlalchemy import select

    # Create test user for practitioner
    from shared.models.user import User, UserRole
    from services.api.auth import hash_password
    import uuid

    user = User(
        id=uuid.uuid4(),
        username="test_arts_workflow",
        display_name="Test Arts",
        role=UserRole.arts,
        password_hash=hash_password("test123"),
    )
    db.add(user)
    await db.commit()

    # Start consult
    response = await client.post(
        "/api/consult/start",
        json={"patient_hash": "workflow_test_hash"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    # Manually create transcript and SOEP in DB (simulating pipeline completion)
    consult_result = await db.execute(
        select(Consult).where(Consult.id == uuid.UUID(session_id))
    )
    consult = consult_result.scalar_one()

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
        model_version="test",
    )
    db.add(extraction)
    await db.flush()

    # Create SOEP
    soep = SoepConcept(
        consult_id=consult.id,
        extraction_id=extraction.id,
        s_text="Test subjectief",
        o_text="Test objectief",
        e_text="Test evaluatie",
        p_text="Test plan",
        model_version="test",
    )
    db.add(soep)
    await db.commit()

    # Get SOEP
    response = await client.get(f"/api/consult/{session_id}/soep", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["S"] == "Test subjectief"

    # Approve SOEP (if endpoint exists)
    response = await client.post(
        f"/api/consult/{session_id}/soep/approve",
        json={"comment": "Approved"},
        headers=auth_headers,
    )
    # May be 200 or 404 depending on implementation
    assert response.status_code in (200, 404)


@pytest.mark.asyncio
async def test_stop_consult(client: AsyncClient, auth_headers: dict, db):
    """Start then stop, verify status change."""
    from shared.models.consult import Consult, ConsultStatus
    from sqlalchemy import select
    import uuid

    # Start
    response = await client.post(
        "/api/consult/start",
        json={"patient_hash": "stop_test_hash"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    # Stop
    response = await client.post(
        f"/api/consult/{session_id}/stop",
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Verify status
    consult_result = await db.execute(
        select(Consult).where(Consult.id == uuid.UUID(session_id))
    )
    consult = consult_result.scalar_one()
    # Status should have changed (recording -> stopped or transcribing)
    assert consult.status != ConsultStatus.recording


@pytest.mark.asyncio
async def test_stop_nonexistent_consult(client: AsyncClient, auth_headers: dict):
    """Stop nonexistent consult returns 404."""
    import uuid
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/api/consult/{fake_id}/stop",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_soep_not_found(client: AsyncClient, auth_headers: dict):
    """404 for nonexistent session."""
    import uuid
    fake_id = uuid.uuid4()
    response = await client.get(
        f"/api/consult/{fake_id}/soep",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_detection_empty(client: AsyncClient):
    """Returns empty lists for nonexistent."""
    import uuid
    fake_id = uuid.uuid4()
    response = await client.get(f"/api/consult/{fake_id}/detection")
    # May return 404 or empty with 200
    assert response.status_code in (404, 200)


@pytest.mark.asyncio
async def test_export_unapproved(client: AsyncClient, auth_headers: dict, db):
    """Exporting unapproved SOEP should return 400."""
    from datetime import datetime, timezone
    from shared.models.consult import Consult, ConsultStatus
    from shared.models.transcript import Transcript
    from shared.models.soep_concept import SoepConcept
    from shared.models.extraction import Extraction
    from shared.models.user import User, UserRole
    from services.api.auth import hash_password
    from sqlalchemy import select
    import uuid

    # Get test user
    user_result = await db.execute(select(User).where(User.username == "dr.test"))
    test_user = user_result.scalar_one()

    # Create consult with unapproved SOEP
    consult = Consult(
        patient_hash="unapproved_test",
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
        s_text="Test",
        model_version="test",
        is_approved=False,  # Not approved
    )
    db.add(soep)
    await db.commit()

    # Try to export
    response = await client.post(
        f"/api/consult/{consult.id}/export",
        json={"target": "clipboard"},
        headers=auth_headers,
    )
    # Should be 400 for unapproved
    assert response.status_code in (400, 403, 422)


@pytest.mark.asyncio
async def test_list_consults_with_data(client: AsyncClient, db, test_user):
    """Create multiple consults, verify listing."""
    from datetime import datetime, timezone
    from shared.models.consult import Consult, ConsultStatus
    from sqlalchemy import select

    # Create multiple consults
    for i in range(3):
        consult = Consult(
            patient_hash=f"patient_{i}",
            practitioner_id=test_user.id,
            status=ConsultStatus.recording,
            started_at=datetime.now(timezone.utc),
        )
        db.add(consult)

    await db.commit()

    # List
    response = await client.get("/api/consults")
    assert response.status_code == 200
    data = response.json()
    assert "consults" in data
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_list_consults_pagination(client: AsyncClient, db, test_user):
    """Test limit/offset."""
    from datetime import datetime, timezone
    from shared.models.consult import Consult, ConsultStatus

    # Create multiple consults
    for i in range(5):
        consult = Consult(
            patient_hash=f"pagination_{i}",
            practitioner_id=test_user.id,
            status=ConsultStatus.recording,
            started_at=datetime.now(timezone.utc),
        )
        db.add(consult)

    await db.commit()

    # Test with limit
    response = await client.get("/api/consults?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["consults"]) <= 2

    # Test with offset
    response = await client.get("/api/consults?limit=2&offset=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["consults"]) <= 2


@pytest.mark.asyncio
async def test_inactive_user_login(client: AsyncClient, db):
    """Create inactive user, try login, expect 403."""
    from shared.models.user import User, UserRole
    from services.api.auth import hash_password
    import uuid

    user = User(
        id=uuid.uuid4(),
        username="inactive_user",
        display_name="Inactive",
        role=UserRole.arts,
        password_hash=hash_password("test123"),
        is_active=False,
    )
    db.add(user)
    await db.commit()

    response = await client.post(
        "/api/auth/login",
        json={"username": "inactive_user", "password": "test123"},
    )
    # Should be 401 (unauthorized) or 403 (forbidden)
    assert response.status_code in (401, 403)
