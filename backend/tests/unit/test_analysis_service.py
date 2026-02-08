"""Unit tests for AnalysisService — analysis orchestration and pattern persistence."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.database import Base
from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
from app.models.claim import ClaimModel
from app.models.company import CompanyModel
from app.models.discrepancy_pattern import DiscrepancyPatternModel
from app.models.financial_data import FinancialDataModel
from app.models.transcript import TranscriptModel
from app.models.verification import VerificationModel
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.discrepancy_pattern_repo import DiscrepancyPatternRepository
from app.repositories.verification_repo import VerificationRepository
from app.services.analysis_service import AnalysisService


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def sample_company(db):
    company = CompanyModel(ticker="AAPL", name="Apple Inc.", sector="Technology")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@pytest.fixture()
def sample_data(db, sample_company):
    """Create 3 quarters of transcripts, claims, financial data, and verifications."""
    items = []
    for q_idx, (year, quarter) in enumerate([(2025, 1), (2025, 2), (2025, 3)]):
        # Transcript
        transcript = TranscriptModel(
            company_id=sample_company.id,
            quarter=quarter,
            year=year,
            call_date=date(year, quarter * 3, 1),
            full_text=f"Earnings call Q{quarter} {year} transcript text.",
        )
        db.add(transcript)
        db.commit()
        db.refresh(transcript)

        # Financial data
        fin = FinancialDataModel(
            company_id=sample_company.id,
            period=f"Q{quarter}",
            year=year,
            quarter=quarter,
            revenue=90_000_000_000 + q_idx * 5_000_000_000,
            gross_profit=40_000_000_000 + q_idx * 2_000_000_000,
            net_income=20_000_000_000 + q_idx * 1_000_000_000,
            eps_diluted=1.2 + q_idx * 0.1,
        )
        db.add(fin)
        db.commit()

        # Claims — mix of metrics, types, GAAP flags
        claims_data = [
            # Revenue claim (absolute)
            {
                "transcript_id": transcript.id,
                "speaker": "CEO",
                "claim_text": f"Revenue was ${90 + q_idx * 5} billion",
                "metric": "revenue",
                "metric_type": "absolute",
                "stated_value": (90_000_000_000 + q_idx * 5_000_000_000) * 1.01,  # slightly overstated
                "unit": "usd_billions",
                "is_gaap": True,
                "confidence": 0.95,
            },
            # EPS claim (per_share)
            {
                "transcript_id": transcript.id,
                "speaker": "CFO",
                "claim_text": f"Diluted EPS was ${1.2 + q_idx * 0.1:.2f}",
                "metric": "eps_diluted",
                "metric_type": "per_share",
                "stated_value": 1.2 + q_idx * 0.1,
                "unit": "usd",
                "is_gaap": True,
                "confidence": 0.99,
            },
            # Growth claim
            {
                "transcript_id": transcript.id,
                "speaker": "CEO",
                "claim_text": "Revenue grew 12% year over year",
                "metric": "revenue",
                "metric_type": "growth_rate",
                "stated_value": 12.0,
                "unit": "percent",
                "is_gaap": True,
                "confidence": 0.9,
            },
        ]

        for cd in claims_data:
            claim = ClaimModel(**cd)
            db.add(claim)
            db.commit()
            db.refresh(claim)

            # Verification — revenue overstated, others exact
            if cd["metric"] == "revenue" and cd["metric_type"] == "absolute":
                actual = 90_000_000_000 + q_idx * 5_000_000_000
                stated = cd["stated_value"]
                acc = 1.0 - abs(stated - actual) / actual
                vf = VerificationModel(
                    claim_id=claim.id,
                    actual_value=actual,
                    accuracy_score=acc,
                    verdict="approximately_correct" if acc >= 0.98 else "verified",
                    explanation="Revenue approximately matches.",
                )
            else:
                vf = VerificationModel(
                    claim_id=claim.id,
                    actual_value=cd["stated_value"],
                    accuracy_score=1.0,
                    verdict="verified",
                    explanation="Exact match.",
                )
            db.add(vf)
            db.commit()

        items.append(transcript)

    return items


class TestAnalysisServiceBasic:
    """Core analysis functionality."""

    def test_analyze_company_returns_complete_analysis(self, db, sample_company, sample_data):
        repos = self._build_repos(db)
        svc = AnalysisService(
            DiscrepancyAnalyzer(), repos["company"], repos["claim"], repos["verification"],
        )

        analysis = svc.analyze_company(sample_company.id)

        assert analysis.ticker == "AAPL"
        assert analysis.name == "Apple Inc."
        assert analysis.total_claims == 9  # 3 claims × 3 quarters
        assert analysis.overall_trust_score > 0
        assert 0 <= analysis.overall_accuracy_rate <= 1.0
        assert isinstance(analysis.patterns, list)
        assert len(analysis.quarters_analyzed) == 3

    def test_analyze_company_raises_for_missing_company(self, db):
        repos = self._build_repos(db)
        svc = AnalysisService(
            DiscrepancyAnalyzer(), repos["company"], repos["claim"], repos["verification"],
        )
        with pytest.raises(ValueError, match="Company 999 not found"):
            svc.analyze_company(999)

    def test_analyze_all_returns_list(self, db, sample_company, sample_data):
        repos = self._build_repos(db)
        svc = AnalysisService(
            DiscrepancyAnalyzer(), repos["company"], repos["claim"], repos["verification"],
        )

        results = svc.analyze_all()
        assert len(results) == 1
        assert results[0].ticker == "AAPL"

    @staticmethod
    def _build_repos(db):
        return {
            "company": CompanyRepository(db),
            "claim": ClaimRepository(db),
            "verification": VerificationRepository(db),
        }


class TestAnalysisServicePersistence:
    """Test that patterns are persisted to the database."""

    def test_patterns_are_persisted_to_db(self, db, sample_company, sample_data):
        company_repo = CompanyRepository(db)
        claim_repo = ClaimRepository(db)
        verification_repo = VerificationRepository(db)
        pattern_repo = DiscrepancyPatternRepository(db)

        svc = AnalysisService(
            DiscrepancyAnalyzer(), company_repo, claim_repo, verification_repo, pattern_repo,
        )

        analysis = svc.analyze_company(sample_company.id)

        # Whether or not patterns are detected, the repo should have the right count
        persisted = pattern_repo.get_for_company(sample_company.id)
        assert len(persisted) == len(analysis.patterns)

        # Each persisted pattern should have valid fields
        for p in persisted:
            assert p.company_id == sample_company.id
            assert p.pattern_type is not None
            assert p.description
            assert p.severity >= 0

    def test_reanalysis_replaces_old_patterns(self, db, sample_company, sample_data):
        """Running analysis twice should replace, not duplicate, patterns."""
        company_repo = CompanyRepository(db)
        claim_repo = ClaimRepository(db)
        verification_repo = VerificationRepository(db)
        pattern_repo = DiscrepancyPatternRepository(db)

        svc = AnalysisService(
            DiscrepancyAnalyzer(), company_repo, claim_repo, verification_repo, pattern_repo,
        )

        # Run twice
        svc.analyze_company(sample_company.id)
        count_1 = pattern_repo.count()

        svc.analyze_company(sample_company.id)
        count_2 = pattern_repo.count()

        # Should be the same, not doubled
        assert count_2 == count_1

    def test_works_without_pattern_repo(self, db, sample_company, sample_data):
        """When pattern_repo is None, analysis still works — just no persistence."""
        company_repo = CompanyRepository(db)
        claim_repo = ClaimRepository(db)
        verification_repo = VerificationRepository(db)

        svc = AnalysisService(
            DiscrepancyAnalyzer(), company_repo, claim_repo, verification_repo,
            pattern_repo=None,
        )

        # Should not raise
        analysis = svc.analyze_company(sample_company.id)
        assert analysis.ticker == "AAPL"


class TestTrustScore:
    """Test the trust score calculation (now delegated to app.utils.scoring)."""

    def test_perfect_score(self):
        from app.utils.scoring import compute_trust_score
        v = {"verified": 10, "approximately_correct": 0, "misleading": 0, "incorrect": 0, "unverifiable": 0}
        score = compute_trust_score(v)
        assert score == 100.0

    def test_zero_verifiable(self):
        from app.utils.scoring import compute_trust_score
        v = {"verified": 0, "approximately_correct": 0, "misleading": 0, "incorrect": 0, "unverifiable": 5}
        score = compute_trust_score(v)
        assert score == 50.0

    def test_all_incorrect(self):
        from app.utils.scoring import compute_trust_score
        v = {"verified": 0, "approximately_correct": 0, "misleading": 0, "incorrect": 10, "unverifiable": 0}
        score = compute_trust_score(v)
        assert score == 0.0

    def test_mixed_results(self):
        from app.utils.scoring import compute_trust_score
        v = {"verified": 5, "approximately_correct": 3, "misleading": 1, "incorrect": 1, "unverifiable": 0}
        score = compute_trust_score(v)
        assert 50 < score < 100
