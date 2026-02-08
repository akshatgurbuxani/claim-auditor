"""Unit tests for DiscrepancyAnalyzer — pattern detection across quarters."""

from unittest.mock import MagicMock

import pytest

from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
from app.schemas.discrepancy import PatternType


def _mock_claim(
    metric="revenue",
    metric_type="absolute",
    stated_value=100.0,
    is_gaap=True,
    accuracy_score=0.95,
    actual_value=100.0,
    verdict="verified",
):
    """Build a mock claim with a mock verification."""
    claim = MagicMock()
    claim.metric = metric
    claim.metric_type = metric_type
    claim.stated_value = stated_value
    claim.is_gaap = is_gaap

    verification = MagicMock()
    verification.accuracy_score = accuracy_score
    verification.actual_value = actual_value
    verification.verdict = verdict
    claim.verification = verification

    return claim


class TestRoundingBias:
    def setup_method(self):
        self.analyzer = DiscrepancyAnalyzer()

    def test_detects_consistent_rounding_up(self):
        """If >70% of inexact claims round favorably, flag it."""
        claims_by_q = {
            "Q1 2024": [
                _mock_claim(stated_value=105, actual_value=100, accuracy_score=0.95),
                _mock_claim(stated_value=52, actual_value=50, accuracy_score=0.96),
            ],
            "Q2 2024": [
                _mock_claim(stated_value=110, actual_value=105, accuracy_score=0.95),
                _mock_claim(stated_value=55, actual_value=52, accuracy_score=0.94),
            ],
        }
        patterns = self.analyzer._detect_rounding_bias(1, claims_by_q)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.CONSISTENT_ROUNDING_UP

    def test_no_bias_when_balanced(self):
        """Roughly equal over/under rounding should NOT flag."""
        claims_by_q = {
            "Q1 2024": [
                _mock_claim(stated_value=105, actual_value=100, accuracy_score=0.95),
                _mock_claim(stated_value=48, actual_value=50, accuracy_score=0.96),
            ],
            "Q2 2024": [
                _mock_claim(stated_value=110, actual_value=105, accuracy_score=0.95),
                _mock_claim(stated_value=49, actual_value=52, accuracy_score=0.94),
            ],
        }
        patterns = self.analyzer._detect_rounding_bias(1, claims_by_q)
        assert len(patterns) == 0

    def test_no_bias_with_too_few_claims(self):
        """Need at least 4 inexact claims to detect a pattern."""
        claims_by_q = {
            "Q1 2024": [
                _mock_claim(stated_value=105, actual_value=100, accuracy_score=0.95),
            ],
        }
        patterns = self.analyzer._detect_rounding_bias(1, claims_by_q)
        assert len(patterns) == 0


class TestMetricSwitching:
    def setup_method(self):
        self.analyzer = DiscrepancyAnalyzer()

    def test_detects_switching_top_metric(self):
        """If the most-emphasized metric changes each quarter, flag it."""
        claims_by_q = {
            "Q1 2024": [
                _mock_claim(metric="revenue"),
                _mock_claim(metric="revenue"),
                _mock_claim(metric="eps"),
            ],
            "Q2 2024": [
                _mock_claim(metric="eps"),
                _mock_claim(metric="eps"),
                _mock_claim(metric="revenue"),
            ],
            "Q3 2024": [
                _mock_claim(metric="ebitda"),
                _mock_claim(metric="ebitda"),
                _mock_claim(metric="revenue"),
            ],
        }
        patterns = self.analyzer._detect_metric_switching(1, claims_by_q)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.METRIC_SWITCHING

    def test_no_switching_when_consistent(self):
        """Same top metric every quarter → no flag."""
        claims_by_q = {
            "Q1 2024": [_mock_claim(metric="revenue"), _mock_claim(metric="revenue")],
            "Q2 2024": [_mock_claim(metric="revenue"), _mock_claim(metric="eps")],
            "Q3 2024": [_mock_claim(metric="revenue"), _mock_claim(metric="eps")],
        }
        patterns = self.analyzer._detect_metric_switching(1, claims_by_q)
        assert len(patterns) == 0


