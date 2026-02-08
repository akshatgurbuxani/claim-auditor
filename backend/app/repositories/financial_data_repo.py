"""Financial data repository."""

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.financial_data import FinancialDataModel
from app.repositories.base import BaseRepository


class FinancialDataRepository(BaseRepository[FinancialDataModel]):
    def __init__(self, db: Session):
        super().__init__(db, FinancialDataModel)

    def get_for_quarter(
        self, company_id: int, year: int, quarter: int
    ) -> Optional[FinancialDataModel]:
        return (
            self.db.query(self.model)
            .filter(
                self.model.company_id == company_id,
                self.model.year == year,
                self.model.quarter == quarter,
            )
            .first()
        )

    def count_for_company(self, company_id: int) -> int:
        """Return the number of financial data rows for a company."""
        return (
            self.db.query(self.model)
            .filter(self.model.company_id == company_id)
            .count()
        )

    def get_for_company(
        self, company_id: int, *, limit: int = 12
    ) -> List[FinancialDataModel]:
        """Return recent financial data ordered newest-first."""
        return (
            self.db.query(self.model)
            .filter(self.model.company_id == company_id)
            .order_by(self.model.year.desc(), self.model.quarter.desc())
            .limit(limit)
            .all()
        )

    def get_comparison_pair(
        self,
        company_id: int,
        year: int,
        quarter: int,
        comparison: str,
    ) -> Tuple[Optional[FinancialDataModel], Optional[FinancialDataModel]]:
        """Return (current_period, comparison_period) for verification.

        *comparison* must be one of the ComparisonPeriod enum values.
        """
        current = self.get_for_quarter(company_id, year, quarter)

        if comparison in ("year_over_year",):
            comp = self.get_for_quarter(company_id, year - 1, quarter)
        elif comparison in ("quarter_over_quarter", "sequential"):
            prev_q = quarter - 1 if quarter > 1 else 4
            prev_y = year if quarter > 1 else year - 1
            comp = self.get_for_quarter(company_id, prev_y, prev_q)
        else:
            comp = None

        return current, comp
