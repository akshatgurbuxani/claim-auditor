"""Discrepancy / analysis schemas."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class PatternType(str, Enum):
    CONSISTENT_ROUNDING_UP = "consistent_rounding_up"
    METRIC_SWITCHING = "metric_switching"
    INCREASING_INACCURACY = "increasing_inaccuracy"
    GAAP_NONGAAP_SHIFTING = "gaap_nongaap_shifting"
    SELECTIVE_EMPHASIS = "selective_emphasis"


class DiscrepancyPattern(BaseModel):
    """Quarter-to-quarter pattern detected across a company's earnings calls."""

    id: int = 0
    company_id: int
    pattern_type: PatternType
    description: str
    affected_quarters: list[str]
    severity: float  # 0–1
    evidence: list[str]

    model_config = {"from_attributes": True}


class CompanyAnalysis(BaseModel):
    """Complete analysis report for a single company."""

    company_id: int
    ticker: str
    name: str

    total_claims: int
    verified_claims: int
    approximately_correct_claims: int
    misleading_claims: int
    incorrect_claims: int
    unverifiable_claims: int

    overall_accuracy_rate: float  # (verified+approx) / verifiable
    overall_trust_score: float  # weighted 0–100

    top_discrepancies: list[dict]
    patterns: list[DiscrepancyPattern]
    quarters_analyzed: list[str]
