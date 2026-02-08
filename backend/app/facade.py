"""Pipeline facade — single entry point for all external interfaces.

Streamlit, CLI (run_pipeline.py), MCP server, and FastAPI should all
use this instead of wiring up services directly.  If the internal
pipeline changes (new engines, different repos, etc.) only this file
needs updating — every consumer is insulated.

Usage::

    facade = PipelineFacade()          # uses Settings() from .env
    result = facade.run_pipeline(["AAPL"], steps="all")
    analysis = facade.get_company_analysis("AAPL")
    facade.close()
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.clients.fmp_client import FMPClient
from app.clients.llm_client import LLMClient
from app.config import Settings
from app.database import Base, build_engine, build_session_factory
from app.engines.claim_extractor import ClaimExtractor
from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
from app.engines.metric_mapper import MetricMapper
from app.engines.verification_engine import VerificationEngine
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.discrepancy_pattern_repo import DiscrepancyPatternRepository
from app.repositories.financial_data_repo import FinancialDataRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.repositories.verification_repo import VerificationRepository
from app.schemas.discrepancy import CompanyAnalysis
from app.services.analysis_service import AnalysisService
from app.services.extraction_service import ExtractionService
from app.services.ingestion_service import IngestionService
from app.services.verification_service import VerificationService
from app.utils.scoring import compute_stats

import app.models  # noqa: F401 — register all models with Base.metadata

logger = logging.getLogger(__name__)


class PipelineFacade:
    """High-level API for the earnings verification pipeline.

    Hides all internal wiring (repos, engines, services, clients).
    Returns only Pydantic schemas and plain dicts — never ORM models.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or Settings()
        self._setup_db()
        self._setup_repos()
        self._setup_clients()

    # ── internal wiring (private) ─────────────────────────────────────

    def _setup_db(self) -> None:
        s = self._settings
        db_path = Path(s.database_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = build_engine(s.database_url, echo=False)
        Base.metadata.create_all(bind=self._engine)
        Session = build_session_factory(self._engine)
        self._db = Session()

    def _setup_repos(self) -> None:
        db = self._db
        self._company_repo = CompanyRepository(db)
        self._transcript_repo = TranscriptRepository(db)
        self._financial_repo = FinancialDataRepository(db)
        self._claim_repo = ClaimRepository(db)
        self._verification_repo = VerificationRepository(db)
        self._pattern_repo = DiscrepancyPatternRepository(db)

    def _setup_clients(self) -> None:
        s = self._settings
        cache_dir = Path(s.database_url.replace("sqlite:///", "")).parent / "fmp_cache"
        self._fmp = FMPClient(api_key=s.fmp_api_key, cache_dir=cache_dir)
        self._llm = LLMClient(api_key=s.anthropic_api_key, model=s.claude_model)

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
        s = self._settings
        tickers = tickers or s.target_tickers
        quarters = quarters or s.target_quarters
        result: Dict[str, Any] = {"steps_run": [], "tickers": tickers}

        if steps in ("ingest", "all"):
            transcript_dir = Path(__file__).resolve().parent.parent / "data" / "transcripts"
            svc = IngestionService(
                self._fmp,
                self._company_repo,
                self._transcript_repo,
                self._financial_repo,
                transcript_dir=transcript_dir,
            )
            result["ingest"] = svc.ingest_all(tickers=tickers, quarters=quarters)
            result["steps_run"].append("ingest")

        if steps in ("extract", "all"):
            extractor = ClaimExtractor(self._llm)
            svc = ExtractionService(extractor, self._transcript_repo, self._claim_repo)
            result["extract"] = svc.extract_all()
            result["steps_run"].append("extract")

        if steps in ("verify", "all"):
            mapper = MetricMapper()
            engine = VerificationEngine(mapper, self._financial_repo, self._settings)
            svc = VerificationService(engine, self._claim_repo, self._verification_repo)
            result["verify"] = svc.verify_all()
            result["steps_run"].append("verify")

        if steps in ("analyze", "all"):
            analyzer = DiscrepancyAnalyzer()
            svc = AnalysisService(
                analyzer,
                self._company_repo,
                self._claim_repo,
                self._verification_repo,
                self._pattern_repo,
            )
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
        companies = self._company_repo.get_all()
        out: List[Dict[str, Any]] = []
        for c in companies:
            claims = self._claim_repo.get_for_company(c.id)
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
        company = self._company_repo.get_by_ticker(ticker)
        if not company:
            return None

        analyzer = DiscrepancyAnalyzer()
        svc = AnalysisService(
            analyzer,
            self._company_repo,
            self._claim_repo,
            self._verification_repo,
            self._pattern_repo,
        )
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
        company = self._company_repo.get_by_ticker(ticker)
        if not company:
            return []

        claims = self._claim_repo.get_for_company(company.id)
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
        company = self._company_repo.get_by_ticker(ticker)
        if not company:
            return []

        claims = self._claim_repo.get_for_company(company.id)
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
        company = self._company_repo.get_by_ticker(ticker)
        if not company:
            return []
        patterns = self._pattern_repo.get_for_company(company.id)
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

    # ── lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        """Close database session and FMP client."""
        self._db.close()
        self._fmp.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
