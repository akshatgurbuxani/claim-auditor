#!/usr/bin/env python3
"""Run the claim auditor pipeline: ingest → extract → verify → analyze.

Usage with Docker (recommended):
    docker compose run streamlit python -m scripts.run_pipeline
    docker compose run streamlit python -m scripts.run_pipeline --step ingest
    docker compose run streamlit python -m scripts.run_pipeline --tickers AAPL MSFT

Usage locally:
    python -m scripts.run_pipeline                    # run all steps, all tickers
    python -m scripts.run_pipeline --step ingest      # only fetch from FMP
    python -m scripts.run_pipeline --step extract     # only run Claude extraction
    python -m scripts.run_pipeline --step verify      # only verify claims
    python -m scripts.run_pipeline --step analyze     # only run discrepancy analysis
    python -m scripts.run_pipeline --tickers AAPL MSFT  # limit to specific tickers

Pipeline steps:
    1. ingest  — Fetch company profiles, transcripts, and financial statements from FMP
    2. extract — Extract quantitative claims from each transcript via Claude
    3. verify  — Verify each claim against the structured financial data
    4. analyze — Cross-quarter discrepancy pattern detection (bonus)

Fully idempotent — safe to re-run. Already-processed items are skipped.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.facade import PipelineFacade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pipeline")

VALID_STEPS = ("ingest", "extract", "verify", "analyze", "all")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the claim auditor pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--step",
        choices=VALID_STEPS,
        default="all",
        help="Which pipeline step to run (default: all)",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="Override target tickers (e.g. --tickers AAPL MSFT)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    settings = Settings()

    # Override tickers if provided via CLI
    if args.tickers:
        settings.target_tickers = [t.upper() for t in args.tickers]

    tickers = settings.target_tickers
    step = args.step

    # Validate API keys based on step
    if step in ("ingest", "all") and not settings.fmp_api_key:
        logger.error("FMP_API_KEY is not set. Add it to backend/.env")
        sys.exit(1)
    if step in ("extract", "all") and not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY is not set. Add it to backend/.env")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("CLAIM AUDITOR — Pipeline Run")
    logger.info("  Step:     %s", step)
    logger.info("  Tickers:  %s", tickers)
    logger.info("  Quarters: %s", settings.target_quarters)
    logger.info("=" * 60)

    t0 = time.time()

    with PipelineFacade(settings=settings) as facade:
        result = facade.run_pipeline(
            tickers=tickers,
            quarters=settings.target_quarters,
            steps=step,
        )

    # ── Log results ──────────────────────────────────────────────────
    total_time = time.time() - t0

    if "ingest" in result:
        logger.info("Ingestion result: %s", result["ingest"])
    if "extract" in result:
        logger.info("Extraction result: %s", result["extract"])
    if "verify" in result:
        logger.info("Verification result: %s", result["verify"])
    if "analyze" in result:
        logger.info("Analysis result: %s", result["analyze"])

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE in %.1fs", total_time)
    logger.info("  Steps run: %s", result["steps_run"])
    logger.info("  Tickers:   %s", result["tickers"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
