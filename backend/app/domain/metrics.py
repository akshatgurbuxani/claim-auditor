"""Domain model for financial metrics.

This is the **single source of truth** for:
- Canonical metric names
- Metric aliases (normalization)
- Metric categories (derived vs. direct)

Usage:
    from app.domain.metrics import normalize_metric_name, is_derived_metric

    canonical = normalize_metric_name("Total Revenue")  # -> "revenue"
    is_calc = is_derived_metric("gross_margin")  # -> True
"""

from dataclasses import dataclass
from typing import Dict, Optional


# ══════════════════════════════════════════════════════════════════════════
# METRIC ALIASES (for normalization)
# ══════════════════════════════════════════════════════════════════════════

METRIC_ALIASES: Dict[str, str] = {
    # Revenue
    "total revenue": "revenue",
    "net revenue": "revenue",
    "net revenues": "revenue",
    "sales": "revenue",
    "net sales": "revenue",
    "top line": "revenue",
    # Earnings
    "earnings per share": "eps",
    "diluted eps": "eps_diluted",
    "diluted earnings per share": "eps_diluted",
    "basic eps": "eps",
    # Operating
    "op income": "operating_income",
    "operating profit": "operating_income",
    "operating loss": "operating_income",
    "op margin": "operating_margin",
    # Margins
    "gross margin": "gross_margin",
    "gross profit margin": "gross_margin",
    "net margin": "net_margin",
    "profit margin": "net_margin",
    # Cash flow
    "fcf": "free_cash_flow",
    # CapEx
    "capex": "capital_expenditure",
    "capital expenditures": "capital_expenditure",
    # R&D
    "r&d": "research_and_development",
    "research and development": "research_and_development",
    # SG&A
    "sg&a": "selling_general_admin",
    "sga": "selling_general_admin",
    # Balance sheet
    "cash": "cash_and_equivalents",
    "cash and cash equivalents": "cash_and_equivalents",
    "debt": "total_debt",
    "long-term debt": "total_debt",
    "stockholders equity": "shareholders_equity",
    "shareholders equity": "shareholders_equity",
    "total stockholders equity": "shareholders_equity",
}


# ══════════════════════════════════════════════════════════════════════════
# METRIC DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class MetricDefinition:
    """Metadata about a financial metric."""

    canonical_name: str
    category: str  # "direct", "derived", "per_share"
    description: str
    typical_unit: str


# Registry of all known metrics
METRICS: Dict[str, MetricDefinition] = {
    # ── Direct metrics (from financial statements) ────────────────────
    "revenue": MetricDefinition(
        canonical_name="revenue",
        category="direct",
        description="Total revenue from income statement",
        typical_unit="usd_billions",
    ),
    "cost_of_revenue": MetricDefinition(
        canonical_name="cost_of_revenue",
        category="direct",
        description="Cost of goods sold",
        typical_unit="usd_billions",
    ),
    "gross_profit": MetricDefinition(
        canonical_name="gross_profit",
        category="direct",
        description="Revenue - cost_of_revenue",
        typical_unit="usd_billions",
    ),
    "operating_income": MetricDefinition(
        canonical_name="operating_income",
        category="direct",
        description="Operating profit (EBIT)",
        typical_unit="usd_billions",
    ),
    "net_income": MetricDefinition(
        canonical_name="net_income",
        category="direct",
        description="Net profit after tax",
        typical_unit="usd_billions",
    ),
    "eps": MetricDefinition(
        canonical_name="eps",
        category="per_share",
        description="Basic earnings per share",
        typical_unit="usd",
    ),
    "eps_diluted": MetricDefinition(
        canonical_name="eps_diluted",
        category="per_share",
        description="Diluted earnings per share",
        typical_unit="usd",
    ),
    "operating_cash_flow": MetricDefinition(
        canonical_name="operating_cash_flow",
        category="direct",
        description="Cash from operations",
        typical_unit="usd_billions",
    ),
    "free_cash_flow": MetricDefinition(
        canonical_name="free_cash_flow",
        category="direct",
        description="Operating cash flow - CapEx",
        typical_unit="usd_billions",
    ),
    "capital_expenditure": MetricDefinition(
        canonical_name="capital_expenditure",
        category="direct",
        description="Capital investments (CapEx)",
        typical_unit="usd_billions",
    ),
    # ── Derived metrics (calculated from other metrics) ───────────────
    "gross_margin": MetricDefinition(
        canonical_name="gross_margin",
        category="derived",
        description="Gross profit / revenue * 100",
        typical_unit="percent",
    ),
    "operating_margin": MetricDefinition(
        canonical_name="operating_margin",
        category="derived",
        description="Operating income / revenue * 100",
        typical_unit="percent",
    ),
    "net_margin": MetricDefinition(
        canonical_name="net_margin",
        category="derived",
        description="Net income / revenue * 100",
        typical_unit="percent",
    ),
}


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════


def normalize_metric_name(raw: str) -> str:
    """Normalize a metric name to its canonical form.

    Examples:
        >>> normalize_metric_name("Total Revenue")
        'revenue'
        >>> normalize_metric_name("FCF")
        'free_cash_flow'
        >>> normalize_metric_name("unknown_metric")
        'unknown_metric'
    """
    normalized = raw.lower().strip()
    return METRIC_ALIASES.get(normalized, normalized)


def is_derived_metric(metric: str) -> bool:
    """Check if a metric is computed (not directly in financial data).

    Derived metrics are calculated from other metrics (e.g., margins).

    Examples:
        >>> is_derived_metric("gross_margin")
        True
        >>> is_derived_metric("revenue")
        False
    """
    defn = METRICS.get(metric)
    return defn.category == "derived" if defn else False


def get_metric_definition(metric: str) -> Optional[MetricDefinition]:
    """Look up metadata for a metric.

    Returns:
        MetricDefinition if metric exists, None otherwise

    Examples:
        >>> defn = get_metric_definition("revenue")
        >>> defn.typical_unit
        'usd_billions'
    """
    return METRICS.get(metric)
