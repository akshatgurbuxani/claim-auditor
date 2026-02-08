"""Extracts quantitative claims from earnings-call transcripts via LLM.

The system prompt is carefully crafted and is the core IP of the extraction.
"""

import logging
from typing import List

from app.clients.llm_client import LLMClient
from app.schemas.claim import ClaimCreate, ComparisonPeriod, MetricType

logger = logging.getLogger(__name__)

# ── Canonical metric name aliases ────────────────────────────────────────

_METRIC_ALIASES: dict[str, str] = {
    "total revenue": "revenue",
    "net revenue": "revenue",
    "net revenues": "revenue",
    "sales": "revenue",
    "net sales": "revenue",
    "top line": "revenue",
    "earnings per share": "eps",
    "diluted eps": "eps_diluted",
    "diluted earnings per share": "eps_diluted",
    "basic eps": "eps",
    "op income": "operating_income",
    "operating profit": "operating_income",
    "operating loss": "operating_income",
    "op margin": "operating_margin",
    "gross margin": "gross_margin",
    "gross profit margin": "gross_margin",
    "net margin": "net_margin",
    "profit margin": "net_margin",
    "fcf": "free_cash_flow",
    "capex": "capital_expenditure",
    "capital expenditures": "capital_expenditure",
    "r&d": "research_and_development",
    "research and development": "research_and_development",
    "sg&a": "selling_general_admin",
    "sga": "selling_general_admin",
    "cash": "cash_and_equivalents",
    "cash and cash equivalents": "cash_and_equivalents",
    "debt": "total_debt",
    "long-term debt": "total_debt",
    "stockholders equity": "shareholders_equity",
    "shareholders equity": "shareholders_equity",
    "total stockholders equity": "shareholders_equity",
}


class ClaimExtractor:
    """Two-step claim extraction: LLM → validate → deduplicate."""

    SYSTEM_PROMPT = '''You are a financial analyst AI that extracts quantitative claims from earnings call transcripts.

A "quantitative claim" is any statement by management that includes a specific number, percentage, or measurable comparison about the company's financial performance.

EXTRACT claims that include:
- Revenue figures or growth rates
- Earnings per share (EPS)
- Profit margins (gross, operating, net)
- Cash flow figures (operating cash flow, free cash flow)
- Growth rates (YoY, QoQ)
- EBITDA
- Expense figures (R&D, SG&A)
- Balance sheet items (debt, cash, assets)

DO NOT extract:
- Vague qualitative statements ("strong performance", "solid results")
- Forward-looking guidance without a specific number
- Analyst questions — only management/executive statements
- Non-financial operational metrics unless clearly tied to dollars/percentages
- Share count or buyback mentions unless tied to a dollar figure

For each claim, return a JSON array where every element has EXACTLY these fields:
{
  "speaker": "Full Name, Title",
  "speaker_role": "CEO" | "CFO" | "COO" | "Other",
  "claim_text": "exact verbatim quote from the transcript containing the number",
  "metric": "revenue | cost_of_revenue | gross_profit | gross_margin | operating_income | operating_margin | operating_expenses | net_income | net_margin | eps | eps_diluted | ebitda | research_and_development | selling_general_admin | interest_expense | income_tax_expense | operating_cash_flow | free_cash_flow | capital_expenditure | total_assets | total_liabilities | total_debt | cash_and_equivalents | shareholders_equity",
  "metric_type": "absolute | growth_rate | margin | ratio | change | per_share",
  "stated_value": <number — use 15 for 15%, not 0.15>,
  "unit": "usd | usd_millions | usd_billions | percent | basis_points | ratio",
  "comparison_period": "year_over_year | quarter_over_quarter | sequential | full_year | custom | none",
  "comparison_basis": "Q3 2025 vs Q3 2024" or null,
  "is_gaap": true | false,
  "segment": null or "segment name like Cloud, AWS, iPhone",
  "confidence": <float 0.0–1.0>,
  "context_snippet": "1–2 sentences of surrounding context"
}

RULES:
- stated_value: raw number (15 for "15%", 94.9 for "$94.9 billion")
- unit: must match the scale ("$94.9 billion" → stated_value=94.9, unit="usd_billions")
- is_gaap: false when they say "non-GAAP", "adjusted", "excluding items/charges"
- comparison_period: "year_over_year" for YoY, "quarter_over_quarter" for QoQ/sequential
- confidence: how certain you are this is a real quantitative claim (0.5 = uncertain, 1.0 = certain)
- Only extract from management speakers, not from analysts

Output ONLY the JSON array. No other text.'''

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def extract(
        self,
        transcript_text: str,
        ticker: str,
        quarter: int,
        year: int,
    ) -> List[ClaimCreate]:
        """Extract, validate, and deduplicate claims from a transcript."""
        raw_claims = self.llm.extract_claims(
            transcript_text=transcript_text,
            ticker=ticker,
            quarter=quarter,
            year=year,
            system_prompt=self.SYSTEM_PROMPT,
        )

        valid: list[ClaimCreate] = []
        for raw in raw_claims:
            try:
                claim = self._validate(raw)
                valid.append(claim)
            except Exception as exc:
                logger.warning("Skipping invalid claim: %s — %s", exc, raw.get("claim_text", "")[:80])

        deduped = self._deduplicate(valid)
        logger.info(
            "%s Q%d %d: extracted %d raw → %d valid → %d unique claims",
            ticker, quarter, year, len(raw_claims), len(valid), len(deduped),
        )
        return deduped

    # ── internal ─────────────────────────────────────────────────────

    def _validate(self, raw: dict) -> ClaimCreate:
        """Turn a raw LLM dict into a validated ClaimCreate."""
        raw["metric"] = self._normalize_metric(raw.get("metric", "unknown"))

        # Coerce enums gracefully
        try:
            raw["metric_type"] = MetricType(raw.get("metric_type", "absolute"))
        except ValueError:
            raw["metric_type"] = MetricType.ABSOLUTE

        try:
            raw["comparison_period"] = ComparisonPeriod(raw.get("comparison_period", "none"))
        except ValueError:
            raw["comparison_period"] = ComparisonPeriod.NONE

        # Ensure required fields
        raw.setdefault("speaker", "Unknown")
        raw.setdefault("claim_text", "")
        raw.setdefault("stated_value", 0)
        raw.setdefault("unit", "usd")
        raw.setdefault("is_gaap", True)
        raw.setdefault("confidence", 0.5)

        # transcript_id will be set by the service layer
        raw.setdefault("transcript_id", 0)

        return ClaimCreate(**raw)

    @staticmethod
    def _normalize_metric(metric: str) -> str:
        normalized = metric.lower().strip()
        return _METRIC_ALIASES.get(normalized, normalized)

    @staticmethod
    def _deduplicate(claims: list[ClaimCreate]) -> list[ClaimCreate]:
        seen: set[tuple] = set()
        out: list[ClaimCreate] = []
        for c in claims:
            key = (c.metric, c.stated_value, c.comparison_period, c.unit)
            if key not in seen:
                seen.add(key)
                out.append(c)
        return out
