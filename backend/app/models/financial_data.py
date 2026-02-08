"""Financial data ORM model."""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class FinancialDataModel(Base):
    __tablename__ = "financial_data"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "quarter", name="uq_financial_company_quarter"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    period = Column(String, nullable=False)  # "Q1" … "Q4" or "FY"
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)

    # ── Income Statement ─────────────────────────────────────────────
    revenue = Column(Float)
    cost_of_revenue = Column(Float)
    gross_profit = Column(Float)
    operating_income = Column(Float)
    operating_expenses = Column(Float)
    net_income = Column(Float)
    eps = Column(Float)
    eps_diluted = Column(Float)
    ebitda = Column(Float)

    research_and_development = Column(Float)
    selling_general_admin = Column(Float)
    interest_expense = Column(Float)
    income_tax_expense = Column(Float)

    # ── Cash Flow Statement ──────────────────────────────────────────
    operating_cash_flow = Column(Float)
    capital_expenditure = Column(Float)
    free_cash_flow = Column(Float)

    # ── Balance Sheet (select items) ─────────────────────────────────
    total_assets = Column(Float)
    total_liabilities = Column(Float)
    total_debt = Column(Float)
    cash_and_equivalents = Column(Float)
    shareholders_equity = Column(Float)

    # Relationships
    company = relationship("CompanyModel", back_populates="financial_data")

    def __repr__(self) -> str:
        return f"<FinancialData company_id={self.company_id} {self.period} {self.year}>"
