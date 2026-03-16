"""
DetectionResult model — Rode vlaggen + ontbrekende informatie.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin


class DetectionResult(Base, UUIDMixin):
    __tablename__ = "detection_results"

    consult_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consults.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    red_flags: Mapped[dict] = mapped_column(JSONB, default=list)
    missing_info: Mapped[dict] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relaties
    consult = relationship("Consult", back_populates="detection_result")
