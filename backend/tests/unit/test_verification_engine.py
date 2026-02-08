"""Unit tests for the VerificationEngine — the heart of the system."""

import pytest

from app.config import Settings
from app.engines.metric_mapper import MetricMapper
from app.engines.verification_engine import VerificationEngine
from app.models.claim import ClaimModel
from app.repositories.financial_data_repo import FinancialDataRepository
from app.schemas.verification import Verdict


def _engine(db) -> VerificationEngine:
    return VerificationEngine(
        metric_mapper=MetricMapper(),
        financial_repo=FinancialDataRepository(db),
        settings=Settings(
            fmp_api_key="test",
            anthropic_api_key="test",
            verification_tolerance=0.02,
            approximate_tolerance=0.10,
            misleading_threshold=0.25,
        ),
    )


def _claim(db, transcript, **overrides) -> ClaimModel:
    """Helper to build a ClaimModel with sensible defaults."""
    defaults = dict(
        transcript_id=transcript.id,
        speaker="Tim Cook, CEO",
        speaker_role="CEO",
        claim_text="test claim",
        metric="revenue",
        metric_type="growth_rate",
        stated_value=10.7,
        unit="percent",
        comparison_period="year_over_year",
        comparison_basis="Q3 2025 vs Q3 2024",
        is_gaap=True,
        confidence=0.95,
    )
    defaults.update(overrides)
    c = ClaimModel(**defaults)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ── Growth rate verification ─────────────────────────────────────────────

