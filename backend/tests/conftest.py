"""Shared test fixtures.

Every test gets a fresh in-memory SQLite database so tests are fully isolated.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.claim import ClaimModel
from app.models.company import CompanyModel
from app.models.financial_data import FinancialDataModel
from app.models.transcript import TranscriptModel


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine) -> Session:
    session = sessionmaker(bind=db_engine)()
    yield session
    session.close()


# ── Convenience fixtures ─────────────────────────────────────────────────

@pytest.fixture()
def sample_company(db: Session) -> CompanyModel:
    company = CompanyModel(ticker="AAPL", name="Apple Inc.", sector="Technology")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@pytest.fixture()
def sample_financial_data(
    db: Session, sample_company: CompanyModel
) -> tuple[FinancialDataModel, FinancialDataModel]:
    """Q3 2025 and Q3 2024 financial data (realistic Apple-like numbers)."""
    q3_2025 = FinancialDataModel(
        company_id=sample_company.id,
        period="Q3",
        year=2025,
        quarter=3,
        revenue=94_930_000_000,
        cost_of_revenue=51_051_000_000,
        gross_profit=43_879_000_000,
        operating_income=29_590_000_000,
        operating_expenses=14_289_000_000,
        net_income=23_636_000_000,
        eps=1.46,
        eps_diluted=1.46,
        ebitda=32_500_000_000,
        research_and_development=7_800_000_000,
        selling_general_admin=6_489_000_000,
        operating_cash_flow=26_760_000_000,
        capital_expenditure=-4_270_000_000,
        free_cash_flow=22_490_000_000,
        total_assets=352_000_000_000,
        total_liabilities=274_000_000_000,
        total_debt=111_000_000_000,
        cash_and_equivalents=29_000_000_000,
        shareholders_equity=78_000_000_000,
    )
    q3_2024 = FinancialDataModel(
        company_id=sample_company.id,
        period="Q3",
        year=2024,
        quarter=3,
        revenue=85_777_000_000,
        cost_of_revenue=46_377_000_000,
        gross_profit=39_400_000_000,
        operating_income=26_200_000_000,
        operating_expenses=13_200_000_000,
        net_income=22_956_000_000,
        eps=1.40,
        eps_diluted=1.40,
        ebitda=30_100_000_000,
        research_and_development=7_200_000_000,
        selling_general_admin=6_000_000_000,
        operating_cash_flow=24_100_000_000,
        capital_expenditure=-3_800_000_000,
        free_cash_flow=20_300_000_000,
        total_assets=340_000_000_000,
        total_liabilities=270_000_000_000,
        total_debt=108_000_000_000,
        cash_and_equivalents=27_000_000_000,
        shareholders_equity=70_000_000_000,
    )
    db.add_all([q3_2025, q3_2024])
    db.commit()
    db.refresh(q3_2025)
    db.refresh(q3_2024)
    return q3_2025, q3_2024


@pytest.fixture()
def sample_transcript(db: Session, sample_company: CompanyModel) -> TranscriptModel:
    t = TranscriptModel(
        company_id=sample_company.id,
        quarter=3,
        year=2025,
        call_date=date(2025, 7, 31),
        full_text="This is a test transcript for Apple Q3 2025.",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture()
def sample_claim(db: Session, sample_transcript: TranscriptModel) -> ClaimModel:
    c = ClaimModel(
        transcript_id=sample_transcript.id,
        speaker="Tim Cook, CEO",
        speaker_role="CEO",
        claim_text="Revenue grew approximately 10.7% year over year",
        metric="revenue",
        metric_type="growth_rate",
        stated_value=10.7,
        unit="percent",
        comparison_period="year_over_year",
        comparison_basis="Q3 2025 vs Q3 2024",
        is_gaap=True,
        confidence=0.95,
        context_snippet="We achieved revenue of $94.9 billion, up approximately 10.7 percent year over year.",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
