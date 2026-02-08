"""Maps natural-language metric names to structured financial data fields.

This is the bridge between what an executive *says* and what column in the
financial statements we should look at.
"""

from typing import Optional

from app.models.financial_data import FinancialDataModel


class MetricMapper:
    """Resolve a claim's metric name to an actual value from financial data."""

    # claim_metric → ORM attribute name (direct lookup)
    DIRECT: dict[str, str] = {
        "revenue": "revenue",
        "cost_of_revenue": "cost_of_revenue",
        "gross_profit": "gross_profit",
        "operating_income": "operating_income",
        "operating_expenses": "operating_expenses",
        "net_income": "net_income",
        "eps": "eps",
        "eps_diluted": "eps_diluted",
        "ebitda": "ebitda",
        "research_and_development": "research_and_development",
        "selling_general_admin": "selling_general_admin",
        "interest_expense": "interest_expense",
        "income_tax_expense": "income_tax_expense",
        "operating_cash_flow": "operating_cash_flow",
        "capital_expenditure": "capital_expenditure",
        "free_cash_flow": "free_cash_flow",
        "total_assets": "total_assets",
        "total_liabilities": "total_liabilities",
        "total_debt": "total_debt",
        "cash_and_equivalents": "cash_and_equivalents",
        "shareholders_equity": "shareholders_equity",
    }

    # Metrics where FMP stores the value as a negative cash outflow, but
    # executives always report as positive numbers.
    SIGN_NORMALIZE: set[str] = {"capital_expenditure"}

    # claim_metric → (numerator_field, denominator_field)  → result is a %
    DERIVED: dict[str, tuple[str, str]] = {
        "gross_margin": ("gross_profit", "revenue"),
        "operating_margin": ("operating_income", "revenue"),
        "net_margin": ("net_income", "revenue"),
    }

    # ── public API ───────────────────────────────────────────────────

    def can_resolve(self, metric: str) -> bool:
        return metric in self.DIRECT or metric in self.DERIVED

    def resolve(
        self, metric: str, data: FinancialDataModel
    ) -> Optional[float]:
        """Return the actual numeric value for *metric* from *data*.

        For derived metrics (margins) the result is a **percentage** (e.g. 46.2).
        Returns *None* when the required fields are missing or zero-denom.
        """
        if metric in self.DIRECT:
            val = getattr(data, self.DIRECT[metric], None)
            if val is not None and metric in self.SIGN_NORMALIZE:
                val = abs(val)
            return val

        if metric in self.DERIVED:
            num_field, den_field = self.DERIVED[metric]
            num = getattr(data, num_field, None)
            den = getattr(data, den_field, None)
            if num is not None and den is not None and den != 0:
                return (num / den) * 100
            return None

        return None
