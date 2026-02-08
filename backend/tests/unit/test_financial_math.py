"""Unit tests for financial math utilities — written FIRST (TDD)."""

import pytest

from app.utils.financial_math import (
    accuracy_score,
    basis_points_to_percentage,
    denormalize_from_unit,
    growth_rate,
    margin,
    normalize_to_unit,
    percentage_difference,
    percentage_to_basis_points,
)


# ── growth_rate ──────────────────────────────────────────────────────────

class TestGrowthRate:
    def test_positive_growth(self):
        assert growth_rate(115, 100) == 15.0

    def test_negative_growth(self):
        assert growth_rate(85, 100) == -15.0

    def test_zero_growth(self):
        assert growth_rate(100, 100) == 0.0

    def test_zero_base_returns_none(self):
        assert growth_rate(100, 0) is None

    def test_large_growth(self):
        assert growth_rate(300, 100) == 200.0

    def test_negative_to_positive(self):
        # -100 to +50 should be 150% growth (relative to abs of base)
        assert growth_rate(50, -100) == 150.0

    def test_both_negative(self):
        # -50 vs -100: improvement of 50%
        result = growth_rate(-50, -100)
        assert result == 50.0

    def test_fractional_growth(self):
        result = growth_rate(101.5, 100)
        assert abs(result - 1.5) < 0.001


# ── margin ───────────────────────────────────────────────────────────────

class TestMargin:
    def test_basic_margin(self):
        assert margin(30, 100) == 30.0

    def test_zero_numerator(self):
        assert margin(0, 100) == 0.0

    def test_zero_denominator_returns_none(self):
        assert margin(30, 0) is None

    def test_100_percent_margin(self):
        assert margin(100, 100) == 100.0

    def test_negative_margin(self):
        assert margin(-10, 100) == -10.0

    def test_real_world_gross_margin(self):
        # Apple-like: gross profit 43.88B on revenue 94.93B
        result = margin(43_879_000_000, 94_930_000_000)
        assert abs(result - 46.22) < 0.1


# ── basis_points ↔ percentage ────────────────────────────────────────────

class TestBasisPoints:
    def test_200_bps_to_pct(self):
        assert basis_points_to_percentage(200) == 2.0

    def test_50_bps_to_pct(self):
        assert basis_points_to_percentage(50) == 0.5

    def test_pct_to_bps(self):
        assert percentage_to_basis_points(2.0) == 200.0

    def test_roundtrip(self):
        bps = 150
        assert percentage_to_basis_points(basis_points_to_percentage(bps)) == bps


# ── normalize / denormalize ──────────────────────────────────────────────

class TestNormalize:
    def test_billions(self):
        assert normalize_to_unit(5_000_000_000, "usd_billions") == 5.0

    def test_millions(self):
        assert normalize_to_unit(5_000_000, "usd_millions") == 5.0

    def test_raw_usd(self):
        assert normalize_to_unit(5, "usd") == 5

    def test_percent_passthrough(self):
        assert normalize_to_unit(15.0, "percent") == 15.0

    def test_denormalize_billions(self):
        assert denormalize_from_unit(5.0, "usd_billions") == 5_000_000_000

    def test_denormalize_millions(self):
        assert denormalize_from_unit(5.0, "usd_millions") == 5_000_000

    def test_roundtrip_billions(self):
        raw = 94_930_000_000
        assert denormalize_from_unit(
            normalize_to_unit(raw, "usd_billions"), "usd_billions"
        ) == raw


# ── accuracy_score ───────────────────────────────────────────────────────

class TestAccuracyScore:
    def test_exact_match(self):
        assert accuracy_score(15.0, 15.0) == 1.0

    def test_close_match(self):
        # 15 vs 14 → off by ~7.1% → score ≈ 0.929
        score = accuracy_score(15.0, 14.0)
        assert 0.92 < score < 0.94

    def test_way_off(self):
        score = accuracy_score(15.0, 5.0)
        assert score < 0.1  # off by 200%

    def test_zero_actual_nonzero_stated(self):
        assert accuracy_score(15.0, 0.0) == 0.0

    def test_both_zero(self):
        assert accuracy_score(0.0, 0.0) == 1.0

    def test_within_2_percent(self):
        # 10.2 vs 10.0 → 2% off → score = 0.98
        score = accuracy_score(10.2, 10.0)
        assert score >= 0.98

    def test_within_10_percent(self):
        # 11.0 vs 10.0 → 10% off → score = 0.90
        score = accuracy_score(11.0, 10.0)
        assert abs(score - 0.90) < 0.001

    def test_negative_values(self):
        # Score should work with negative actuals too
        score = accuracy_score(-14.0, -15.0)
        assert score > 0.90

    def test_never_negative(self):
        # Even absurd mismatches should clamp to 0
        assert accuracy_score(1000, 1) >= 0.0


# ── percentage_difference ────────────────────────────────────────────────

class TestPercentageDifference:
    def test_overshoot(self):
        assert percentage_difference(115, 100) == 15.0

    def test_undershoot(self):
        assert percentage_difference(85, 100) == -15.0

    def test_exact(self):
        assert percentage_difference(100, 100) == 0.0

    def test_zero_actual_returns_none(self):
        assert percentage_difference(10, 0) is None

    def test_real_world_revenue_claim(self):
        # CEO says "revenue grew 15%" but actual is 10.68%
        diff = percentage_difference(15.0, 10.68)
        assert diff is not None
        assert abs(diff - 40.45) < 0.5  # ~40% overstated
