"""Tests for PipelineFacade — the decoupling layer between external interfaces
and the internal pipeline.

The facade is tested with a real in-memory DB (same as other unit tests)
but mocked external clients so we never hit real APIs.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from dependency_injector import providers

from app.config import Settings
from app.container import AppContainer
from app.database import Base
from app.facade import PipelineFacade
from app.models.claim import ClaimModel
from app.models.company import CompanyModel
from app.models.discrepancy_pattern import DiscrepancyPatternModel
from app.models.financial_data import FinancialDataModel
from app.models.transcript import TranscriptModel
from app.models.verification import VerificationModel

import app.models  # noqa: F401


# ── Helpers ───────────────────────────────────────────────────────────────


def _in_memory_db() -> Session:
    """Create a fresh in-memory DB with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db: Session) -> CompanyModel:
    """Seed a minimal dataset: 1 company, 1 transcript, 2 claims, 2 verifications."""
    company = CompanyModel(ticker="AAPL", name="Apple Inc.", sector="Technology")
    db.add(company)
    db.commit()
    db.refresh(company)

    transcript = TranscriptModel(
        company_id=company.id,
        quarter=3,
        year=2025,
        call_date=date(2025, 7, 31),
        full_text="Apple Q3 2025 transcript.",
    )
    db.add(transcript)
    db.commit()
    db.refresh(transcript)

    fin = FinancialDataModel(
        company_id=company.id,
        period="Q3",
        year=2025,
        quarter=3,
        revenue=94_930_000_000,
        gross_profit=43_879_000_000,
        net_income=23_636_000_000,
        eps_diluted=1.46,
    )
    db.add(fin)
    db.commit()
    db.refresh(fin)

    claim1 = ClaimModel(
        transcript_id=transcript.id,
        speaker="Tim Cook, CEO",
        speaker_role="CEO",
        claim_text="Revenue was $94.9 billion",
        metric="revenue",
        metric_type="absolute",
        stated_value=94.9,
        unit="usd_billions",
        is_gaap=True,
        confidence=0.95,
    )
    claim2 = ClaimModel(
        transcript_id=transcript.id,
        speaker="Luca Maestri, CFO",
        speaker_role="CFO",
        claim_text="EPS was $1.50",
        metric="eps_diluted",
        metric_type="per_share",
        stated_value=1.50,
        unit="usd",
        is_gaap=True,
        confidence=0.90,
    )
    db.add_all([claim1, claim2])
    db.commit()
    db.refresh(claim1)
    db.refresh(claim2)

    v1 = VerificationModel(
        claim_id=claim1.id,
        verdict="verified",
        actual_value=94.93,
        accuracy_score=0.9997,
        explanation="Revenue matches within 0.03%",
    )
    v2 = VerificationModel(
        claim_id=claim2.id,
        verdict="incorrect",
        actual_value=1.46,
        accuracy_score=0.973,
        explanation="Stated $1.50 vs actual $1.46 — 2.7% off",
    )
    db.add_all([v1, v2])
    db.commit()

    # Add a discrepancy pattern
    pattern = DiscrepancyPatternModel(
        company_id=company.id,
        pattern_type="selective_emphasis",
        description="Management emphasises positive metrics",
        affected_quarters=["Q3 2025"],
        severity=0.6,
        evidence=["90% positive claims"],
    )
    db.add(pattern)
    db.commit()

    return company


def _build_facade_with_seeded_db() -> PipelineFacade:
    """Build a PipelineFacade that uses a seeded in-memory DB.

    Uses the DI container pattern with mocked external clients.
    """
    # Create in-memory database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    # Create container and override with test database
    container = AppContainer()
    container.db_engine.override(providers.Object(engine))
    container.db_session.override(providers.Factory(lambda: SessionLocal()))

    # Mock external clients (never call real APIs)
    class MockFMPClient:
        def get_company_profile(self, ticker):
            return {"ticker": ticker, "name": f"{ticker} Inc", "sector": "Technology"}
        def get_financial_statements(self, ticker, year, quarter):
            return []
        def get_earnings_transcript(self, ticker, year, quarter):
            return None

    class MockLLMClient:
        def extract_claims(self, transcript_text):
            return []

    container.fmp_client.override(providers.Factory(MockFMPClient))
    container.llm_client.override(providers.Factory(MockLLMClient))

    # Seed test data
    db = SessionLocal()
    _seed(db)
    db.close()

    # Create facade with test container
    facade = PipelineFacade(container=container)

    return facade


# ══════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════


