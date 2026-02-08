"""Claim schemas and supporting enums."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.schemas.verification import Verification


class MetricType(str, Enum):
    ABSOLUTE = "absolute"  # "$5B in revenue"
    GROWTH_RATE = "growth_rate"  # "grew 15%"
    MARGIN = "margin"  # "operating margin of 30%"
    RATIO = "ratio"  # "debt-to-equity of 0.5"
    CHANGE = "change"  # "expanded 200 basis points"
    PER_SHARE = "per_share"  # "EPS of $2.50"


class ComparisonPeriod(str, Enum):
    YOY = "year_over_year"
    QOQ = "quarter_over_quarter"
    SEQUENTIAL = "sequential"
    FULL_YEAR = "full_year"
    CUSTOM = "custom"
    NONE = "none"


class ClaimBase(BaseModel):
    transcript_id: int
    speaker: str
    speaker_role: Optional[str] = None
    claim_text: str

    # Structured extraction fields
    metric: str
    metric_type: MetricType
    stated_value: float
    unit: str  # "percent", "usd", "usd_billions", "usd_millions", "basis_points", …

    comparison_period: ComparisonPeriod = ComparisonPeriod.NONE
    comparison_basis: Optional[str] = None  # e.g. "Q3 2025 vs Q3 2024"

    is_gaap: bool = True
    segment: Optional[str] = None

    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    context_snippet: Optional[str] = None


class ClaimCreate(ClaimBase):
    pass


class Claim(ClaimBase):
    id: int

    model_config = {"from_attributes": True}


class ClaimWithVerification(Claim):
    """Claim bundled with its verification result for API responses."""

    verification: Optional[Verification] = None  # type: ignore[override]

    model_config = {"from_attributes": True}


# Resolve forward reference
from app.schemas.verification import Verification  # noqa: E402

ClaimWithVerification.model_rebuild()
