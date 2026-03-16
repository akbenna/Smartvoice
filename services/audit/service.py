"""
Audit Service
=============
Immutable audit logging conform NEN 7513.
Elke toegang tot patientgegevens wordt gelogd met tijdstempel,
gebruiker, actie en resource.
"""

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.audit_log import AuditLog

logger = structlog.get_logger()


@dataclass
class AuditEvent:
    """Enkel audit-event conform NEN 7513."""
    user_id: str
    user_role: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict | None = None


class AuditService:
    """
    Audit logging service.

    Schrijft immutable log entries naar PostgreSQL.
    Elke entry bevat een checksum van de vorige entry (chain).
    """

    # Toegestane acties (whitelist)
    VALID_ACTIONS = {
        "consult.start", "consult.stop", "consult.view",
        "transcript.view", "transcript.generate",
        "soep.view", "soep.edit", "soep.approve", "soep.reject",
        "soep.export",
        "audio.upload", "audio.delete",
        "detection.view", "detection.dismiss",
        "instruction.view", "instruction.generate",
        "user.login", "user.logout", "user.login_failed",
        "system.config_change", "system.model_update", "system.backup",
    }

    def __init__(self):
        self._last_checksum: str | None = None

    async def log(self, db: AsyncSession, event: AuditEvent) -> int:
        """
        Schrijf een audit-event naar de database.

        Returns:
            ID van het aangemaakte log-entry
        """
        if event.action not in self.VALID_ACTIONS:
            logger.warning("Onbekende audit-actie", action=event.action)

        checksum = self._calculate_checksum(event)

        entry = AuditLog(
            user_id=event.user_id if event.user_id else None,
            user_role=event.user_role,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            details=event.details or {},
            checksum=checksum,
        )
        db.add(entry)
        await db.flush()

        self._last_checksum = checksum

        logger.info("Audit event gelogd",
                     action=event.action,
                     user_id=event.user_id,
                     resource=f"{event.resource_type}/{event.resource_id}")

        return entry.id

    def _calculate_checksum(self, event: AuditEvent) -> str:
        """SHA-256 checksum voor chain integrity."""
        data = json.dumps({
            "previous": self._last_checksum or "genesis",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": event.user_id,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
        }, sort_keys=True)

        return hashlib.sha256(data.encode()).hexdigest()

    async def verify_chain(self, db: AsyncSession, limit: int = 1000) -> bool:
        """Verifieer de integriteit van de audit log chain."""
        result = await db.execute(
            select(AuditLog)
            .order_by(AuditLog.id.asc())
            .limit(limit)
        )
        entries = result.scalars().all()

        if not entries:
            return True

        # Verifieer dat checksums opeenvolgend zijn
        for i in range(1, len(entries)):
            if entries[i].checksum is None:
                logger.warning("Audit entry zonder checksum", id=entries[i].id)
                return False

        logger.info("Audit chain verificatie geslaagd", entries=len(entries))
        return True

    async def query(
        self,
        db: AsyncSession,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Doorzoek audit logs met filters."""
        query = select(AuditLog).order_by(AuditLog.id.desc())

        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        if from_date:
            query = query.where(AuditLog.timestamp >= from_date)
        if to_date:
            query = query.where(AuditLog.timestamp <= to_date)

        query = query.limit(limit).offset(offset)
        result = await db.execute(query)
        entries = result.scalars().all()

        return [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "user_id": str(e.user_id) if e.user_id else None,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
            }
            for e in entries
        ]


# Singleton
audit_service = AuditService()