class TestIncreasingInaccuracy:
    def setup_method(self):
        self.analyzer = DiscrepancyAnalyzer()

    def test_detects_declining_accuracy(self):
        """If average accuracy drops over 3+ quarters, flag it."""
        claims_by_q = {
            "Q1 2024": [_mock_claim(accuracy_score=0.98)],
            "Q2 2024": [_mock_claim(accuracy_score=0.95)],
            "Q3 2024": [_mock_claim(accuracy_score=0.90)],
        }
        patterns = self.analyzer._detect_increasing_inaccuracy(1, claims_by_q)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.INCREASING_INACCURACY

    def test_no_flag_when_accuracy_stable(self):
        """Stable accuracy → no flag."""
        claims_by_q = {
            "Q1 2024": [_mock_claim(accuracy_score=0.96)],
            "Q2 2024": [_mock_claim(accuracy_score=0.95)],
            "Q3 2024": [_mock_claim(accuracy_score=0.96)],
        }
        patterns = self.analyzer._detect_increasing_inaccuracy(1, claims_by_q)
        assert len(patterns) == 0


class TestGAAPShifting:
    def setup_method(self):
        self.analyzer = DiscrepancyAnalyzer()

    def test_detects_gaap_ratio_change(self):
        """If GAAP ratio changes by >30% across quarters, flag it."""
        claims_by_q = {
            "Q1 2024": [
                _mock_claim(is_gaap=True),
                _mock_claim(is_gaap=True),
            ],
            "Q2 2024": [
                _mock_claim(is_gaap=False),
                _mock_claim(is_gaap=False),
            ],
        }
        patterns = self.analyzer._detect_gaap_shifting(1, claims_by_q)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.GAAP_NONGAAP_SHIFTING

    def test_no_flag_when_ratio_stable(self):
        """Stable GAAP/non-GAAP mix → no flag."""
        claims_by_q = {
            "Q1 2024": [_mock_claim(is_gaap=True), _mock_claim(is_gaap=False)],
            "Q2 2024": [_mock_claim(is_gaap=True), _mock_claim(is_gaap=False)],
        }
        patterns = self.analyzer._detect_gaap_shifting(1, claims_by_q)
        assert len(patterns) == 0


class TestSelectiveEmphasis:
    def setup_method(self):
        self.analyzer = DiscrepancyAnalyzer()

    def test_detects_only_positive_growth_mentions(self):
        """If >90% of growth claims are positive across 2+ quarters, flag it."""
        claims_by_q = {
            "Q1 2024": [
                _mock_claim(metric_type="growth_rate", stated_value=10),
                _mock_claim(metric_type="growth_rate", stated_value=15),
                _mock_claim(metric_type="growth_rate", stated_value=8),
            ],
            "Q2 2024": [
                _mock_claim(metric_type="growth_rate", stated_value=12),
                _mock_claim(metric_type="growth_rate", stated_value=20),
                _mock_claim(metric_type="growth_rate", stated_value=5),
            ],
        }
        patterns = self.analyzer._detect_selective_emphasis(1, claims_by_q)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == PatternType.SELECTIVE_EMPHASIS

    def test_no_flag_when_negative_growth_mentioned(self):
        """If negative growth is mentioned, no selective emphasis flag."""
        claims_by_q = {
            "Q1 2024": [
                _mock_claim(metric_type="growth_rate", stated_value=10),
                _mock_claim(metric_type="growth_rate", stated_value=-5),
                _mock_claim(metric_type="growth_rate", stated_value=8),
            ],
            "Q2 2024": [
                _mock_claim(metric_type="growth_rate", stated_value=12),
                _mock_claim(metric_type="growth_rate", stated_value=-3),
                _mock_claim(metric_type="growth_rate", stated_value=5),
            ],
        }
        patterns = self.analyzer._detect_selective_emphasis(1, claims_by_q)
        assert len(patterns) == 0


class TestFullAnalysis:
    """Test the top-level analyze_company method."""

    def test_returns_all_pattern_types(self):
        analyzer = DiscrepancyAnalyzer()
        # Minimal input — just verify it runs without error
        result = analyzer.analyze_company(1, {})
        assert isinstance(result, list)
        assert len(result) == 0  # empty input → no patterns
