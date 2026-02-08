"""Verification schemas and supporting enums."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Verdict(str, Enum):
    VERIFIED = "verified"
    APPROXIMATELY_CORRECT = "approximately_correct"
    MISLEADING = "misleading"
    INCORRECT = "incorrect"
    UNVERIFIABLE = "unverifiable"


class MisleadingFlag(str, Enum):
    GAAP_NONGAAP_MISMATCH = "gaap_nongaap_mismatch"
    CHERRY_PICKED_PERIOD = "cherry_picked_period"
    SEGMENT_VS_TOTAL = "segment_vs_total"
    ROUNDING_BIAS = "rounding_bias"
    MISLEADING_COMPARISON = "misleading_comparison"
    OMITS_CONTEXT = "omits_context"


class VerificationBase(BaseModel):
    claim_id: int

    actual_value: Optional[float] = None
    accuracy_score: Optional[float] = None

    verdict: Verdict
    explanation: str

    financial_data_source: Optional[str] = None
    financial_data_id: Optional[int] = None
    comparison_data_id: Optional[int] = None

    misleading_flags: list[str] = []
    misleading_details: Optional[str] = None


class VerificationCreate(VerificationBase):
    pass


class Verification(VerificationBase):
    id: int

    model_config = {"from_attributes": True}
