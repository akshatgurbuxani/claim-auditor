"""Transcript ORM model."""

from sqlalchemy import Column, Date, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class TranscriptModel(Base):
    __tablename__ = "transcripts"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "quarter", name="uq_transcript_company_quarter"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    quarter = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    call_date = Column(Date, nullable=False)
    full_text = Column(Text, nullable=False)

    # Relationships
    company = relationship("CompanyModel", back_populates="transcripts")
    claims = relationship("ClaimModel", back_populates="transcript", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Transcript company_id={self.company_id} Q{self.quarter} {self.year}>"
