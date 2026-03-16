"""
Transcript model — Whisper STT output.
"""

from sqlalchemy import String, Float, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin


class Transcript(Base, UUIDMixin):
    __tablename__ = "transcripts"

    consult_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consults.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="nl")
    confidence_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_secs: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relaties
    consult = relationship("Consult", back_populates="transcript")
    extraction = relationship("Extraction", back_populates="transcript", uselist=False)
