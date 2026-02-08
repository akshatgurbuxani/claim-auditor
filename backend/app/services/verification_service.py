"""Orchestrates verification of all unverified claims."""

import logging
from typing import Any, Dict

from app.engines.verification_engine import VerificationEngine
from app.models.verification import VerificationModel
from app.repositories.claim_repo import ClaimRepository
from app.repositories.verification_repo import VerificationRepository

logger = logging.getLogger(__name__)


class VerificationService:
    def __init__(
        self,
        verification_engine: VerificationEngine,
        claim_repo: ClaimRepository,
        verification_repo: VerificationRepository,
    ):
        self.engine = verification_engine
        self.claims = claim_repo
        self.verifications = verification_repo

    def verify_all(self) -> Dict[str, Any]:
        summary = {
            "verified": 0,
            "approximately_correct": 0,
            "misleading": 0,
            "incorrect": 0,
            "unverifiable": 0,
            "errors": 0,
        }

        for claim in self.claims.get_unverified():
            try:
                result = self.engine.verify(
                    claim=claim,
                    company_id=claim.transcript.company_id,
                    transcript_year=claim.transcript.year,
                    transcript_quarter=claim.transcript.quarter,
                )
                self.verifications.create(VerificationModel(**result.model_dump()))
                summary[result.verdict.value] += 1
            except Exception as exc:
                logger.exception("Verification error for claim %d: %s", claim.id, exc)
                summary["errors"] += 1

        return summary
