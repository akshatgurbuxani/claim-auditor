"""MCP (Model Context Protocol) server — exposes the claim auditor as
tools that AI agents (Claude Code, Cursor, etc.) can call.

Run:
    python mcp_server.py                     # stdio transport (default)
    python mcp_server.py --transport sse     # SSE transport (for web)

Configure in Claude Code / Cursor MCP settings::

    {
      "mcpServers": {
        "claim-auditor": {
          "command": "python",
          "args": ["<path>/claim-auditor/backend/mcp_server.py"],
          "env": {
            "FMP_API_KEY": "your-key",
            "ANTHROPIC_API_KEY": "your-key"
          }
        }
      }
    }

This file imports ONLY the PipelineFacade.  It never touches repos,
engines, services, or ORM models directly — ensuring full decoupling.
"""

import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from app.facade import PipelineFacade

# ── Server setup ──────────────────────────────────────────────────────────

mcp = FastMCP(
    "claim-auditor",
    instructions=(
        "Claim Auditor — analyzes management claims from earnings "
        "calls and verifies them against actual financial data.  Detects "
        "misleading framing and cross-quarter discrepancy patterns.\n\n"
        "Start with list_companies() to see available data, then use "
        "analyze_company(), get_claims(), compare_quarters(), or "
        "get_discrepancy_patterns() to dive deeper."
    ),
)

# Lazy-initialise facade so the server starts fast;
# created on first tool call.
_facade: PipelineFacade | None = None


def _get_facade() -> PipelineFacade:
    global _facade
    if _facade is None:
        _facade = PipelineFacade()
    return _facade


# ══════════════════════════════════════════════════════════════════════════
# TOOLS — actions an AI agent can invoke
# ══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def list_companies() -> list[dict]:
    """List all companies in the database with trust scores and verdict summaries.

    Use this first to see what data is available before diving deeper.
    Returns a list of dicts, each with: ticker, name, sector, total_claims,
    accuracy, trust_score, and verdicts breakdown.
    """
    return _get_facade().list_companies()


@mcp.tool()
def analyze_company(ticker: str) -> dict:
    """Full analysis for a company: trust score, accuracy rate, verdict
    breakdown, top discrepancies, and cross-quarter patterns.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL", "MSFT", "NVDA")

    Returns:
        Complete analysis dict including trust_score (0-100),
        overall_accuracy_rate (0-1), verdict counts, top 5 discrepancies,
        detected patterns, and quarters analyzed.
        Returns {error: ...} if company not found.
    """
    facade = _get_facade()
    result = facade.get_company_analysis(ticker.upper())
    if result is None:
        return {"error": f"Company '{ticker}' not found in database."}
    return result


@mcp.tool()
def get_claims(ticker: str, verdict: str | None = None) -> list[dict]:
    """Get individual claims extracted from a company's earnings calls.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL")
        verdict: Optional filter — one of: verified, approximately_correct,
                 misleading, incorrect, unverifiable.  Omit for all claims.

    Returns:
        List of claims, each with: claim_text, speaker, metric, stated_value,
        actual_value, verdict, explanation, misleading_flags, quarter, etc.
    """
    return _get_facade().get_claims(ticker.upper(), verdict_filter=verdict)


@mcp.tool()
def compare_quarters(ticker: str) -> list[dict]:
    """Compare management claim accuracy across quarters for a company.

    Shows per-quarter trust scores, accuracy rates, and verdict breakdowns.
    Useful for spotting trends — is management becoming more or less accurate?

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL")

    Returns:
        List of quarters (newest first), each with: quarter label,
        total_claims, accuracy, trust_score, and verdicts breakdown.
    """
    return _get_facade().get_quarter_breakdown(ticker.upper())


@mcp.tool()
def get_discrepancy_patterns(ticker: str) -> list[dict]:
    """Get detected cross-quarter discrepancy patterns for a company.

    Patterns include:
    - consistent_rounding_up: >70% of inexact claims round favourably
    - metric_switching: most-emphasised metric changes between quarters
    - increasing_inaccuracy: accuracy declining over quarters
    - gaap_nongaap_shifting: shifting between GAAP and non-GAAP framing
    - selective_emphasis: >90% of claims emphasise positive growth

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL")

    Returns:
        List of patterns, each with: pattern_type, description,
        severity (0-1), affected_quarters, and evidence list.
    """
    return _get_facade().get_discrepancy_patterns(ticker.upper())


@mcp.tool()
def run_pipeline(
    tickers: list[str],
    steps: str = "all",
) -> dict:
    """Run the earnings verification pipeline for specified companies.

    Fetches data from FMP, extracts claims via Claude, verifies them
    against financial statements, and detects discrepancy patterns.

    WARNING: The 'extract' step calls the Anthropic API and costs money.
    Use 'ingest' or 'verify' for cheaper, local-only operations.

    Args:
        tickers: List of stock ticker symbols (e.g. ["AAPL", "MSFT"])
        steps: Which pipeline step(s) to run — one of:
               ingest, extract, verify, analyze, all

    Returns:
        Summary of what was processed in each step.
    """
    facade = _get_facade()
    return facade.run_pipeline(
        tickers=[t.upper() for t in tickers],
        steps=steps,
    )


# ══════════════════════════════════════════════════════════════════════════
# RESOURCES — reference data the agent can read
# ══════════════════════════════════════════════════════════════════════════


@mcp.resource("claim-auditor://help")
def get_help() -> str:
    """How to use the Claim Auditor tools."""
    return """\
# Claim Auditor — Tool Guide

## Quick Start
1. `list_companies()` — See what's in the database
2. `analyze_company("AAPL")` — Full analysis for a company
3. `compare_quarters("AAPL")` — Quarter-over-quarter trends
4. `get_discrepancy_patterns("AAPL")` — Systematic bias patterns
5. `get_claims("AAPL", verdict="misleading")` — Drill into specific claims

## Adding New Companies
`run_pipeline(tickers=["GOOG"], steps="all")` — Runs full pipeline (costs API tokens)

## Verdicts Explained
- **verified**: Claim matches financial data within 2%
- **approximately_correct**: Within 10%
- **misleading**: 10-25% off, may have misleading framing
- **incorrect**: >25% off or materially inaccurate
- **unverifiable**: Cannot cross-reference against available data

## Trust Score (0-100)
Weighted score: verified=+1, approx=+0.7, misleading=-0.3, incorrect=-1.0
Normalised to 0-100 scale.  Above 80 = trustworthy, below 40 = concerning.

## Pattern Types
- 🔺 consistent_rounding_up — >70% of inexact claims round favourably
- 🔄 metric_switching — most-emphasised metric changes between quarters
- 📉 increasing_inaccuracy — accuracy declining over quarters
- 📊 gaap_nongaap_shifting — shifting between GAAP and non-GAAP framing
- 🎯 selective_emphasis — >90% of claims emphasise positive growth
"""


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
