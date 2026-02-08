"""Pydantic schemas for request/response validation and domain types."""

from app.schemas.claim import (
    Claim,
    ClaimBase,
    ClaimCreate,
    ClaimWithVerification,
    ComparisonPeriod,
    MetricType,
)
from app.schemas.company import Company, CompanyCreate, CompanyWithStats
from app.schemas.discrepancy import CompanyAnalysis, DiscrepancyPattern, PatternType
from app.schemas.financial_data import FinancialData, FinancialDataCreate
from app.schemas.transcript import Transcript, TranscriptCreate, TranscriptSummary
from app.schemas.verification import (
    MisleadingFlag,
    Verdict,
    Verification,
    VerificationCreate,
)

__all__ = [
    "Company", "CompanyCreate", "CompanyWithStats",
    "Transcript", "TranscriptCreate", "TranscriptSummary",
    "FinancialData", "FinancialDataCreate",
    "Claim", "ClaimBase", "ClaimCreate", "ClaimWithVerification",
    "MetricType", "ComparisonPeriod",
    "Verification", "VerificationCreate", "Verdict", "MisleadingFlag",
    "CompanyAnalysis", "DiscrepancyPattern", "PatternType",
]
