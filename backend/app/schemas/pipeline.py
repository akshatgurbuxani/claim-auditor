"""Pydantic schemas for pipeline API endpoints.

Provides request validation and response models for pipeline operations.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TickerValidator:
    """Common validator for ticker symbols."""

    @staticmethod
    def validate_ticker(v: str) -> str:
        """Validate ticker format.

        Args:
            v: Ticker string to validate.

        Returns:
            Validated ticker in uppercase.

        Raises:
            ValueError: If ticker format is invalid.
        """
        v = v.upper().strip()
        if not v:
            raise ValueError("Ticker cannot be empty")
        if len(v) > 5:
            raise ValueError(f"Ticker too long: {v} (max 5 characters)")
        if not v.isalpha():
            raise ValueError(f"Ticker must contain only letters: {v}")
        return v


class PipelineIngestRequest(BaseModel):
    """Request model for pipeline ingestion.

    Validates ticker list and optional quarter specifications.
    """

    tickers: Optional[List[str]] = Field(
        default=None,
        description="List of stock tickers to ingest (e.g., ['AAPL', 'MSFT']). If not provided, uses default list from settings.",
        max_length=20,
        examples=[["AAPL", "MSFT", "AMZN"]],
    )

    quarters: Optional[List[tuple[int, int]]] = Field(
        default=None,
        description="List of (year, quarter) tuples to fetch. If not provided, uses default from settings.",
        max_length=10,
        examples=[[(2025, 4), (2025, 3), (2025, 2)]],
    )

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate all tickers in the list.

        Args:
            v: List of ticker strings.

        Returns:
            Validated list of tickers.

        Raises:
            ValueError: If any ticker is invalid.
        """
        if v is None:
            return None
        if len(v) == 0:
            raise ValueError("Ticker list cannot be empty")
        return [TickerValidator.validate_ticker(ticker) for ticker in v]

    @field_validator("quarters")
    @classmethod
    def validate_quarters(cls, v: Optional[List[tuple[int, int]]]) -> Optional[List[tuple[int, int]]]:
        """Validate quarter specifications.

        Args:
            v: List of (year, quarter) tuples.

        Returns:
            Validated list of quarters.

        Raises:
            ValueError: If any quarter specification is invalid.
        """
        if v is None:
            return None
        if len(v) == 0:
            raise ValueError("Quarter list cannot be empty")

        for year, quarter in v:
            if year < 2020 or year > 2030:
                raise ValueError(f"Invalid year: {year} (must be between 2020-2030)")
            if quarter < 1 or quarter > 4:
                raise ValueError(f"Invalid quarter: {quarter} (must be between 1-4)")
        return v


class PipelineResponse(BaseModel):
    """Response model for pipeline operations."""

    status: str = Field(..., description="Operation status (e.g., 'completed', 'failed')")
    summary: Optional[Dict[str, Any]] = Field(
        None, description="Summary of operation results"
    )
    pipeline: Optional[Dict[str, Any]] = Field(
        None, description="Full pipeline results (for run-all endpoint)"
    )


class PipelineStatusResponse(BaseModel):
    """Response model for pipeline status endpoint."""

    companies: int = Field(..., description="Total number of companies in database")
    transcripts: int = Field(..., description="Total number of transcripts")
    transcripts_unprocessed: int = Field(
        ..., description="Number of transcripts not yet processed for claims"
    )
    claims: int = Field(..., description="Total number of claims extracted")
    claims_unverified: int = Field(..., description="Number of claims not yet verified")
    verifications: int = Field(..., description="Total number of verified claims")
