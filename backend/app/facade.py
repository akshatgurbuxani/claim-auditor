"""Pipeline facade — single entry point for all external interfaces.

Now powered by Dependency Injection container for explicit, testable wiring.

Streamlit, CLI (run_pipeline.py), MCP server, and FastAPI should all
use this instead of wiring up services directly. If the internal
pipeline changes (new engines, different repos, etc.) only the container
needs updating — every consumer is insulated.

Usage::

    facade = PipelineFacade()          # uses default container
    result = facade.run_pipeline(["AAPL"], steps="all")
    analysis = facade.get_company_analysis("AAPL")
    facade.close()

Or with custom container::

    container = AppContainer()
    container.settings.override(custom_settings)
    facade = PipelineFacade(container=container)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.container import AppContainer
from app.schemas.discrepancy import CompanyAnalysis
from app.utils.scoring import compute_stats

import app.models  # noqa: F401 — register all models with Base.metadata

logger = logging.getLogger(__name__)


class PipelineFacade:
    """High-level API for the earnings verification pipeline.

    Uses dependency injection container for clean, explicit wiring.
    Returns only Pydantic schemas and plain dicts — never ORM models.

    Benefits of container-based approach:
    - Explicit dependencies (no hidden wiring)
    - Easy to mock for testing
    - Centralized configuration
    - Follows Dependency Inversion Principle
    """

    def __init__(self, container: Optional[AppContainer] = None):
        """Initialize facade with optional custom container.

        Args:
            container: Optional DI container. If None, creates default container.
        """
        self.container = container or AppContainer()
        self.container.init_resources()  # Initialize database

    # ══════════════════════════════════════════════════════════════════
    # PIPELINE EXECUTION
    # ══════════════════════════════════════════════════════════════════

    def run_pipeline(
        self,
        tickers: Optional[List[str]] = None,
        quarters: Optional[List[Tuple[int, int]]] = None,
        steps: str = "all",
    ) -> Dict[str, Any]:
        """Run pipeline steps.

        ``steps`` is one of: ingest, extract, verify, analyze, all.
        """
        settings = self.container.settings()
        tickers = tickers or settings.target_tickers
        quarters = quarters or settings.target_quarters
        result: Dict[str, Any] = {"steps_run": [], "tickers": tickers}

        if steps in ("ingest", "all"):
            svc = self.container.ingestion_service()
            result["ingest"] = svc.ingest_all(tickers=tickers, quarters=quarters)
            result["steps_run"].append("ingest")

        if steps in ("extract", "all"):
            svc = self.container.extraction_service()
            result["extract"] = svc.extract_all()
            result["steps_run"].append("extract")

        if steps in ("verify", "all"):
            svc = self.container.verification_service()
            result["verify"] = svc.verify_all()
            result["steps_run"].append("verify")

        if steps in ("analyze", "all"):
            svc = self.container.analysis_service()
            analyses = svc.analyze_all()
            result["analyze"] = {
                "companies_analyzed": len(analyses),
                "total_patterns": sum(len(a.patterns) for a in analyses),
            }
            result["steps_run"].append("analyze")

        return result

    # ══════════════════════════════════════════════════════════════════
    # READ-ONLY QUERIES
    # ══════════════════════════════════════════════════════════════════

    def list_companies(self) -> List[Dict[str, Any]]:
        """Return all companies with summary trust scores."""
        company_repo = self.container.company_repo()
        claim_repo = self.container.claim_repo()

        companies = company_repo.get_all()
        out: List[Dict[str, Any]] = []
        for c in companies:
            claims = claim_repo.get_for_company(c.id)
            v, total, acc, trust = compute_stats(claims)
            out.append({
                "ticker": c.ticker,
                "name": c.name,
                "sector": c.sector,
                "total_claims": total,
                "accuracy": round(acc, 4),
                "trust_score": round(trust, 1),
                "verdicts": v,
            })
        return out

    def get_company_analysis(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Full analysis for a company (re-computes from DB, persists patterns)."""
        company_repo = self.container.company_repo()
        company = company_repo.get_by_ticker(ticker)
        if not company:
            return None

        svc = self.container.analysis_service()
        try:
            analysis: CompanyAnalysis = svc.analyze_company(company.id)
            return analysis.model_dump()
        except ValueError:
            return None

    def get_claims(
        self,
        ticker: str,
        verdict_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return claims for a company, optionally filtered by verdict."""
        company_repo = self.container.company_repo()
        claim_repo = self.container.claim_repo()

        company = company_repo.get_by_ticker(ticker)
        if not company:
            return []

        claims = claim_repo.get_for_company(company.id)
        out: List[Dict[str, Any]] = []
        for c in claims:
            vf = c.verification
            if verdict_filter and (not vf or vf.verdict != verdict_filter):
                continue
            out.append({
                "claim_text": c.claim_text,
                "speaker": c.speaker,
                "metric": c.metric,
                "metric_type": c.metric_type,
                "stated_value": c.stated_value,
                "unit": c.unit,
                "quarter": f"Q{c.transcript.quarter} {c.transcript.year}",
                "verdict": vf.verdict if vf else None,
                "actual_value": vf.actual_value if vf else None,
                "accuracy_score": vf.accuracy_score if vf else None,
                "explanation": vf.explanation if vf else None,
                "misleading_flags": vf.misleading_flags if vf else [],
                "is_gaap": c.is_gaap,
                "confidence": c.confidence,
            })
        return out

    def get_quarter_breakdown(self, ticker: str) -> List[Dict[str, Any]]:
        """Per-quarter verdict breakdown for a company."""
        company_repo = self.container.company_repo()
        claim_repo = self.container.claim_repo()

        company = company_repo.get_by_ticker(ticker)
        if not company:
            return []

        claims = claim_repo.get_for_company(company.id)
        quarter_map: Dict[str, list] = {}
        for c in claims:
            key = f"Q{c.transcript.quarter} {c.transcript.year}"
            quarter_map.setdefault(key, []).append(c)

        results: List[Dict[str, Any]] = []
        for qkey in sorted(quarter_map.keys(), reverse=True):
            qclaims = quarter_map[qkey]
            v, total, acc, trust = compute_stats(qclaims)
            results.append({
                "quarter": qkey,
                "total_claims": total,
                "accuracy": round(acc, 4),
                "trust_score": round(trust, 1),
                "verdicts": v,
            })
        return results

    def get_discrepancy_patterns(self, ticker: str) -> List[Dict[str, Any]]:
        """Return persisted cross-quarter discrepancy patterns."""
        company_repo = self.container.company_repo()
        pattern_repo = self.container.discrepancy_pattern_repo()

        company = company_repo.get_by_ticker(ticker)
        if not company:
            return []
        patterns = pattern_repo.get_for_company(company.id)
        return [
            {
                "pattern_type": p.pattern_type,
                "description": p.description,
                "affected_quarters": p.affected_quarters,
                "severity": p.severity,
                "evidence": p.evidence,
            }
            for p in patterns
        ]

    def get_top_discrepancies(
        self,
        ticker: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return top discrepancies (misleading/incorrect claims) for a company."""
        company_repo = self.container.company_repo()
        claim_repo = self.container.claim_repo()

        company = company_repo.get_by_ticker(ticker)
        if not company:
            return []

        claims = claim_repo.get_for_company(company.id)
        bad_claims = [
            c for c in claims
            if c.verification and c.verification.verdict in ("misleading", "incorrect")
        ]

        # Sort by accuracy score (worst first)
        bad_claims.sort(key=lambda c: c.verification.accuracy_score if c.verification else 1.0)

        return [
            {
                "claim_text": c.claim_text,
                "speaker": c.speaker,
                "metric": c.metric,
                "metric_type": c.metric_type,
                "stated_value": c.stated_value,
                "unit": c.unit,
                "quarter": f"Q{c.transcript.quarter} {c.transcript.year}",
                "verdict": c.verification.verdict,
                "actual_value": c.verification.actual_value,
                "accuracy_score": c.verification.accuracy_score,
                "explanation": c.verification.explanation,
                "misleading_flags": c.verification.misleading_flags,
                "context_snippet": c.context_snippet,
                "comparison_period": c.comparison_period,
                "comparison_basis": c.comparison_basis,
                "is_gaap": c.is_gaap,
                "segment": c.segment,
                "confidence": c.confidence,
            }
            for c in bad_claims[:limit]
        ]

    def get_all_patterns_grouped(self) -> Dict[int, List[Dict[str, Any]]]:
        """Return all discrepancy patterns grouped by company_id."""
        pattern_repo = self.container.discrepancy_pattern_repo()
        patterns = pattern_repo.get_all_grouped()
        return {
            company_id: [
                {
                    "pattern_type": p.pattern_type,
                    "description": p.description,
                    "affected_quarters": p.affected_quarters,
                    "severity": p.severity,
                    "evidence": p.evidence,
                }
                for p in pattern_list
            ]
            for company_id, pattern_list in patterns.items()
        }

    # ══════════════════════════════════════════════════════════════════
    # LIFECYCLE
    # ══════════════════════════════════════════════════════════════════

    def close(self) -> None:
        """Close database session and clients."""
        # Container manages lifecycle, just shutdown resources
        self.container.shutdown_resources()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
