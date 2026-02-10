"""End-to-end pipeline test — proves the full chain works with ZERO API calls.

Uses fixture data (mock FMP responses + mock LLM extraction) to:
  1. Ingest company data (profile + financials + transcript)
  2. Extract claims from transcript
  3. Verify each claim against financial data
  4. Run discrepancy analysis

This test catches integration issues between layers that unit tests miss:
  - Schema mismatches between services
  - ORM relationship loading failures
  - Transaction / session issues
  - Field mapping errors from FMP → FinancialDataModel → MetricMapper

Run with:
    pytest tests/integration/test_pipeline_e2e.py -v
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.clients.fmp_client import FMPClient, FMPTranscript
from app.config import Settings
from app.database import Base
from app.engines.claim_extractor import ClaimExtractor
from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
from app.engines.metric_mapper import MetricMapper
from app.engines.verification_engine import VerificationEngine
from app.models.claim import ClaimModel
from app.models.company import CompanyModel
from app.models.financial_data import FinancialDataModel
from app.models.transcript import TranscriptModel
from app.models.verification import VerificationModel
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.discrepancy_pattern_repo import DiscrepancyPatternRepository
from app.repositories.financial_data_repo import FinancialDataRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.repositories.verification_repo import VerificationRepository
from app.services.analysis_service import AnalysisService
from app.services.extraction_service import ExtractionService
from app.services.ingestion_service import IngestionService
from app.services.verification_service import VerificationService
from tests.fixtures import load_fixture


# ── Fixture: Fresh in-memory DB ─────────────────────────────────────────


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


# ── Fixture: Mock FMP client using saved fixture data ────────────────────


@pytest.fixture()
def mock_fmp():
    """FMPClient that returns fixture data instead of hitting the network."""
    fmp = MagicMock(spec=FMPClient)

    fmp.get_company_profile.return_value = load_fixture("fmp_profile_AAPL.json")
    fmp.get_income_statement.return_value = load_fixture("fmp_income_statement_AAPL.json")
    fmp.get_cash_flow_statement.return_value = load_fixture("fmp_cashflow_AAPL.json")
    fmp.get_balance_sheet.return_value = load_fixture("fmp_balance_sheet_AAPL.json")

    transcript_data = load_fixture("fmp_transcript_AAPL_Q3_2024.json")
    fmp.get_transcript.return_value = FMPTranscript(
        ticker=transcript_data["ticker"],
        quarter=transcript_data["quarter"],
        year=transcript_data["year"],
        call_date=date.fromisoformat(transcript_data["call_date"]),
        content=transcript_data["content"],
    )

    return fmp


# ── Fixture: Mock LLM client using saved extraction ─────────────────────


class FixtureLLMClient:
    """LLM client that returns fixture extraction data."""

    def __init__(self):
        self._response = load_fixture("llm_extraction_AAPL_Q3_2024.json")
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def extract_claims(self, **kwargs) -> list[dict]:
        return self._response


# ══════════════════════════════════════════════════════════════════════════
# THE TEST
# ══════════════════════════════════════════════════════════════════════════


class TestFullPipeline:
    """End-to-end pipeline test: ingest → extract → verify → analyze."""

    def test_full_pipeline_with_fixtures(self, db: Session, mock_fmp):
        """Run the complete pipeline with fixture data and assert every stage."""

        # ── Repositories ─────────────────────────────────────────────
        company_repo = CompanyRepository(db)
        transcript_repo = TranscriptRepository(db)
        financial_repo = FinancialDataRepository(db)
        claim_repo = ClaimRepository(db)
        verification_repo = VerificationRepository(db)

        settings = Settings(
            fmp_api_key="test",
            anthropic_api_key="test",
            verification_tolerance=0.02,
            approximate_tolerance=0.10,
            misleading_threshold=0.25,
        )

        # ═════════════════════════════════════════════════════════════
        # STEP 1: Ingest
        # ═════════════════════════════════════════════════════════════
        ingestion = IngestionService(
            db, mock_fmp, company_repo, transcript_repo, financial_repo, settings=settings
        )
        ingest_result = ingestion.ingest_all(
            tickers=["AAPL"],
            quarters=[(2024, 3)],
        )

        # Assertions: company, transcript, and financial data created
        assert ingest_result["companies"] == 1
        assert ingest_result["transcripts_fetched"] == 1
        assert ingest_result["financial_periods_fetched"] >= 1
        assert ingest_result["errors"] == 0

        company = company_repo.get_by_ticker("AAPL")
        assert company is not None
        assert company.name == "Apple Inc."
        assert company.sector == "Technology"

        transcript = transcript_repo.get_for_quarter(company.id, 2024, 3)
        assert transcript is not None
        assert len(transcript.full_text) > 100

        fin = financial_repo.get_for_quarter(company.id, 2024, 3)
        assert fin is not None
        assert fin.revenue == 85777000000
        assert fin.eps_diluted == 1.40

        # ═════════════════════════════════════════════════════════════
        # STEP 2: Extract claims
        # ═════════════════════════════════════════════════════════════
        llm = FixtureLLMClient()
        extractor = ClaimExtractor(llm)
        extraction = ExtractionService(db, extractor, transcript_repo, claim_repo)
        extract_result = extraction.extract_all()

        assert extract_result["transcripts_processed"] == 1
        assert extract_result["claims_extracted"] > 0
        assert extract_result["errors"] == 0

        claims = claim_repo.get_for_transcript(transcript.id)
        assert len(claims) > 0

        # Verify claim structure
        for c in claims:
            assert c.transcript_id == transcript.id
            assert c.metric is not None
            assert c.stated_value is not None
            assert c.speaker is not None

        # ═════════════════════════════════════════════════════════════
        # STEP 3: Verify claims
        # ═════════════════════════════════════════════════════════════
        mapper = MetricMapper()
        ver_engine = VerificationEngine(mapper, financial_repo, settings)
        verification = VerificationService(db, ver_engine, claim_repo, verification_repo)
        verify_result = verification.verify_all()

        total_verified = sum(v for k, v in verify_result.items() if k != "errors")
        assert total_verified > 0
        assert verify_result["errors"] == 0

        # Check that verifications actually exist in the DB
        for c in claims:
            vf = verification_repo.get_for_claim(c.id)
            assert vf is not None, f"Claim {c.id} ({c.metric}) has no verification"
            assert vf.verdict in (
                "verified", "approximately_correct", "misleading",
                "incorrect", "unverifiable",
            )

        # ═════════════════════════════════════════════════════════════
        # Check specific claims against known fixture data
        # ═════════════════════════════════════════════════════════════

        # Revenue $85.8B stated vs $85.777B actual → should be VERIFIED
        rev_claims = [c for c in claims if c.metric == "revenue" and c.metric_type == "absolute" and c.segment is None]
        if rev_claims:
            rev_claim = rev_claims[0]
            vf = verification_repo.get_for_claim(rev_claim.id)
            assert vf.verdict in ("verified", "approximately_correct"), (
                f"Revenue claim (stated={rev_claim.stated_value}) got verdict={vf.verdict}: {vf.explanation}"
            )

        # EPS $1.40 stated vs $1.40 actual → should be VERIFIED
        eps_claims = [c for c in claims if c.metric == "eps_diluted"]
        if eps_claims:
            eps_claim = eps_claims[0]
            vf = verification_repo.get_for_claim(eps_claim.id)
            assert vf.verdict == "verified", (
                f"EPS claim (stated={eps_claim.stated_value}) got verdict={vf.verdict}: {vf.explanation}"
            )
            assert vf.accuracy_score == 1.0

        # Total debt $108B stated vs $108B actual → should be VERIFIED
        debt_claims = [c for c in claims if c.metric == "total_debt"]
        if debt_claims:
            debt_claim = debt_claims[0]
            vf = verification_repo.get_for_claim(debt_claim.id)
            assert vf.verdict == "verified", (
                f"Debt claim (stated={debt_claim.stated_value}) got verdict={vf.verdict}: {vf.explanation}"
            )

        # ═════════════════════════════════════════════════════════════
        # STEP 4: Analysis (bonus — discrepancy patterns with persistence)
        # ═════════════════════════════════════════════════════════════
        pattern_repo = DiscrepancyPatternRepository(db)
        analyzer = DiscrepancyAnalyzer()
        analysis_svc = AnalysisService(
            db, analyzer, company_repo, claim_repo, verification_repo, pattern_repo,
        )
        analysis = analysis_svc.analyze_company(company.id)

        assert analysis.ticker == "AAPL"
        assert analysis.total_claims == len(claims)
        assert 0 <= analysis.overall_trust_score <= 100
        assert 0 <= analysis.overall_accuracy_rate <= 1.0
        assert isinstance(analysis.patterns, list)
        assert len(analysis.quarters_analyzed) > 0

        # Verify patterns are persisted in the database
        persisted_patterns = pattern_repo.get_for_company(company.id)
        assert len(persisted_patterns) == len(analysis.patterns)

        # ═════════════════════════════════════════════════════════════
        # IDEMPOTENCY: Re-run should be a no-op
        # ═════════════════════════════════════════════════════════════

        # Re-run ingestion → should skip everything
        ingest_result2 = ingestion.ingest_all(tickers=["AAPL"], quarters=[(2024, 3)])
        assert ingest_result2["transcripts_skipped"] == 1
        assert ingest_result2["transcripts_fetched"] == 0
        mock_fmp.get_company_profile.assert_called_once()  # only from first run

        # Re-run extraction → should find 0 unprocessed
        extract_result2 = extraction.extract_all()
        assert extract_result2["transcripts_processed"] == 0

        # Re-run verification → should find 0 unverified
        verify_result2 = verification.verify_all()
        total2 = sum(v for k, v in verify_result2.items() if k != "errors")
        assert total2 == 0

    def test_pipeline_handles_missing_data_gracefully(self, db: Session):
        """Pipeline should not crash when FMP returns no data."""
        mock_fmp = MagicMock(spec=FMPClient)
        mock_fmp.get_company_profile.return_value = {}
        mock_fmp.get_transcript.return_value = None
        mock_fmp.get_income_statement.return_value = []
        mock_fmp.get_cash_flow_statement.return_value = []
        mock_fmp.get_balance_sheet.return_value = []

        company_repo = CompanyRepository(db)
        transcript_repo = TranscriptRepository(db)
        financial_repo = FinancialDataRepository(db)

        ingestion = IngestionService(db, mock_fmp, company_repo, transcript_repo, financial_repo)
        result = ingestion.ingest_all(tickers=["ZZZZZ"], quarters=[(2024, 3)])

        # Should not crash, just report 0 data
        assert result["companies"] == 1
        assert result["transcripts_fetched"] == 0
        assert result["financial_periods_fetched"] == 0
        assert result["errors"] == 0
