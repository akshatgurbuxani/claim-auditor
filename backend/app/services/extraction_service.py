"""Orchestrates LLM-based claim extraction for transcripts."""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.engines.claim_extractor import ClaimExtractor
from app.models.claim import ClaimModel
from app.repositories.claim_repo import ClaimRepository
from app.repositories.transcript_repo import TranscriptRepository

logger = logging.getLogger(__name__)


class ExtractionService:
    def __init__(
        self,
        db: Session,
        claim_extractor: ClaimExtractor,
        transcript_repo: TranscriptRepository,
        claim_repo: ClaimRepository,
    ):
        self.db = db
        self.extractor = claim_extractor
        self.transcripts = transcript_repo
        self.claims = claim_repo

    def extract_all(self) -> Dict[str, Any]:
        """Extract claims from every unprocessed transcript."""
        summary = {"transcripts_processed": 0, "claims_extracted": 0, "errors": 0}

        for transcript in self.transcripts.get_unprocessed():
            try:
                claims = self.extractor.extract(
                    transcript_text=transcript.full_text,
                    ticker=transcript.company.ticker,
                    quarter=transcript.quarter,
                    year=transcript.year,
                )
                for c in claims:
                    c.transcript_id = transcript.id
                    self.claims.create(ClaimModel(**c.model_dump()))

                self.db.commit()  # Commit per transcript for atomicity
                summary["transcripts_processed"] += 1
                summary["claims_extracted"] += len(claims)
            except Exception as exc:
                self.db.rollback()  # Rollback failed extraction
                logger.exception("Extraction error for transcript %d (rolled back): %s", transcript.id, exc)
                summary["errors"] += 1

        return summary

    def extract_for_transcript(self, transcript_id: int) -> List[ClaimModel]:
        """Extract claims from one specific transcript."""
        transcript = self.transcripts.get(transcript_id)
        if not transcript:
            raise ValueError(f"Transcript {transcript_id} not found")

        claims = self.extractor.extract(
            transcript_text=transcript.full_text,
            ticker=transcript.company.ticker,
            quarter=transcript.quarter,
            year=transcript.year,
        )

        result: list[ClaimModel] = []
        for c in claims:
            c.transcript_id = transcript.id
            model = self.claims.create(ClaimModel(**c.model_dump()))
            result.append(model)

        self.db.commit()  # Commit all claims for this transcript
        return result
