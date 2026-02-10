"""Tests for pipeline Pydantic validation schemas.

Verifies that API request validation works correctly and rejects invalid input.
"""

import pytest
from pydantic import ValidationError

from app.schemas.pipeline import (
    PipelineIngestRequest,
    PipelineResponse,
    PipelineStatusResponse,
    TickerValidator,
)


class TestTickerValidator:
    """Test ticker validation logic."""

    def test_validate_ticker_success(self):
        """Valid tickers pass validation."""
        valid_tickers = ["AAPL", "MSFT", "AMZN", "GOOG", "META"]

        for ticker in valid_tickers:
            result = TickerValidator.validate_ticker(ticker)
            assert result == ticker.upper()

    def test_validate_ticker_converts_to_uppercase(self):
        """Tickers are converted to uppercase."""
        assert TickerValidator.validate_ticker("aapl") == "AAPL"
        assert TickerValidator.validate_ticker("MsFt") == "MSFT"

    def test_validate_ticker_strips_whitespace(self):
        """Tickers have whitespace stripped."""
        assert TickerValidator.validate_ticker("  AAPL  ") == "AAPL"
        assert TickerValidator.validate_ticker("\tMSFT\n") == "MSFT"

    def test_validate_ticker_rejects_empty(self):
        """Empty tickers are rejected."""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            TickerValidator.validate_ticker("")

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            TickerValidator.validate_ticker("   ")

    def test_validate_ticker_rejects_too_long(self):
        """Tickers longer than 5 characters are rejected."""
        with pytest.raises(ValueError, match="Ticker too long"):
            TickerValidator.validate_ticker("TOOLONG")

        with pytest.raises(ValueError, match="Ticker too long"):
            TickerValidator.validate_ticker("ABCDEF")

    def test_validate_ticker_rejects_non_alphabetic(self):
        """Non-alphabetic tickers are rejected."""
        invalid_tickers = ["AAPL1", "MS-FT", "AMZN!", "123", "AA.PL"]

        for ticker in invalid_tickers:
            with pytest.raises(ValueError, match="Ticker must contain only letters"):
                TickerValidator.validate_ticker(ticker)


class TestPipelineIngestRequest:
    """Test pipeline ingestion request validation."""

    def test_create_with_valid_data(self):
        """Valid request data passes validation."""
        request = PipelineIngestRequest(
            tickers=["AAPL", "MSFT"],
            quarters=[(2025, 4), (2025, 3)]
        )

        assert request.tickers == ["AAPL", "MSFT"]
        assert request.quarters == [(2025, 4), (2025, 3)]

    def test_create_with_defaults(self):
        """Request can be created with defaults (None)."""
        request = PipelineIngestRequest()

        assert request.tickers is None
        assert request.quarters is None

    def test_create_with_partial_data(self):
        """Request can have tickers without quarters or vice versa."""
        request1 = PipelineIngestRequest(tickers=["AAPL"])
        assert request1.tickers == ["AAPL"]
        assert request1.quarters is None

        request2 = PipelineIngestRequest(quarters=[(2025, 4)])
        assert request2.tickers is None
        assert request2.quarters == [(2025, 4)]

    def test_tickers_converted_to_uppercase(self):
        """Tickers are automatically converted to uppercase."""
        request = PipelineIngestRequest(tickers=["aapl", "msft"])

        assert request.tickers == ["AAPL", "MSFT"]

    def test_empty_ticker_list_rejected(self):
        """Empty ticker list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineIngestRequest(tickers=[])

        errors = exc_info.value.errors()
        assert any("Ticker list cannot be empty" in str(e) for e in errors)

    def test_invalid_ticker_format_rejected(self):
        """Invalid ticker formats are rejected."""
        invalid_tickers = [
            ["AAPL", "TOOLONG"],  # Too long
            ["AAPL", "MS-FT"],     # Contains hyphen
            ["AAPL", "123"],       # Numbers only
            ["AAPL", ""],          # Empty
        ]

        for tickers in invalid_tickers:
            with pytest.raises(ValidationError):
                PipelineIngestRequest(tickers=tickers)

    def test_too_many_tickers_rejected(self):
        """More than 20 tickers are rejected."""
        # Use 21 valid ticker symbols
        too_many = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "JPM",
                    "V", "WMT", "JNJ", "PG", "UNH", "MA", "HD", "DIS", "BAC", "ADBE",
                    "CRM", "NFLX", "PYPL"]  # 21 tickers

        with pytest.raises(ValidationError):
            PipelineIngestRequest(tickers=too_many)

    def test_valid_quarters(self):
        """Valid quarter specifications pass."""
        valid_quarters = [
            [(2025, 1)],
            [(2025, 1), (2025, 2), (2025, 3), (2025, 4)],
            [(2020, 1), (2030, 4)],  # Boundary values
        ]

        for quarters in valid_quarters:
            request = PipelineIngestRequest(quarters=quarters)
            assert request.quarters == quarters

    def test_empty_quarters_list_rejected(self):
        """Empty quarters list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineIngestRequest(quarters=[])

        errors = exc_info.value.errors()
        assert any("Quarter list cannot be empty" in str(e) for e in errors)

    def test_invalid_year_rejected(self):
        """Years outside 2020-2030 range are rejected."""
        invalid_years = [
            [(2019, 1)],  # Too early
            [(2031, 1)],  # Too late
            [(1999, 1)],  # Way too early
        ]

        for quarters in invalid_years:
            with pytest.raises(ValidationError) as exc_info:
                PipelineIngestRequest(quarters=quarters)

            errors = exc_info.value.errors()
            assert any("Invalid year" in str(e) for e in errors)

    def test_invalid_quarter_rejected(self):
        """Quarters outside 1-4 range are rejected."""
        invalid_quarters = [
            [(2025, 0)],   # Too low
            [(2025, 5)],   # Too high
            [(2025, -1)],  # Negative
        ]

        for quarters in invalid_quarters:
            with pytest.raises(ValidationError) as exc_info:
                PipelineIngestRequest(quarters=quarters)

            errors = exc_info.value.errors()
            assert any("Invalid quarter" in str(e) for e in errors)

    def test_too_many_quarters_rejected(self):
        """More than 10 quarters are rejected."""
        too_many = [(2025, q % 4 + 1) for q in range(11)]  # 11 quarters

        with pytest.raises(ValidationError):
            PipelineIngestRequest(quarters=too_many)

    def test_mixed_valid_and_invalid_tickers_rejected(self):
        """If any ticker is invalid, entire request is rejected."""
        with pytest.raises(ValidationError):
            PipelineIngestRequest(tickers=["AAPL", "INVALID123", "MSFT"])

    def test_request_serialization(self):
        """Request can be serialized to JSON."""
        request = PipelineIngestRequest(
            tickers=["AAPL", "MSFT"],
            quarters=[(2025, 4), (2025, 3)]
        )

        json_data = request.model_dump()

        assert json_data["tickers"] == ["AAPL", "MSFT"]
        assert json_data["quarters"] == [(2025, 4), (2025, 3)]


