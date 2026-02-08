"""Verification ORM model."""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database import Base


class VerificationModel(Base):
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False, unique=True)

    actual_value = Column(Float)
    accuracy_score = Column(Float)

    verdict = Column(String, nullable=False)  # Verdict enum value
    explanation = Column(Text, nullable=False)

    financial_data_source = Column(String)
    financial_data_id = Column(Integer, ForeignKey("financial_data.id"))
    comparison_data_id = Column(Integer, ForeignKey("financial_data.id"))

    misleading_flags = Column(JSON, default=list)
    misleading_details = Column(Text)

    # Relationships
    claim = relationship("ClaimModel", back_populates="verification")

    def __repr__(self) -> str:
        return f"<Verification claim_id={self.claim_id} verdict={self.verdict}>"
