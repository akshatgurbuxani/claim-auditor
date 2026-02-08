"""Orchestrates ingestion of transcripts and financial data from FMP."""

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.clients.fmp_client import FMPClient, FMPTranscript
from app.models.financial_data import FinancialDataModel
from app.models.transcript import TranscriptModel
from app.repositories.company_repo import CompanyRepository
from app.repositories.financial_data_repo import FinancialDataRepository
from app.repositories.transcript_repo import TranscriptRepository

logger = logging.getLogger(__name__)


class IngestionService:
    """Fetches transcripts + financials from FMP and stores them.

    Fully idempotent — safe to re-run.

    If ``transcript_dir`` is provided, local ``.txt`` files are used as a
    fallback when the FMP transcript endpoint is unavailable (e.g. restricted
    on the current plan).  Expected filename pattern::

        {TICKER}_Q{quarter}_{year}.txt
    """

    def __init__(
        self,
        fmp_client: FMPClient,
        company_repo: CompanyRepository,
        transcript_repo: TranscriptRepository,
        financial_repo: FinancialDataRepository,
        transcript_dir: Optional[Path] = None,
    ):
        self.fmp = fmp_client
        self.companies = company_repo
        self.transcripts = transcript_repo
        self.financials = financial_repo
        self._transcript_dir = transcript_dir

    def ingest_all(
        self,
        tickers: List[str],
        quarters: List[Tuple[int, int]],
    ) -> Dict[str, Any]:
        """Run full ingestion pipeline for all target companies + quarters."""
        summary: Dict[str, int] = {
            "companies": 0,
            "transcripts_fetched": 0,
            "transcripts_skipped": 0,
            "financial_periods_fetched": 0,
            "errors": 0,
        }

        for ticker in tickers:
            try:
                self._ingest_company(ticker, quarters, summary)
            except Exception as exc:
                logger.exception("Error ingesting %s: %s", ticker, exc)
                summary["errors"] += 1

        return summary

    def _ingest_company(
        self,
        ticker: str,
        quarters: list[tuple[int, int]],
        summary: dict,
    ) -> None:
        # 1. Get or create company — only call FMP profile if new
        company = self.companies.get_by_ticker(ticker)
        if company is None:
            profile = self.fmp.get_company_profile(ticker)
            company = self.companies.get_or_create(
                ticker=ticker,
                name=profile.get("companyName", ticker),
                sector=profile.get("sector", "Unknown"),
            )
        summary["companies"] += 1
        logger.info("Processing %s (%s)", company.ticker, company.name)

        # 2. Transcripts — only fetch from FMP if not already in DB
        for year, quarter in quarters:
            existing = self.transcripts.get_for_quarter(company.id, year, quarter)
            if existing:
                summary["transcripts_skipped"] += 1
                continue

            # Try FMP first, then fall back to local file
            transcript = self.fmp.get_transcript(ticker, quarter, year)
            if transcript is None:
                transcript = self._load_local_transcript(ticker, quarter, year)

            if transcript:
                self.transcripts.create(TranscriptModel(
                    company_id=company.id,
                    quarter=quarter,
                    year=year,
                    call_date=transcript.call_date,
                    full_text=transcript.content,
                ))
                summary["transcripts_fetched"] += 1
                logger.info("  Fetched transcript Q%d %d", quarter, year)
            else:
                logger.warning("  No transcript for Q%d %d", quarter, year)

        # 3. Financial data — skip entirely if we already have rows for this company
        if self.financials.count_for_company(company.id) > 0:
            logger.info("  Financial data already exists, skipping FMP fetch")
        else:
            self._ingest_financials(company, summary)

    def _ingest_financials(self, company, summary: dict) -> None:
        """Fetch income, cash-flow, balance-sheet and merge by period."""
        income = self.fmp.get_income_statement(company.ticker, limit=5)
        cashflow = self.fmp.get_cash_flow_statement(company.ticker, limit=5)
        balance = self.fmp.get_balance_sheet(company.ticker, limit=5)

        for entry in income:
            q, y = self._parse_period(entry)
            if q == 0 or y == 0:
                continue

            if self.financials.get_for_quarter(company.id, y, q):
                continue

            cf = self._match(cashflow, y, q)
            bs = self._match(balance, y, q)

            self.financials.create(FinancialDataModel(
                company_id=company.id,
                period=f"Q{q}",
                year=y,
                quarter=q,
                revenue=entry.get("revenue"),
                cost_of_revenue=entry.get("costOfRevenue"),
                gross_profit=entry.get("grossProfit"),
                operating_income=entry.get("operatingIncome"),
                operating_expenses=entry.get("operatingExpenses"),
                net_income=entry.get("netIncome"),
                eps=entry.get("eps"),
                # Stable API: "epsDiluted"; legacy v3: "epsdiluted"
                eps_diluted=entry.get("epsDiluted") or entry.get("epsdiluted"),
                ebitda=entry.get("ebitda"),
                research_and_development=entry.get("researchAndDevelopmentExpenses"),
                selling_general_admin=entry.get("sellingGeneralAndAdministrativeExpenses"),
                interest_expense=entry.get("interestExpense"),
                income_tax_expense=entry.get("incomeTaxExpense"),
                operating_cash_flow=cf.get("operatingCashFlow") if cf else None,
                capital_expenditure=cf.get("capitalExpenditure") if cf else None,
                free_cash_flow=cf.get("freeCashFlow") if cf else None,
                total_assets=bs.get("totalAssets") if bs else None,
                total_liabilities=bs.get("totalLiabilities") if bs else None,
                total_debt=bs.get("totalDebt") if bs else None,
                cash_and_equivalents=bs.get("cashAndCashEquivalents") if bs else None,
                shareholders_equity=bs.get("totalStockholdersEquity") if bs else None,
            ))
            summary["financial_periods_fetched"] += 1

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_period(entry: dict) -> Tuple[int, int]:
        """Return (quarter, year) from an FMP statement entry.

        The stable API uses ``fiscalYear`` (v3 used ``calendarYear``).
        We try both for backward compatibility with cached/fixture data.
        """
        period = entry.get("period", "")
        date_str = entry.get("date", "")
        # Stable API: fiscalYear;  Legacy/fixture: calendarYear
        year = int(entry.get("fiscalYear", 0) or entry.get("calendarYear", 0) or 0)
        if not year and date_str:
            try:
                year = int(date_str[:4])
            except (ValueError, IndexError):
                year = 0
        quarter = int(period[1]) if period.startswith("Q") and len(period) >= 2 else 0
        return quarter, year

    @staticmethod
    def _match(entries: List[Dict], year: int, quarter: int) -> Optional[Dict]:
        for e in entries:
            q, y = IngestionService._parse_period(e)
            if q == quarter and y == year:
                return e
        return None

    def _load_local_transcript(
        self, ticker: str, quarter: int, year: int
    ) -> Optional[FMPTranscript]:
        """Load a transcript from a local .txt file as a fallback.

        Looks for ``{transcript_dir}/{TICKER}_Q{quarter}_{year}.txt``.
        Returns None if the directory is not set or the file doesn't exist.
        """
        if not self._transcript_dir:
            return None

        path = self._transcript_dir / f"{ticker.upper()}_Q{quarter}_{year}.txt"
        if not path.exists():
            return None

        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return None

        logger.info("  Loaded local transcript %s", path.name)
        return FMPTranscript(
            ticker=ticker.upper(),
            quarter=quarter,
            year=year,
            call_date=date.today(),
            content=content,
        )
