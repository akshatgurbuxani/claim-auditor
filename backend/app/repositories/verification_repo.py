"""Verification repository."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.verification import VerificationModel
from app.repositories.base import BaseRepository


class VerificationRepository(BaseRepository[VerificationModel]):
    def __init__(self, db: Session):
        super().__init__(db, VerificationModel)

    def get_for_claim(self, claim_id: int) -> Optional[VerificationModel]:
        return (
            self.db.query(self.model)
            .filter(self.model.claim_id == claim_id)
            .first()
        )
