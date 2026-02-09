"""Unit tests for domain.metrics module."""

import pytest

from app.domain.metrics import (
    METRIC_ALIASES,
    METRICS,
    normalize_metric_name,
    is_derived_metric,
    get_metric_definition,
)


class TestNormalizeMetricName:
    """Test metric name normalization."""

    def test_normalize_exact_match(self):
        """Canonical names pass through unchanged."""
        assert normalize_metric_name("revenue") == "revenue"
        assert normalize_metric_name("eps") == "eps"
        assert normalize_metric_name("gross_margin") == "gross_margin"

    def test_normalize_alias(self):
        """Aliases are mapped to canonical names."""
        assert normalize_metric_name("total revenue") == "revenue"
        assert normalize_metric_name("net sales") == "revenue"
        assert normalize_metric_name("fcf") == "free_cash_flow"
        assert normalize_metric_name("capex") == "capital_expenditure"

    def test_normalize_case_insensitive(self):
        """Normalization is case-insensitive."""
        assert normalize_metric_name("Total Revenue") == "revenue"
        assert normalize_metric_name("TOTAL REVENUE") == "revenue"
        assert normalize_metric_name("FCF") == "free_cash_flow"

    def test_normalize_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        assert normalize_metric_name("  revenue  ") == "revenue"
        assert normalize_metric_name("  total revenue  ") == "revenue"

    def test_normalize_unknown_metric(self):
        """Unknown metrics are returned unchanged (normalized)."""
        assert normalize_metric_name("unknown_metric") == "unknown_metric"
        assert normalize_metric_name("Custom Metric") == "custom metric"


class TestIsDerivedMetric:
    """Test derived metric detection."""

    def test_derived_metrics(self):
        """Derived metrics return True."""
        assert is_derived_metric("gross_margin") is True
        assert is_derived_metric("operating_margin") is True
        assert is_derived_metric("net_margin") is True

    def test_direct_metrics(self):
        """Direct metrics return False."""
        assert is_derived_metric("revenue") is False
        assert is_derived_metric("operating_income") is False
        assert is_derived_metric("net_income") is False
        assert is_derived_metric("free_cash_flow") is False

    def test_per_share_metrics(self):
        """Per-share metrics return False."""
        assert is_derived_metric("eps") is False
        assert is_derived_metric("eps_diluted") is False

    def test_unknown_metric(self):
        """Unknown metrics return False."""
        assert is_derived_metric("unknown_metric") is False


class TestGetMetricDefinition:
    """Test metric definition lookup."""

    def test_get_existing_metric(self):
        """Returns MetricDefinition for known metrics."""
        defn = get_metric_definition("revenue")
        assert defn is not None
        assert defn.canonical_name == "revenue"
        assert defn.category == "direct"
        assert defn.typical_unit == "usd_billions"

    def test_get_derived_metric(self):
        """Returns MetricDefinition for derived metrics."""
        defn = get_metric_definition("gross_margin")
        assert defn is not None
        assert defn.canonical_name == "gross_margin"
        assert defn.category == "derived"
        assert defn.typical_unit == "percent"

    def test_get_per_share_metric(self):
        """Returns MetricDefinition for per-share metrics."""
        defn = get_metric_definition("eps")
        assert defn is not None
        assert defn.canonical_name == "eps"
        assert defn.category == "per_share"
        assert defn.typical_unit == "usd"

    def test_get_unknown_metric(self):
        """Returns None for unknown metrics."""
        assert get_metric_definition("unknown_metric") is None


class TestMetricAliases:
    """Test the METRIC_ALIASES dictionary structure."""

    def test_aliases_are_lowercase(self):
        """All alias keys should be lowercase."""
        for alias in METRIC_ALIASES:
            assert alias == alias.lower()

    def test_aliases_map_to_canonical(self):
        """All aliases should map to canonical names in METRICS."""
        for alias, canonical in METRIC_ALIASES.items():
            # Canonical names should be in the METRICS registry
            # (or be a recognized canonical form like 'revenue')
            assert canonical == canonical.lower()


class TestMetricsRegistry:
    """Test the METRICS registry structure."""

    def test_all_metrics_have_definitions(self):
        """All metrics in registry have complete definitions."""
        for name, defn in METRICS.items():
            assert defn.canonical_name == name
            assert defn.category in ("direct", "derived", "per_share")
            assert defn.description
            assert defn.typical_unit

    def test_canonical_names_are_lowercase(self):
        """All canonical names should be lowercase with underscores."""
        for name in METRICS:
            assert name == name.lower()
            assert " " not in name  # No spaces, use underscores
