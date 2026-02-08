"""Application configuration loaded from environment variables."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Check if .env file exists and is readable
_env_file = None
try:
    env_path = Path(".env")
    if env_path.exists() and os.access(env_path, os.R_OK):
        _env_file = ".env"
except (OSError, PermissionError):
    # If we can't access .env, continue without it
    pass


class Settings(BaseSettings):
    """All configuration for the claim auditor application.

    Values are loaded from environment variables or a .env file.
    """

    # Application
    app_name: str = "claim-auditor"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./data/claim_auditor.db"

    # Financial Modeling Prep API (stable endpoint)
    fmp_api_key: str = ""
    fmp_base_url: str = "https://financialmodelingprep.com/stable"

    # Anthropic Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Processing thresholds
    max_claims_per_transcript: int = 50
    verification_tolerance: float = 0.02  # 2% → VERIFIED
    approximate_tolerance: float = 0.10  # 10% → APPROXIMATELY CORRECT
    misleading_threshold: float = 0.25  # 25% off → INCORRECT

    # Target companies (financial data fetched for all; transcripts loaded
    # from data/transcripts/ when FMP transcript endpoint is restricted)
    target_tickers: list[str] = [
        "AAPL", "MSFT", "NVDA",      # Technology
        "AMZN", "GOOG", "META",       # Tech / Communication
        "JPM",                         # Financial
        "JNJ",                         # Healthcare
        "TSLA",                        # Automotive
        "CRM",                         # Software
    ]

    # Target quarters (fiscal year, quarter) — covers recent filings.
    # Different companies have different fiscal-year ends, so we cast a
    # wide net and skip quarters with no data.
    target_quarters: list[tuple[int, int]] = [
        (2026, 3), (2026, 2), (2026, 1),
        (2025, 4), (2025, 3), (2025, 2), (2025, 1),
    ]

    model_config = {
        "env_file": _env_file,
        "env_file_encoding": "utf-8",
        "env_file_ignore_empty": True,
    }
