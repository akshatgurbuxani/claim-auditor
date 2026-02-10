"""Orchestrates ingestion of transcripts and financial data from FMP."""

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.clients.fmp_client import FMPClient, FMPTranscript
from app.config import Settings
from app.models.financial_data import FinancialDataModel
from app.models.transcript import TranscriptModel
from app.repositories.company_repo import CompanyRepository
from app.repositories.financial_data_repo import FinancialDataRepository
from app.repositories.transcript_repo import TranscriptRepository

logger = logging.getLogger(__name__)


class IngestionService:
    """Fetches transcripts + financials from FMP and stores them.

    Fully idempotent — safe to re-run.

    Three-tier transcript fallback strategy:
    1. Fetch from FMP API
    2. Load from local file in ``transcript_dir`` ({TICKER}_Q{quarter}_{year}.txt)
    3. Generate with LLM using financial data and save to ``transcript_dir``
    """

    def __init__(
        self,
        db: Session,
        fmp_client: FMPClient,
        company_repo: CompanyRepository,
        transcript_repo: TranscriptRepository,
        financial_repo: FinancialDataRepository,
        transcript_dir: Optional[Path] = None,
        settings: Optional[Settings] = None,
    ):
        self.db = db
        self.fmp = fmp_client
        self.companies = company_repo
        self.transcripts = transcript_repo
        self.financials = financial_repo
        self._transcript_dir = transcript_dir
        self._settings = settings or Settings()

        # Initialize Anthropic client for LLM-based transcript generation
        self._anthropic_client = None
        if self._settings.anthropic_api_key:
            self._anthropic_client = Anthropic(api_key=self._settings.anthropic_api_key)

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
                self.db.commit()  # Commit per company for atomicity
                logger.info("Successfully committed data for %s", ticker)
            except Exception as exc:
                self.db.rollback()  # Rollback failed company
                logger.exception("Error ingesting %s (rolled back): %s", ticker, exc)
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

        # 2. Financial data — fetch heavy structured data FIRST (needed for LLM generation)
        if self.financials.count_for_company(company.id) > 0:
            logger.info("  Financial data already exists, skipping FMP fetch")
        else:
            self._ingest_financials(company, summary)

        # 3. Transcripts — three-tier fallback: FMP → local file → LLM generation
        # NOTE: This step comes AFTER financial data so LLM generation can use DB data
        for year, quarter in quarters:
            existing = self.transcripts.get_for_quarter(company.id, year, quarter)
            if existing:
                summary["transcripts_skipped"] += 1
                continue

            # Tier 1: Try FMP API
            transcript = self.fmp.get_transcript(ticker, quarter, year)

            # Tier 2: Fall back to local file
            if transcript is None:
                transcript = self._load_local_transcript(ticker, quarter, year)

            # Tier 3: Generate with LLM using financial data from DB
            if transcript is None:
                transcript = self._generate_transcript_with_llm(
                    company, ticker, quarter, year
                )
                if transcript:
                    # Save generated transcript to file for future use
                    self._save_transcript_to_file(transcript, ticker, quarter, year)

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

    def _ingest_financials(self, company, summary: dict) -> None:
        """Fetch income, cash-flow, balance-sheet and merge by period."""
        income = self.fmp.get_income_statement(company.ticker, limit=5)
        cashflow = self.fmp.get_cash_flow_statement(company.ticker, limit=5)
        balance = self.fmp.get_balance_sheet(company.ticker, limit=5)

        if not income:
            logger.warning(f"No income statement data for {company.ticker}")
            return

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
        if not entries:
            return None
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

    def _generate_transcript_with_llm(
        self, company, ticker: str, quarter: int, year: int
    ) -> Optional[FMPTranscript]:
        """Generate a transcript using LLM based on financial data.

        This is the third fallback tier when FMP API and local files are unavailable.
        Generates a realistic earnings call transcript based on structured financial
        data and saves it to the transcript directory for future use.

        Returns None if:
        - Anthropic client is not configured
        - Financial data is not available for the quarter
        - LLM generation fails
        """
        if not self._anthropic_client:
            logger.debug("  Anthropic client not configured, skipping LLM generation")
            return None

        # Get financial data for this quarter
        financial_data = self.financials.get_for_quarter(company.id, year, quarter)
        if not financial_data:
            logger.debug(
                "  No financial data for Q%d %d, cannot generate transcript", quarter, year
            )
            return None

        logger.info("  Generating transcript with LLM for Q%d %d", quarter, year)

        try:
            # Build financial data context
            financial_context = self._build_financial_context(
                company, financial_data, quarter, year
            )

            # Call Claude API to generate transcript
            prompt = self._build_transcript_generation_prompt(financial_context)
            response = self._anthropic_client.messages.create(
                model=self._settings.claude_model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract generated transcript
            generated_text = response.content[0].text.strip()
            if not generated_text:
                logger.warning("  LLM returned empty transcript")
                return None

            logger.info("  Successfully generated transcript with LLM (%d chars)", len(generated_text))
            return FMPTranscript(
                ticker=ticker.upper(),
                quarter=quarter,
                year=year,
                call_date=date.today(),
                content=generated_text,
            )

        except Exception as exc:
            logger.exception("  Failed to generate transcript with LLM: %s", exc)
            return None

    def _build_financial_context(
        self, company, financial_data: FinancialDataModel, quarter: int, year: int
    ) -> str:
        """Build a context string with financial data for LLM prompt."""

        def format_billions(value: Optional[float]) -> str:
            """Format a value in billions with proper formatting."""
            if value is None:
                return "N/A"
            return f"${value / 1e9:.3f}B"

        def format_currency(value: Optional[float]) -> str:
            """Format a currency value."""
            if value is None:
                return "N/A"
            return f"${value:.2f}"

        def format_percent(value: Optional[float]) -> str:
            """Format a percentage."""
            if value is None:
                return "N/A"
            return f"{value:.1f}%"

        # Calculate margins if possible
        gross_margin = None
        operating_margin = None
        if financial_data.revenue and financial_data.revenue > 0:
            if financial_data.gross_profit:
                gross_margin = (financial_data.gross_profit / financial_data.revenue) * 100
            if financial_data.operating_income:
                operating_margin = (financial_data.operating_income / financial_data.revenue) * 100

        context = f"""Company: {company.name} ({company.ticker})
Period: Q{quarter} {year}
Sector: {company.sector}

Financial Metrics:
- Revenue: {format_billions(financial_data.revenue)}
- Cost of Revenue: {format_billions(financial_data.cost_of_revenue)}
- Gross Profit: {format_billions(financial_data.gross_profit)}
- Gross Margin: {format_percent(gross_margin)}
- Operating Income: {format_billions(financial_data.operating_income)}
- Operating Margin: {format_percent(operating_margin)}
- Net Income: {format_billions(financial_data.net_income)}
- EPS (Diluted): {format_currency(financial_data.eps_diluted)}
- Operating Cash Flow: {format_billions(financial_data.operating_cash_flow)}
- Free Cash Flow: {format_billions(financial_data.free_cash_flow)}
- Total Assets: {format_billions(financial_data.total_assets)}
- Total Debt: {format_billions(financial_data.total_debt)}
- Cash and Equivalents: {format_billions(financial_data.cash_and_equivalents)}
"""
        return context

    def _build_transcript_generation_prompt(self, financial_context: str) -> str:
        """Build the prompt for LLM transcript generation."""
        return f"""Generate a realistic earnings call transcript based on the following financial data.

{financial_context}

Generate a realistic earnings call transcript that includes:
1. A header with company name, quarter, year, and date
2. CEO opening remarks discussing the quarter's results and key highlights
3. CFO presentation with specific financial metrics (revenue, EPS, margins, cash flow)
4. 2-3 analyst Q&A exchanges where analysts ask about the results

Requirements:
- Use the EXACT financial figures provided above
- Make the tone professional and realistic (like an actual earnings call)
- Include specific executives by typical role (CEO, CFO, etc.)
- Keep it concise (aim for 1500-2000 characters)
- Reference the actual numbers multiple times in different ways (e.g., "$X billion revenue", "revenue of $X billion", etc.)
- Make it sound natural with some variation in phrasing

Do NOT include any preamble, explanation, or meta-commentary. Start directly with the transcript header."""

    def _save_transcript_to_file(
        self, transcript: FMPTranscript, ticker: str, quarter: int, year: int
    ) -> None:
        """Save a generated transcript to the local file system.

        Saves to: {transcript_dir}/{TICKER}_Q{quarter}_{year}.txt
        """
        if not self._transcript_dir:
            logger.debug("  Transcript directory not set, skipping file save")
            return

        try:
            # Ensure directory exists
            self._transcript_dir.mkdir(parents=True, exist_ok=True)

            # Write transcript to file
            path = self._transcript_dir / f"{ticker.upper()}_Q{quarter}_{year}.txt"
            path.write_text(transcript.content, encoding="utf-8")
            logger.info("  Saved generated transcript to %s", path.name)

        except Exception as exc:
            logger.warning("  Failed to save transcript to file: %s", exc)
