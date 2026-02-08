"""Discrepancy pattern ORM model — persisted cross-quarter analysis results."""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database import Base


class DiscrepancyPatternModel(Base):
    __tablename__ = "discrepancy_patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)

    pattern_type = Column(String, nullable=False)  # PatternType enum value
    description = Column(Text, nullable=False)
    affected_quarters = Column(JSON, nullable=False, default=list)
    severity = Column(Float, nullable=False)
    evidence = Column(JSON, nullable=False, default=list)

    # Relationships
    company = relationship("CompanyModel", backref="discrepancy_patterns")

    def __repr__(self) -> str:
        return f"<DiscrepancyPattern company_id={self.company_id} type={self.pattern_type} severity={self.severity}>"
