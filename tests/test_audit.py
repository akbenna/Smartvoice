"""
Audit service tests.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit.service import AuditService, AuditEvent


@pytest.mark.asyncio
async def test_audit_log_valid_action(db: AsyncSession):
    """Log een geldige actie."""
    service = AuditService()
    event = AuditEvent(
        user_id="11111111-1111-1111-1111-111111111111",
        user_role="arts",
        action="soep.view",
        resource_type="soep",
        resource_id="test-id",
    )
    entry_id = await service.log(db, event)
    await db.commit()
    assert entry_id is not None


@pytest.mark.asyncio
async def test_audit_checksum_chain(db: AsyncSession):
    """Checksums moeten verschillen per event."""
    service = AuditService()

    event1 = AuditEvent(
        user_id="user1", user_role="arts",
        action="consult.start", resource_type="consult",
    )
    event2 = AuditEvent(
        user_id="user1", user_role="arts",
        action="consult.stop", resource_type="consult",
    )

    await service.log(db, event1)
    checksum1 = service._last_checksum

    await service.log(db, event2)
    checksum2 = service._last_checksum

    await db.commit()

    # Elke entry moet een andere checksum hebben
    assert checksum1 != checksum2


@pytest.mark.asyncio
async def test_audit_verify_chain(db: AsyncSession):
    """Chain verificatie op lege database moet True geven."""
    service = AuditService()
    result = await service.verify_chain(db)
    assert result is True


@pytest.mark.asyncio
async def test_audit_query(db: AsyncSession):
    """Query op lege database moet lege lijst geven."""
    service = AuditService()
    result = await service.query(db, action="soep.view")
    assert result == []
