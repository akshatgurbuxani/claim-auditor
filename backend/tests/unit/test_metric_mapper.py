"""Unit tests for MetricMapper — written FIRST (TDD)."""

import pytest

from app.engines.metric_mapper import MetricMapper


class TestMetricMapperCanResolve:
    def setup_method(self):
        self.mapper = MetricMapper()

    def test_direct_metrics(self):
        for m in ("revenue", "net_income", "eps", "eps_diluted", "ebitda", "free_cash_flow"):
            assert self.mapper.can_resolve(m), f"{m} should be resolvable"

    def test_derived_metrics(self):
        for m in ("gross_margin", "operating_margin", "net_margin"):
            assert self.mapper.can_resolve(m), f"{m} should be resolvable"

    def test_unknown_metric(self):
        assert not self.mapper.can_resolve("subscriber_count")
        assert not self.mapper.can_resolve("daily_active_users")
        assert not self.mapper.can_resolve("")


class TestMetricMapperResolve:
    def setup_method(self):
        self.mapper = MetricMapper()

    def test_revenue(self, sample_financial_data):
        q3_2025, _ = sample_financial_data
        assert self.mapper.resolve("revenue", q3_2025) == 94_930_000_000

    def test_eps(self, sample_financial_data):
        q3_2025, _ = sample_financial_data
        assert self.mapper.resolve("eps", q3_2025) == 1.46

    def test_net_income(self, sample_financial_data):
        q3_2025, _ = sample_financial_data
        assert self.mapper.resolve("net_income", q3_2025) == 23_636_000_000

    def test_gross_margin_derived(self, sample_financial_data):
        q3_2025, _ = sample_financial_data
        result = self.mapper.resolve("gross_margin", q3_2025)
        assert result is not None
        # 43_879_000_000 / 94_930_000_000 * 100 ≈ 46.22%
        assert abs(result - 46.22) < 0.1

    def test_operating_margin_derived(self, sample_financial_data):
        q3_2025, _ = sample_financial_data
        result = self.mapper.resolve("operating_margin", q3_2025)
        assert result is not None
        # 29_590_000_000 / 94_930_000_000 * 100 ≈ 31.17%
        assert abs(result - 31.17) < 0.1

    def test_unknown_returns_none(self, sample_financial_data):
        q3_2025, _ = sample_financial_data
        assert self.mapper.resolve("unknown", q3_2025) is None

    def test_derived_with_zero_denominator(self, db, sample_company):
        """Margin with zero revenue should return None."""
        from app.models.financial_data import FinancialDataModel
        data = FinancialDataModel(
            company_id=sample_company.id,
            period="Q1", year=2025, quarter=1,
            revenue=0, gross_profit=100,
        )
        db.add(data)
        db.commit()
        assert self.mapper.resolve("gross_margin", data) is None
