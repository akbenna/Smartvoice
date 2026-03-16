"""
Correction model — Arts-correcties op SOEP (feedbackloop).
"""

import enum
from datetime import datetime

from sqlalchemy import Text, ForeignKey, Enum, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin


class SoepField(str, enum.Enum):
    S = "S"
    O = "O"
    E = "E"
    P = "P"


class Correction(Base, UUIDMixin):
    __tablename__ = "corrections"

    soep_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("soep_concepts.id", ondelete="CASCADE"),
        nullable=False,
    )
    field: Mapped[SoepField] = mapped_column(Enum(SoepField, name="soep_field"), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_by: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relaties
    soep = relationship("SoepConcept", back_populates="corrections")
    corrected_by_user = relationship("User", back_populates="corrections")
