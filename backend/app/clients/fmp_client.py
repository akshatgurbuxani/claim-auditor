"""Client for the Financial Modeling Prep (FMP) *stable* API.

Handles transcript fetching, income statements, cash flows, and balance sheets.
All data is returned as plain dicts/dataclasses so the caller can map to ORM models.

NOTE: FMP deprecated /api/v3 in late 2025.  The /stable/ endpoints use query-param
``symbol=TICKER`` instead of path-based ``/{TICKER}``.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.clients.base_client import BaseHTTPClient

logger = logging.getLogger(__name__)


@dataclass
class FMPTranscript:
    """Cleaned transcript from FMP."""
    ticker: str
    quarter: int
    year: int
    call_date: date
    content: str


class FMPClient(BaseHTTPClient):
    """Financial Modeling Prep API client (stable endpoint).

    Docs: https://site.financialmodelingprep.com/developer/docs
    """

    def __init__(self, api_key: str, cache_dir: Optional[Path] = None):
        super().__init__(
            base_url="https://financialmodelingprep.com/stable",
            api_key=api_key,
            cache_dir=cache_dir,
        )

    # ── Transcripts ──────────────────────────────────────────────────

    def get_transcript(
        self, ticker: str, quarter: int, year: int
    ) -> Optional[FMPTranscript]:
        """Fetch a single earnings-call transcript.

        Returns *None* when FMP has no transcript for that quarter or
        when the endpoint is restricted on the current plan.
        """
        try:
            data = self._get(
                "earning_call_transcript",
                params={"symbol": ticker.upper(), "quarter": quarter, "year": year},
            )
        except Exception as exc:
            logger.warning("FMP transcript fetch failed for %s Q%d %d: %s", ticker, quarter, year, exc)
            return None

        # Handle string error responses (e.g. "Restricted Endpoint: ...")
        if isinstance(data, str):
            logger.warning("FMP transcript restricted for %s Q%d %d: %s", ticker, quarter, year, data[:120])
            return None

        if not data:
            return None

        entry = data[0] if isinstance(data, list) else data
        raw_date = entry.get("date", "")

        try:
            call_date = datetime.fromisoformat(raw_date.replace(" ", "T").split("+")[0]).date()
        except (ValueError, AttributeError):
            call_date = date.today()

        content = entry.get("content", "")
        if not content:
            return None

        return FMPTranscript(
            ticker=ticker.upper(),
            quarter=quarter,
            year=year,
            call_date=call_date,
            content=content,
        )

    # ── Financial Statements ─────────────────────────────────────────

    def get_income_statement(
        self, ticker: str, *, period: str = "quarter", limit: int = 12
    ) -> List[Dict[str, Any]]:
        try:
            return self._get(
                "income-statement",
                params={"symbol": ticker.upper(), "period": period, "limit": limit},
            )
        except Exception as exc:
            logger.warning("FMP income statement fetch failed for %s: %s", ticker, exc)
            return []

    def get_cash_flow_statement(
        self, ticker: str, *, period: str = "quarter", limit: int = 12
    ) -> List[Dict[str, Any]]:
        try:
            return self._get(
                "cash-flow-statement",
                params={"symbol": ticker.upper(), "period": period, "limit": limit},
            )
        except Exception as exc:
            logger.warning("FMP cash flow fetch failed for %s: %s", ticker, exc)
            return []

    def get_balance_sheet(
        self, ticker: str, *, period: str = "quarter", limit: int = 12
    ) -> List[Dict[str, Any]]:
        try:
            return self._get(
                "balance-sheet-statement",
                params={"symbol": ticker.upper(), "period": period, "limit": limit},
            )
        except Exception as exc:
            logger.warning("FMP balance sheet fetch failed for %s: %s", ticker, exc)
            return []

    def get_company_profile(self, ticker: str) -> Dict[str, Any]:
        """Company name, sector, etc."""
        try:
            data = self._get("profile", params={"symbol": ticker.upper()})
            return data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
        except Exception as exc:
            logger.warning("FMP profile fetch failed for %s: %s", ticker, exc)
            return {}
