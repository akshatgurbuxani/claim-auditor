"""Unit tests for domain.verdicts module."""

import pytest

from app.domain.verdicts import assign_verdict
from app.schemas.verification import MisleadingFlag, Verdict


class TestAssignVerdict:
    """Test verdict assignment logic."""

    # ── Base verdicts (no flags) ──────────────────────────────────────

    def test_verified_perfect_match(self):
        """Perfect accuracy = VERIFIED."""
        verdict = assign_verdict(1.0, [])
        assert verdict == Verdict.VERIFIED

    def test_verified_within_tolerance(self):
        """Accuracy >= 98% = VERIFIED."""
        verdict = assign_verdict(0.99, [])
        assert verdict == Verdict.VERIFIED

        verdict = assign_verdict(0.98, [])
        assert verdict == Verdict.VERIFIED

    def test_approximately_correct(self):
        """Accuracy >= 90% but < 98% = APPROXIMATELY_CORRECT."""
        verdict = assign_verdict(0.95, [])
        assert verdict == Verdict.APPROXIMATELY_CORRECT

        verdict = assign_verdict(0.90, [])
        assert verdict == Verdict.APPROXIMATELY_CORRECT

    def test_misleading_range(self):
        """Accuracy >= 75% but < 90% = MISLEADING."""
        verdict = assign_verdict(0.85, [])
        assert verdict == Verdict.MISLEADING

        verdict = assign_verdict(0.75, [])
        assert verdict == Verdict.MISLEADING

    def test_incorrect(self):
        """Accuracy < 75% = INCORRECT."""
        verdict = assign_verdict(0.70, [])
        assert verdict == Verdict.INCORRECT

        verdict = assign_verdict(0.50, [])
        assert verdict == Verdict.INCORRECT

        verdict = assign_verdict(0.0, [])
        assert verdict == Verdict.INCORRECT

    # ── With misleading flags ─────────────────────────────────────────

    def test_verified_with_rounding_bias_stays_verified(self):
        """ROUNDING_BIAS doesn't upgrade VERIFIED → MISLEADING."""
        verdict = assign_verdict(0.99, [MisleadingFlag.ROUNDING_BIAS])
        assert verdict == Verdict.VERIFIED

    def test_verified_with_substantive_flag_becomes_misleading(self):
        """Substantive flags upgrade VERIFIED → MISLEADING."""
        verdict = assign_verdict(0.99, [MisleadingFlag.GAAP_NONGAAP_MISMATCH])
        assert verdict == Verdict.MISLEADING

        verdict = assign_verdict(0.99, [MisleadingFlag.SEGMENT_VS_TOTAL])
        assert verdict == Verdict.MISLEADING

        verdict = assign_verdict(0.99, [MisleadingFlag.CHERRY_PICKED_PERIOD])
        assert verdict == Verdict.MISLEADING

    def test_approximately_correct_with_substantive_flag_becomes_misleading(self):
        """Substantive flags upgrade APPROXIMATELY_CORRECT → MISLEADING."""
        verdict = assign_verdict(0.95, [MisleadingFlag.GAAP_NONGAAP_MISMATCH])
        assert verdict == Verdict.MISLEADING

    def test_misleading_stays_misleading_with_flags(self):
        """MISLEADING doesn't change with additional flags."""
        verdict = assign_verdict(0.80, [MisleadingFlag.GAAP_NONGAAP_MISMATCH])
        assert verdict == Verdict.MISLEADING

    def test_incorrect_stays_incorrect_with_flags(self):
        """INCORRECT doesn't change with flags."""
        verdict = assign_verdict(0.50, [MisleadingFlag.GAAP_NONGAAP_MISMATCH])
        assert verdict == Verdict.INCORRECT

    def test_multiple_flags_with_rounding_bias(self):
        """Multiple flags including ROUNDING_BIAS still upgrade if any are substantive."""
        flags = [
            MisleadingFlag.ROUNDING_BIAS,
            MisleadingFlag.GAAP_NONGAAP_MISMATCH,
        ]
        verdict = assign_verdict(0.99, flags)
        assert verdict == Verdict.MISLEADING

    def test_only_rounding_bias_no_upgrade(self):
        """Only ROUNDING_BIAS doesn't upgrade verdict."""
        verdict = assign_verdict(0.99, [MisleadingFlag.ROUNDING_BIAS])
        assert verdict == Verdict.VERIFIED

        verdict = assign_verdict(0.95, [MisleadingFlag.ROUNDING_BIAS])
        assert verdict == Verdict.APPROXIMATELY_CORRECT

    # ── Custom tolerances ─────────────────────────────────────────────

    def test_custom_verified_tolerance(self):
        """Custom tolerance_verified threshold."""
        # With 5% tolerance, 95% accuracy = VERIFIED
        verdict = assign_verdict(
            0.95, [], tolerance_verified=0.05, tolerance_approx=0.10
        )
        assert verdict == Verdict.VERIFIED

        # But 94% = APPROXIMATELY_CORRECT
        verdict = assign_verdict(
            0.94, [], tolerance_verified=0.05, tolerance_approx=0.10
        )
        assert verdict == Verdict.APPROXIMATELY_CORRECT

    def test_custom_approx_tolerance(self):
        """Custom tolerance_approx threshold."""
        # With 20% tolerance, 85% accuracy = APPROXIMATELY_CORRECT
        verdict = assign_verdict(
            0.85,
            [],
            tolerance_verified=0.02,
            tolerance_approx=0.20,
            tolerance_misleading=0.25,
        )
        assert verdict == Verdict.APPROXIMATELY_CORRECT

    def test_custom_misleading_tolerance(self):
        """Custom tolerance_misleading threshold."""
        # With 50% tolerance, 60% accuracy = MISLEADING
        verdict = assign_verdict(
            0.60,
            [],
            tolerance_verified=0.02,
            tolerance_approx=0.10,
            tolerance_misleading=0.50,
        )
        assert verdict == Verdict.MISLEADING

        # But 49% = INCORRECT
        verdict = assign_verdict(
            0.49,
            [],
            tolerance_verified=0.02,
            tolerance_approx=0.10,
            tolerance_misleading=0.50,
        )
        assert verdict == Verdict.INCORRECT

    # ── Edge cases ────────────────────────────────────────────────────

    def test_boundary_values(self):
        """Test exact boundary values."""
        # Exactly at tolerance_verified (0.98 with default)
        assert assign_verdict(0.98, []) == Verdict.VERIFIED
        assert assign_verdict(0.979999, []) == Verdict.APPROXIMATELY_CORRECT

        # Exactly at tolerance_approx (0.90 with default)
        assert assign_verdict(0.90, []) == Verdict.APPROXIMATELY_CORRECT
        assert assign_verdict(0.899999, []) == Verdict.MISLEADING

        # Exactly at tolerance_misleading (0.75 with default)
        assert assign_verdict(0.75, []) == Verdict.MISLEADING
        assert assign_verdict(0.749999, []) == Verdict.INCORRECT

    def test_empty_flags_list(self):
        """Empty flags list behaves same as no flags."""
        verdict = assign_verdict(0.99, [])
        assert verdict == Verdict.VERIFIED
