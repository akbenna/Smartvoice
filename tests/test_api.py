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
    """Zonder token moet /me 403 geven."""
    response = await client.get("/api/auth/me")
    assert response.status_code == 403


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
    assert response.status_code == 403


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
