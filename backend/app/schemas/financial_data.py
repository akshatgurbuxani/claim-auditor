"""Financial data schemas."""

from typing import Optional

from pydantic import BaseModel


class FinancialDataBase(BaseModel):
    company_id: int
    period: str  # "Q1" … "Q4" or "FY"
    year: int
    quarter: int

    # Income Statement
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    operating_expenses: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    eps_diluted: Optional[float] = None
    ebitda: Optional[float] = None

    # Additional Income Statement
    research_and_development: Optional[float] = None
    selling_general_admin: Optional[float] = None
    interest_expense: Optional[float] = None
    income_tax_expense: Optional[float] = None

    # Cash Flow Statement
    operating_cash_flow: Optional[float] = None
    capital_expenditure: Optional[float] = None
    free_cash_flow: Optional[float] = None

    # Balance Sheet (select items)
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    shareholders_equity: Optional[float] = None


class FinancialDataCreate(FinancialDataBase):
    pass


class FinancialData(FinancialDataBase):
    id: int

    model_config = {"from_attributes": True}
