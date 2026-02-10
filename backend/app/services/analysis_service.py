"""Generates company-level analysis reports including discrepancy patterns.

Persists detected discrepancy patterns to the database for later retrieval.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
from app.models.claim import ClaimModel
from app.models.discrepancy_pattern import DiscrepancyPatternModel
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.discrepancy_pattern_repo import DiscrepancyPatternRepository
from app.repositories.verification_repo import VerificationRepository
from app.schemas.discrepancy import CompanyAnalysis, DiscrepancyPattern
from app.utils.scoring import compute_verdict_counts, compute_accuracy, compute_trust_score

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(
        self,
        db: Session,
        discrepancy_analyzer: DiscrepancyAnalyzer,
        company_repo: CompanyRepository,
        claim_repo: ClaimRepository,
        verification_repo: VerificationRepository,
        pattern_repo: DiscrepancyPatternRepository | None = None,
    ):
        self.db = db
        self.analyzer = discrepancy_analyzer
        self.companies = company_repo
        self.claims = claim_repo
        self.verifications = verification_repo
        self.patterns = pattern_repo

    def analyze_company(self, company_id: int) -> CompanyAnalysis:
        company = self.companies.get(company_id)
        if not company:
            raise ValueError(f"Company {company_id} not found")

        claims = self.claims.get_for_company(company_id)

        # Group by quarter label
        cbq: dict[str, list[ClaimModel]] = {}
        for c in claims:
            key = f"Q{c.transcript.quarter} {c.transcript.year}"
            cbq.setdefault(key, []).append(c)

        # Tally verdicts using shared scoring utilities
        v = compute_verdict_counts(claims)
        accuracy = compute_accuracy(v)
        trust = compute_trust_score(v)

        detected_patterns = self.analyzer.analyze_company(company_id, cbq)
        top = self._top_discrepancies(claims, limit=5)

        # Persist patterns to DB (clear old ones first to support re-analysis)
        if self.patterns is not None:
            self.patterns.delete_for_company(company_id)
            for p in detected_patterns:
                self.patterns.create(DiscrepancyPatternModel(
                    company_id=company_id,
                    pattern_type=p.pattern_type.value,
                    description=p.description,
                    affected_quarters=p.affected_quarters,
                    severity=p.severity,
                    evidence=p.evidence,
                ))
            self.db.commit()  # Commit pattern changes
            logger.info(
                "Persisted %d discrepancy patterns for %s",
                len(detected_patterns), company.ticker,
            )

        return CompanyAnalysis(
            company_id=company.id,
            ticker=company.ticker,
            name=company.name,
            total_claims=len(claims),
            verified_claims=v["verified"],
            approximately_correct_claims=v["approximately_correct"],
            misleading_claims=v["misleading"],
            incorrect_claims=v["incorrect"],
            unverifiable_claims=v["unverifiable"],
            overall_accuracy_rate=round(accuracy, 4),
            overall_trust_score=round(trust, 1),
            top_discrepancies=top,
            patterns=detected_patterns,
            quarters_analyzed=sorted(cbq.keys()),
        )

    def analyze_all(self) -> List[CompanyAnalysis]:
        """Run analysis for every company in the database."""
        results = []
        for c in self.companies.get_all():
            try:
                analysis = self.analyze_company(c.id)
                results.append(analysis)
            except Exception as exc:
                self.db.rollback()  # Rollback failed analysis
                logger.exception("Analysis error for company %s (rolled back): %s", c.ticker, exc)
        return results

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _top_discrepancies(claims: list[ClaimModel], limit: int = 5) -> list[dict]:
        bad: list[dict] = []
        for c in claims:
            vf = c.verification
            if vf and vf.verdict in ("misleading", "incorrect"):
                bad.append({
                    "claim_id": c.id,
                    "claim_text": c.claim_text,
                    "speaker": c.speaker,
                    "metric": c.metric,
                    "stated_value": c.stated_value,
                    "actual_value": vf.actual_value,
                    "verdict": vf.verdict,
                    "explanation": vf.explanation,
                })
        bad.sort(key=lambda d: d.get("accuracy_score", 1))
        return bad[:limit]
