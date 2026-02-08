# Claim Auditor — Approach Document

## Problem Statement

Build a system that:
1. Ingests earnings call transcripts for **10 public companies × 4 quarters** (40 transcripts)
2. Extracts **quantitative claims** made by executives (CEO, CFO, etc.)
3. Verifies each claim against **actual structured financial data**
4. Flags **discrepancies and misleading framing**
5. (Bonus) Tracks **quarter-to-quarter discrepancy patterns**
6. Is **deployed** for interactive use

---

## Fundamental Analysis: What Makes This Hard

### 1. Claim Extraction is Ambiguous
Executives don't say "revenue was $X." They say things like:
- "We saw strong double-digit growth across our cloud business" (vague)
- "Revenue grew approximately 15% year-over-year" (verifiable)
- "Excluding one-time charges, our operating margin expanded" (adjusted metric)
- "We significantly outperformed our initial guidance" (relative to what?)

**Challenge**: We need to distinguish verifiable quantitative claims from vague qualitative statements, and we need to understand the context (time period, metric, comparison basis, whether it's GAAP or adjusted).

### 2. Financial Data Has Multiple Representations
- GAAP vs Non-GAAP (adjusted) metrics
- Revenue recognition can differ (ASC 606 timing)
- Companies report different segment breakdowns
- Currency effects can change numbers
- Restatements happen

**Challenge**: A claim can be "true" under one accounting framework and "misleading" under another. We need to be aware of this.

### 3. "Misleading" is Subjective (But We Can Systematize)
We define "misleading" as a spectrum:
- **Factually Incorrect**: The number is simply wrong (stated 15% growth, actual was 12%)
- **Selectively Framed**: True but cherry-picked (comparing to a weak quarter, ignoring recent decline)
- **Adjusted Without Disclosure**: Using non-GAAP without saying so
- **Rounding Bias**: Consistently rounding favorably ("approximately 20%" when it's 18.6%)
- **Misleading Comparison Basis**: Comparing to a non-standard period
- **Omission**: Highlighting revenue growth while ignoring margin compression

### 4. Data Acquisition is the Real Bottleneck
- Free transcript APIs are limited (most are paywalled)
- Financial data APIs have rate limits
- SEC EDGAR has XBRL data but it's complex to parse

---

## Strategic Decisions

### Companies (10 — chosen for data availability, claim density, sector mix)

| # | Company | Ticker | Sector | Why |
|---|---------|--------|--------|-----|
| 1 | Apple | AAPL | Tech | High-profile, rich quantitative claims |
| 2 | Microsoft | MSFT | Tech | Cloud growth claims, easy to verify |
| 3 | Amazon | AMZN | Tech/Retail | Complex segments, AWS vs retail |
| 4 | Alphabet | GOOGL | Tech | Advertising + Cloud metrics |
| 5 | Meta | META | Tech | Heavy user metric claims |
| 6 | Tesla | TSLA | Auto/Tech | Elon makes bold claims, interesting to verify |
| 7 | NVIDIA | NVDA | Semiconductors | Explosive growth claims |
| 8 | JPMorgan Chase | JPM | Finance | Financial sector representation |
| 9 | Netflix | NFLX | Media | Subscriber + revenue metrics |
| 10 | Salesforce | CRM | SaaS | Enterprise SaaS metrics |

### Data Sources

**Transcripts**: 
- **Primary**: Financial Modeling Prep (FMP) API — free tier has transcripts
- **Fallback**: SEC EDGAR 8-K filings (some companies file transcripts)
- **Alternative**: Scrape from public sources as last resort

**Financial Data**:
- **Primary**: Financial Modeling Prep API — income statement, balance sheet, cash flow
- **Secondary**: Yahoo Finance API (yfinance) — for quick lookups
- **Validation**: SEC EDGAR XBRL — for authoritative numbers

### Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.12+ | Fast to build, rich ecosystem for NLP/finance |
| Backend Framework | FastAPI | Async, fast, auto-docs, production-ready |
| LLM | Anthropic Claude API | Best at structured extraction, we know the API |
| Database | SQLite (dev) → PostgreSQL (prod) | Simple locally, scalable for deployment |
| ORM | SQLAlchemy | Type-safe, declarative models |
| Frontend | Next.js (React) | Modern, deployable on Vercel |
| Deployment | Railway (API) + Vercel (UI) | Easy, free tier available |
| Testing | pytest + pytest-asyncio | TDD from the start |

### Quarters to Analyze
Last 4 quarters from current date (Feb 2026):
- Q3 2025 (July-Sept 2025)
- Q2 2025 (April-June 2025)
- Q1 2025 (Jan-March 2025)
- Q4 2024 (Oct-Dec 2024)

Note: Some Q3/Q4 2025 results may not yet be filed. We adjust to whatever 4 most recent quarters are available per company.

---

## System Architecture (High Level)

```
┌──────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                    │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Company   │  │ Transcript   │  │ Claim Verification     │ │
│  │ Selector  │  │ Viewer       │  │ Dashboard              │ │
│  └──────────┘  └──────────────┘  └────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────┘
                           │ REST API
┌──────────────────────────▼───────────────────────────────────┐
│                      FastAPI Backend                          │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    API Layer                              │ │
│  │  /companies  /transcripts  /claims  /verifications       │ │
│  └──────────────────────┬──────────────────────────────────┘ │
│                          │                                    │
│  ┌──────────────────────▼──────────────────────────────────┐ │
│  │                  Service Layer                            │ │
│  │                                                           │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │ │
│  │  │ Transcript   │  │ Claim        │  │ Verification  │  │ │
│  │  │ Service      │  │ Extractor    │  │ Engine        │  │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬────────┘  │ │
│  │         │                  │                  │           │ │
│  │  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼────────┐  │ │
│  │  │ Financial    │  │ LLM          │  │ Discrepancy   │  │ │
│  │  │ Data Service │  │ Client       │  │ Analyzer      │  │ │
│  │  └──────────────┘  └──────────────┘  └───────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          │                                    │
│  ┌──────────────────────▼──────────────────────────────────┐ │
│  │              Data Access Layer (Repository)               │ │
│  │                                                           │ │
│  │  SQLAlchemy Models + Repository Pattern                   │ │
│  └──────────────────────┬──────────────────────────────────┘ │
│                          │                                    │
│  ┌──────────────────────▼──────────────────────────────────┐ │
│  │                    Database (SQLite/Postgres)             │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## Pipeline Flow

```
Step 1: DATA INGESTION
  ┌────────────┐     ┌────────────────┐
  │ FMP API    │────▶│ Raw Transcripts │
  │ (transcripts)│   │ (text)          │
  └────────────┘     └───────┬─────────┘
                              │
  ┌────────────┐     ┌───────▼─────────┐
  │ FMP/Yahoo  │────▶│ Financial Data   │
  │ (financials)│    │ (structured)     │
  └────────────┘     └───────┬─────────┘
                              │
Step 2: CLAIM EXTRACTION      │
  ┌────────────┐     ┌───────▼─────────┐
  │ Claude API │────▶│ Extracted Claims │
  │ (LLM)     │     │ (structured)     │
  └────────────┘     └───────┬─────────┘
                              │
Step 3: VERIFICATION          │
  ┌────────────┐     ┌───────▼─────────┐
  │ Financial  │────▶│ Verified Claims  │
  │ Data       │     │ (with verdicts)  │
  └────────────┘     └───────┬─────────┘
                              │
Step 4: ANALYSIS              │
                      ┌───────▼─────────┐
                      │ Discrepancy      │
                      │ Report           │
                      └─────────────────┘
```

---

## Claim Extraction Strategy

### What We're Looking For
The LLM will extract claims with this structure:
```
{
  "claim_text": "revenue grew 15% year-over-year",
  "speaker": "Tim Cook, CEO",
  "metric": "revenue",
  "metric_type": "growth_rate",      // absolute | growth_rate | margin | ratio
  "stated_value": 15.0,
  "unit": "percent",
  "comparison_period": "year-over-year",
  "comparison_basis": "Q3 2024 vs Q3 2023",
  "is_gaap": true,                   // or false if they say "adjusted" or "non-GAAP"
  "segment": null,                   // or "Cloud", "AWS", etc.
  "context": "opening remarks about quarterly performance"
}
```

### Categories of Claims
1. **Revenue claims**: Total revenue, segment revenue, growth rates
2. **Profitability claims**: EPS, operating income, margins, EBITDA
3. **Cash flow claims**: Free cash flow, operating cash flow
4. **Growth metrics**: YoY growth, QoQ growth, CAGR
5. **Operational metrics**: Users, subscribers, units sold (harder to verify from financials alone)
6. **Guidance claims**: Forward-looking (we can compare to previous guidance)

### Extraction Prompt Strategy
Use Claude with structured output:
1. **System prompt**: Define what constitutes a "quantitative claim" with examples
2. **Few-shot examples**: Show claim extraction from sample text
3. **Output schema**: Enforce JSON structure with all required fields
4. **Multi-pass**: First extract candidates, then classify and structure

---

## Verification Logic

### Verification Steps
For each extracted claim:

1. **Resolve the metric**: Map "revenue" → `totalRevenue` in financial data
2. **Resolve the time period**: Map "year-over-year" → compare Q3 2025 to Q3 2024
3. **Compute the actual value**: Calculate from financial data
4. **Compare**: Stated value vs actual value
5. **Score**: How accurate? How misleading?

### Metric Mapping
```
"revenue"                → income_statement.revenue
"earnings per share"     → income_statement.eps / income_statement.epsdiluted
"operating income"       → income_statement.operatingIncome
"operating margin"       → income_statement.operatingIncome / income_statement.revenue
"net income"             → income_statement.netIncome
"gross margin"           → income_statement.grossProfit / income_statement.revenue
"free cash flow"         → cash_flow.freeCashFlow
"operating cash flow"    → cash_flow.operatingCashFlow
"R&D spending"           → income_statement.researchAndDevelopmentExpenses
```

### Verification Scoring
```
accuracy_score = 1.0 - abs(stated_value - actual_value) / abs(actual_value)

Verdict:
  VERIFIED     : accuracy_score >= 0.98  (within 2%)
  APPROXIMATELY: accuracy_score >= 0.90  (within 10% — "approximately" claims)
  MISLEADING   : accuracy_score >= 0.75  (off by 10-25%)
  INCORRECT    : accuracy_score < 0.75   (off by 25%+)
  UNVERIFIABLE : cannot find matching financial data
```

### Misleading Framing Detection
Beyond simple number comparison:

1. **GAAP vs Non-GAAP mismatch**: Claim sounds like GAAP but only true for adjusted
2. **Cherry-picked period**: Comparing to unusually weak/strong quarter
3. **Segment vs Total confusion**: Claiming "growth" but only for one segment
4. **Rounding bias**: Always rounding in favorable direction (18.6% → "approximately 20%")
5. **Quarter-over-quarter inconsistency** (bonus): Claim type of metric changes, suggesting they highlight whatever looks best

---

## Database Schema

```
companies
  id, ticker, name, sector

transcripts  
  id, company_id, quarter, year, date, full_text, speaker_sections

financial_data
  id, company_id, period, year, quarter, 
  revenue, cost_of_revenue, gross_profit, operating_income,
  net_income, eps, eps_diluted, ebitda,
  operating_cash_flow, free_cash_flow,
  total_assets, total_debt, shareholders_equity

claims
  id, transcript_id, speaker, claim_text, 
  metric, metric_type, stated_value, unit,
  comparison_period, comparison_basis,
  is_gaap, segment, context_snippet

verifications
  id, claim_id, actual_value, accuracy_score,
  verdict (VERIFIED|APPROXIMATELY|MISLEADING|INCORRECT|UNVERIFIABLE),
  explanation, financial_data_used,
  misleading_flags (JSON array of detected issues)

discrepancy_patterns (bonus)
  id, company_id, pattern_type, description, 
  affected_quarters, severity
```

---

## Frontend Design

### Pages
1. **Dashboard**: Overview of all 10 companies with aggregate scores
   - Traffic-light system: Green (mostly verified), Yellow (some issues), Red (many discrepancies)
   - Sortable by accuracy, company, quarter

2. **Company Detail**: Deep dive into one company
   - 4 quarters of data
   - All claims listed with verdicts
   - Quarter-to-quarter pattern analysis (bonus)
   
3. **Claim Detail**: Individual claim verification
   - Original transcript context (highlighted)
   - Stated vs actual comparison
   - Explanation of verdict
   - Misleading flags with explanations

4. **Transcript Viewer**: Full transcript with claims highlighted
   - Color-coded by verdict
   - Click to see verification details

---

## What "Misleading" Means to Our System

Our definition is principled and systematic:

**Level 0 — VERIFIED**: The claim matches financial data within 2% tolerance. The comparison basis is standard and clearly stated.

**Level 1 — APPROXIMATELY CORRECT**: The claim is directionally correct and within 10%. Common with rounded figures. Not misleading per se.

**Level 2 — MISLEADING FRAMING**: The number may be technically correct but the framing creates a false impression:
- Using non-GAAP without disclosure
- Cherry-picking comparison periods
- Highlighting segment performance while total company declined
- Rounding consistently in one direction

**Level 3 — FACTUALLY INCORRECT**: The stated number is materially wrong (>10% off) even under the most charitable interpretation.

**Level 4 — UNVERIFIABLE**: The claim references a metric we can't verify from public financial data (e.g., internal operational metrics).

---

## Development Phases

### Phase 1: Data Pipeline (Day 1)
- Set up project structure, database, models
- Build FMP API client for transcripts
- Build FMP/Yahoo Finance client for financial data
- Ingest data for all 10 companies × 4 quarters
- Tests: API client tests (mocked), data model tests

### Phase 2: Claim Extraction (Day 1-2)
- Build Claude API integration
- Design extraction prompt with few-shot examples
- Build structured claim parser
- Extract claims from all 40 transcripts
- Tests: Extraction accuracy tests with known transcripts

### Phase 3: Verification Engine (Day 2)
- Build metric mapper (claim metric → financial data field)
- Build time period resolver
- Build verification scorer
- Verify all extracted claims
- Tests: Verification logic unit tests with known claims

### Phase 4: Discrepancy Analysis (Day 2)
- Build misleading framing detector
- Build quarter-to-quarter pattern analyzer (bonus)
- Generate discrepancy reports
- Tests: Discrepancy detection tests

### Phase 5: API Layer (Day 2-3)
- FastAPI endpoints for all entities
- Pagination, filtering, sorting
- Error handling, validation
- Tests: API integration tests

### Phase 6: Frontend + Deployment (Day 3)
- Next.js dashboard
- Company detail pages
- Claim verification detail
- Deploy to Railway + Vercel
- Tests: E2E smoke tests

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| FMP API rate limits | Cache all data locally after first fetch |
| LLM extraction errors | Validate structure, confidence scoring, human review flag |
| Financial data mismatches | Cross-reference multiple sources, handle GAAP vs non-GAAP |
| Deployment issues | Test locally first, simple deployment targets |
| Time pressure | Prioritize core pipeline > UI > bonus features |

---

## What I'd Improve With More Time

1. **More sophisticated NLP**: Fine-tuned extraction model instead of prompt engineering
2. **Real-time processing**: Watch for new transcripts and auto-verify
3. **Historical analysis**: Look at years of calls to find patterns of misleading behavior
4. **Comparison to analyst expectations**: Verify against consensus estimates too
5. **Sentiment analysis**: Detect tone shifts when discussing bad numbers
6. **Multi-source verification**: Cross-reference SEC EDGAR XBRL, Bloomberg, etc.
7. **User feedback loop**: Let users flag claims the system missed or misclassified
8. **Confidence intervals**: Better uncertainty quantification on verifications
