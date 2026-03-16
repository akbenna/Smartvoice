"""
Extraction model — LLM medische extractie uit transcript.
"""

from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin


class Extraction(Base, UUIDMixin):
    __tablename__ = "extractions"

    consult_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consults.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    transcript_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
    )
    klachten: Mapped[dict] = mapped_column(JSONB, default=list)
    anamnese: Mapped[dict] = mapped_column(JSONB, default=dict)
    lich_onderzoek: Mapped[dict] = mapped_column(JSONB, default=dict)
    vitale_params: Mapped[dict] = mapped_column(JSONB, default=dict)
    medicatie: Mapped[dict] = mapped_column(JSONB, default=list)
    allergieen: Mapped[dict] = mapped_column(JSONB, default=list)
    voorgeschiedenis: Mapped[dict] = mapped_column(JSONB, default=list)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relaties
    consult = relationship("Consult", back_populates="extraction")
    transcript = relationship("Transcript", back_populates="extraction")
    soep_concept = relationship("SoepConcept", back_populates="extraction", uselist=False)
