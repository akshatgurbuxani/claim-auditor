# Architecture Deep Dive

**Complete guide to the Claim Auditor architecture, design decisions, and implementation details.**

This document explains every architectural decision, shows how layers interact.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [6-Layer Architecture](#2-6-layer-architecture)
3. [Detailed Data Flow](#3-detailed-data-flow)
4. [File-to-Layer Mapping](#4-file-to-layer-mapping)
5. [Pipeline Execution Flow](#5-pipeline-execution-flow)
6. [Key Design Decisions](#6-key-design-decisions)
7. [Interface Architecture](#7-interface-architecture)
8. [Testing Strategy](#8-testing-strategy)
9. [Trade-offs](#9-trade-offs)

---

## 1. System Overview

### The Problem We Solve

**Context:** Company executives make 30-50 quantitative claims per earnings call.

**Challenge:** These claims can be:
- **Inaccurate** - Stated 15% growth, actual was 12.3%
- **Misleading** - Using non-GAAP figures, favorable rounding, GAAP mismatch
- **Systematically biased** - Consistent patterns across quarters

**Manual verification is impractical** - Requires cross-referencing multiple statements, unit conversions, and pattern detection.

### Our Solution

4-stage automated pipeline:

```
┌─────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                        │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────────────────┐           ┌──────────────────────┐
    │   FMP API (Free)     │           │  Local Files (.txt)  │
    │  ✅ Company Profile  │           │  📝 Transcripts      │
    │  ✅ Income Stmt      │           │                      │
    │  ✅ Cash Flow        │           │  (FMP API blocked    │
    │  ✅ Balance Sheet    │           │   on free tier)      │
    └──────────┬───────────┘           └──────────┬───────────┘
               │                                  │
               ▼                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 1: INGEST                                                  │
│  (app/services/ingestion_service.py)                            │
│                                                                  │
│  • Fetch structured financial data from FMP API                 │
│  • Try FMP transcript API → Falls back to local .txt files      │
│  • Store both in SQLite database                                │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │   SQLite Database     │
               │                       │
               │  ┌─────────────────┐  │
               │  │ companies       │  │  ← FMP (profile)
               │  │  - ticker       │  │
               │  │  - name, sector │  │
               │  └─────────────────┘  │
               │                       │
               │  ┌─────────────────┐  │
               │  │ transcripts     │  │  ← Local .txt
               │  │  - full_text    │  │  (unstructured)
               │  │  - quarter/year │  │
               │  └─────────────────┘  │
               │                       │
               │  ┌─────────────────┐  │
               │  │ financial_data  │  │  ← FMP (statements)
               │  │  - revenue      │  │  (structured)
               │  │  - net_income   │  │
               │  │  - op_income    │  │
               │  └─────────────────┘  │
               └───────────┬───────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 2: EXTRACT                                                 │
│  (app/services/extraction_service.py)                           │
│                                                                  │
│  For each transcript in database:                               │
│  1. Read unstructured text: "Revenue was $170.8B, up 11% YoY"   │
│  2. Send to Claude AI (Anthropic API)                           │
│  3. Claude returns structured JSON:                             │
│     {                                                            │
│       "speaker": "Andy Jassy",                                   │
│       "claim_text": "Revenue was $170.8B...",                    │
│       "metric": "revenue",                                       │
│       "stated_value": 170800000000,                              │
│       "unit": "usd"                                              │
│     }                                                            │
│  4. Store claims in database                                    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │   SQLite Database     │
               │                       │
               │  ┌─────────────────┐  │
               │  │ claims          │  │  ← Claude extraction
               │  │  - claim_text   │  │
               │  │  - speaker      │  │
               │  │  - metric       │  │
               │  │  - stated_value │  │
               │  └─────────────────┘  │
               └───────────┬───────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 3: VERIFY                                                  │
│  (app/services/verification_service.py)                         │
│                                                                  │
│  For each claim:                                                │
│  1. Get stated value from claim                                 │
│     Stated: $170.8B (what exec said)                            │
│  2. Get actual value from financial_data                        │
│     Actual: $213.4B (from FMP API)                              │
│  3. Calculate accuracy                                          │
│     accuracy = 1 - |stated - actual| / actual = 0.80 (80%)     │
│  4. Assign verdict                                              │
│     ≥98% → Correct, ≥90% → Mostly Correct,                     │
│     ≥80% → Misleading, <80% → Incorrect                        │
│  5. Store verification result                                   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │   SQLite Database     │
               │                       │
               │  ┌─────────────────┐  │
               │  │ verifications   │  │  ← Computed
               │  │  - verdict      │  │
               │  │  - actual_value │  │
               │  │  - accuracy     │  │
               │  │  - explanation  │  │
               │  └─────────────────┘  │
               └───────────┬───────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 4: ANALYZE                                                 │
│  (app/services/analysis_service.py)                             │
│                                                                  │
│  Look for patterns across multiple quarters:                    │
│  • Consistent rounding up (>70% favor company)                  │
│  • Metric switching (different metrics each quarter)            │
│  • Increasing inaccuracy (accuracy declining)                   │
│  • GAAP shifting (switching GAAP/non-GAAP)                      │
│  • Selective emphasis (only positive metrics)                   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │   SQLite Database     │
               │                       │
               │  ┌─────────────────┐  │
               │  │ discrepancy_    │  │  ← Pattern detection
               │  │   patterns      │  │
               │  │  - pattern_type │  │
               │  │  - severity     │  │
               │  └─────────────────┘  │
               └───────────────────────┘
```

---

## 2. 6-Layer Architecture

Our system follows **clean architecture principles** with strict layer separation:

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: PRESENTATION                                       │
│ • FastAPI REST API  • Streamlit UI  • CLI  • MCP Server     │
│                                                             │
│ Responsibility: Handle requests, render responses           │
│ Dependencies: Only imports PipelineFacade                   │
│ Files: streamlit_app.py, app/main.py, mcp_server.py,       │
│        scripts/run_pipeline.py                              │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2: FACADE (Integration Layer)                         │
│ • PipelineFacade: Single entry point for all clients        │
│ • Wires up services, repos, engines, clients                │
│ • Returns only plain dicts (never ORM models)               │
│                                                             │
│ Responsibility: Hide complexity, prevent coupling           │
│ Dependencies: Services, Repos, Engines                      │
│ Files: app/facade.py                                        │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3: SERVICE (Orchestration Layer)                      │
│ • IngestionService   • ExtractionService                    │
│ • VerificationService • AnalysisService                     │
│                                                             │
│ Responsibility: Coordinate workflows, handle transactions   │
│ Dependencies: Engines, Repos, Clients                       │
│ Files: app/services/*.py                                    │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌─────────────────────────────────────────────────────────────┐
│ LAYER 4: DOMAIN (Business Logic Layer)                      │
│ Engines: ClaimExtractor, VerificationEngine,                │
│          DiscrepancyAnalyzer, MetricMapper                  │
│ Pure Functions: app/domain/{metrics, verdicts, scoring}.py  │
│                                                             │
│ Responsibility: Core algorithms, zero external dependencies │
│ Dependencies: Domain functions only                         │
│ Files: app/engines/*.py, app/domain/*.py                    │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌─────────────────────────────────────────────────────────────┐
│ LAYER 5: REPOSITORY (Data Access Layer)                     │
│ • BaseRepository (template method pattern)                  │
│ • CompanyRepo, ClaimRepo, VerificationRepo, etc.            │
│                                                             │
│ Responsibility: Abstract database operations                │
│ Dependencies: Models                                        │
│ Files: app/repositories/*.py                                │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌─────────────────────────────────────────────────────────────┐
│ LAYER 6: INFRASTRUCTURE                                     │
│ • SQLAlchemy ORM models  • HTTP clients (FMP, Anthropic)    │
│ • Database engine        • Configuration (Pydantic)         │
│                                                             │
│ Responsibility: External systems, persistence               │
│ Dependencies: None (lowest layer)                           │
│ Files: app/models/*.py, app/clients/*.py, app/database.py   │
└─────────────────────────────────────────────────────────────┘
```

### Dependency Flow

**Key principle:** Dependencies flow downward only.

```
Presentation → Facade → Services → Engines/Repos → Domain/Infrastructure
```

**Never the reverse.** This ensures:
- **Testability** - Test each layer independently
- **Flexibility** - Swap implementations without breaking dependents
- **Clarity** - Bugs have a clear location

---

## 3. Detailed Data Flow

### Complete Request Flow Example

**User action:** "Analyze AMZN"

```
1. USER
   │
   │ Clicks button in Streamlit UI
   ▼
┌──────────────────────────────────────┐
│ LAYER 1: streamlit_app.py           │
│                                      │
│ def show_company_details(ticker):    │
│     facade = get_facade()            │
│     data = facade.get_company_...    │
│                                      │
└──────────────┬───────────────────────┘
               │
               │ facade.get_company_analysis("AMZN")
               ▼
┌──────────────────────────────────────┐
│ LAYER 2: facade.py                  │
│                                      │
│ def get_company_analysis(ticker):    │
│     session = get_session()          │
│     service = AnalysisService(...)   │
│     result = service.analyze(...)    │
│     return result.to_dict()          │
│                                      │
└──────────────┬───────────────────────┘
               │
               │ service.analyze_company(company_id)
               ▼
┌──────────────────────────────────────┐
│ LAYER 3: analysis_service.py        │
│                                      │
│ def analyze_company(company_id):     │
│     # Get claims from database       │
│     claims = claim_repo.get(...)     │
│                                      │
│     # Run pattern detection          │
│     patterns = analyzer.analyze(...) │
│                                      │
│     # Calculate trust score          │
│     score = compute_trust_score(...) │
│                                      │
│     return Analysis(...)             │
│                                      │
└──────────────┬───────────────────────┘
               │
               ├─→ claim_repo.get_for_company(company_id)
               │   ┌──────────────────────────────────┐
               │   │ LAYER 5: claim_repo.py           │
               │   │                                  │
               │   │ def get_for_company(id):         │
               │   │     return session.query(Claim)  │
               │   │       .filter_by(company_id=id)  │
               │   │       .all()                     │
               │   │                                  │
               │   └──────────────────────────────────┘
               │
               └─→ analyzer.analyze_company(claims)
                   ┌──────────────────────────────────┐
                   │ LAYER 4: discrepancy_analyzer.py │
                   │                                  │
                   │ def analyze_company(claims):     │
                   │     patterns = []                │
                   │     patterns += detect_rounding()│
                   │     patterns += detect_switching()│
                   │     return patterns              │
                   │                                  │
                   └──────────────────────────────────┘
```

---

## 4. File-to-Layer Mapping

This visual map shows **exactly** which files belong to which layer and **why**.

```
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1: PRESENTATION                                           │
│ "Where users interact"                                          │
│                                                                 │
│ streamlit_app.py     → Web dashboard (humans click buttons)   │
│ app/main.py          → REST API (programs make HTTP calls)    │
│ mcp_server.py        → MCP server (AI agents connect)         │
│ scripts/run_pipeline.py → CLI (terminal commands)             │
│                                                                 │
│ WHY SEPARATE? You can add a mobile app without touching       │
│               anything below this layer                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓ calls
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2: FACADE                                                 │
│ "The simple menu"                                               │
│                                                                 │
│ app/facade.py        → Single entry point, hides complexity   │
│                                                                 │
│ WHY SEPARATE? Provides a stable interface. Internal changes   │
│               don't break external clients                     │
└─────────────────────────────────────────────────────────────────┘
                            ↓ calls
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3: SERVICES                                               │
│ "The coordinators"                                              │
│                                                                 │
│ app/services/ingestion_service.py    → Coordinates fetching   │
│ app/services/extraction_service.py   → Coordinates extraction │
│ app/services/verification_service.py → Coordinates verification│
│ app/services/analysis_service.py     → Coordinates analysis   │
│                                                                 │
│ WHY SEPARATE? Services handle workflows and transactions.     │
│               They don't DO the work, they COORDINATE it       │
└─────────────────────────────────────────────────────────────────┘
                            ↓ calls
┌───────────────────────────────┬─────────────────────────────────┐
│ LAYER 4A: ENGINES             │ LAYER 4B: REPOSITORIES          │
│ "The workers"                 │ "The database interface"        │
│                               │                                 │
│ app/engines/claim_extractor.py│ app/repositories/base.py        │
│   → Extracts claims via LLM   │   → Generic CRUD operations     │
│                               │                                 │
│ app/engines/verification_     │ app/repositories/claim_repo.py  │
│   engine.py                   │   → Claim-specific queries      │
│   → Core verification logic   │                                 │
│   → 400+ lines                │ app/repositories/company_repo.py│
│                               │   → Company queries             │
│ app/engines/metric_mapper.py │                                 │
│   → Maps metrics to DB columns│ app/repositories/verification_ │
│                               │   repo.py                       │
│ app/engines/discrepancy_      │   → Verification queries        │
│   analyzer.py                 │                                 │
│   → Detects patterns          │                                 │
│                               │                                 │
│ WHY SEPARATE ENGINES?         │ WHY SEPARATE REPOS?            │
│ Pure business logic that can  │ Abstracts database access so   │
│ be tested without touching    │ you can swap SQLite for        │
│ database or external APIs     │ Postgres without changing      │
│                               │ services or engines            │
└───────────────────────────────┴─────────────────────────────────┘
                            ↓ calls
┌───────────────────────────────┬─────────────────────────────────┐
│ LAYER 5: DOMAIN               │ LAYER 4C: CLIENTS               │
│ "The pure rules"              │ "The API wrappers"              │
│                               │                                 │
│ app/domain/metrics.py         │ app/clients/base_client.py      │
│   → Metric definitions        │   → HTTP retry logic            │
│                               │                                 │
│ app/domain/verdicts.py        │ app/clients/fmp_client.py       │
│   → Verdict assignment rules  │   → FMP API calls               │
│                               │                                 │
│ app/domain/scoring.py         │ app/clients/llm_client.py       │
│   → Trust score formulas      │   → Claude API calls            │
│                               │                                 │
│ WHY SEPARATE DOMAIN?          │ WHY SEPARATE CLIENTS?          │
│ ZERO dependencies. These are │ External APIs change. When FMP │
│ your business rules. Can test │ updates, you only change this  │
│ with: assert verdict(.99)=="ok"│ file. Core logic unaffected   │
└───────────────────────────────┴─────────────────────────────────┘
                            ↓ uses
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 6: MODELS & SCHEMAS                                       │
│ "Data structures"                                               │
│                                                                 │
│ app/models/*.py              → Database tables (SQLAlchemy ORM)│
│   - What you STORE                                             │
│   - company.py, claim.py, verification.py, etc.                │
│                                                                 │
│ app/schemas/*.py             → API contracts (Pydantic)        │
│   - What you SEND/RECEIVE                                      │
│   - claim.py, verification.py, discrepancy.py                  │
│                                                                 │
│ WHY SEPARATE? Database structure ≠ API structure. You can     │
│               add DB columns without breaking API clients      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Pipeline Execution Flow

### Detailed Method Call Chain

When you run `python -m scripts.run_pipeline`:

```python
# scripts/run_pipeline.py
def main():
    facade = PipelineFacade()
    facade.run_pipeline(tickers=["AMZN"], steps="all")

# ═══════════════════════════════════════════════════════════════
# STEP 1: INGEST
# ═══════════════════════════════════════════════════════════════
facade.run_pipeline()
  ├─→ ingestion_service.ingest_company("AMZN")
  │   ├─→ fmp_client.get_company_profile("AMZN")
  │   │   ├─ Check cache: data/fmp_cache/profile_AMZN.json
  │   │   └─ If not cached: HTTP GET → save to cache
  │   │
  │   ├─→ company_repo.get_by_ticker("AMZN")
  │   │   └─ If exists: skip, else: company_repo.create(...)
  │   │
  │   ├─→ fmp_client.get_transcripts("AMZN", quarters)
  │   │   ├─ Try FMP API endpoint
  │   │   └─ If fails: fallback to data/transcripts/AMZN_Q1_2025.txt
  │   │
  │   ├─→ transcript_repo.get_by_ticker_quarter(AMZN, Q1, 2025)
  │   │   └─ If exists: skip, else: transcript_repo.create(...)
  │   │
  │   ├─→ fmp_client.get_income_statement("AMZN")
  │   ├─→ fmp_client.get_cash_flow("AMZN")
  │   ├─→ fmp_client.get_balance_sheet("AMZN")
  │   │   └─ All cached in data/fmp_cache/
  │   │
  │   └─→ For each quarter:
  │       ├─ Merge income/cash/balance data
  │       └─ financial_data_repo.create(revenue=155.7B, ...)

# ═══════════════════════════════════════════════════════════════
# STEP 2: EXTRACT
# ═══════════════════════════════════════════════════════════════
facade.run_pipeline()
  ├─→ extraction_service.extract_all()
  │   ├─→ transcript_repo.get_all() → [transcript1, ...]
  │   │
  │   └─→ For each transcript:
  │       ├─→ claim_repo.count_by_transcript(transcript.id)
  │       │   └─ If > 0: skip (already extracted)
  │       │
  │       ├─→ claim_extractor.extract(transcript.full_text)
  │       │   ├─→ prompt_manager.get_latest("claim_extraction")
  │       │   │   └─ Load app/prompts/templates/claim_extraction/v1.txt
  │       │   │
  │       │   ├─→ llm_client.extract_claims(system, transcript)
  │       │   │   ├─ Call Anthropic API
  │       │   │   └─ Return JSON array of claims
  │       │   │
  │       │   ├─ For each claim dict:
  │       │   │  ├─ Validate with Pydantic (ClaimCreate)
  │       │   │  └─ If invalid: skip
  │       │   │
  │       │   ├─ Deduplicate (remove exact duplicates)
  │       │   └─ Return [ClaimCreate, ...]
  │       │
  │       └─→ claim_repo.create_many(claims)

# ═══════════════════════════════════════════════════════════════
# STEP 3: VERIFY
# ═══════════════════════════════════════════════════════════════
facade.run_pipeline()
  ├─→ verification_service.verify_all()
  │   ├─→ claim_repo.get_unverified() → [claim1, ...]
  │   │
  │   └─→ For each claim:
  │       ├─→ verification_engine.verify(claim)
  │       │   ├─→ metric_mapper.can_resolve(claim.metric)
  │       │   │   └─ Check if "revenue" maps to DB column
  │       │   │
  │       │   ├─ If unresolvable:
  │       │   │  └─ Return Verification(verdict="unverifiable")
  │       │   │
  │       │   ├─→ metric_mapper.resolve(claim, financial_data)
  │       │   │   ├─ For growth: fetch current + prior quarter
  │       │   │   ├─ For margins: compute (numerator/denominator)
  │       │   │   └─ For absolute: get raw value
  │       │   │
  │       │   ├─→ _normalize_stated_and_comparable(stated, actual)
  │       │   │   └─ Convert both to same unit (billions/millions)
  │       │   │
  │       │   ├─→ accuracy_score(stated, actual)
  │       │   │   └─ 1 - |stated - actual| / |actual|
  │       │   │
  │       │   ├─→ _check_misleading_flags(claim, actual)
  │       │   │   ├─ Rounding bias?
  │       │   │   ├─ GAAP mismatch?
  │       │   │   └─ Segment flag?
  │       │   │
  │       │   ├─→ assign_verdict(accuracy, flags)
  │       │   │   └─ domain/verdicts.py logic
  │       │   │
  │       │   └─ Generate explanation string
  │       │
  │       └─→ verification_repo.create(...)

# ═══════════════════════════════════════════════════════════════
# STEP 4: ANALYZE
# ═══════════════════════════════════════════════════════════════
facade.run_pipeline()
  └─→ analysis_service.analyze_all()
      ├─→ company_repo.get_all() → [company1, ...]
      │
      └─→ For each company:
          ├─→ claim_repo.get_by_company(company.id)
          │   └─ Returns claims grouped by quarter
          │
          ├─→ discrepancy_analyzer.analyze_company(claims_by_q)
          │   ├─ _detect_rounding_bias()
          │   ├─ _detect_metric_switching()
          │   ├─ _detect_increasing_inaccuracy()
          │   ├─ _detect_gaap_shifting()
          │   └─ _detect_selective_emphasis()
          │
          ├─→ pattern_repo.delete_for_company(company.id)
          │   └─ Remove old patterns
          │
          └─→ pattern_repo.create_many(patterns)
```

---

## 6. Key Design Decisions

### 1. Why Repository Pattern?

**Problem:** Services directly using SQLAlchemy queries.

**Bad (without repos):**
```python
# services/verification_service.py
def verify_all():
    claims = session.query(ClaimModel)\
        .filter(ClaimModel.verification == None)\
        .all()  # SQLAlchemy leaking into service
```

**Good (with repos):**
```python
# services/verification_service.py
def verify_all():
    claims = claim_repo.get_unverified()  # Clean abstraction
```

**Benefits:**
- Swap SQLite → Postgres: change 1 file (repo), not 50 (services)
- Easy to mock for testing
- Single place to optimize queries
- Services don't know about database

### 2. Why Facade Pattern?

**Problem:** Presentation layer calling multiple services directly.

**Bad (without facade):**
```python
# streamlit_app.py
def show_analysis(ticker):
    company = CompanyRepository(db).get_by_ticker(ticker)
    claims = ClaimRepository(db).get_for_company(company.id)
    verifications = VerificationRepository(db).get_for_claims(claims)
    # ... 50 more lines of service coordination
```

**Good (with facade):**
```python
# streamlit_app.py
def show_analysis(ticker):
    data = facade.get_company_analysis(ticker)
    # Single call, simple interface
```

**Benefits:**
- Presentation layer doesn't know about internal structure
- Can refactor services without breaking UI/API
- Single integration point
- Easier to test

### 3. Why Separate Domain Layer?

**Problem:** Business rules mixed with infrastructure.

**Bad (mixed):**
```python
# verification_service.py
def verify(claim):
    # Business rule buried in service
    if accuracy >= 0.98:
        verdict = "correct"
    elif accuracy >= 0.90:
        verdict = "mostly_correct"
    # ...
```

**Good (separated):**
```python
# domain/verdicts.py (pure function)
def assign_verdict(accuracy_score):
    if accuracy_score >= 0.98:
        return "correct"
    elif accuracy_score >= 0.90:
        return "mostly_correct"
    # ...

# verification_service.py
def verify(claim):
    verdict = assign_verdict(accuracy)  # Use domain function
```

**Benefits:**
- Business rules testable without database/APIs
- Testing: `assert assign_verdict(0.99) == "correct"` (instant)
- Clear location for business logic
- Zero dependencies = maximum portability

### 4. Why Service Layer?

**Problem:** Business logic mixed with database operations and external API calls.

**Bad (without services):**
```python
# verification_engine.py - doing too much
def verify_all():
    # Database access in engine
    session = get_session()
    claims = session.query(Claim).filter_by(verified=False).all()

    # Business logic
    for claim in claims:
        result = self._calculate_accuracy(claim)

        # Database writes in engine
        session.add(Verification(claim_id=claim.id, ...))
    session.commit()  # Transaction management in wrong place
```

**Good (with services):**
```python
# verification_service.py - orchestrates
def verify_all(self):
    # Get data via repo
    claims = self.claim_repo.get_unverified()

    # Process via engine
    for claim in claims:
        result = self.engine.verify(claim)

        # Save via repo
        self.verification_repo.create(result)
    # Transaction boundary handled here
```

**Benefits:**
- **Transaction boundaries** - Services manage database transactions, not engines
- **Orchestration** - Coordinate multiple engines and repos
- **Error handling** - Centralized place for rollback logic
- **Workflow control** - Services know WHAT and WHEN, engines know HOW

Services are the orchestration layer. They coordinate workflows, manage transactions, and handle the sequence of operations. Engines have pure business logic, repos have data access, services tie them together.

---

### 5. Why Engine Layer?

**Problem:** Business logic mixed with orchestration logic.

**Bad (logic in services):**
```python
# verification_service.py - too much business logic
def verify(self, claim):
    # Complex business logic buried in service
    stated = claim.stated_value
    actual = self._get_actual_from_db(claim)

    # Normalization logic
    if claim.unit == "billions":
        stated *= 1_000_000_000

    # Calculation logic
    accuracy = 1 - abs(stated - actual) / abs(actual)

    # Verdict logic
    if accuracy >= 0.98:
        verdict = "correct"
    # ... 50 more lines of business logic
```

**Good (extracted to engine):**
```python
# verification_engine.py - pure business logic
def verify(self, claim: Claim, financial_data: FinancialData) -> Verification:
    actual = self.metric_mapper.resolve(claim, financial_data)
    normalized_stated, normalized_actual = self._normalize(stated, actual)
    accuracy = self._calculate_accuracy(normalized_stated, normalized_actual)
    flags = self._check_misleading_flags(claim, actual)
    verdict = assign_verdict(accuracy, flags)
    return Verification(verdict=verdict, accuracy=accuracy, ...)

# verification_service.py - simple orchestration
def verify_all(self):
    claims = self.claim_repo.get_unverified()
    for claim in claims:
        financial_data = self.financial_data_repo.get_for_claim(claim)
        result = self.engine.verify(claim, financial_data)  # Just call engine
        self.verification_repo.create(result)
```

**Benefits:**
- **Testability** - Test business logic without database: `assert engine.verify(claim, data).verdict == "correct"`
- **Reusability** - Engine can be used by CLI, API, or batch jobs
- **Focus** - Engine focuses on HOW (algorithm), service focuses on WHAT (workflow)
- **No side effects** - Engines are pure: same inputs → same outputs

Engines contain pure business logic with no side effects. They take inputs, apply algorithms, return outputs. Services call engines, but engines never call services or repos. This makes business logic independently testable without mocking infrastructure.

---

### 6. Why Separate Clients?

**Problem:** External API calls scattered throughout codebase.

**Bad (API calls in services):**
```python
# ingestion_service.py - HTTP calls directly in service
def ingest_company(self, ticker: str):
    # Service making HTTP calls
    response = requests.get(
        f"https://financialmodelingprep.com/api/v3/profile/{ticker}",
        params={"apikey": self.api_key}
    )
    data = response.json()

    # What if API changes? Have to update every service
```

**Good (wrapped in client):**
```python
# clients/fmp_client.py - encapsulated
class FMPClient:
    def get_company_profile(self, ticker: str) -> dict:
        return self._get(f"/profile/{ticker}")

    def _get(self, endpoint: str) -> dict:
        # Retry logic, caching, error handling centralized
        return self._retry_with_backoff(...)

# ingestion_service.py - clean
def ingest_company(self, ticker: str):
    profile = self.fmp_client.get_company_profile(ticker)
    # Service doesn't know about HTTP, retries, caching
```

**Benefits:**
- **Encapsulation** - API details hidden from services
- **Centralized logic** - Retry, caching, error handling in one place
- **Easy swapping** - Switch FMP to Yahoo Finance, change one file
- **Testing** - Mock client instead of HTTP calls

Clients wrap external APIs to isolate integration details. Services call `client.get_profile(ticker)`, not `requests.get(url)`. When external APIs change, you update one client, not ten services. Also centralizes retry logic and caching.

---

### 7. Why Models vs Schemas?

**Problem:** Exposing ORM models directly to API clients.

**Bad (ORM leakage):**
```python
# API returns ORM model directly
@app.get("/claims/{id}")
def get_claim(id: int):
    return ClaimModel.query.get(id)  # SQLAlchemy object exposed
```

**Good (schemas):**
```python
# API returns Pydantic schema
@app.get("/claims/{id}", response_model=ClaimWithVerification)
def get_claim(id: int):
    claim = claim_repo.get(id)
    return ClaimWithVerification.from_orm(claim)  # Controlled contract
```

**Benefits:**
- Database changes don't break API
- Control what clients see (hide internal fields)
- Validation at API boundary
- ORM implementation detail

---

### 8. Why This Layering (Not MVC)?

**Problem:** Traditional MVC doesn't scale for complex domains.

**MVC issues:**
```
Model (data + logic) ← Fat models with business logic
View (presentation)
Controller (request handling)
```

**Problems with MVC for this domain:**
- Models become "god objects" with too many responsibilities
- Business logic mixed with ORM concerns
- Hard to test (models tied to database)
- No clear place for orchestration

**Our layering:**
```
Presentation → Facade → Services → Engines/Repos/Clients → Domain → Infrastructure
```

**Why better:**
- **Single Responsibility** - Each layer has one job
- **Testability** - Test each layer independently
- **Flexibility** - Swap implementations without breaking dependents
- **Clarity** - Bug in verification? Check VerificationEngine, not "Claim model"

MVC works for simple CRUD apps, but not for complex domains with orchestration, external APIs, and algorithmic logic. Clean architecture provides clear separation: services orchestrate, engines compute, repos persist. Each layer is independently testable and swappable.

---

### 9. Why Pydantic for Schemas?

**Decision:** Use Pydantic 2.0 for API contracts and validation.

**Why Pydantic:**
- **Fast validation** - Rust core, 10-50x faster than manual validation
- **Type safety** - Integrates with Python type hints
- **Auto-documentation** - FastAPI generates OpenAPI docs from Pydantic models
- **Serialization** - `.model_dump()`, `.model_dump_json()` built-in
- **Conversion** - `.from_orm()` converts SQLAlchemy models to Pydantic

**Alternative considered:** Dataclasses + manual validation
- Slower
- No auto-docs
- Have to write serialization logic

Pydantic provides fast validation, type safety, and auto-documentation. FastAPI generates OpenAPI specs from Pydantic schemas. The `.from_orm()` method cleanly converts database models to API contracts.

---

### 10. Why SQLAlchemy for Models?

**Decision:** Use SQLAlchemy 2.0 ORM for database access.

**Why SQLAlchemy:**
- **ORM benefits** - Write Python, not SQL (but can drop to SQL when needed)
- **Relationship management** - `claim.verification` auto-loads related objects
- **Migration support** - Alembic integrates seamlessly
- **Database agnostic** - Same code works for SQLite, Postgres, MySQL
- **Type hints** - SQLAlchemy 2.0 has full type support

**Alternative considered:** Raw SQL or asyncpg
- Pros: Faster, more control
- Cons: More boilerplate, harder to maintain relationships

SQLAlchemy provides ORM convenience while being database-agnostic. Repository pattern abstracts it anyway, so if we needed raw SQL for performance, we'd just change repository internals without touching services.

---

### 11. Why Deterministic Verification (Not LLM)?

**Decision:** Use algorithmic verification, not LLM-based.

**Why:**
- **Explainability** - Can show exact calculation
- **Consistency** - Same claim always gets same verdict
- **Testing** - Easy to write unit tests
- **Cost** - No API calls for verification (only extraction)

**Trade-off:** Less flexible than LLM (can't handle nuanced cases).

---

## 7. Interface Architecture

We have **4 interfaces**, all using the same backend:

```
The architecture has 3 interfaces:
┌─────────────────────────┐
│ CLI (run_pipeline.py)   │──┐
│ Uses: facade directly   │  │
└─────────────────────────┘  │
                             │
┌─────────────────────────┐  │    ┌──────────────────┐
│ Streamlit UI            │──┼───→│ PipelineFacade   │
│ Uses: facade directly   │  │    │ (single entry)   │
└─────────────────────────┘  │    └──────────────────┘
                             │
┌─────────────────────────┐  │
│ REST API (app/main.py)  │──┘
│ Uses: dependencies.py   │
│       schemas/*.py      │
└─────────────────────────┘

┌─────────────────────────┐
│ MCP Server              │───→ Also uses PipelineFacade
│ (AI agent integration)  │
└─────────────────────────┘
```

### Why Multiple Interfaces?

1. **CLI** - For pipeline execution, automation
2. **Streamlit** - For human exploration (visual dashboard)
3. **REST API** - For programmatic access (other systems)
4. **MCP Server** - For AI agent integration (Claude Code, Cursor)

**Key insight:** Same backend, different "faces". Add a mobile app? Just another interface.

---

## 8. Testing Strategy

### Test Pyramid

```
    ┌─────────────┐
    │ Integration │  ← 2 tests (E2E pipeline, live API)
    │   Tests     │    Slow, expensive, brittle
    └──────┬──────┘
       ┌───┴───┐
       │  Unit │      ← 228 tests (<2s runtime)
       │ Tests │        Fast, cheap, reliable
       └───────┘
```

### Testing Each Layer

**Domain layer (easiest):**
```python
def test_assign_verdict():
    assert assign_verdict(0.99) == "correct"
    assert assign_verdict(0.85) == "mostly_correct"
    # Pure functions = instant tests
```

**Engine layer:**
```python
def test_verification_engine(mock_financial_data):
    engine = VerificationEngine(mock_mapper, mock_repo, settings)
    result = engine.verify(claim)
    assert result.verdict == "misleading"
    # Mocked dependencies, tests logic only
```

**Service layer:**
```python
def test_verification_service(in_memory_db, mock_engine):
    service = VerificationService(mock_engine, claim_repo, verification_repo)
    service.verify_all()
    # Tests orchestration, not business logic
```

**Integration tests:**
```python
@pytest.mark.integration
def test_full_pipeline():
    # Requires: real database, real API keys
    facade.run_pipeline(tickers=["AAPL"], steps="all")
    # Tests everything together
```

### Why This Works

- **230 tests run in <2 seconds** (all unit tests)
- Integration tests skipped by default (`pytest -m integration` to run)
- Can test business logic without database/APIs
- Services tested with mocks
- Presentation tested against facade

---

## 9. Trade-offs

### SQLite vs Postgres

**Decision:** SQLite for development

**Why:**
- Zero configuration
- File-based (easy to share/demo)
- Good enough for <100K records

**Trade-off:**
- Doesn't scale (no concurrent writes)
- No advanced features (full-text search, JSON operators)

**Production path:** Swap to Postgres (only change: connection string in config)

### Deterministic vs LLM Verification

**Decision:** Algorithmic verification

**Why:**
- Explainable (show calculation)
- Testable (unit tests)
- Consistent (same result every time)
- Free (no API calls)

**Trade-off:**
- Less flexible (can't handle edge cases)
- Requires explicit rules

### Local Transcripts vs API

**Decision:** Fallback to local .txt files

**Why:**
- FMP transcript endpoint restricted on free tier
- Still demonstrates full pipeline

**Trade-off:**
- Manual transcript creation
- Doesn't scale to many companies

**Production path:** Pay for FMP Pro or use alternative API

### Monolith vs Microservices

**Decision:** Monolith

**Why:**
- Simple deployment (one container)
- No network overhead
- Easier to develop/debug

**Trade-off:**
- Can't scale services independently
- All-or-nothing deployment

**Production path:** Split into services (ingestion, extraction, verification) when traffic justifies it

---

## 10. Future Improvements

### Infrastructure Improvements

**Database & Caching:**
- **Postgres with connection pooling** - SQLite doesn't support concurrent writes; Postgres scales horizontally
- **Redis for distributed caching** - Current in-memory cache doesn't work across processes
- **Connection pooling** - Reuse database connections for better performance

**Async & Performance:**
- **Celery task queue** - Run pipeline steps asynchronously, enable parallel processing
- **Async/await throughout** - Currently synchronous for simplicity; async improves throughput
- **Message queue (RabbitMQ/Kafka)** - Decouple services for better scalability

**Operations:**
- **Structured logging (JSON)** - Enable log aggregation with ELK/Datadog
- **Rate limiting** - Protect API from abuse (currently unlimited)
- **Secret management** - Use Vault/AWS Secrets Manager instead of .env files
- **Health checks & metrics** - Prometheus/Grafana for monitoring

### Architecture Improvements

**Code Quality:**
- **Reduce architectural debt** - Refactor components that were rapidly prototyped
- **1:1 documentation** - Markdown file for each Python module with detailed explanations
- **Type hints coverage** - Ensure 100% type annotation for better IDE support
- **More granular error types** - Custom exceptions for different failure modes

**LLM Flexibility:**
- **OpenRouter integration** - Single interface for multiple LLM providers (Claude, GPT-4, Gemini)
- **Model switching** - Easy A/B testing between models via config
- **Prompt versioning** - Track prompt performance over time
- **Fallback models** - If Claude is down, auto-switch to GPT-4

### Feature Improvements

**User Experience:**
- **Custom React/Vue UI** - Replace Streamlit with production-grade frontend
- **UI-based company addition** - Let users add companies via interface (currently CLI only)
- **Real-time updates** - WebSocket for live pipeline status
- **User authentication** - Multi-user support with role-based access

**Functionality:**
- **Scheduled pipeline runs** - Cron-based automatic updates
- **Email/Slack notifications** - Alert on pattern detection
- **Export to PDF/Excel** - Generate reports for analysts
- **Historical trend analysis** - Track company accuracy over years

### Deployment Improvements

**Scalability:**
- **Horizontal scaling** - Multiple API instances behind load balancer
- **Microservices split** - Separate extraction (CPU-heavy) from verification (I/O-bound)
- **CDN for static assets** - Faster UI loading
- **Database read replicas** - Separate read/write workloads

**Reliability:**
- **Automated backups** - Daily database snapshots to S3
- **Disaster recovery** - Multi-region deployment
- **Circuit breakers** - Graceful degradation when external APIs fail
- **Retry with exponential backoff** - Already implemented, but extend to all external calls

---

## Summary: Architecture in One Paragraph


I built a 6-layer clean architecture with strict separation of concerns. The presentation layer (UI/API/CLI/MCP) calls a facade, which coordinates services. Services orchestrate workflows using engines (business logic), repositories (data access), and clients (external APIs). The domain layer contains pure business rules with zero dependencies, making them instantly testable. This architecture provides three key benefits: testability (230 tests run in <2 seconds), flexibility (swap databases without touching business logic), and clarity (bugs have a specific layer location). Every separation decision serves one of these goals.

**Key numbers to remember:**
- 6 layers
- 4 interfaces
- 230 tests (<2s)
- 400+ lines in core verification algorithm
- 0 dependencies in domain layer
