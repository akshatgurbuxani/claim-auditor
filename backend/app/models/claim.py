"""Claim ORM model."""

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ClaimModel(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transcript_id = Column(Integer, ForeignKey("transcripts.id"), nullable=False, index=True)

    speaker = Column(String, nullable=False)
    speaker_role = Column(String)
    claim_text = Column(Text, nullable=False)

    metric = Column(String, nullable=False)
    metric_type = Column(String, nullable=False)  # MetricType enum value
    stated_value = Column(Float, nullable=False)
    unit = Column(String, nullable=False)

    comparison_period = Column(String, default="none")  # ComparisonPeriod enum value
    comparison_basis = Column(String)

    is_gaap = Column(Boolean, default=True)
    segment = Column(String)

    confidence = Column(Float, default=0.8)
    context_snippet = Column(Text)

    # Relationships
    transcript = relationship("TranscriptModel", back_populates="claims")
    verification = relationship(
        "VerificationModel", back_populates="claim", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Claim id={self.id} metric={self.metric} stated={self.stated_value}>"
