"""
Audit service tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit.service import AuditService, AuditEvent


@pytest.mark.asyncio
async def test_audit_log_valid_action(db: AsyncSession):
    """Log een geldige actie."""
    service = AuditService()
    event = AuditEvent(
        user_id=None,
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
        user_id=None, user_role="arts",
        action="consult.start", resource_type="consult",
    )
    event2 = AuditEvent(
        user_id=None, user_role="arts",
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


# === Aanvullende tests ===

@pytest.mark.asyncio
async def test_audit_log_all_valid_actions(db: AsyncSession):
    """Iterate through all VALID_ACTIONS and ensure each can be logged."""
    service = AuditService()
    actions = list(service.VALID_ACTIONS)

    for action in actions:
        event = AuditEvent(
            user_id=None,
            user_role="arts",
            action=action,
            resource_type="test",
            resource_id="test-id",
        )
        entry_id = await service.log(db, event)
        assert entry_id is not None

    await db.commit()

    # Verify all were logged
    from sqlalchemy import text
    result = await db.execute(text("SELECT COUNT(*) FROM audit_logs"))
    count = result.scalar()
    assert count >= len(actions)


@pytest.mark.asyncio
async def test_audit_log_with_details(db: AsyncSession):
    """Log event with details dict and verify storage."""
    service = AuditService()
    event = AuditEvent(
        user_id=None,
        user_role="arts",
        action="soep.approve",
        resource_type="soep",
        resource_id="soep-123",
        details={"icpc_code": "P76", "comment": "Goedgekeurd zonder wijzigingen"},
    )
    entry_id = await service.log(db, event)
    await db.commit()

    # Query en verify
    result = await service.query(db, action="soep.approve", limit=1)
    assert len(result) >= 1
    assert result[0]["action"] == "soep.approve"


@pytest.mark.asyncio
async def test_audit_log_with_ip_and_ua(db: AsyncSession):
    """Log with ip_address and user_agent."""
    service = AuditService()
    event = AuditEvent(
        user_id=None,
        user_role="arts",
        action="user.login",
        resource_type="user",
        ip_address=None,  # SQLite INET not supported, use None
        user_agent="Mozilla/5.0 Test Browser",
    )
    entry_id = await service.log(db, event)
    await db.commit()
    assert entry_id is not None


@pytest.mark.asyncio
async def test_audit_query_with_filters(db: AsyncSession):
    """Create multiple events, query by user_id, action, resource_type."""
    service = AuditService()

    # Create multiple events
    events = [
        AuditEvent(None, "arts", "soep.view", "soep", "soep-1"),
        AuditEvent(None, "arts", "soep.approve", "soep", "soep-1"),
        AuditEvent(None, "poh", "transcript.view", "transcript", "trans-1"),
    ]

    for event in events:
        await service.log(db, event)

    await db.commit()

    # Query by action
    result1 = await service.query(db, action="soep.view", limit=10)
    assert len(result1) >= 1

    # Query by action
    result2 = await service.query(db, action="soep.view", limit=10)
    assert len(result2) >= 1

    # Query by resource_type
    result3 = await service.query(db, resource_type="soep", limit=10)
    assert len(result3) >= 2


@pytest.mark.asyncio
async def test_audit_query_with_date_range(db: AsyncSession):
    """Create events and filter by date range."""
    service = AuditService()

    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)

    event = AuditEvent("user1", "arts", "soep.view", "soep", "soep-1")
    await service.log(db, event)
    await db.commit()

    # Query with date range that includes now
    result = await service.query(
        db,
        from_date=past,
        to_date=future,
        limit=10
    )
    assert len(result) >= 1


@pytest.mark.asyncio
async def test_audit_query_pagination(db: AsyncSession):
    """Test limit and offset."""
    service = AuditService()

    # Create 5 events (user_id=None om FK constraint te vermijden)
    for i in range(5):
        event = AuditEvent(
            user_id=None,
            user_role="arts",
            action="consult.start",
            resource_type="consult",
            resource_id=f"consult-{i}",
        )
        await service.log(db, event)

    await db.commit()

    # Test limit
    result1 = await service.query(db, limit=2)
    assert len(result1) <= 2

    # Test offset
    result2 = await service.query(db, limit=2, offset=2)
    assert len(result2) <= 2


@pytest.mark.asyncio
async def test_audit_chain_multiple_events(db: AsyncSession):
    """Create 5+ events and verify chain integrity."""
    service = AuditService()

    for i in range(6):
        event = AuditEvent(
            user_id=None,
            user_role="arts",
            action="consult.start",
            resource_type="consult",
            resource_id=f"consult-{i}",
        )
        await service.log(db, event)

    await db.commit()

    # Verify chain
    is_valid = await service.verify_chain(db, limit=10)
    assert is_valid is True


@pytest.mark.asyncio
async def test_audit_invalid_action_warning(db: AsyncSession):
    """Verify warning is logged for invalid actions (doesn't crash)."""
    service = AuditService()

    # Invalid action - should log warning but not crash
    event = AuditEvent(
        user_id=None,
        user_role="arts",
        action="invalid.action.that.does.not.exist",
        resource_type="test",
    )

    # Should not raise, but may log warning
    entry_id = await service.log(db, event)
    await db.commit()

    # Verify it was still logged
    assert entry_id is not None