class TestFacadeListCompanies:
    def test_returns_seeded_companies(self):
        facade = _build_facade_with_seeded_db()
        companies = facade.list_companies()
        assert len(companies) == 1
        assert companies[0]["ticker"] == "AAPL"
        assert companies[0]["name"] == "Apple Inc."
        assert companies[0]["total_claims"] == 2

    def test_trust_score_is_computed(self):
        facade = _build_facade_with_seeded_db()
        companies = facade.list_companies()
        # 1 verified + 1 incorrect → trust should be between 0 and 100
        trust = companies[0]["trust_score"]
        assert 0 <= trust <= 100

    def test_verdicts_breakdown(self):
        facade = _build_facade_with_seeded_db()
        companies = facade.list_companies()
        verdicts = companies[0]["verdicts"]
        assert verdicts["verified"] == 1
        assert verdicts["incorrect"] == 1

    def test_empty_db_returns_empty_list(self):
        # Create empty in-memory database
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)

        # Create container with test database
        container = AppContainer()
        container.db_engine.override(providers.Object(engine))
        container.db_session.override(providers.Factory(lambda: SessionLocal()))

        # Mock clients
        container.fmp_client.override(providers.Factory(MagicMock))
        container.llm_client.override(providers.Factory(MagicMock))

        # Create facade with empty database
        facade = PipelineFacade(container=container)

        assert facade.list_companies() == []


class TestFacadeGetCompanyAnalysis:
    def test_returns_analysis_for_existing_company(self):
        facade = _build_facade_with_seeded_db()
        result = facade.get_company_analysis("AAPL")
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert "overall_trust_score" in result
        assert "overall_accuracy_rate" in result
        assert "patterns" in result
        assert "top_discrepancies" in result

    def test_returns_none_for_missing_company(self):
        facade = _build_facade_with_seeded_db()
        result = facade.get_company_analysis("ZZZZ")
        assert result is None


class TestFacadeGetClaims:
    def test_returns_all_claims(self):
        facade = _build_facade_with_seeded_db()
        claims = facade.get_claims("AAPL")
        assert len(claims) == 2

    def test_filter_by_verdict(self):
        facade = _build_facade_with_seeded_db()
        verified = facade.get_claims("AAPL", verdict_filter="verified")
        assert len(verified) == 1
        assert verified[0]["verdict"] == "verified"

        incorrect = facade.get_claims("AAPL", verdict_filter="incorrect")
        assert len(incorrect) == 1
        assert incorrect[0]["verdict"] == "incorrect"

    def test_missing_company_returns_empty(self):
        facade = _build_facade_with_seeded_db()
        claims = facade.get_claims("ZZZZ")
        assert claims == []

    def test_claim_has_expected_fields(self):
        facade = _build_facade_with_seeded_db()
        claims = facade.get_claims("AAPL")
        c = claims[0]
        expected_fields = {
            "claim_text", "speaker", "metric", "metric_type",
            "stated_value", "unit", "quarter", "verdict",
            "actual_value", "accuracy_score", "explanation",
            "misleading_flags", "is_gaap", "confidence",
        }
        assert expected_fields.issubset(set(c.keys()))


class TestFacadeQuarterBreakdown:
    def test_returns_quarter_data(self):
        facade = _build_facade_with_seeded_db()
        quarters = facade.get_quarter_breakdown("AAPL")
        assert len(quarters) == 1
        assert quarters[0]["quarter"] == "Q3 2025"
        assert quarters[0]["total_claims"] == 2

    def test_missing_company_returns_empty(self):
        facade = _build_facade_with_seeded_db()
        assert facade.get_quarter_breakdown("ZZZZ") == []


class TestFacadeDiscrepancyPatterns:
    def test_returns_persisted_patterns(self):
        facade = _build_facade_with_seeded_db()
        patterns = facade.get_discrepancy_patterns("AAPL")
        assert len(patterns) == 1
        assert patterns[0]["pattern_type"] == "selective_emphasis"
        assert patterns[0]["severity"] == 0.6

    def test_missing_company_returns_empty(self):
        facade = _build_facade_with_seeded_db()
        assert facade.get_discrepancy_patterns("ZZZZ") == []


class TestFacadeOutputsArePlainDicts:
    """Ensure the facade never leaks ORM models — everything is plain dict/list."""

    def test_list_companies_returns_dicts(self):
        facade = _build_facade_with_seeded_db()
        for item in facade.list_companies():
            assert isinstance(item, dict)

    def test_get_claims_returns_dicts(self):
        facade = _build_facade_with_seeded_db()
        for item in facade.get_claims("AAPL"):
            assert isinstance(item, dict)

    def test_get_quarter_breakdown_returns_dicts(self):
        facade = _build_facade_with_seeded_db()
        for item in facade.get_quarter_breakdown("AAPL"):
            assert isinstance(item, dict)

    def test_get_discrepancy_patterns_returns_dicts(self):
        facade = _build_facade_with_seeded_db()
        for item in facade.get_discrepancy_patterns("AAPL"):
            assert isinstance(item, dict)

    def test_get_company_analysis_returns_dict(self):
        facade = _build_facade_with_seeded_db()
        result = facade.get_company_analysis("AAPL")
        assert isinstance(result, dict)


class TestFacadeContextManager:
    def test_works_as_context_manager(self):
        facade = _build_facade_with_seeded_db()
        with facade:
            companies = facade.list_companies()
            assert len(companies) == 1
