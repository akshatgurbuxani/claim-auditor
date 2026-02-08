"""Company repository."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.company import CompanyModel
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[CompanyModel]):
    def __init__(self, db: Session):
        super().__init__(db, CompanyModel)

    def get_by_ticker(self, ticker: str) -> Optional[CompanyModel]:
        """Return existing company by ticker."""
        return (
            self.db.query(self.model)
            .filter(self.model.ticker == ticker.upper())
            .first()
        )

    def get_or_create(self, ticker: str, name: str, sector: str) -> CompanyModel:
        """Return existing company or create a new one (idempotent)."""
        existing = self.get_by_ticker(ticker)
        if existing:
            return existing
        return self.create(
            CompanyModel(ticker=ticker.upper(), name=name, sector=sector)
        )
