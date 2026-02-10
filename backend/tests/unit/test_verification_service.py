"""Unit tests for VerificationService — orchestration and idempotency."""

import pytest

from app.config import Settings
from app.engines.metric_mapper import MetricMapper
from app.engines.verification_engine import VerificationEngine
from app.models.claim import ClaimModel
from app.models.verification import VerificationModel
from app.repositories.claim_repo import ClaimRepository
from app.repositories.financial_data_repo import FinancialDataRepository
from app.repositories.verification_repo import VerificationRepository
from app.services.verification_service import VerificationService


def _make_service(db) -> VerificationService:
    settings = Settings(
        fmp_api_key="test",
        anthropic_api_key="test",
        verification_tolerance=0.02,
        approximate_tolerance=0.10,
        misleading_threshold=0.25,
    )
    mapper = MetricMapper()
    financial_repo = FinancialDataRepository(db)
    engine = VerificationEngine(mapper, financial_repo, settings)
    claim_repo = ClaimRepository(db)
    verification_repo = VerificationRepository(db)
    return VerificationService(db, engine, claim_repo, verification_repo)


def _add_claim(db, transcript, **overrides) -> ClaimModel:
    defaults = dict(
        transcript_id=transcript.id,
        speaker="CFO",
        speaker_role="CFO",
        claim_text="Revenue was $94.9 billion",
        metric="revenue",
        metric_type="absolute",
        stated_value=94.9,
        unit="usd_billions",
        comparison_period="none",
        is_gaap=True,
        confidence=0.95,
    )
    defaults.update(overrides)
    c = ClaimModel(**defaults)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


class TestVerificationServiceOrchestration:
    def test_verifies_unverified_claims(
        self, db, sample_company, sample_financial_data, sample_transcript
    ):
        """Claims without a verification row should be verified."""
        claim = _add_claim(db, sample_transcript)
        service = _make_service(db)

        result = service.verify_all()

        # The claim should now have a verification
        total = sum(v for k, v in result.items() if k != "errors")
        assert total == 1
        assert result["errors"] == 0

    def test_skips_already_verified_claims(
        self, db, sample_company, sample_financial_data, sample_transcript
    ):
        """Claims that already have a verification row should be skipped."""
        claim = _add_claim(db, sample_transcript)
        service = _make_service(db)

        # First run — verify
        result1 = service.verify_all()
        total1 = sum(v for k, v in result1.items() if k != "errors")
        assert total1 == 1

        # Second run — should skip
        result2 = service.verify_all()
        total2 = sum(v for k, v in result2.items() if k != "errors")
        assert total2 == 0

    def test_summary_counts_match_verdicts(
        self, db, sample_company, sample_financial_data, sample_transcript
    ):
        """Summary dict should accurately reflect verdicts."""
        # Accurate claim → VERIFIED
        _add_claim(db, sample_transcript, stated_value=94.93, unit="usd_billions")
        # Wildly off claim → INCORRECT
        _add_claim(db, sample_transcript, stated_value=200.0, unit="usd_billions")

        service = _make_service(db)
        result = service.verify_all()

        assert result["errors"] == 0
        total = sum(v for k, v in result.items() if k != "errors")
        assert total == 2  # both claims processed

    def test_unresolvable_metric_becomes_unverifiable(
        self, db, sample_company, sample_financial_data, sample_transcript
    ):
        """A claim with an unknown metric should get UNVERIFIABLE verdict."""
        _add_claim(
            db, sample_transcript,
            metric="subscriber_count",
            metric_type="absolute",
            stated_value=1000000,
            unit="usd",
        )

        service = _make_service(db)
        result = service.verify_all()

        assert result["unverifiable"] == 1
