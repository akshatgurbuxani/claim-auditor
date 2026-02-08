"""Company schemas."""

from pydantic import BaseModel


class CompanyBase(BaseModel):
    ticker: str
    name: str
    sector: str


class CompanyCreate(CompanyBase):
    pass


class Company(CompanyBase):
    id: int

    model_config = {"from_attributes": True}


class CompanyWithStats(Company):
    """Company with aggregated verification statistics."""

    total_claims: int = 0
    verified_count: int = 0
    approximately_correct_count: int = 0
    misleading_count: int = 0
    incorrect_count: int = 0
    unverifiable_count: int = 0
    accuracy_rate: float = 0.0  # (verified + approx) / verifiable
    trust_score: float = 50.0  # 0–100 weighted score
