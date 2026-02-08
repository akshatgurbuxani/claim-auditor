"""Discrepancy pattern repository."""

from typing import List

from sqlalchemy.orm import Session

from app.models.discrepancy_pattern import DiscrepancyPatternModel
from app.repositories.base import BaseRepository


class DiscrepancyPatternRepository(BaseRepository[DiscrepancyPatternModel]):
    def __init__(self, db: Session):
        super().__init__(db, DiscrepancyPatternModel)

    def get_for_company(self, company_id: int) -> List[DiscrepancyPatternModel]:
        return (
            self.db.query(self.model)
            .filter(self.model.company_id == company_id)
            .order_by(self.model.severity.desc())
            .all()
        )

    def delete_for_company(self, company_id: int) -> int:
        """Delete all patterns for a company (for re-analysis). Returns count."""
        count = (
            self.db.query(self.model)
            .filter(self.model.company_id == company_id)
            .delete()
        )
        self.db.commit()
        return count

    def get_all_grouped(self) -> dict[int, List[DiscrepancyPatternModel]]:
        """Return all patterns grouped by company_id."""
        patterns = (
            self.db.query(self.model)
            .order_by(self.model.company_id, self.model.severity.desc())
            .all()
        )
        result: dict[int, List[DiscrepancyPatternModel]] = {}
        for p in patterns:
            result.setdefault(p.company_id, []).append(p)
        return result