class TestVerifyGrowthRate:
    """Verify 'revenue grew X% YoY'-style claims."""

    def test_accurate_yoy_growth(self, db, sample_company, sample_financial_data, sample_transcript):
        """Actual revenue growth: (94.93B − 85.78B) / 85.78B ≈ 10.68%. Stated 10.7% → VERIFIED."""
        engine = _engine(db)
        claim = _claim(db, sample_transcript, stated_value=10.7, metric="revenue")
        result = engine.verify(claim, sample_company.id, 2025, 3)

        assert result.verdict == Verdict.VERIFIED
        assert result.accuracy_score is not None
        assert result.accuracy_score > 0.98

    def test_slightly_off_growth(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated 12% growth when actual is ~10.68%.

        accuracy = 1 - |12 - 10.67| / 10.67 ≈ 0.875 → below 0.90 → MISLEADING
        (falls below the "approximately correct" threshold but above "incorrect")
        """
        engine = _engine(db)
        claim = _claim(db, sample_transcript, stated_value=12.0, metric="revenue")
        result = engine.verify(claim, sample_company.id, 2025, 3)

        assert result.verdict == Verdict.MISLEADING
        assert result.accuracy_score is not None
        assert result.accuracy_score < 0.90

    def test_slightly_off_growth_under(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated 10% growth when actual is ~10.68% → APPROXIMATELY_CORRECT (no favorable rounding)."""
        engine = _engine(db)
        claim = _claim(db, sample_transcript, stated_value=10.0, metric="revenue")
        result = engine.verify(claim, sample_company.id, 2025, 3)

        assert result.verdict == Verdict.APPROXIMATELY_CORRECT

    def test_misleading_growth(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated 15% growth when actual is ~10.68% → MISLEADING."""
        engine = _engine(db)
        claim = _claim(db, sample_transcript, stated_value=15.0, metric="revenue")
        result = engine.verify(claim, sample_company.id, 2025, 3)

        assert result.verdict in (Verdict.MISLEADING, Verdict.INCORRECT)

    def test_wildly_incorrect_growth(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated 50% growth when actual is ~10.68% → INCORRECT."""
        engine = _engine(db)
        claim = _claim(db, sample_transcript, stated_value=50.0, metric="revenue")
        result = engine.verify(claim, sample_company.id, 2025, 3)

        assert result.verdict == Verdict.INCORRECT

    def test_missing_comparison_data(self, db, sample_company, sample_financial_data, sample_transcript):
        """No prior-year data for the comparison quarter → UNVERIFIABLE."""
        engine = _engine(db)
        claim = _claim(db, sample_transcript, stated_value=10.0, metric="revenue")
        # Try to verify for Q1 2025 where we have no Q1 2024 data
        result = engine.verify(claim, sample_company.id, 2020, 3)

        assert result.verdict == Verdict.UNVERIFIABLE


# ── Absolute value verification ──────────────────────────────────────────

class TestVerifyAbsolute:
    """Verify 'revenue was $X billion'-style claims."""

    def test_accurate_revenue_billions(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated $94.9B, actual ~$94.93B → VERIFIED."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="revenue",
            metric_type="absolute",
            stated_value=94.9,
            unit="usd_billions",
            comparison_period="none",
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert result.verdict == Verdict.VERIFIED

    def test_accurate_revenue_millions(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated $94,930M, actual $94,930M → VERIFIED."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="revenue",
            metric_type="absolute",
            stated_value=94930,
            unit="usd_millions",
            comparison_period="none",
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert result.verdict == Verdict.VERIFIED

    def test_incorrect_absolute(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated $120B revenue when actual is ~$94.9B → INCORRECT."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="revenue",
            metric_type="absolute",
            stated_value=120.0,
            unit="usd_billions",
            comparison_period="none",
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert result.verdict == Verdict.INCORRECT


# ── Per-share verification ───────────────────────────────────────────────

class TestVerifyPerShare:
    def test_exact_eps(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated EPS $1.46, actual $1.46 → VERIFIED with score 1.0."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="eps_diluted",
            metric_type="per_share",
            stated_value=1.46,
            unit="usd",
            comparison_period="none",
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert result.verdict == Verdict.VERIFIED
        assert result.accuracy_score == 1.0


# ── Margin verification ─────────────────────────────────────────────────

class TestVerifyMargin:
    def test_gross_margin(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated gross margin 46%, actual ~46.22% → VERIFIED."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="gross_margin",
            metric_type="margin",
            stated_value=46.0,
            unit="percent",
            comparison_period="none",
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert result.verdict in (Verdict.VERIFIED, Verdict.APPROXIMATELY_CORRECT)

    def test_operating_margin(self, db, sample_company, sample_financial_data, sample_transcript):
        """Stated operating margin 31%, actual ~31.17% → VERIFIED."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="operating_margin",
            metric_type="margin",
            stated_value=31.0,
            unit="percent",
            comparison_period="none",
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert result.verdict in (Verdict.VERIFIED, Verdict.APPROXIMATELY_CORRECT)


# ── Unresolvable metrics ────────────────────────────────────────────────

class TestUnresolvable:
    def test_unknown_metric(self, db, sample_company, sample_transcript):
        """Metric like 'subscriber_count' → UNVERIFIABLE."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="subscriber_count",
            metric_type="absolute",
            stated_value=1_000_000,
            unit="usd",
            comparison_period="none",
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert result.verdict == Verdict.UNVERIFIABLE


# ── Misleading flag detection ────────────────────────────────────────────

class TestMisleadingFlags:
    def test_non_gaap_flag(self, db, sample_company, sample_financial_data, sample_transcript):
        """Non-GAAP claim should get flagged."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="revenue",
            metric_type="absolute",
            stated_value=94.9,
            unit="usd_billions",
            comparison_period="none",
            is_gaap=False,
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert "gaap_nongaap_mismatch" in result.misleading_flags

    def test_segment_flag(self, db, sample_company, sample_financial_data, sample_transcript):
        """Segment claim verified against total → flag it."""
        engine = _engine(db)
        claim = _claim(
            db, sample_transcript,
            metric="revenue",
            metric_type="absolute",
            stated_value=94.9,
            unit="usd_billions",
            comparison_period="none",
            segment="iPhone",
        )
        result = engine.verify(claim, sample_company.id, 2025, 3)
        assert "segment_vs_total" in result.misleading_flags
