"""Integration tests for the FMP stable API.

These tests make real HTTP requests to Financial Modeling Prep. They:
  - Validate that the field names we depend on actually exist in API responses
  - Save responses as JSON fixtures for offline testing

Run with:
    pytest -m integration tests/integration/test_fmp_live.py -o "addopts="

Requires FMP_API_KEY in the environment or .env file.
Skipped automatically when the key is not set.

NOTE: FMP free plan limits the ``limit`` query param to 5. Tests use limit=1
to minimise credit usage.
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.clients.fmp_client import FMPClient

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# ── Field lists that MUST exist in API responses ─────────────────────────
# These mirror the exact .get() keys used in IngestionService._ingest_financials()

INCOME_FIELDS = [
    "revenue", "costOfRevenue", "grossProfit", "operatingIncome",
    "operatingExpenses", "netIncome", "eps", "epsDiluted", "ebitda",
    "researchAndDevelopmentExpenses", "sellingGeneralAndAdministrativeExpenses",
    "interestExpense", "incomeTaxExpense",
    "period", "date", "fiscalYear",
]

CASHFLOW_FIELDS = [
    "operatingCashFlow", "capitalExpenditure", "freeCashFlow",
    "period", "date", "fiscalYear",
]

BALANCE_SHEET_FIELDS = [
    "totalAssets", "totalLiabilities", "totalDebt",
    "cashAndCashEquivalents", "totalStockholdersEquity",
    "period", "date", "fiscalYear",
]

PROFILE_FIELDS = ["companyName", "sector"]


def _get_api_key() -> str:
    """Try env var, then .env file."""
    key = os.environ.get("FMP_API_KEY", "")
    if not key:
        env_file = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("FMP_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return key


def _save_fixture(name: str, data) -> None:
    """Save API response to fixtures dir for offline testing."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / name
    path.write_text(json.dumps(data, indent=2))


# Skip the entire module if no API key
api_key = _get_api_key()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not api_key, reason="FMP_API_KEY not set"),
]


@pytest.fixture(scope="module")
def fmp() -> FMPClient:
    client = FMPClient(api_key=api_key)
    yield client
    client.close()


# ── Tests ────────────────────────────────────────────────────────────────


class TestFMPProfileEndpoint:
    def test_profile_has_required_fields(self, fmp: FMPClient):
        profile = fmp.get_company_profile("AAPL")
        assert profile, "Profile response should not be empty"

        _save_fixture("fmp_profile_AAPL_live.json", profile)

        for field in PROFILE_FIELDS:
            assert field in profile, f"Profile missing field: {field}"
        assert isinstance(profile["companyName"], str)
        assert len(profile["companyName"]) > 0


class TestFMPIncomeStatementEndpoint:
    def test_income_statement_has_required_fields(self, fmp: FMPClient):
        data = fmp.get_income_statement("AAPL", period="quarter", limit=1)
        assert isinstance(data, list), "Income statement should return a list"
        assert len(data) >= 1, "Should have at least 1 quarter"

        _save_fixture("fmp_income_statement_AAPL_live.json", data)

        entry = data[0]
        for field in INCOME_FIELDS:
            assert field in entry, f"Income statement missing field: {field}"
        assert isinstance(entry["revenue"], (int, float))
        assert entry["revenue"] > 0, "Revenue should be positive"


class TestFMPCashFlowEndpoint:
    def test_cashflow_has_required_fields(self, fmp: FMPClient):
        data = fmp.get_cash_flow_statement("AAPL", period="quarter", limit=1)
        assert isinstance(data, list), "Cash flow should return a list"
        assert len(data) >= 1

        _save_fixture("fmp_cashflow_AAPL_live.json", data)

        entry = data[0]
        for field in CASHFLOW_FIELDS:
            assert field in entry, f"Cash flow missing field: {field}"


class TestFMPBalanceSheetEndpoint:
    def test_balance_sheet_has_required_fields(self, fmp: FMPClient):
        data = fmp.get_balance_sheet("AAPL", period="quarter", limit=1)
        assert isinstance(data, list), "Balance sheet should return a list"
        assert len(data) >= 1

        _save_fixture("fmp_balance_sheet_AAPL_live.json", data)

        entry = data[0]
        for field in BALANCE_SHEET_FIELDS:
            assert field in entry, f"Balance sheet missing field: {field}"


class TestFMPTranscriptEndpoint:
    def test_transcript_returns_none_on_restricted_plan(self, fmp: FMPClient):
        """Transcripts are restricted on the free plan — should return None gracefully."""
        transcript = fmp.get_transcript("AAPL", quarter=3, year=2024)
        # On paid plans this would return data; on free plans it should return None
        # Either way, no crash.
        if transcript is not None:
            assert len(transcript.content) > 100, "Transcript content should be substantial"
            _save_fixture(
                "fmp_transcript_AAPL_Q3_2024.json",
                {
                    "ticker": transcript.ticker,
                    "quarter": transcript.quarter,
                    "year": transcript.year,
                    "call_date": str(transcript.call_date),
                    "content": transcript.content,
                },
            )


class TestFieldMappingConsistency:
    """Cross-check that the field names we use in IngestionService._ingest_financials
    match what FMP actually returns."""

    def test_income_field_mapping(self, fmp: FMPClient):
        """Verify every .get() key in _ingest_financials matches the real response."""
        data = fmp.get_income_statement("AAPL", period="quarter", limit=1)
        entry = data[0]

        # These are the exact keys used in ingestion_service.py
        mapping_keys = {
            "revenue", "costOfRevenue", "grossProfit", "operatingIncome",
            "operatingExpenses", "netIncome", "eps", "epsDiluted", "ebitda",
            "researchAndDevelopmentExpenses",
            "sellingGeneralAndAdministrativeExpenses",
            "interestExpense", "incomeTaxExpense",
        }
        for key in mapping_keys:
            assert key in entry, (
                f"IngestionService uses entry.get('{key}') but FMP response "
                f"does not contain this field. Available keys: {sorted(entry.keys())}"
            )

    def test_cashflow_field_mapping(self, fmp: FMPClient):
        data = fmp.get_cash_flow_statement("AAPL", period="quarter", limit=1)
        entry = data[0]

        mapping_keys = {"operatingCashFlow", "capitalExpenditure", "freeCashFlow"}
        for key in mapping_keys:
            assert key in entry, (
                f"IngestionService uses cf.get('{key}') but FMP response "
                f"does not contain this field. Available keys: {sorted(entry.keys())}"
            )

    def test_balance_sheet_field_mapping(self, fmp: FMPClient):
        data = fmp.get_balance_sheet("AAPL", period="quarter", limit=1)
        entry = data[0]

        mapping_keys = {
            "totalAssets", "totalLiabilities", "totalDebt",
            "cashAndCashEquivalents", "totalStockholdersEquity",
        }
        for key in mapping_keys:
            assert key in entry, (
                f"IngestionService uses bs.get('{key}') but FMP response "
                f"does not contain this field. Available keys: {sorted(entry.keys())}"
            )
