"""Transcript repository."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.claim import ClaimModel
from app.models.transcript import TranscriptModel
from app.repositories.base import BaseRepository


class TranscriptRepository(BaseRepository[TranscriptModel]):
    def __init__(self, db: Session):
        super().__init__(db, TranscriptModel)

    def get_for_quarter(
        self, company_id: int, year: int, quarter: int
    ) -> Optional[TranscriptModel]:
        return (
            self.db.query(self.model)
            .filter(
                self.model.company_id == company_id,
                self.model.year == year,
                self.model.quarter == quarter,
            )
            .first()
        )

    def get_for_company(self, company_id: int) -> List[TranscriptModel]:
        return (
            self.db.query(self.model)
            .filter(self.model.company_id == company_id)
            .order_by(self.model.year.desc(), self.model.quarter.desc())
            .all()
        )

    def get_unprocessed(self) -> List[TranscriptModel]:
        """Transcripts with no claims extracted yet."""
        return (
            self.db.query(self.model)
            .outerjoin(ClaimModel)
            .filter(ClaimModel.id.is_(None))
            .all()
        )