class TestPipelineResponse:
    """Test pipeline response model."""

    def test_create_with_status_and_summary(self):
        """Response can be created with status and summary."""
        response = PipelineResponse(
            status="completed",
            summary={"companies": 10, "transcripts": 42}
        )

        assert response.status == "completed"
        assert response.summary["companies"] == 10
        assert response.summary["transcripts"] == 42

    def test_create_with_pipeline_results(self):
        """Response can include pipeline results (for run-all)."""
        response = PipelineResponse(
            status="completed",
            pipeline={
                "ingestion": {"companies": 10},
                "extraction": {"claims": 100},
                "verification": {"verified": 90},
                "analysis": {"patterns": 5}
            }
        )

        assert response.pipeline is not None
        assert response.pipeline["ingestion"]["companies"] == 10

    def test_create_with_minimal_data(self):
        """Response requires only status."""
        response = PipelineResponse(status="completed")

        assert response.status == "completed"
        assert response.summary is None
        assert response.pipeline is None

    def test_response_serialization(self):
        """Response can be serialized to JSON."""
        response = PipelineResponse(
            status="completed",
            summary={"count": 5}
        )

        json_data = response.model_dump()

        assert json_data["status"] == "completed"
        assert json_data["summary"]["count"] == 5


class TestPipelineStatusResponse:
    """Test pipeline status response model."""

    def test_create_with_all_counts(self):
        """Status response includes all pipeline stage counts."""
        status = PipelineStatusResponse(
            companies=10,
            transcripts=42,
            transcripts_unprocessed=3,
            claims=1247,
            claims_unverified=12,
            verifications=1235
        )

        assert status.companies == 10
        assert status.transcripts == 42
        assert status.transcripts_unprocessed == 3
        assert status.claims == 1247
        assert status.claims_unverified == 12
        assert status.verifications == 1235

    def test_create_with_zero_counts(self):
        """Status response works with zero counts."""
        status = PipelineStatusResponse(
            companies=0,
            transcripts=0,
            transcripts_unprocessed=0,
            claims=0,
            claims_unverified=0,
            verifications=0
        )

        assert status.companies == 0
        assert status.verifications == 0

    def test_status_serialization(self):
        """Status response can be serialized to JSON."""
        status = PipelineStatusResponse(
            companies=10,
            transcripts=42,
            transcripts_unprocessed=3,
            claims=1247,
            claims_unverified=12,
            verifications=1235
        )

        json_data = status.model_dump()

        assert json_data["companies"] == 10
        assert json_data["transcripts"] == 42
        assert json_data["claims"] == 1247


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_exactly_5_character_ticker_accepted(self):
        """5-character tickers are accepted (boundary)."""
        request = PipelineIngestRequest(tickers=["ABCDE"])
        assert request.tickers == ["ABCDE"]

    def test_exactly_20_tickers_accepted(self):
        """20 tickers are accepted (boundary)."""
        # Use valid ticker symbols (alphabetic only)
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "JPM",
                   "V", "WMT", "JNJ", "PG", "UNH", "MA", "HD", "DIS", "BAC", "ADBE",
                   "CRM", "NFLX"]
        request = PipelineIngestRequest(tickers=tickers)
        assert len(request.tickers) == 20

    def test_exactly_10_quarters_accepted(self):
        """10 quarters are accepted (boundary)."""
        quarters = [(2025, q % 4 + 1) for q in range(10)]
        request = PipelineIngestRequest(quarters=quarters)
        assert len(request.quarters) == 10

    def test_year_2020_accepted(self):
        """Year 2020 is accepted (lower boundary)."""
        request = PipelineIngestRequest(quarters=[(2020, 1)])
        assert request.quarters == [(2020, 1)]

    def test_year_2030_accepted(self):
        """Year 2030 is accepted (upper boundary)."""
        request = PipelineIngestRequest(quarters=[(2030, 4)])
        assert request.quarters == [(2030, 4)]

    def test_quarter_1_accepted(self):
        """Quarter 1 is accepted (lower boundary)."""
        request = PipelineIngestRequest(quarters=[(2025, 1)])
        assert request.quarters == [(2025, 1)]

    def test_quarter_4_accepted(self):
        """Quarter 4 is accepted (upper boundary)."""
        request = PipelineIngestRequest(quarters=[(2025, 4)])
        assert request.quarters == [(2025, 4)]
