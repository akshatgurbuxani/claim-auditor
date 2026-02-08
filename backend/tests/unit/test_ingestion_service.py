"""Unit tests for IngestionService — verifies idempotency and data mapping."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.clients.fmp_client import FMPClient, FMPTranscript
from app.models.company import CompanyModel
from app.models.financial_data import FinancialDataModel
from app.models.transcript import TranscriptModel
from app.repositories.company_repo import CompanyRepository
from app.repositories.financial_data_repo import FinancialDataRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.services.ingestion_service import IngestionService
from tests.fixtures import load_fixture


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_service(db) -> tuple[IngestionService, MagicMock]:
    """Create an IngestionService with a mocked FMPClient."""
    mock_fmp = MagicMock(spec=FMPClient)
    company_repo = CompanyRepository(db)
    transcript_repo = TranscriptRepository(db)
    financial_repo = FinancialDataRepository(db)
    service = IngestionService(mock_fmp, company_repo, transcript_repo, financial_repo)
    return service, mock_fmp


# ── Idempotency Tests ────────────────────────────────────────────────────


class TestIngestionIdempotency:
    """Verify that re-runs do NOT make unnecessary FMP API calls."""

    def test_skips_profile_fetch_when_company_exists(self, db, sample_company):
        """If AAPL already in DB, do NOT call get_company_profile."""
        service, mock_fmp = _make_service(db)

        # Mock transcript fetch to return None (no transcript available)
        mock_fmp.get_transcript.return_value = None

        service.ingest_all(tickers=["AAPL"], quarters=[(2025, 3)])

        # Profile should NOT be fetched — company already exists
        mock_fmp.get_company_profile.assert_not_called()

    def test_fetches_profile_for_new_company(self, db):
        """If company is NOT in DB, call get_company_profile."""
        service, mock_fmp = _make_service(db)

        mock_fmp.get_company_profile.return_value = {
            "companyName": "Microsoft Corp.",
            "sector": "Technology",
        }
        mock_fmp.get_transcript.return_value = None
        mock_fmp.get_income_statement.return_value = []
        mock_fmp.get_cash_flow_statement.return_value = []
        mock_fmp.get_balance_sheet.return_value = []

        service.ingest_all(tickers=["MSFT"], quarters=[(2025, 3)])

        mock_fmp.get_company_profile.assert_called_once_with("MSFT")

    def test_skips_transcript_fetch_when_exists(self, db, sample_company, sample_transcript):
        """If transcript for Q3 2025 already in DB, do NOT fetch from FMP."""
        service, mock_fmp = _make_service(db)

        service.ingest_all(tickers=["AAPL"], quarters=[(2025, 3)])

        mock_fmp.get_transcript.assert_not_called()

    def test_fetches_transcript_when_missing(self, db, sample_company):
        """If no transcript for Q2 2025, fetch from FMP."""
        service, mock_fmp = _make_service(db)

        mock_fmp.get_transcript.return_value = FMPTranscript(
            ticker="AAPL",
            quarter=2,
            year=2025,
            call_date=date(2025, 5, 1),
            content="Test transcript content...",
        )

        result = service.ingest_all(tickers=["AAPL"], quarters=[(2025, 2)])

        mock_fmp.get_transcript.assert_called_once_with("AAPL", 2, 2025)
        assert result["transcripts_fetched"] == 1

    def test_skips_financials_when_data_exists(self, db, sample_company, sample_financial_data):
        """If financial data rows exist for company, do NOT call any financial endpoints."""
        service, mock_fmp = _make_service(db)
        mock_fmp.get_transcript.return_value = None

        service.ingest_all(tickers=["AAPL"], quarters=[(2025, 3)])

        mock_fmp.get_income_statement.assert_not_called()
        mock_fmp.get_cash_flow_statement.assert_not_called()
        mock_fmp.get_balance_sheet.assert_not_called()

    def test_fetches_financials_when_empty(self, db, sample_company):
        """If NO financial data for company, call all three statement endpoints."""
        service, mock_fmp = _make_service(db)
        mock_fmp.get_transcript.return_value = None
        mock_fmp.get_income_statement.return_value = []
        mock_fmp.get_cash_flow_statement.return_value = []
        mock_fmp.get_balance_sheet.return_value = []

        service.ingest_all(tickers=["AAPL"], quarters=[(2025, 3)])

        mock_fmp.get_income_statement.assert_called_once()
        mock_fmp.get_cash_flow_statement.assert_called_once()
        mock_fmp.get_balance_sheet.assert_called_once()


# ── Period Parsing ───────────────────────────────────────────────────────


class TestPeriodParsing:
    """Test IngestionService._parse_period with real FMP-like entries."""

    def test_standard_quarter_stable_api(self):
        """Stable API uses 'fiscalYear' instead of 'calendarYear'."""
        entry = {"period": "Q3", "date": "2024-06-29", "fiscalYear": "2024"}
        q, y = IngestionService._parse_period(entry)
        assert q == 3
        assert y == 2024

    def test_legacy_calendar_year_still_works(self):
        """Old fixtures / cached data still use 'calendarYear'."""
        entry = {"period": "Q3", "date": "2024-06-29", "calendarYear": "2024"}
        q, y = IngestionService._parse_period(entry)
        assert q == 3
        assert y == 2024

    def test_fallback_to_date_year(self):
        entry = {"period": "Q1", "date": "2024-03-30", "fiscalYear": ""}
        q, y = IngestionService._parse_period(entry)
        assert q == 1
        assert y == 2024

    def test_no_period(self):
        entry = {"period": "", "date": "2024-06-29", "fiscalYear": "2024"}
        q, y = IngestionService._parse_period(entry)
        assert q == 0  # unrecognized period → skip

    def test_no_year_no_date(self):
        entry = {"period": "Q1", "date": "", "fiscalYear": ""}
        q, y = IngestionService._parse_period(entry)
        assert y == 0


# ── Financial Data Mapping ───────────────────────────────────────────────


class TestFinancialDataMapping:
    """Test that fixture data maps correctly through _ingest_financials."""

    def test_ingest_creates_financial_rows_from_fixtures(self, db, sample_company):
        """Use real fixture data to verify the field mapping is correct."""
        service, mock_fmp = _make_service(db)

        income = load_fixture("fmp_income_statement_AAPL.json")
        cashflow = load_fixture("fmp_cashflow_AAPL.json")
        balance = load_fixture("fmp_balance_sheet_AAPL.json")

        mock_fmp.get_income_statement.return_value = income
        mock_fmp.get_cash_flow_statement.return_value = cashflow
        mock_fmp.get_balance_sheet.return_value = balance
        mock_fmp.get_transcript.return_value = None

        result = service.ingest_all(tickers=["AAPL"], quarters=[(2024, 3)])

        # Should have created 1 financial data row
        assert result["financial_periods_fetched"] == 1

        # Verify the data was mapped correctly
        fin_repo = FinancialDataRepository(db)
        fin = fin_repo.get_for_quarter(sample_company.id, 2024, 3)
        assert fin is not None

        # Cross-check a few critical fields against the fixture
        assert fin.revenue == income[0]["revenue"]
        assert fin.eps_diluted == income[0]["epsDiluted"]
        assert fin.operating_cash_flow == cashflow[0]["operatingCashFlow"]
        assert fin.free_cash_flow == cashflow[0]["freeCashFlow"]
        assert fin.total_debt == balance[0]["totalDebt"]
        assert fin.shareholders_equity == balance[0]["totalStockholdersEquity"]
        assert fin.cash_and_equivalents == balance[0]["cashAndCashEquivalents"]


# ── Match Helper ─────────────────────────────────────────────────────────


class TestMatchHelper:
    """Test IngestionService._match that pairs statements by quarter."""

    def test_match_finds_correct_period(self):
        entries = [
            {"period": "Q1", "date": "2024-03-30", "fiscalYear": "2024"},
            {"period": "Q3", "date": "2024-06-29", "fiscalYear": "2024"},
        ]
        result = IngestionService._match(entries, 2024, 3)
        assert result is not None
        assert result["period"] == "Q3"

    def test_match_returns_none_when_missing(self):
        entries = [
            {"period": "Q1", "date": "2024-03-30", "fiscalYear": "2024"},
        ]
        result = IngestionService._match(entries, 2024, 3)
        assert result is None
