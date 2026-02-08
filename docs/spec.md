# Claim Auditor — Implementation Specification

> This spec defines every class, interface, factory, and module needed to implement the system.
> It is designed to be used as a Claude Code skill — each section can be implemented independently with TDD.

---

## Table of Contents
1. [Project Structure](#project-structure)
2. [Configuration & Environment](#configuration--environment)
3. [Domain Models (Pydantic)](#domain-models)
4. [Database Models (SQLAlchemy)](#database-models)
5. [Repository Layer](#repository-layer)
6. [Data Source Clients](#data-source-clients)
7. [Claim Extraction Engine](#claim-extraction-engine)
8. [Verification Engine](#verification-engine)
9. [Discrepancy Analyzer](#discrepancy-analyzer)
10. [Service Layer (Orchestration)](#service-layer)
11. [API Layer (FastAPI)](#api-layer)
12. [Frontend Spec](#frontend-spec)
13. [Test Strategy](#test-strategy)
14. [Deployment Spec](#deployment-spec)

---

## 1. Project Structure

```
claim-auditor/
├── docs/
│   ├── doc.md                    # Approach document
│   └── spec.md                   # This file
├── backend/
│   ├── pyproject.toml            # Dependencies (Poetry)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app entry point
│   │   ├── config.py             # Settings & configuration
│   │   ├── database.py           # Database connection & session
│   │   │
│   │   ├── models/               # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── company.py
│   │   │   ├── transcript.py
│   │   │   ├── financial_data.py
│   │   │   ├── claim.py
│   │   │   ├── verification.py
│   │   │   └── discrepancy_pattern.py
│   │   │
│   │   ├── schemas/              # Pydantic schemas (API + domain)
│   │   │   ├── __init__.py
│   │   │   ├── company.py
│   │   │   ├── transcript.py
│   │   │   ├── financial_data.py
│   │   │   ├── claim.py
│   │   │   ├── verification.py
│   │   │   └── discrepancy.py
│   │   │
│   │   ├── repositories/         # Data access layer
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # Abstract base repository
│   │   │   ├── company_repo.py
│   │   │   ├── transcript_repo.py
│   │   │   ├── financial_data_repo.py
│   │   │   ├── claim_repo.py
│   │   │   └── verification_repo.py
│   │   │
│   │   ├── clients/              # External API clients
│   │   │   ├── __init__.py
│   │   │   ├── base_client.py    # Abstract HTTP client
│   │   │   ├── fmp_client.py     # Financial Modeling Prep
│   │   │   └── llm_client.py     # Claude API wrapper
│   │   │
│   │   ├── engines/              # Core business logic
│   │   │   ├── __init__.py
│   │   │   ├── claim_extractor.py
│   │   │   ├── metric_mapper.py
│   │   │   ├── verification_engine.py
│   │   │   └── discrepancy_analyzer.py
│   │   │
│   │   ├── services/             # Orchestration layer
│   │   │   ├── __init__.py
│   │   │   ├── ingestion_service.py
│   │   │   ├── extraction_service.py
│   │   │   ├── verification_service.py
│   │   │   └── analysis_service.py
│   │   │
│   │   ├── api/                  # FastAPI routers
│   │   │   ├── __init__.py
│   │   │   ├── companies.py
│   │   │   ├── transcripts.py
│   │   │   ├── claims.py
│   │   │   ├── verifications.py
│   │   │   └── pipeline.py       # Trigger full pipeline
│   │   │
│   │   └── utils/                # Shared utilities
│   │       ├── __init__.py
│   │       ├── financial_math.py  # Growth rate, margin calcs
│   │       └── text_processing.py # Transcript parsing helpers
│   │
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py            # Shared fixtures
│       ├── fixtures/              # Test data
│       │   ├── sample_transcript.txt
│       │   ├── sample_financial_data.json
│       │   └── sample_claims.json
│       ├── unit/
│       │   ├── __init__.py
│       │   ├── test_metric_mapper.py
│       │   ├── test_verification_engine.py
│       │   ├── test_claim_extractor.py
│       │   ├── test_discrepancy_analyzer.py
│       │   └── test_financial_math.py
│       ├── integration/
│       │   ├── __init__.py
│       │   ├── test_fmp_client.py
│       │   ├── test_ingestion_service.py
│       │   ├── test_extraction_service.py
│       │   └── test_verification_service.py
│       └── api/
│           ├── __init__.py
│           └── test_api_endpoints.py
│
└── frontend/
    ├── package.json
    ├── next.config.js
    ├── tailwind.config.ts
    ├── tsconfig.json
    ├── src/
    │   ├── app/
    │   │   ├── layout.tsx
    │   │   ├── page.tsx              # Dashboard
    │   │   ├── companies/
    │   │   │   └── [ticker]/
    │   │   │       └── page.tsx      # Company detail
    │   │   └── claims/
    │   │       └── [id]/
    │   │           └── page.tsx      # Claim detail
    │   ├── components/
    │   │   ├── CompanyCard.tsx
    │   │   ├── ClaimTable.tsx
    │   │   ├── VerificationBadge.tsx
    │   │   ├── TranscriptViewer.tsx
    │   │   ├── DiscrepancyChart.tsx
    │   │   └── Dashboard.tsx
    │   ├── lib/
    │   │   └── api.ts                # API client
    │   └── types/
    │       └── index.ts              # TypeScript types
    └── public/
```

---

## 2. Configuration & Environment

### `app/config.py`

```python
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""
    
    # Application
    app_name: str = "claim-auditor"
    debug: bool = False
    
    # Database
    database_url: str = "sqlite:///./data/claim_auditor.db"
    
    # Financial Modeling Prep API
    fmp_api_key: str
    fmp_base_url: str = "https://financialmodelingprep.com/api/v3"
    
    # Anthropic Claude API
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-20250514"
    
    # Processing
    max_claims_per_transcript: int = 50
    verification_tolerance: float = 0.02  # 2% tolerance for VERIFIED
    approximate_tolerance: float = 0.10   # 10% tolerance for APPROXIMATELY
    misleading_threshold: float = 0.25    # 25% off = INCORRECT
    
    # Companies to analyze
    target_tickers: list[str] = [
        "AAPL", "MSFT", "AMZN", "GOOGL", "META",
        "TSLA", "NVDA", "JPM", "NFLX", "CRM"
    ]
    
    # Quarters to analyze (most recent 4)
    target_quarters: list[tuple[int, int]] = [
        (2025, 3), (2025, 2), (2025, 1), (2024, 4)
    ]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### `.env` (template)
```
FMP_API_KEY=your_fmp_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
DATABASE_URL=sqlite:///./data/claim_auditor.db
DEBUG=true
```

---

## 3. Domain Models (Pydantic Schemas)

### `app/schemas/company.py`
```python
from pydantic import BaseModel
from typing import Optional


class CompanyBase(BaseModel):
    ticker: str
    name: str
    sector: str


class CompanyCreate(CompanyBase):
    pass


class Company(CompanyBase):
    id: int
    
    class Config:
        from_attributes = True


class CompanyWithStats(Company):
    """Company with aggregated verification statistics."""
    total_claims: int = 0
    verified_count: int = 0
    misleading_count: int = 0
    incorrect_count: int = 0
    accuracy_rate: float = 0.0  # percentage of verified+approximate claims
```

### `app/schemas/transcript.py`
```python
from pydantic import BaseModel
from datetime import date
from typing import Optional


class TranscriptBase(BaseModel):
    company_id: int
    quarter: int          # 1-4
    year: int             # e.g. 2025
    call_date: date
    full_text: str


class TranscriptCreate(TranscriptBase):
    pass


class Transcript(TranscriptBase):
    id: int
    
    class Config:
        from_attributes = True


class TranscriptSummary(BaseModel):
    """Lightweight transcript without full text."""
    id: int
    company_id: int
    ticker: str
    quarter: int
    year: int
    call_date: date
    claim_count: int = 0
```

### `app/schemas/financial_data.py`
```python
from pydantic import BaseModel
from typing import Optional


class FinancialDataBase(BaseModel):
    company_id: int
    period: str           # "Q1", "Q2", "Q3", "Q4", "FY"
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
    
    # Derived Margins (computed, not stored)
    # gross_margin, operating_margin, net_margin are computed on the fly


class FinancialDataCreate(FinancialDataBase):
    pass


class FinancialData(FinancialDataBase):
    id: int
    
    class Config:
        from_attributes = True
    
    @property
    def gross_margin(self) -> Optional[float]:
        if self.gross_profit and self.revenue and self.revenue != 0:
            return self.gross_profit / self.revenue
        return None
    
    @property
    def operating_margin(self) -> Optional[float]:
        if self.operating_income and self.revenue and self.revenue != 0:
            return self.operating_income / self.revenue
        return None
    
    @property
    def net_margin(self) -> Optional[float]:
        if self.net_income and self.revenue and self.revenue != 0:
            return self.net_income / self.revenue
        return None
```

### `app/schemas/claim.py`
```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class MetricType(str, Enum):
    ABSOLUTE = "absolute"           # "$5B in revenue"
    GROWTH_RATE = "growth_rate"     # "grew 15%"
    MARGIN = "margin"               # "operating margin of 30%"
    RATIO = "ratio"                 # "debt-to-equity of 0.5"
    CHANGE = "change"               # "expanded 200 basis points"
    PER_SHARE = "per_share"         # "EPS of $2.50"


class ComparisonPeriod(str, Enum):
    YOY = "year_over_year"          # Q3 2025 vs Q3 2024
    QOQ = "quarter_over_quarter"    # Q3 2025 vs Q2 2025
    SEQUENTIAL = "sequential"       # same as QoQ
    FULL_YEAR = "full_year"         # FY 2025 vs FY 2024
    CUSTOM = "custom"               # non-standard comparison
    NONE = "none"                   # standalone figure, no comparison


class ClaimBase(BaseModel):
    transcript_id: int
    speaker: str                    # "Tim Cook, CEO"
    speaker_role: Optional[str] = None  # "CEO", "CFO", etc.
    claim_text: str                 # Original verbatim text
    
    # Structured claim fields
    metric: str                     # "revenue", "eps", "operating_margin"
    metric_type: MetricType
    stated_value: float             # The number they claimed
    unit: str                       # "percent", "usd", "usd_billions", "basis_points"
    
    comparison_period: ComparisonPeriod = ComparisonPeriod.NONE
    comparison_basis: Optional[str] = None  # "Q3 2025 vs Q3 2024"
    
    is_gaap: bool = True            # False if explicitly non-GAAP/adjusted
    segment: Optional[str] = None   # None = total company, else segment name
    
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)  # LLM extraction confidence
    context_snippet: Optional[str] = None  # Surrounding transcript text


class ClaimCreate(ClaimBase):
    pass


class Claim(ClaimBase):
    id: int
    
    class Config:
        from_attributes = True


class ClaimWithVerification(Claim):
    """Claim with its verification result attached."""
    verification: Optional["Verification"] = None
```

### `app/schemas/verification.py`
```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Verdict(str, Enum):
    VERIFIED = "verified"               # Within 2% — accurate
    APPROXIMATELY_CORRECT = "approximately_correct"  # Within 10% — close
    MISLEADING = "misleading"           # 10-25% off or framing issue
    INCORRECT = "incorrect"             # >25% off — materially wrong
    UNVERIFIABLE = "unverifiable"       # Cannot find matching data


class MisleadingFlag(str, Enum):
    GAAP_NONGAAP_MISMATCH = "gaap_nongaap_mismatch"
    CHERRY_PICKED_PERIOD = "cherry_picked_period"
    SEGMENT_VS_TOTAL = "segment_vs_total"
    ROUNDING_BIAS = "rounding_bias"
    MISLEADING_COMPARISON = "misleading_comparison"
    OMITS_CONTEXT = "omits_context"


class VerificationBase(BaseModel):
    claim_id: int
    
    actual_value: Optional[float] = None       # What the financial data says
    accuracy_score: Optional[float] = None     # 0-1, how close the claim is
    
    verdict: Verdict
    explanation: str                            # Human-readable explanation
    
    # What data was used for verification
    financial_data_source: Optional[str] = None   # e.g. "income_statement.revenue Q3 2025"
    financial_data_id: Optional[int] = None
    comparison_data_id: Optional[int] = None       # For growth rate claims
    
    misleading_flags: list[MisleadingFlag] = []
    misleading_details: Optional[str] = None       # Explanation of misleading flags


class VerificationCreate(VerificationBase):
    pass


class Verification(VerificationBase):
    id: int
    
    class Config:
        from_attributes = True
```

### `app/schemas/discrepancy.py`
```python
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class PatternType(str, Enum):
    CONSISTENT_ROUNDING_UP = "consistent_rounding_up"
    METRIC_SWITCHING = "metric_switching"          # Changes what they highlight
    INCREASING_INACCURACY = "increasing_inaccuracy"
    GAAP_NONGAAP_SHIFTING = "gaap_nongaap_shifting"
    SELECTIVE_EMPHASIS = "selective_emphasis"


class DiscrepancyPattern(BaseModel):
    """Quarter-to-quarter pattern detected across a company's earnings calls."""
    id: int
    company_id: int
    pattern_type: PatternType
    description: str
    affected_quarters: list[str]      # e.g. ["Q1 2025", "Q2 2025"]
    severity: float                   # 0-1
    evidence: list[str]               # Supporting claim IDs or descriptions
    
    class Config:
        from_attributes = True


class CompanyAnalysis(BaseModel):
    """Complete analysis report for a company."""
    company_id: int
    ticker: str
    name: str
    
    total_claims: int
    verified_claims: int
    approximately_correct_claims: int
    misleading_claims: int
    incorrect_claims: int
    unverifiable_claims: int
    
    overall_accuracy_rate: float      # (verified + approx) / total_verifiable
    overall_trust_score: float        # Weighted score 0-100
    
    top_discrepancies: list[dict]     # Worst claims
    patterns: list[DiscrepancyPattern]  # Quarter-to-quarter patterns
    
    quarters_analyzed: list[str]
```

---

## 4. Database Models (SQLAlchemy)

### `app/database.py`
```python
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase

class Base(DeclarativeBase):
    pass

# Sync engine for simplicity (can migrate to async later)
engine = create_engine(settings.database_url, echo=settings.debug)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
```

### `app/models/company.py`
```python
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class CompanyModel(Base):
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    sector = Column(String, nullable=False)
    
    transcripts = relationship("TranscriptModel", back_populates="company")
    financial_data = relationship("FinancialDataModel", back_populates="company")
```

### `app/models/transcript.py`
```python
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class TranscriptModel(Base):
    __tablename__ = "transcripts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    quarter = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    call_date = Column(Date, nullable=False)
    full_text = Column(Text, nullable=False)
    
    company = relationship("CompanyModel", back_populates="transcripts")
    claims = relationship("ClaimModel", back_populates="transcript")
```

### `app/models/financial_data.py`
```python
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class FinancialDataModel(Base):
    __tablename__ = "financial_data"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    period = Column(String, nullable=False)    # Q1, Q2, Q3, Q4, FY
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    
    # Income Statement
    revenue = Column(Float)
    cost_of_revenue = Column(Float)
    gross_profit = Column(Float)
    operating_income = Column(Float)
    operating_expenses = Column(Float)
    net_income = Column(Float)
    eps = Column(Float)
    eps_diluted = Column(Float)
    ebitda = Column(Float)
    
    # Additional
    research_and_development = Column(Float)
    selling_general_admin = Column(Float)
    interest_expense = Column(Float)
    income_tax_expense = Column(Float)
    
    # Cash Flow
    operating_cash_flow = Column(Float)
    capital_expenditure = Column(Float)
    free_cash_flow = Column(Float)
    
    # Balance Sheet
    total_assets = Column(Float)
    total_liabilities = Column(Float)
    total_debt = Column(Float)
    cash_and_equivalents = Column(Float)
    shareholders_equity = Column(Float)
    
    company = relationship("CompanyModel", back_populates="financial_data")
```

### `app/models/claim.py`
```python
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ClaimModel(Base):
    __tablename__ = "claims"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    transcript_id = Column(Integer, ForeignKey("transcripts.id"), nullable=False)
    
    speaker = Column(String, nullable=False)
    speaker_role = Column(String)
    claim_text = Column(Text, nullable=False)
    
    metric = Column(String, nullable=False)
    metric_type = Column(String, nullable=False)
    stated_value = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    
    comparison_period = Column(String, default="none")
    comparison_basis = Column(String)
    
    is_gaap = Column(Boolean, default=True)
    segment = Column(String)
    
    confidence = Column(Float, default=0.8)
    context_snippet = Column(Text)
    
    transcript = relationship("TranscriptModel", back_populates="claims")
    verification = relationship("VerificationModel", back_populates="claim", uselist=False)
```

### `app/models/verification.py`
```python
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class VerificationModel(Base):
    __tablename__ = "verifications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False, unique=True)
    
    actual_value = Column(Float)
    accuracy_score = Column(Float)
    
    verdict = Column(String, nullable=False)
    explanation = Column(Text, nullable=False)
    
    financial_data_source = Column(String)
    financial_data_id = Column(Integer, ForeignKey("financial_data.id"))
    comparison_data_id = Column(Integer, ForeignKey("financial_data.id"))
    
    misleading_flags = Column(JSON, default=[])
    misleading_details = Column(Text)
    
    claim = relationship("ClaimModel", back_populates="verification")
```

---

## 5. Repository Layer

### `app/repositories/base.py`
```python
from typing import TypeVar, Generic, Type, Optional, List
from sqlalchemy.orm import Session
from app.database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Abstract base repository with common CRUD operations."""
    
    def __init__(self, db: Session, model: Type[T]):
        self.db = db
        self.model = model
    
    def get(self, id: int) -> Optional[T]:
        return self.db.query(self.model).filter(self.model.id == id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        return self.db.query(self.model).offset(skip).limit(limit).all()
    
    def create(self, obj: T) -> T:
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
    
    def create_many(self, objs: List[T]) -> List[T]:
        self.db.add_all(objs)
        self.db.commit()
        for obj in objs:
            self.db.refresh(obj)
        return objs
    
    def update(self, obj: T) -> T:
        self.db.commit()
        self.db.refresh(obj)
        return obj
    
    def delete(self, id: int) -> bool:
        obj = self.get(id)
        if obj:
            self.db.delete(obj)
            self.db.commit()
            return True
        return False
```

### `app/repositories/company_repo.py`
```python
class CompanyRepository(BaseRepository[CompanyModel]):
    
    def __init__(self, db: Session):
        super().__init__(db, CompanyModel)
    
    def get_by_ticker(self, ticker: str) -> Optional[CompanyModel]:
        return self.db.query(self.model).filter(
            self.model.ticker == ticker.upper()
        ).first()
    
    def get_or_create(self, ticker: str, name: str, sector: str) -> CompanyModel:
        existing = self.get_by_ticker(ticker)
        if existing:
            return existing
        return self.create(CompanyModel(ticker=ticker.upper(), name=name, sector=sector))
```

### `app/repositories/financial_data_repo.py`
```python
class FinancialDataRepository(BaseRepository[FinancialDataModel]):
    
    def __init__(self, db: Session):
        super().__init__(db, FinancialDataModel)
    
    def get_for_quarter(
        self, company_id: int, year: int, quarter: int
    ) -> Optional[FinancialDataModel]:
        return self.db.query(self.model).filter(
            self.model.company_id == company_id,
            self.model.year == year,
            self.model.quarter == quarter
        ).first()
    
    def get_for_company(
        self, company_id: int, limit: int = 8
    ) -> List[FinancialDataModel]:
        """Get recent financial data for a company, ordered by date."""
        return self.db.query(self.model).filter(
            self.model.company_id == company_id
        ).order_by(
            self.model.year.desc(), self.model.quarter.desc()
        ).limit(limit).all()
    
    def get_comparison_pair(
        self, company_id: int, year: int, quarter: int, comparison: str
    ) -> tuple[Optional[FinancialDataModel], Optional[FinancialDataModel]]:
        """Get current and comparison period data for verification.
        
        Returns: (current_period, comparison_period)
        """
        current = self.get_for_quarter(company_id, year, quarter)
        
        if comparison == "year_over_year":
            comparison_data = self.get_for_quarter(company_id, year - 1, quarter)
        elif comparison in ("quarter_over_quarter", "sequential"):
            prev_q = quarter - 1 if quarter > 1 else 4
            prev_y = year if quarter > 1 else year - 1
            comparison_data = self.get_for_quarter(company_id, prev_y, prev_q)
        else:
            comparison_data = None
        
        return current, comparison_data
```

### `app/repositories/claim_repo.py`
```python
class ClaimRepository(BaseRepository[ClaimModel]):
    
    def __init__(self, db: Session):
        super().__init__(db, ClaimModel)
    
    def get_for_transcript(self, transcript_id: int) -> List[ClaimModel]:
        return self.db.query(self.model).filter(
            self.model.transcript_id == transcript_id
        ).all()
    
    def get_for_company(self, company_id: int) -> List[ClaimModel]:
        return self.db.query(self.model).join(TranscriptModel).filter(
            TranscriptModel.company_id == company_id
        ).all()
    
    def get_unverified(self) -> List[ClaimModel]:
        """Get claims that don't have a verification yet."""
        return self.db.query(self.model).outerjoin(
            VerificationModel
        ).filter(
            VerificationModel.id == None
        ).all()
```

---

## 6. Data Source Clients

### `app/clients/base_client.py`
```python
from abc import ABC, abstractmethod
import httpx
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseHTTPClient(ABC):
    """Abstract base for all external API clients."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=30.0)
    
    def _get(self, endpoint: str, params: dict = None) -> Any:
        """Make a GET request with error handling and logging."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        params = params or {}
        if self.api_key:
            params["apikey"] = self.api_key
        
        logger.info(f"GET {url}")
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def close(self):
        self._client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
```

### `app/clients/fmp_client.py`

```python
from dataclasses import dataclass
from typing import Optional
from datetime import date


@dataclass
class FMPTranscript:
    """Raw transcript data from FMP API."""
    ticker: str
    quarter: int
    year: int
    date: date
    content: str


@dataclass
class FMPFinancialData:
    """Raw financial data from FMP API."""
    ticker: str
    period: str
    year: int
    quarter: int
    # All financial fields matching our schema


class FMPClient(BaseHTTPClient):
    """Client for Financial Modeling Prep API.
    
    API Docs: https://financialmodelingprep.com/developer/docs
    
    Endpoints used:
    - /earning_call_transcript/{ticker}?quarter={q}&year={y}
    - /income-statement/{ticker}?period=quarter
    - /cash-flow-statement/{ticker}?period=quarter
    - /balance-sheet-statement/{ticker}?period=quarter
    """
    
    def __init__(self, api_key: str):
        super().__init__(
            base_url="https://financialmodelingprep.com/api/v3",
            api_key=api_key
        )
    
    def get_transcript(
        self, ticker: str, quarter: int, year: int
    ) -> Optional[FMPTranscript]:
        """Fetch a single earnings call transcript.
        
        Returns None if no transcript found for the given quarter.
        """
        data = self._get(
            f"earning_call_transcript/{ticker.upper()}",
            params={"quarter": quarter, "year": year}
        )
        
        if not data:
            return None
        
        # FMP returns a list; take the first entry
        entry = data[0] if isinstance(data, list) else data
        
        return FMPTranscript(
            ticker=ticker.upper(),
            quarter=quarter,
            year=year,
            date=date.fromisoformat(entry.get("date", "").split(" ")[0]),
            content=entry.get("content", "")
        )
    
    def get_income_statement(
        self, ticker: str, period: str = "quarter", limit: int = 8
    ) -> list[dict]:
        """Fetch quarterly income statements."""
        return self._get(
            f"income-statement/{ticker.upper()}",
            params={"period": period, "limit": limit}
        )
    
    def get_cash_flow_statement(
        self, ticker: str, period: str = "quarter", limit: int = 8
    ) -> list[dict]:
        """Fetch quarterly cash flow statements."""
        return self._get(
            f"cash-flow-statement/{ticker.upper()}",
            params={"period": period, "limit": limit}
        )
    
    def get_balance_sheet(
        self, ticker: str, period: str = "quarter", limit: int = 8
    ) -> list[dict]:
        """Fetch quarterly balance sheets."""
        return self._get(
            f"balance-sheet-statement/{ticker.upper()}",
            params={"period": period, "limit": limit}
        )
    
    def get_company_profile(self, ticker: str) -> dict:
        """Fetch company profile (name, sector, etc.)."""
        data = self._get(f"profile/{ticker.upper()}")
        return data[0] if isinstance(data, list) and data else {}
```

### `app/clients/llm_client.py`

```python
import anthropic
from typing import Any


class LLMClient:
    """Wrapper around Anthropic Claude API for structured extraction.
    
    Responsibilities:
    - Send prompts with structured output expectations
    - Parse and validate JSON responses  
    - Handle rate limiting and retries
    - Track token usage for cost awareness
    """
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.total_input_tokens = 0
        self.total_output_tokens = 0
    
    def extract_claims(
        self, 
        transcript_text: str,
        ticker: str,
        quarter: int,
        year: int,
        system_prompt: str,
    ) -> list[dict]:
        """Extract quantitative claims from a transcript.
        
        Args:
            transcript_text: Full transcript text
            ticker: Company ticker symbol
            quarter: Fiscal quarter (1-4)
            year: Fiscal year
            system_prompt: The extraction system prompt
        
        Returns:
            List of claim dictionaries matching ClaimCreate schema
        """
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this {ticker} Q{quarter} {year} earnings call transcript.
                    
Extract ALL quantitative claims made by management (CEO, CFO, etc.).

Transcript:
{transcript_text}"""
                }
            ]
        )
        
        self.total_input_tokens += message.usage.input_tokens
        self.total_output_tokens += message.usage.output_tokens
        
        # Parse the JSON response
        return self._parse_claims_response(message.content[0].text)
    
    def _parse_claims_response(self, response_text: str) -> list[dict]:
        """Parse LLM response into structured claim dicts.
        
        Handles:
        - JSON array responses
        - JSON wrapped in markdown code blocks
        - Partial/malformed JSON (graceful degradation)
        """
        import json
        import re
        
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        
        # Try direct JSON parse
        try:
            result = json.loads(response_text)
            return result if isinstance(result, list) else [result]
        except json.JSONDecodeError:
            # Try to find JSON array in the response
            array_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if array_match:
                return json.loads(array_match.group(0))
            raise ValueError(f"Could not parse claims from LLM response: {response_text[:200]}")
```

---

## 7. Claim Extraction Engine

### `app/engines/claim_extractor.py`

```python
class ClaimExtractor:
    """Extracts quantitative claims from earnings call transcripts using LLM.
    
    Design Decisions:
    - Uses Claude for extraction (best at structured output)
    - Two-pass approach: extract candidates, then validate structure
    - Confidence scoring based on LLM's own assessment
    - Deduplication of claims that appear multiple times
    
    The system prompt is the core IP of this engine.
    """
    
    SYSTEM_PROMPT = '''You are a financial analyst AI that extracts quantitative claims 
from earnings call transcripts. 

A "quantitative claim" is any statement by management that includes a specific number, 
percentage, or measurable comparison about the company's financial performance.

EXTRACT claims that are:
- Revenue figures or growth rates
- Earnings per share (EPS) 
- Profit margins (gross, operating, net)
- Cash flow figures
- Growth rates (YoY, QoQ)
- Guidance figures
- Expense figures
- Any other quantitative financial metrics

DO NOT extract:
- Vague qualitative statements ("strong performance")
- Forward-looking projections without specific numbers
- Analyst questions (only management statements)
- Non-financial operational metrics (unless tied to financials)

For each claim, output a JSON array of objects with these EXACT fields:
{
  "speaker": "Name, Title",
  "speaker_role": "CEO|CFO|COO|Other",
  "claim_text": "exact verbatim quote containing the claim",
  "metric": "one of: revenue, cost_of_revenue, gross_profit, gross_margin, operating_income, operating_margin, operating_expenses, net_income, net_margin, eps, eps_diluted, ebitda, research_and_development, selling_general_admin, operating_cash_flow, free_cash_flow, capital_expenditure, total_debt, cash_and_equivalents",
  "metric_type": "absolute|growth_rate|margin|ratio|change|per_share",
  "stated_value": <number>,
  "unit": "usd|usd_millions|usd_billions|percent|basis_points|ratio|shares",
  "comparison_period": "year_over_year|quarter_over_quarter|sequential|full_year|custom|none",
  "comparison_basis": "Q3 2025 vs Q3 2024" or null,
  "is_gaap": true or false,
  "segment": null or "segment name",
  "confidence": 0.0-1.0,
  "context_snippet": "1-2 sentences of surrounding context"
}

IMPORTANT:
- stated_value should be the raw number (15 for 15%, not 0.15)
- For dollar amounts, normalize to the unit specified (e.g., if they say "$5 billion", use stated_value=5 and unit="usd_billions")
- If they say "non-GAAP" or "adjusted" or "excluding items", set is_gaap=false
- confidence reflects how certain you are about the extraction accuracy
- Only include claims from management speakers (CEO, CFO, etc.), not analysts

Output ONLY the JSON array, no other text.'''
    
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
    
    def extract(
        self, 
        transcript_text: str, 
        ticker: str, 
        quarter: int, 
        year: int
    ) -> list[ClaimCreate]:
        """Extract claims from a transcript and return structured ClaimCreate objects.
        
        Steps:
        1. Send transcript to LLM with system prompt
        2. Parse response into raw claim dicts
        3. Validate and convert to ClaimCreate objects
        4. Deduplicate
        5. Return sorted by position in transcript
        """
        raw_claims = self.llm.extract_claims(
            transcript_text=transcript_text,
            ticker=ticker,
            quarter=quarter,
            year=year,
            system_prompt=self.SYSTEM_PROMPT
        )
        
        # Validate and convert
        valid_claims = []
        for raw in raw_claims:
            try:
                claim = self._validate_and_convert(raw)
                valid_claims.append(claim)
            except (ValueError, KeyError) as e:
                logger.warning(f"Skipping invalid claim: {e}")
                continue
        
        # Deduplicate
        return self._deduplicate(valid_claims)
    
    def _validate_and_convert(self, raw: dict) -> ClaimCreate:
        """Validate raw claim dict and convert to ClaimCreate."""
        # Normalize metric name
        raw["metric"] = self._normalize_metric(raw.get("metric", ""))
        
        # Validate metric_type
        raw["metric_type"] = MetricType(raw.get("metric_type", "absolute"))
        
        # Validate comparison_period
        raw["comparison_period"] = ComparisonPeriod(
            raw.get("comparison_period", "none")
        )
        
        return ClaimCreate(**raw)
    
    def _normalize_metric(self, metric: str) -> str:
        """Normalize metric names to our canonical set."""
        METRIC_ALIASES = {
            "total revenue": "revenue",
            "net revenue": "revenue",
            "sales": "revenue",
            "top line": "revenue",
            "earnings per share": "eps",
            "diluted eps": "eps_diluted",
            "diluted earnings per share": "eps_diluted",
            "op income": "operating_income",
            "operating profit": "operating_income",
            "op margin": "operating_margin",
            "gross margin": "gross_margin",
            "net margin": "net_margin",
            "profit margin": "net_margin",
            "fcf": "free_cash_flow",
            "capex": "capital_expenditure",
            "r&d": "research_and_development",
            "sg&a": "selling_general_admin",
            "cash": "cash_and_equivalents",
            "debt": "total_debt",
        }
        normalized = metric.lower().strip()
        return METRIC_ALIASES.get(normalized, normalized)
    
    def _deduplicate(self, claims: list[ClaimCreate]) -> list[ClaimCreate]:
        """Remove duplicate claims (same metric + same value)."""
        seen = set()
        unique = []
        for claim in claims:
            key = (claim.metric, claim.stated_value, claim.comparison_period)
            if key not in seen:
                seen.add(key)
                unique.append(claim)
        return unique
```

---

## 8. Verification Engine

### `app/engines/metric_mapper.py`

```python
class MetricMapper:
    """Maps claim metrics to financial data fields.
    
    This is the bridge between natural language claims and structured data.
    Handles aliases, derived metrics, and segment-level data.
    """
    
    # Direct field mappings: claim_metric -> financial_data field name
    DIRECT_MAPPINGS: dict[str, str] = {
        "revenue": "revenue",
        "cost_of_revenue": "cost_of_revenue",
        "gross_profit": "gross_profit",
        "operating_income": "operating_income",
        "operating_expenses": "operating_expenses",
        "net_income": "net_income",
        "eps": "eps",
        "eps_diluted": "eps_diluted",
        "ebitda": "ebitda",
        "research_and_development": "research_and_development",
        "selling_general_admin": "selling_general_admin",
        "interest_expense": "interest_expense",
        "income_tax_expense": "income_tax_expense",
        "operating_cash_flow": "operating_cash_flow",
        "capital_expenditure": "capital_expenditure",
        "free_cash_flow": "free_cash_flow",
        "total_assets": "total_assets",
        "total_liabilities": "total_liabilities",
        "total_debt": "total_debt",
        "cash_and_equivalents": "cash_and_equivalents",
        "shareholders_equity": "shareholders_equity",
    }
    
    # Derived metrics that require computation
    DERIVED_MAPPINGS: dict[str, tuple[str, str]] = {
        "gross_margin": ("gross_profit", "revenue"),           # gross_profit / revenue
        "operating_margin": ("operating_income", "revenue"),   # operating_income / revenue
        "net_margin": ("net_income", "revenue"),               # net_income / revenue
    }
    
    def resolve(
        self, 
        metric: str, 
        financial_data: FinancialDataModel
    ) -> Optional[float]:
        """Resolve a metric name to its actual value from financial data.
        
        Returns None if the metric cannot be resolved.
        """
        # Check direct mappings
        if metric in self.DIRECT_MAPPINGS:
            field_name = self.DIRECT_MAPPINGS[metric]
            return getattr(financial_data, field_name, None)
        
        # Check derived mappings
        if metric in self.DERIVED_MAPPINGS:
            numerator_field, denominator_field = self.DERIVED_MAPPINGS[metric]
            numerator = getattr(financial_data, numerator_field, None)
            denominator = getattr(financial_data, denominator_field, None)
            
            if numerator is not None and denominator is not None and denominator != 0:
                return (numerator / denominator) * 100  # Return as percentage
            return None
        
        return None
    
    def can_resolve(self, metric: str) -> bool:
        """Check if we can resolve this metric."""
        return metric in self.DIRECT_MAPPINGS or metric in self.DERIVED_MAPPINGS
```

### `app/engines/verification_engine.py`

```python
class VerificationEngine:
    """Core verification logic: compares claimed values to actual financial data.
    
    Design decisions:
    - Tolerance-based scoring (not binary correct/incorrect)
    - Different handling for absolute values vs growth rates
    - Unit normalization before comparison
    - Misleading framing detection beyond just number comparison
    """
    
    def __init__(
        self,
        metric_mapper: MetricMapper,
        financial_repo: FinancialDataRepository,
        settings: Settings,
    ):
        self.mapper = metric_mapper
        self.financial_repo = financial_repo
        self.tolerance_verified = settings.verification_tolerance     # 0.02
        self.tolerance_approximate = settings.approximate_tolerance   # 0.10
        self.threshold_misleading = settings.misleading_threshold     # 0.25
    
    def verify(
        self, 
        claim: ClaimModel, 
        company_id: int,
        transcript_year: int,
        transcript_quarter: int,
    ) -> VerificationCreate:
        """Verify a single claim against financial data.
        
        Strategy:
        1. Check if we can resolve the metric
        2. Fetch the relevant financial data
        3. Compute actual value (handling growth rates, margins, etc.)
        4. Compare stated vs actual
        5. Score and assign verdict
        6. Check for misleading framing
        """
        
        # Step 1: Can we resolve this metric?
        if not self.mapper.can_resolve(claim.metric):
            return VerificationCreate(
                claim_id=claim.id,
                verdict=Verdict.UNVERIFIABLE,
                explanation=f"Metric '{claim.metric}' cannot be mapped to available financial data."
            )
        
        # Step 2: Fetch financial data
        if claim.metric_type in (MetricType.GROWTH_RATE, MetricType.CHANGE):
            actual_value = self._verify_growth_claim(
                claim, company_id, transcript_year, transcript_quarter
            )
        elif claim.metric_type == MetricType.MARGIN:
            actual_value = self._verify_margin_claim(
                claim, company_id, transcript_year, transcript_quarter
            )
        elif claim.metric_type in (MetricType.ABSOLUTE, MetricType.PER_SHARE):
            actual_value = self._verify_absolute_claim(
                claim, company_id, transcript_year, transcript_quarter
            )
        else:
            actual_value = None
        
        if actual_value is None:
            return VerificationCreate(
                claim_id=claim.id,
                verdict=Verdict.UNVERIFIABLE,
                explanation=f"Could not find financial data to verify this claim."
            )
        
        # Step 3: Normalize and compare
        stated = self._normalize_value(claim.stated_value, claim.unit)
        actual = actual_value  # Already normalized by verify methods
        
        # Step 4: Score
        accuracy_score = self._compute_accuracy(stated, actual)
        verdict = self._assign_verdict(accuracy_score)
        
        # Step 5: Check misleading framing
        misleading_flags = self._check_misleading_flags(claim, stated, actual, accuracy_score)
        if misleading_flags and verdict in (Verdict.VERIFIED, Verdict.APPROXIMATELY_CORRECT):
            verdict = Verdict.MISLEADING  # Upgrade severity if framing issues found
        
        # Step 6: Build explanation
        explanation = self._build_explanation(claim, stated, actual, accuracy_score, verdict)
        
        return VerificationCreate(
            claim_id=claim.id,
            actual_value=actual,
            accuracy_score=accuracy_score,
            verdict=verdict,
            explanation=explanation,
            misleading_flags=misleading_flags,
        )
    
    def _verify_growth_claim(
        self, claim, company_id, year, quarter
    ) -> Optional[float]:
        """Verify a growth rate claim (e.g., 'revenue grew 15% YoY').
        
        Computes actual growth rate from two periods of financial data.
        """
        current, comparison = self.financial_repo.get_comparison_pair(
            company_id, year, quarter, claim.comparison_period
        )
        
        if not current or not comparison:
            return None
        
        current_value = self.mapper.resolve(claim.metric, current)
        comparison_value = self.mapper.resolve(claim.metric, comparison)
        
        if current_value is None or comparison_value is None or comparison_value == 0:
            return None
        
        # Compute actual growth rate as percentage
        return ((current_value - comparison_value) / abs(comparison_value)) * 100
    
    def _verify_margin_claim(
        self, claim, company_id, year, quarter
    ) -> Optional[float]:
        """Verify a margin claim (e.g., 'operating margin of 30%')."""
        data = self.financial_repo.get_for_quarter(company_id, year, quarter)
        if not data:
            return None
        
        return self.mapper.resolve(claim.metric, data)
    
    def _verify_absolute_claim(
        self, claim, company_id, year, quarter
    ) -> Optional[float]:
        """Verify an absolute value claim (e.g., 'revenue was $5 billion')."""
        data = self.financial_repo.get_for_quarter(company_id, year, quarter)
        if not data:
            return None
        
        value = self.mapper.resolve(claim.metric, data)
        if value is None:
            return None
        
        # Normalize to match the claim's unit
        return self._normalize_financial_value(value, claim.unit)
    
    def _normalize_value(self, value: float, unit: str) -> float:
        """Normalize a claimed value to a standard unit for comparison."""
        # For percentage claims, value is already in percentage points
        if unit in ("percent", "basis_points"):
            if unit == "basis_points":
                return value / 100  # Convert bps to percentage
            return value
        
        # For dollar amounts, normalize to raw dollars
        if unit == "usd_billions":
            return value * 1_000_000_000
        elif unit == "usd_millions":
            return value * 1_000_000
        elif unit == "usd":
            return value
        
        return value
    
    def _normalize_financial_value(self, value: float, target_unit: str) -> float:
        """Convert financial data (raw dollars) to the claim's unit."""
        if target_unit == "usd_billions":
            return value / 1_000_000_000
        elif target_unit == "usd_millions":
            return value / 1_000_000
        return value
    
    def _compute_accuracy(self, stated: float, actual: float) -> float:
        """Compute accuracy score between 0 and 1.
        
        1.0 = perfect match, 0.0 = completely wrong
        """
        if actual == 0:
            return 0.0 if stated != 0 else 1.0
        
        return max(0.0, 1.0 - abs(stated - actual) / abs(actual))
    
    def _assign_verdict(self, accuracy_score: float) -> Verdict:
        """Assign a verdict based on accuracy score."""
        if accuracy_score >= (1 - self.tolerance_verified):
            return Verdict.VERIFIED
        elif accuracy_score >= (1 - self.tolerance_approximate):
            return Verdict.APPROXIMATELY_CORRECT
        elif accuracy_score >= (1 - self.threshold_misleading):
            return Verdict.MISLEADING
        else:
            return Verdict.INCORRECT
    
    def _check_misleading_flags(
        self, claim, stated, actual, accuracy_score
    ) -> list[MisleadingFlag]:
        """Detect misleading framing beyond simple number comparison."""
        flags = []
        
        # Check rounding bias (always rounding favorably)
        if accuracy_score < 0.98 and accuracy_score >= 0.90:
            # Check if the rounding direction is favorable
            if (stated > actual and stated > 0) or (stated < actual and stated < 0):
                flags.append(MisleadingFlag.ROUNDING_BIAS)
        
        # Check GAAP vs non-GAAP issues
        if not claim.is_gaap:
            flags.append(MisleadingFlag.GAAP_NONGAAP_MISMATCH)
        
        # Check segment vs total
        if claim.segment:
            flags.append(MisleadingFlag.SEGMENT_VS_TOTAL)
        
        return flags
    
    def _build_explanation(
        self, claim, stated, actual, accuracy_score, verdict
    ) -> str:
        """Generate human-readable explanation of the verification."""
        pct_diff = ((stated - actual) / abs(actual)) * 100 if actual != 0 else 0
        
        if verdict == Verdict.VERIFIED:
            return (
                f"Claim verified. Management stated {stated:.2f}, "
                f"actual was {actual:.2f} ({pct_diff:+.1f}% difference). "
                f"Within acceptable tolerance."
            )
        elif verdict == Verdict.APPROXIMATELY_CORRECT:
            return (
                f"Approximately correct. Management stated {stated:.2f}, "
                f"actual was {actual:.2f} ({pct_diff:+.1f}% difference)."
            )
        elif verdict == Verdict.MISLEADING:
            return (
                f"Misleading. Management stated {stated:.2f}, "
                f"actual was {actual:.2f} ({pct_diff:+.1f}% difference). "
                f"The framing may create a false impression."
            )
        elif verdict == Verdict.INCORRECT:
            return (
                f"Incorrect. Management stated {stated:.2f}, "
                f"actual was {actual:.2f} ({pct_diff:+.1f}% difference). "
                f"This is materially inaccurate."
            )
        else:
            return "Cannot verify: insufficient data."
```

### `app/utils/financial_math.py`

```python
"""Financial calculation utilities used across the verification engine."""


def growth_rate(current: float, previous: float) -> Optional[float]:
    """Calculate growth rate as a percentage.
    
    Returns None if previous is 0 (undefined growth).
    
    Examples:
        growth_rate(115, 100) == 15.0
        growth_rate(85, 100) == -15.0
    """
    if previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100


def margin(numerator: float, denominator: float) -> Optional[float]:
    """Calculate a margin/ratio as a percentage.
    
    Examples:
        margin(30, 100) == 30.0
        margin(0, 100) == 0.0
    """
    if denominator == 0:
        return None
    return (numerator / denominator) * 100


def basis_points_to_percentage(bps: float) -> float:
    """Convert basis points to percentage points.
    
    Examples:
        basis_points_to_percentage(200) == 2.0
        basis_points_to_percentage(50) == 0.5
    """
    return bps / 100


def normalize_to_unit(value: float, unit: str) -> float:
    """Normalize a raw dollar value to the specified unit.
    
    Examples:
        normalize_to_unit(5_000_000_000, "usd_billions") == 5.0
        normalize_to_unit(5_000_000, "usd_millions") == 5.0
    """
    if unit == "usd_billions":
        return value / 1_000_000_000
    elif unit == "usd_millions":
        return value / 1_000_000
    return value


def accuracy_score(stated: float, actual: float) -> float:
    """Compute accuracy score between 0.0 and 1.0.
    
    Examples:
        accuracy_score(15.0, 15.0) == 1.0
        accuracy_score(15.0, 14.0) ≈ 0.929
        accuracy_score(15.0, 10.0) == 0.5
    """
    if actual == 0:
        return 0.0 if stated != 0 else 1.0
    return max(0.0, 1.0 - abs(stated - actual) / abs(actual))
```

---

## 9. Discrepancy Analyzer (Bonus)

### `app/engines/discrepancy_analyzer.py`

```python
class DiscrepancyAnalyzer:
    """Analyzes patterns across quarters for a single company.
    
    Detects:
    1. Consistent rounding bias (always rounding up)
    2. Metric switching (highlighting different metrics each quarter)
    3. Increasing inaccuracy over time
    4. GAAP/non-GAAP shifting (switching basis when convenient)
    5. Selective emphasis (only highlighting good numbers)
    """
    
    def analyze_company(
        self,
        company_id: int,
        claims_by_quarter: dict[str, list[ClaimWithVerification]],
    ) -> list[DiscrepancyPattern]:
        """Run all pattern detectors for a company across quarters.
        
        Args:
            company_id: The company ID
            claims_by_quarter: Dict mapping "Q1 2025" -> list of claims with verifications
        
        Returns:
            List of detected discrepancy patterns
        """
        patterns = []
        
        patterns.extend(self._detect_rounding_bias(company_id, claims_by_quarter))
        patterns.extend(self._detect_metric_switching(company_id, claims_by_quarter))
        patterns.extend(self._detect_increasing_inaccuracy(company_id, claims_by_quarter))
        patterns.extend(self._detect_gaap_shifting(company_id, claims_by_quarter))
        patterns.extend(self._detect_selective_emphasis(company_id, claims_by_quarter))
        
        return patterns
    
    def _detect_rounding_bias(
        self, company_id, claims_by_quarter
    ) -> list[DiscrepancyPattern]:
        """Detect if management consistently rounds in a favorable direction.
        
        Logic:
        - For each verified/approximate claim, check if stated > actual
        - If >70% of claims round favorably across multiple quarters, flag it
        """
        favorable_rounds = 0
        total_roundings = 0
        affected = []
        
        for quarter, claims in claims_by_quarter.items():
            for claim in claims:
                v = claim.verification
                if v and v.actual_value and v.accuracy_score and v.accuracy_score < 1.0:
                    total_roundings += 1
                    # Check if stated is more favorable than actual
                    if claim.stated_value > v.actual_value:
                        favorable_rounds += 1
                        affected.append(quarter)
        
        if total_roundings >= 4 and (favorable_rounds / total_roundings) > 0.7:
            return [DiscrepancyPattern(
                id=0,  # Will be assigned by DB
                company_id=company_id,
                pattern_type=PatternType.CONSISTENT_ROUNDING_UP,
                description=(
                    f"Management consistently rounds in a favorable direction. "
                    f"{favorable_rounds}/{total_roundings} claims round up."
                ),
                affected_quarters=list(set(affected)),
                severity=favorable_rounds / total_roundings,
                evidence=[f"{favorable_rounds}/{total_roundings} favorable roundings"]
            )]
        return []
    
    def _detect_metric_switching(
        self, company_id, claims_by_quarter
    ) -> list[DiscrepancyPattern]:
        """Detect if management highlights different metrics each quarter.
        
        Logic:
        - Track which metrics are emphasized (mentioned most) per quarter
        - If the top metric changes frequently, they may be cherry-picking
        """
        top_metrics_by_quarter = {}
        for quarter, claims in claims_by_quarter.items():
            metric_counts = {}
            for claim in claims:
                metric_counts[claim.metric] = metric_counts.get(claim.metric, 0) + 1
            if metric_counts:
                top_metric = max(metric_counts, key=metric_counts.get)
                top_metrics_by_quarter[quarter] = top_metric
        
        unique_top_metrics = set(top_metrics_by_quarter.values())
        if len(unique_top_metrics) >= 3 and len(top_metrics_by_quarter) >= 3:
            return [DiscrepancyPattern(
                id=0,
                company_id=company_id,
                pattern_type=PatternType.METRIC_SWITCHING,
                description=(
                    f"Management emphasizes different metrics across quarters: "
                    f"{', '.join(f'{q}: {m}' for q, m in top_metrics_by_quarter.items())}. "
                    f"This may indicate selective emphasis."
                ),
                affected_quarters=list(top_metrics_by_quarter.keys()),
                severity=0.5,
                evidence=[f"Top metrics: {top_metrics_by_quarter}"]
            )]
        return []
    
    def _detect_increasing_inaccuracy(
        self, company_id, claims_by_quarter
    ) -> list[DiscrepancyPattern]:
        """Detect if claims are becoming less accurate over time."""
        quarter_accuracy = {}
        for quarter, claims in sorted(claims_by_quarter.items()):
            scores = [
                c.verification.accuracy_score 
                for c in claims 
                if c.verification and c.verification.accuracy_score is not None
            ]
            if scores:
                quarter_accuracy[quarter] = sum(scores) / len(scores)
        
        # Check for downward trend
        values = list(quarter_accuracy.values())
        if len(values) >= 3:
            # Simple check: is the last value lower than the first?
            if values[-1] < values[0] - 0.05:  # 5% decline
                return [DiscrepancyPattern(
                    id=0,
                    company_id=company_id,
                    pattern_type=PatternType.INCREASING_INACCURACY,
                    description=(
                        f"Claim accuracy declining over time: "
                        f"{', '.join(f'{q}: {v:.1%}' for q, v in quarter_accuracy.items())}"
                    ),
                    affected_quarters=list(quarter_accuracy.keys()),
                    severity=abs(values[-1] - values[0]),
                    evidence=[f"Accuracy trend: {quarter_accuracy}"]
                )]
        return []
    
    def _detect_gaap_shifting(
        self, company_id, claims_by_quarter
    ) -> list[DiscrepancyPattern]:
        """Detect if company shifts between GAAP and non-GAAP reporting."""
        gaap_ratio_by_quarter = {}
        for quarter, claims in claims_by_quarter.items():
            gaap_claims = sum(1 for c in claims if c.is_gaap)
            total = len(claims)
            if total > 0:
                gaap_ratio_by_quarter[quarter] = gaap_claims / total
        
        ratios = list(gaap_ratio_by_quarter.values())
        if len(ratios) >= 2 and max(ratios) - min(ratios) > 0.3:
            return [DiscrepancyPattern(
                id=0,
                company_id=company_id,
                pattern_type=PatternType.GAAP_NONGAAP_SHIFTING,
                description=(
                    f"Company shifts between GAAP and non-GAAP emphasis across quarters. "
                    f"GAAP ratios: {gaap_ratio_by_quarter}"
                ),
                affected_quarters=list(gaap_ratio_by_quarter.keys()),
                severity=max(ratios) - min(ratios),
                evidence=[f"GAAP ratios: {gaap_ratio_by_quarter}"]
            )]
        return []
    
    def _detect_selective_emphasis(
        self, company_id, claims_by_quarter
    ) -> list[DiscrepancyPattern]:
        """Detect if management only highlights metrics that look good.
        
        Logic:
        - For each quarter, check if the most-mentioned metrics are also the most accurate
        - If management avoids mentioning declining metrics, that's selective emphasis
        """
        # This is more complex and would need full financial data context
        # For now, we check if verified claims heavily skew toward positive metrics
        quarters_with_bias = []
        
        for quarter, claims in claims_by_quarter.items():
            positive_claims = sum(
                1 for c in claims 
                if c.metric_type == MetricType.GROWTH_RATE and c.stated_value > 0
            )
            negative_claims = sum(
                1 for c in claims 
                if c.metric_type == MetricType.GROWTH_RATE and c.stated_value < 0
            )
            total_growth = positive_claims + negative_claims
            
            if total_growth > 2 and positive_claims / total_growth > 0.9:
                quarters_with_bias.append(quarter)
        
        if len(quarters_with_bias) >= 2:
            return [DiscrepancyPattern(
                id=0,
                company_id=company_id,
                pattern_type=PatternType.SELECTIVE_EMPHASIS,
                description=(
                    f"Management overwhelmingly highlights positive growth metrics "
                    f"while avoiding negative ones in {len(quarters_with_bias)} quarters."
                ),
                affected_quarters=quarters_with_bias,
                severity=0.6,
                evidence=[f"Quarters with >90% positive claims: {quarters_with_bias}"]
            )]
        return []
```

---

## 10. Service Layer (Orchestration)

### `app/services/ingestion_service.py`

```python
class IngestionService:
    """Orchestrates data ingestion from external APIs into the database.
    
    Responsibilities:
    - Create company records
    - Fetch and store transcripts for target quarters
    - Fetch and store financial data for target quarters (+ comparison periods)
    - Idempotent: skip already-ingested data
    """
    
    def __init__(
        self,
        fmp_client: FMPClient,
        company_repo: CompanyRepository,
        transcript_repo: TranscriptRepository,
        financial_repo: FinancialDataRepository,
    ):
        self.fmp = fmp_client
        self.companies = company_repo
        self.transcripts = transcript_repo
        self.financials = financial_repo
    
    def ingest_all(self, tickers: list[str], quarters: list[tuple[int, int]]) -> dict:
        """Ingest transcripts and financials for all target companies and quarters.
        
        Returns a summary dict with counts of ingested items.
        """
        summary = {
            "companies_created": 0,
            "transcripts_fetched": 0,
            "transcripts_skipped": 0,
            "financials_fetched": 0,
        }
        
        for ticker in tickers:
            # 1. Get or create company
            profile = self.fmp.get_company_profile(ticker)
            company = self.companies.get_or_create(
                ticker=ticker,
                name=profile.get("companyName", ticker),
                sector=profile.get("sector", "Unknown")
            )
            summary["companies_created"] += 1
            
            # 2. Fetch transcripts
            for year, quarter in quarters:
                self._ingest_transcript(company, year, quarter, summary)
            
            # 3. Fetch financial data (need extra quarters for YoY comparison)
            self._ingest_financial_data(company, quarters, summary)
        
        return summary
    
    def _ingest_transcript(self, company, year, quarter, summary):
        """Fetch and store a single transcript (idempotent)."""
        existing = self.transcripts.get_for_quarter(company.id, year, quarter)
        if existing:
            summary["transcripts_skipped"] += 1
            return
        
        transcript = self.fmp.get_transcript(company.ticker, quarter, year)
        if transcript:
            self.transcripts.create(TranscriptModel(
                company_id=company.id,
                quarter=quarter,
                year=year,
                call_date=transcript.date,
                full_text=transcript.content,
            ))
            summary["transcripts_fetched"] += 1
    
    def _ingest_financial_data(self, company, quarters, summary):
        """Fetch and store financial data including comparison periods."""
        # Get income statements, cash flows, balance sheets
        income = self.fmp.get_income_statement(company.ticker, limit=12)
        cashflow = self.fmp.get_cash_flow_statement(company.ticker, limit=12)
        balance = self.fmp.get_balance_sheet(company.ticker, limit=12)
        
        # Merge and store by quarter
        for inc_entry in income:
            q, y = self._parse_fmp_period(inc_entry)
            existing = self.financials.get_for_quarter(company.id, y, q)
            if existing:
                continue
            
            # Find matching cash flow and balance sheet entries
            cf_entry = self._find_matching_entry(cashflow, y, q)
            bs_entry = self._find_matching_entry(balance, y, q)
            
            self.financials.create(FinancialDataModel(
                company_id=company.id,
                period=f"Q{q}",
                year=y,
                quarter=q,
                revenue=inc_entry.get("revenue"),
                cost_of_revenue=inc_entry.get("costOfRevenue"),
                gross_profit=inc_entry.get("grossProfit"),
                operating_income=inc_entry.get("operatingIncome"),
                operating_expenses=inc_entry.get("operatingExpenses"),
                net_income=inc_entry.get("netIncome"),
                eps=inc_entry.get("eps"),
                eps_diluted=inc_entry.get("epsdiluted"),
                ebitda=inc_entry.get("ebitda"),
                research_and_development=inc_entry.get("researchAndDevelopmentExpenses"),
                selling_general_admin=inc_entry.get("sellingGeneralAndAdministrativeExpenses"),
                interest_expense=inc_entry.get("interestExpense"),
                income_tax_expense=inc_entry.get("incomeTaxExpense"),
                operating_cash_flow=cf_entry.get("operatingCashFlow") if cf_entry else None,
                capital_expenditure=cf_entry.get("capitalExpenditure") if cf_entry else None,
                free_cash_flow=cf_entry.get("freeCashFlow") if cf_entry else None,
                total_assets=bs_entry.get("totalAssets") if bs_entry else None,
                total_liabilities=bs_entry.get("totalLiabilities") if bs_entry else None,
                total_debt=bs_entry.get("totalDebt") if bs_entry else None,
                cash_and_equivalents=bs_entry.get("cashAndCashEquivalents") if bs_entry else None,
                shareholders_equity=bs_entry.get("totalStockholdersEquity") if bs_entry else None,
            ))
            summary["financials_fetched"] += 1
    
    @staticmethod
    def _parse_fmp_period(entry: dict) -> tuple[int, int]:
        """Parse FMP API response to get quarter and year."""
        period = entry.get("period", "")  # "Q1", "Q2", etc.
        date_str = entry.get("date", "")
        year = int(date_str[:4]) if date_str else entry.get("calendarYear", 0)
        quarter = int(period[1]) if period.startswith("Q") else 1
        return quarter, year
    
    @staticmethod
    def _find_matching_entry(entries: list[dict], year: int, quarter: int) -> Optional[dict]:
        """Find the entry matching the given year and quarter."""
        for entry in entries:
            q, y = IngestionService._parse_fmp_period(entry)
            if q == quarter and y == year:
                return entry
        return None
```

### `app/services/extraction_service.py`

```python
class ExtractionService:
    """Orchestrates claim extraction for all transcripts."""
    
    def __init__(
        self,
        claim_extractor: ClaimExtractor,
        transcript_repo: TranscriptRepository,
        claim_repo: ClaimRepository,
    ):
        self.extractor = claim_extractor
        self.transcripts = transcript_repo
        self.claims = claim_repo
    
    def extract_all(self) -> dict:
        """Extract claims from all transcripts that haven't been processed.
        
        Returns summary of extraction results.
        """
        summary = {"transcripts_processed": 0, "claims_extracted": 0, "errors": 0}
        
        transcripts = self.transcripts.get_unprocessed()
        for transcript in transcripts:
            try:
                claims = self.extractor.extract(
                    transcript_text=transcript.full_text,
                    ticker=transcript.company.ticker,
                    quarter=transcript.quarter,
                    year=transcript.year,
                )
                
                for claim_create in claims:
                    claim_create.transcript_id = transcript.id
                    self.claims.create(ClaimModel(**claim_create.model_dump()))
                
                summary["transcripts_processed"] += 1
                summary["claims_extracted"] += len(claims)
            except Exception as e:
                logger.error(f"Error extracting from transcript {transcript.id}: {e}")
                summary["errors"] += 1
        
        return summary
    
    def extract_for_transcript(self, transcript_id: int) -> list[ClaimModel]:
        """Extract claims from a specific transcript."""
        transcript = self.transcripts.get(transcript_id)
        if not transcript:
            raise ValueError(f"Transcript {transcript_id} not found")
        
        claims = self.extractor.extract(
            transcript_text=transcript.full_text,
            ticker=transcript.company.ticker,
            quarter=transcript.quarter,
            year=transcript.year,
        )
        
        result = []
        for claim_create in claims:
            claim_create.transcript_id = transcript.id
            model = self.claims.create(ClaimModel(**claim_create.model_dump()))
            result.append(model)
        
        return result
```

### `app/services/verification_service.py`

```python
class VerificationService:
    """Orchestrates claim verification."""
    
    def __init__(
        self,
        verification_engine: VerificationEngine,
        claim_repo: ClaimRepository,
        verification_repo: VerificationRepository,
    ):
        self.engine = verification_engine
        self.claims = claim_repo
        self.verifications = verification_repo
    
    def verify_all(self) -> dict:
        """Verify all unverified claims.
        
        Returns summary of verification results.
        """
        summary = {
            "verified": 0, "approximately_correct": 0,
            "misleading": 0, "incorrect": 0, "unverifiable": 0, "errors": 0,
        }
        
        unverified = self.claims.get_unverified()
        for claim in unverified:
            try:
                verification = self.engine.verify(
                    claim=claim,
                    company_id=claim.transcript.company_id,
                    transcript_year=claim.transcript.year,
                    transcript_quarter=claim.transcript.quarter,
                )
                
                self.verifications.create(VerificationModel(**verification.model_dump()))
                summary[verification.verdict.value] += 1
            except Exception as e:
                logger.error(f"Error verifying claim {claim.id}: {e}")
                summary["errors"] += 1
        
        return summary
```

### `app/services/analysis_service.py`

```python
class AnalysisService:
    """Generates company-level and cross-company analysis reports."""
    
    def __init__(
        self,
        discrepancy_analyzer: DiscrepancyAnalyzer,
        company_repo: CompanyRepository,
        claim_repo: ClaimRepository,
        verification_repo: VerificationRepository,
    ):
        self.analyzer = discrepancy_analyzer
        self.companies = company_repo
        self.claims = claim_repo
        self.verifications = verification_repo
    
    def analyze_company(self, company_id: int) -> CompanyAnalysis:
        """Generate full analysis for a single company."""
        company = self.companies.get(company_id)
        claims = self.claims.get_for_company(company_id)
        
        # Group claims by quarter
        claims_by_quarter = {}
        for claim in claims:
            quarter_key = f"Q{claim.transcript.quarter} {claim.transcript.year}"
            if quarter_key not in claims_by_quarter:
                claims_by_quarter[quarter_key] = []
            claims_by_quarter[quarter_key].append(claim)
        
        # Count verdicts
        verdicts = {"verified": 0, "approximately_correct": 0, 
                    "misleading": 0, "incorrect": 0, "unverifiable": 0}
        for claim in claims:
            if claim.verification:
                verdicts[claim.verification.verdict] += 1
        
        total_verifiable = sum(v for k, v in verdicts.items() if k != "unverifiable")
        accuracy_rate = (
            (verdicts["verified"] + verdicts["approximately_correct"]) / total_verifiable
            if total_verifiable > 0 else 0
        )
        
        # Compute trust score (weighted)
        trust_score = self._compute_trust_score(verdicts, total_verifiable)
        
        # Run discrepancy analysis
        patterns = self.analyzer.analyze_company(company_id, claims_by_quarter)
        
        # Get worst claims
        top_discrepancies = self._get_top_discrepancies(claims, limit=5)
        
        return CompanyAnalysis(
            company_id=company.id,
            ticker=company.ticker,
            name=company.name,
            total_claims=len(claims),
            verified_claims=verdicts["verified"],
            approximately_correct_claims=verdicts["approximately_correct"],
            misleading_claims=verdicts["misleading"],
            incorrect_claims=verdicts["incorrect"],
            unverifiable_claims=verdicts["unverifiable"],
            overall_accuracy_rate=accuracy_rate,
            overall_trust_score=trust_score,
            top_discrepancies=top_discrepancies,
            patterns=patterns,
            quarters_analyzed=list(claims_by_quarter.keys()),
        )
    
    def _compute_trust_score(self, verdicts: dict, total: int) -> float:
        """Compute a 0-100 trust score based on verdict distribution.
        
        Weights:
        - Verified: +1.0
        - Approximately correct: +0.7
        - Misleading: -0.3
        - Incorrect: -1.0
        """
        if total == 0:
            return 50.0  # Neutral if no data
        
        score = (
            verdicts["verified"] * 1.0 +
            verdicts["approximately_correct"] * 0.7 +
            verdicts["misleading"] * -0.3 +
            verdicts["incorrect"] * -1.0
        ) / total
        
        # Normalize to 0-100 scale
        return max(0, min(100, (score + 1) * 50))
    
    def _get_top_discrepancies(self, claims, limit=5) -> list[dict]:
        """Get the worst/most interesting discrepancies."""
        discrepancies = []
        for claim in claims:
            if claim.verification and claim.verification.verdict in (
                Verdict.MISLEADING, Verdict.INCORRECT
            ):
                discrepancies.append({
                    "claim_id": claim.id,
                    "claim_text": claim.claim_text,
                    "speaker": claim.speaker,
                    "metric": claim.metric,
                    "stated_value": claim.stated_value,
                    "actual_value": claim.verification.actual_value,
                    "verdict": claim.verification.verdict,
                    "explanation": claim.verification.explanation,
                })
        
        # Sort by severity (accuracy_score ascending = worst first)
        discrepancies.sort(
            key=lambda d: d.get("actual_value", 0) if d["actual_value"] else 0
        )
        return discrepancies[:limit]
```

---

## 11. API Layer (FastAPI)

### `app/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import companies, transcripts, claims, verifications, pipeline
from app.database import init_db

app = FastAPI(
    title="Claim Auditor",
    description="Analyzes earnings call transcripts and verifies quantitative claims",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(transcripts.router, prefix="/api/transcripts", tags=["transcripts"])
app.include_router(claims.router, prefix="/api/claims", tags=["claims"])
app.include_router(verifications.router, prefix="/api/verifications", tags=["verifications"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/health")
async def health():
    return {"status": "ok"}
```

### `app/api/companies.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter()

@router.get("/", response_model=list[CompanyWithStats])
def list_companies(db: Session = Depends(get_db)):
    """List all companies with their verification statistics."""
    ...

@router.get("/{ticker}", response_model=CompanyAnalysis)
def get_company(ticker: str, db: Session = Depends(get_db)):
    """Get full analysis for a company."""
    ...

@router.get("/{ticker}/claims", response_model=list[ClaimWithVerification])
def get_company_claims(
    ticker: str, 
    quarter: Optional[int] = None,
    year: Optional[int] = None,
    verdict: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get all claims for a company with optional filters."""
    ...
```

### `app/api/claims.py`

```python
router = APIRouter()

@router.get("/", response_model=list[ClaimWithVerification])
def list_claims(
    company_id: Optional[int] = None,
    verdict: Optional[str] = None,
    metric: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List claims with filters."""
    ...

@router.get("/{claim_id}", response_model=ClaimWithVerification)
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    """Get a single claim with full verification details."""
    ...
```

### `app/api/pipeline.py`

```python
router = APIRouter()

@router.post("/ingest")
def trigger_ingestion(db: Session = Depends(get_db)):
    """Trigger data ingestion for all target companies."""
    ...

@router.post("/extract")
def trigger_extraction(db: Session = Depends(get_db)):
    """Trigger claim extraction for all unprocessed transcripts."""
    ...

@router.post("/verify")
def trigger_verification(db: Session = Depends(get_db)):
    """Trigger verification for all unverified claims."""
    ...

@router.post("/run-all")
def run_full_pipeline(db: Session = Depends(get_db)):
    """Run the complete pipeline: ingest → extract → verify → analyze."""
    ...

@router.get("/status")
def pipeline_status(db: Session = Depends(get_db)):
    """Get current pipeline status (counts of each stage)."""
    ...
```

---

## 12. Frontend Spec

### TypeScript Types (`src/types/index.ts`)

```typescript
export type Verdict = 
  | "verified" 
  | "approximately_correct" 
  | "misleading" 
  | "incorrect" 
  | "unverifiable";

export interface Company {
  id: number;
  ticker: string;
  name: string;
  sector: string;
  total_claims: number;
  verified_count: number;
  misleading_count: number;
  incorrect_count: number;
  accuracy_rate: number;
}

export interface Claim {
  id: number;
  transcript_id: number;
  speaker: string;
  speaker_role: string | null;
  claim_text: string;
  metric: string;
  metric_type: string;
  stated_value: number;
  unit: string;
  comparison_period: string;
  is_gaap: boolean;
  segment: string | null;
  confidence: number;
  verification: Verification | null;
}

export interface Verification {
  id: number;
  claim_id: number;
  actual_value: number | null;
  accuracy_score: number | null;
  verdict: Verdict;
  explanation: string;
  misleading_flags: string[];
  misleading_details: string | null;
}

export interface CompanyAnalysis {
  company_id: number;
  ticker: string;
  name: string;
  total_claims: number;
  verified_claims: number;
  approximately_correct_claims: number;
  misleading_claims: number;
  incorrect_claims: number;
  unverifiable_claims: number;
  overall_accuracy_rate: number;
  overall_trust_score: number;
  top_discrepancies: Discrepancy[];
  patterns: DiscrepancyPattern[];
  quarters_analyzed: string[];
}

export interface DiscrepancyPattern {
  id: number;
  company_id: number;
  pattern_type: string;
  description: string;
  affected_quarters: string[];
  severity: number;
  evidence: string[];
}
```

### Component Design

**Dashboard** (`src/app/page.tsx`):
- Grid of CompanyCards showing ticker, name, trust score (color-coded gauge)
- Summary bar: total claims analyzed, overall verification rate
- Filter: by sector, by verdict type

**CompanyCard** (`src/components/CompanyCard.tsx`):
- Company name + ticker
- Trust score as color-coded badge (0-100)
- Mini breakdown: ✅ verified / ⚠️ misleading / ❌ incorrect
- Click navigates to company detail

**Company Detail** (`src/app/companies/[ticker]/page.tsx`):
- Header with company info + overall trust score
- Quarter selector tabs
- ClaimTable for selected quarter
- DiscrepancyChart showing patterns (bonus)
- Top discrepancies highlighted

**ClaimTable** (`src/components/ClaimTable.tsx`):
- Sortable table: Speaker | Claim | Metric | Stated | Actual | Verdict
- Color-coded verdict badges
- Expandable rows showing full verification details
- Filters: by verdict, by metric, by speaker

**VerificationBadge** (`src/components/VerificationBadge.tsx`):
- Color-coded badge:
  - Green: VERIFIED
  - Blue: APPROXIMATELY CORRECT
  - Yellow: MISLEADING
  - Red: INCORRECT
  - Gray: UNVERIFIABLE

**TranscriptViewer** (`src/components/TranscriptViewer.tsx`):
- Full transcript text with claims highlighted inline
- Color-coded highlights matching verdicts
- Click highlight to see verification popup

---

## 13. Test Strategy

### Test Philosophy
- **TDD**: Write tests BEFORE implementation for core engines
- **Unit tests**: All business logic (verification, extraction parsing, financial math)
- **Integration tests**: API clients (mocked), service orchestration
- **API tests**: FastAPI TestClient for endpoint behavior
- **Fixtures**: Realistic sample data for reproducible tests

### Test File Structure

#### `tests/conftest.py` — Shared Fixtures
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import *

@pytest.fixture
def db_session():
    """Create a fresh in-memory database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def sample_company(db_session):
    """Create a sample company for testing."""
    company = CompanyModel(ticker="AAPL", name="Apple Inc.", sector="Technology")
    db_session.add(company)
    db_session.commit()
    return company

@pytest.fixture
def sample_financial_data(db_session, sample_company):
    """Create sample financial data for testing verification."""
    q3_2025 = FinancialDataModel(
        company_id=sample_company.id,
        period="Q3", year=2025, quarter=3,
        revenue=94_930_000_000,
        gross_profit=43_879_000_000,
        operating_income=29_590_000_000,
        net_income=23_636_000_000,
        eps=1.46, eps_diluted=1.46,
        ebitda=32_500_000_000,
        operating_cash_flow=26_760_000_000,
        free_cash_flow=22_490_000_000,
    )
    q3_2024 = FinancialDataModel(
        company_id=sample_company.id,
        period="Q3", year=2024, quarter=3,
        revenue=85_777_000_000,
        gross_profit=39_400_000_000,
        operating_income=26_200_000_000,
        net_income=22_956_000_000,
        eps=1.40, eps_diluted=1.40,
        ebitda=30_100_000_000,
        operating_cash_flow=24_100_000_000,
        free_cash_flow=20_300_000_000,
    )
    db_session.add_all([q3_2025, q3_2024])
    db_session.commit()
    return q3_2025, q3_2024
```

#### `tests/unit/test_financial_math.py`
```python
"""Test financial calculation utilities."""

def test_growth_rate_positive():
    assert growth_rate(115, 100) == 15.0

def test_growth_rate_negative():
    assert growth_rate(85, 100) == -15.0

def test_growth_rate_zero_base():
    assert growth_rate(100, 0) is None

def test_margin_calculation():
    assert margin(30, 100) == 30.0

def test_margin_zero_denominator():
    assert margin(30, 0) is None

def test_accuracy_score_exact():
    assert accuracy_score(15.0, 15.0) == 1.0

def test_accuracy_score_close():
    score = accuracy_score(15.0, 14.0)
    assert 0.92 < score < 0.94  # ~7% off

def test_accuracy_score_way_off():
    score = accuracy_score(15.0, 5.0)
    assert score < 0.5

def test_normalize_billions():
    assert normalize_to_unit(5_000_000_000, "usd_billions") == 5.0

def test_normalize_millions():
    assert normalize_to_unit(5_000_000, "usd_millions") == 5.0

def test_basis_points():
    assert basis_points_to_percentage(200) == 2.0
```

#### `tests/unit/test_metric_mapper.py`
```python
"""Test metric mapping from claim terms to financial data fields."""

def test_direct_metric_resolution(sample_financial_data):
    mapper = MetricMapper()
    q3_2025, _ = sample_financial_data
    
    assert mapper.resolve("revenue", q3_2025) == 94_930_000_000
    assert mapper.resolve("net_income", q3_2025) == 23_636_000_000
    assert mapper.resolve("eps", q3_2025) == 1.46

def test_derived_margin_resolution(sample_financial_data):
    mapper = MetricMapper()
    q3_2025, _ = sample_financial_data
    
    gross_margin = mapper.resolve("gross_margin", q3_2025)
    assert gross_margin is not None
    assert abs(gross_margin - 46.22) < 0.1  # ~46.22%

def test_unknown_metric():
    mapper = MetricMapper()
    assert mapper.can_resolve("unknown_metric") is False

def test_all_direct_metrics_recognized():
    mapper = MetricMapper()
    expected = [
        "revenue", "cost_of_revenue", "gross_profit", "operating_income",
        "net_income", "eps", "eps_diluted", "ebitda", "free_cash_flow",
    ]
    for metric in expected:
        assert mapper.can_resolve(metric), f"{metric} should be resolvable"
```

#### `tests/unit/test_verification_engine.py`
```python
"""Test the core verification logic."""

def test_verify_accurate_revenue_growth(db_session, sample_company, sample_financial_data):
    """CEO says 'revenue grew 10.7% YoY' — should be VERIFIED."""
    # Actual: (94.93B - 85.78B) / 85.78B = 10.68%
    engine = create_verification_engine(db_session)
    
    claim = create_test_claim(
        metric="revenue",
        metric_type=MetricType.GROWTH_RATE,
        stated_value=10.7,
        unit="percent",
        comparison_period=ComparisonPeriod.YOY,
    )
    
    result = engine.verify(claim, sample_company.id, 2025, 3)
    assert result.verdict == Verdict.VERIFIED
    assert result.accuracy_score > 0.98

def test_verify_misleading_revenue_growth(db_session, sample_company, sample_financial_data):
    """CEO says 'revenue grew 15% YoY' — should be MISLEADING (actual ~10.7%)."""
    engine = create_verification_engine(db_session)
    
    claim = create_test_claim(
        metric="revenue",
        metric_type=MetricType.GROWTH_RATE,
        stated_value=15.0,
        unit="percent",
        comparison_period=ComparisonPeriod.YOY,
    )
    
    result = engine.verify(claim, sample_company.id, 2025, 3)
    assert result.verdict in (Verdict.MISLEADING, Verdict.INCORRECT)
    assert result.accuracy_score < 0.90

def test_verify_absolute_revenue(db_session, sample_company, sample_financial_data):
    """CFO says 'revenue was $94.9 billion' — should be VERIFIED."""
    engine = create_verification_engine(db_session)
    
    claim = create_test_claim(
        metric="revenue",
        metric_type=MetricType.ABSOLUTE,
        stated_value=94.9,
        unit="usd_billions",
    )
    
    result = engine.verify(claim, sample_company.id, 2025, 3)
    assert result.verdict == Verdict.VERIFIED

def test_verify_eps(db_session, sample_company, sample_financial_data):
    """CFO says 'diluted EPS was $1.46' — should be VERIFIED."""
    engine = create_verification_engine(db_session)
    
    claim = create_test_claim(
        metric="eps_diluted",
        metric_type=MetricType.PER_SHARE,
        stated_value=1.46,
        unit="usd",
    )
    
    result = engine.verify(claim, sample_company.id, 2025, 3)
    assert result.verdict == Verdict.VERIFIED
    assert result.accuracy_score == 1.0

def test_verify_margin(db_session, sample_company, sample_financial_data):
    """CFO says 'gross margin was 46%' — should be APPROXIMATELY_CORRECT (actual ~46.2%)."""
    engine = create_verification_engine(db_session)
    
    claim = create_test_claim(
        metric="gross_margin",
        metric_type=MetricType.MARGIN,
        stated_value=46.0,
        unit="percent",
    )
    
    result = engine.verify(claim, sample_company.id, 2025, 3)
    assert result.verdict in (Verdict.VERIFIED, Verdict.APPROXIMATELY_CORRECT)

def test_verify_unresolvable_metric(db_session, sample_company):
    """Claim references a metric we can't verify — should be UNVERIFIABLE."""
    engine = create_verification_engine(db_session)
    
    claim = create_test_claim(
        metric="subscriber_count",
        metric_type=MetricType.ABSOLUTE,
        stated_value=1_000_000,
        unit="units",
    )
    
    result = engine.verify(claim, sample_company.id, 2025, 3)
    assert result.verdict == Verdict.UNVERIFIABLE

def test_verify_missing_comparison_period(db_session, sample_company, sample_financial_data):
    """YoY claim but no comparison data — should be UNVERIFIABLE."""
    engine = create_verification_engine(db_session)
    
    # Try to compare to a year we don't have data for
    claim = create_test_claim(
        metric="revenue",
        metric_type=MetricType.GROWTH_RATE,
        stated_value=10.0,
        unit="percent",
        comparison_period=ComparisonPeriod.YOY,
    )
    
    # Verify for a quarter where we don't have prior year data
    result = engine.verify(claim, sample_company.id, 2023, 3)
    assert result.verdict == Verdict.UNVERIFIABLE
```

#### `tests/unit/test_claim_extractor.py`
```python
"""Test claim extraction parsing and validation."""

def test_parse_valid_claims_json():
    """Test parsing a well-formed JSON response from LLM."""
    extractor = ClaimExtractor(mock_llm_client)
    ...

def test_parse_claims_in_markdown_block():
    """Test parsing JSON wrapped in ```json code block."""
    ...

def test_normalize_metric_aliases():
    """Test that metric aliases are properly normalized."""
    extractor = ClaimExtractor(mock_llm_client)
    assert extractor._normalize_metric("total revenue") == "revenue"
    assert extractor._normalize_metric("earnings per share") == "eps"
    assert extractor._normalize_metric("FCF") == "free_cash_flow"
    assert extractor._normalize_metric("op margin") == "operating_margin"

def test_deduplicate_claims():
    """Test that duplicate claims are removed."""
    ...

def test_invalid_claim_skipped():
    """Test that malformed claims are skipped with a warning."""
    ...
```

#### `tests/unit/test_discrepancy_analyzer.py`
```python
"""Test quarter-to-quarter discrepancy detection."""

def test_detect_rounding_bias():
    """Detect when management consistently rounds favorably."""
    ...

def test_detect_metric_switching():
    """Detect when management highlights different metrics each quarter."""
    ...

def test_no_false_positives_with_clean_data():
    """Ensure no patterns detected for perfectly accurate claims."""
    ...
```

#### `tests/integration/test_fmp_client.py`
```python
"""Integration tests for FMP API client (with mocking)."""

@patch("httpx.Client.get")
def test_get_transcript(mock_get):
    """Test transcript fetching with mocked HTTP response."""
    mock_get.return_value = MockResponse(200, [SAMPLE_TRANSCRIPT_RESPONSE])
    
    client = FMPClient(api_key="test")
    result = client.get_transcript("AAPL", 3, 2025)
    
    assert result is not None
    assert result.ticker == "AAPL"
    assert result.quarter == 3

@patch("httpx.Client.get")
def test_get_income_statement(mock_get):
    """Test financial data fetching."""
    mock_get.return_value = MockResponse(200, SAMPLE_INCOME_RESPONSE)
    
    client = FMPClient(api_key="test")
    result = client.get_income_statement("AAPL")
    
    assert len(result) > 0
    assert "revenue" in result[0]

@patch("httpx.Client.get")
def test_handles_404(mock_get):
    """Test graceful handling of missing data."""
    mock_get.return_value = MockResponse(404, {})
    ...
```

#### `tests/api/test_api_endpoints.py`
```python
"""Test FastAPI endpoints."""
from fastapi.testclient import TestClient

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_list_companies(client: TestClient, seeded_db):
    response = client.get("/api/companies/")
    assert response.status_code == 200
    companies = response.json()
    assert len(companies) == 10

def test_get_company_claims(client: TestClient, seeded_db):
    response = client.get("/api/companies/AAPL/claims")
    assert response.status_code == 200

def test_filter_claims_by_verdict(client: TestClient, seeded_db):
    response = client.get("/api/claims/?verdict=misleading")
    assert response.status_code == 200
    for claim in response.json():
        assert claim["verification"]["verdict"] == "misleading"
```

---

## 14. Deployment Spec

### Backend Deployment (Railway)

**Dockerfile**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev --no-root

COPY . .
RUN poetry install --no-dev

EXPOSE 8000
CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Environment Variables** (Railway):
```
DATABASE_URL=postgresql://...  (Railway Postgres addon)
FMP_API_KEY=...
ANTHROPIC_API_KEY=...
```

### Frontend Deployment (Vercel)

**next.config.js**:
```javascript
module.exports = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
}
```

**Environment Variables** (Vercel):
```
NEXT_PUBLIC_API_URL=https://your-railway-app.up.railway.app
```

### Database Migration Strategy
```bash
# Tables are created automatically via init_db() on startup.
# No separate migration step needed for SQLite.
```

---

## Dependency Injection / Factory Pattern

### `app/dependencies.py`

```python
"""Factory functions for creating service instances with all dependencies."""

from functools import lru_cache
from app.config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_fmp_client(settings: Settings = None) -> FMPClient:
    settings = settings or get_settings()
    return FMPClient(api_key=settings.fmp_api_key)


def get_llm_client(settings: Settings = None) -> LLMClient:
    settings = settings or get_settings()
    return LLMClient(api_key=settings.anthropic_api_key, model=settings.claude_model)


def get_claim_extractor(llm_client: LLMClient = None) -> ClaimExtractor:
    llm_client = llm_client or get_llm_client()
    return ClaimExtractor(llm_client=llm_client)


def get_metric_mapper() -> MetricMapper:
    return MetricMapper()


def get_verification_engine(
    db: Session,
    settings: Settings = None,
) -> VerificationEngine:
    settings = settings or get_settings()
    return VerificationEngine(
        metric_mapper=get_metric_mapper(),
        financial_repo=FinancialDataRepository(db),
        settings=settings,
    )


def get_discrepancy_analyzer() -> DiscrepancyAnalyzer:
    return DiscrepancyAnalyzer()


# Service factories

def get_ingestion_service(db: Session) -> IngestionService:
    return IngestionService(
        fmp_client=get_fmp_client(),
        company_repo=CompanyRepository(db),
        transcript_repo=TranscriptRepository(db),
        financial_repo=FinancialDataRepository(db),
    )


def get_extraction_service(db: Session) -> ExtractionService:
    return ExtractionService(
        claim_extractor=get_claim_extractor(),
        transcript_repo=TranscriptRepository(db),
        claim_repo=ClaimRepository(db),
    )


def get_verification_service(db: Session) -> VerificationService:
    return VerificationService(
        verification_engine=get_verification_engine(db),
        claim_repo=ClaimRepository(db),
        verification_repo=VerificationRepository(db),
    )


def get_analysis_service(db: Session) -> AnalysisService:
    return AnalysisService(
        discrepancy_analyzer=get_discrepancy_analyzer(),
        company_repo=CompanyRepository(db),
        claim_repo=ClaimRepository(db),
        verification_repo=VerificationRepository(db),
    )
```

---

## Implementation Order (TDD)

1. **`utils/financial_math.py`** — Pure functions, test first
2. **`schemas/*`** — Pydantic models (validated by instantiation tests)
3. **`models/*`** — SQLAlchemy models + `database.py`
4. **`repositories/*`** — Data access with in-memory SQLite tests
5. **`clients/fmp_client.py`** — With mocked HTTP tests
6. **`clients/llm_client.py`** — With mocked Anthropic tests
7. **`engines/metric_mapper.py`** — Test first, pure logic
8. **`engines/verification_engine.py`** — Test first, core logic
9. **`engines/claim_extractor.py`** — Test parsing, mock LLM
10. **`engines/discrepancy_analyzer.py`** — Test pattern detection
11. **`services/*`** — Integration orchestration
12. **`api/*`** — FastAPI endpoints with TestClient
13. **`main.py`** — Wire everything together
14. **Frontend** — After API is working
15. **Deployment** — After everything works locally

Each step: **Write test → See it fail → Implement → See it pass → Refactor**
