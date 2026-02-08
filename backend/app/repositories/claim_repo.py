"""Claim repository."""

from typing import List

from sqlalchemy.orm import Session, joinedload

from app.models.claim import ClaimModel
from app.models.transcript import TranscriptModel
from app.models.verification import VerificationModel
from app.repositories.base import BaseRepository


class ClaimRepository(BaseRepository[ClaimModel]):
    def __init__(self, db: Session):
        super().__init__(db, ClaimModel)

    def get_with_verification(self, claim_id: int) -> ClaimModel | None:
        return (
            self.db.query(self.model)
            .options(joinedload(self.model.verification))
            .filter(self.model.id == claim_id)
            .first()
        )

    def get_for_transcript(self, transcript_id: int) -> List[ClaimModel]:
        return (
            self.db.query(self.model)
            .options(joinedload(self.model.verification))
            .filter(self.model.transcript_id == transcript_id)
            .all()
        )

    def get_for_company(self, company_id: int) -> List[ClaimModel]:
        return (
            self.db.query(self.model)
            .join(TranscriptModel)
            .options(
                joinedload(self.model.verification),
                joinedload(self.model.transcript),
            )
            .filter(TranscriptModel.company_id == company_id)
            .order_by(TranscriptModel.year.desc(), TranscriptModel.quarter.desc())
            .all()
        )

    def get_unverified(self) -> List[ClaimModel]:
        """Claims that have no associated verification row yet."""
        return (
            self.db.query(self.model)
            .outerjoin(VerificationModel)
            .options(joinedload(self.model.transcript))
            .filter(VerificationModel.id.is_(None))
            .all()
        )

    def get_by_verdict(self, verdict: str, *, limit: int = 100) -> List[ClaimModel]:
        return (
            self.db.query(self.model)
            .join(VerificationModel)
            .options(joinedload(self.model.verification))
            .filter(VerificationModel.verdict == verdict)
            .limit(limit)
            .all()
        )
