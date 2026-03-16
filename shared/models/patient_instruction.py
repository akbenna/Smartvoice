"""
PatientInstruction model — Patientinstructie in eenvoudig Nederlands.
"""

from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin


class PatientInstruction(Base, UUIDMixin):
    __tablename__ = "patient_instructions"

    consult_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consults.id", ondelete="CASCADE"),
        nullable=False,
    )
    instruction_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="nl")
    readability: Mapped[str] = mapped_column(String(10), default="B1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relaties
    consult = relationship("Consult", back_populates="patient_instruction")
