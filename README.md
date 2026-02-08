# Claim Auditor

**Analyzes earnings call transcripts, extracts quantitative claims made by management, and verifies them against actual financial data.**

Executives say things on earnings calls. This system checks if what they say is true.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Quick Start (TL;DR)](#quick-start-tldr)
3. [Prerequisites & Setup](#prerequisites--setup)
4. [Project Structure](#project-structure)
5. [How the Pipeline Works](#how-the-pipeline-works)
6. [Running the Pipeline](#running-the-pipeline)
7. [Viewing Results (Streamlit UI)](#viewing-results-streamlit-ui)
8. [Running Tests](#running-tests)
9. [Adding a New Company](#adding-a-new-company)
10. [API Clients & How Data Flows](#api-clients--how-data-flows)
11. [Verification Logic](#verification-logic)
12. [Cross-Quarter Discrepancy Detection (Bonus)](#cross-quarter-discrepancy-detection-bonus)
13. [MCP Server — AI Agent Skill](#mcp-server--ai-agent-skill)
14. [Deployment (Docker)](#deployment-docker)
15. [Architecture Diagram](#architecture-diagram)
16. [Key Design Decisions](#key-design-decisions)
17. [Scaling to Production](#scaling-to-production)

---

## What It Does

1. **Ingests** transcripts and financial statements for public companies via the [Financial Modeling Prep](https://financialmodelingprep.com) API
2. **Extracts** quantitative claims using Claude — every time a CEO says "revenue grew 15%", we capture it with structured metadata
3. **Verifies** each claim against structured financial data with a multi-tier verdict system
4. **Detects cross-quarter patterns** — consistent rounding bias, metric switching, increasing inaccuracy, GAAP/non-GAAP shifting, selective emphasis

### Verdict Tiers

| Verdict | Meaning | Threshold |
|---------|---------|-----------|
| ✅ Verified | Claim matches the data | Within 2% |
| ≈ Approximately Correct | Close but not exact | Within 10% |
| ⚠️ Misleading | Numerically questionable or deceptively framed | 10–25% off, or flagged framing |
| ❌ Incorrect | Materially wrong | >25% off |
| ❓ Unverifiable | Can't check (segment data, non-financial metric, etc.) | — |

### What "Misleading" Means

A claim can be misleading even if the number is approximately right. We flag:
- **Favorable rounding** — saying "grew 11%" when the real number is 10.3%
- **GAAP/non-GAAP mismatch** — using adjusted figures without disclosure
- **Segment vs. total** — quoting a segment number against total-company data
- **Cross-quarter patterns** — consistently rounding up, switching which metric gets highlighted, increasing inaccuracy over time

---

## Quick Start (TL;DR)

```bash
# 1. Setup
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
# Edit .env and add your FMP_API_KEY and ANTHROPIC_API_KEY

# 3. Run the full pipeline (ingest → extract → verify → analyze)
python -m scripts.run_pipeline

# 4. Launch the UI
.venv/bin/streamlit run streamlit_app.py --server.port 8501

# 5. Open http://localhost:8501
```

---

## Prerequisites & Setup

### What You Need

| Requirement | Notes |
|-------------|-------|
| **Python 3.12+** | Tested on 3.13 |
| **FMP API Key** | Get one free at [financialmodelingprep.com](https://financialmodelingprep.com/developer/docs/) |
| **Anthropic API Key** | Get one at [console.anthropic.com](https://console.anthropic.com/) |

### Step-by-Step Setup

```bash
# Clone and enter the project
cd claim-auditor/backend

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

### Configure Environment Variables

Create a `.env` file in `backend/`:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
FMP_API_KEY=your_fmp_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

That's it. Everything else (database path, model name, tolerances, target companies) has sensible defaults in `app/config.py`.

### Configuration Reference (`app/config.py`)

| Setting | Default | What It Controls |
|---------|---------|-----------------|
| `database_url` | `sqlite:///./data/claim_auditor.db` | Where the SQLite DB is stored |
| `fmp_base_url` | `https://financialmodelingprep.com/stable` | FMP API base URL (stable endpoint) |
| `claude_model` | `claude-sonnet-4-20250514` | Which Claude model to use |
| `verification_tolerance` | `0.02` | ≤2% → Verified |
| `approximate_tolerance` | `0.10` | ≤10% → Approximately Correct |
| `misleading_threshold` | `0.25` | ≤25% → Misleading; >25% → Incorrect |
| `target_tickers` | `["AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "META", "JPM", "JNJ", "TSLA", "CRM"]` | Companies to process by default |
| `target_quarters` | `[(2026,3)...(2025,1)]` | Fiscal quarters to target |
| `max_claims_per_transcript` | `50` | Cap on extracted claims per transcript |

---

## Project Structure

```
claim-auditor/
├── docs/
│   ├── doc.md                    # Approach document
│   └── spec.md                   # Specification document
├── README.md                          ← You are here
├── backend/
│   ├── .env                           ← Your API keys (git-ignored)
│   ├── requirements.txt               ← Python dependencies
│   ├── pyproject.toml                 ← Project metadata & pytest config
│   │
│   ├── app/                           ← Core application code
│   │   ├── config.py                  ← Settings (loaded from .env)
│   │   ├── database.py                ← SQLAlchemy engine & session setup
│   │   ├── facade.py                  ← Pipeline facade (decoupling layer)
│   │   │
│   │   ├── clients/                   ← External API clients
│   │   │   ├── base_client.py         ← HTTP client with disk caching
│   │   │   ├── fmp_client.py          ← Financial Modeling Prep API
│   │   │   └── llm_client.py          ← Anthropic Claude API
│   │   │
│   │   ├── models/                    ← SQLAlchemy ORM models (DB tables)
│   │   │   ├── company.py             ← companies table
│   │   │   ├── transcript.py          ← transcripts table
│   │   │   ├── financial_data.py      ← financial_data table
│   │   │   ├── claim.py               ← claims table
│   │   │   ├── verification.py        ← verifications table
│   │   │   └── discrepancy_pattern.py ← discrepancy_patterns table
│   │   │
│   │   ├── repositories/             ← Data access layer (CRUD operations)
│   │   │   ├── base.py               ← Generic base repo
│   │   │   ├── company_repo.py
│   │   │   ├── transcript_repo.py
│   │   │   ├── financial_data_repo.py
│   │   │   ├── claim_repo.py
│   │   │   ├── verification_repo.py
│   │   │   └── discrepancy_pattern_repo.py
│   │   │
│   │   ├── schemas/                   ← Pydantic schemas (validation + serialization)
│   │   │   ├── claim.py
│   │   │   ├── verification.py
│   │   │   └── discrepancy.py
│   │   │
│   │   ├── engines/                   ← Business logic (the "brains")
│   │   │   ├── claim_extractor.py     ← LLM prompt + output parsing
│   │   │   ├── metric_mapper.py       ← Maps "revenue" → data.revenue
│   │   │   ├── verification_engine.py ← Core: compares stated vs actual
│   │   │   └── discrepancy_analyzer.py← Cross-quarter pattern detection
│   │   │
│   │   ├── services/                  ← Orchestration layer
│   │   │   ├── ingestion_service.py   ← Fetch data from FMP → DB
│   │   │   ├── extraction_service.py  ← Run LLM on transcripts → claims
│   │   │   ├── verification_service.py← Verify all unverified claims
│   │   │   └── analysis_service.py    ← Run discrepancy analysis
│   │   │
│   │   └── utils/
│   │       ├── financial_math.py      ← Pure math: growth rates, margins, accuracy
│   │       └── scoring.py             ← Shared trust score & accuracy functions
│   │
│   ├── scripts/
│   │   └── run_pipeline.py            ← CLI to run the pipeline
│   │
│   ├── data/
│   │   ├── claim_auditor.db       ← SQLite database (generated)
│   │   ├── fmp_cache/                 ← Cached FMP API responses (JSON)
│   │   └── transcripts/               ← Local transcript files (fallback)
│   │       ├── AAPL_Q1_2026.txt
│   │       ├── MSFT_Q2_2026.txt
│   │       └── ...
│   │
│   ├── streamlit_app.py              ← Web UI
│   ├── mcp_server.py                 ← AI agent interface (MCP tools)
│   │
│   └── tests/
│       ├── conftest.py               ← Shared fixtures (in-memory DB)
│       ├── fixtures/                  ← Golden API response fixtures
│       ├── unit/                      ← 148 unit tests
│       │   ├── test_facade.py
│       │   ├── test_verification_engine.py
│       │   ├── test_financial_math.py
│       │   ├── test_claim_extractor.py
│       │   ├── test_ingestion_service.py
│       │   ├── test_extraction_service.py
│       │   ├── test_verification_service.py
│       │   ├── test_analysis_service.py
│       │   ├── test_discrepancy_analyzer.py
│       │   ├── test_discrepancy_pattern_repo.py
│       │   └── test_metric_mapper.py
│       └── integration/
│           ├── test_fmp_live.py       ← Live FMP API tests
│           └── test_pipeline_e2e.py   ← End-to-end pipeline test
```

---

## How the Pipeline Works

The pipeline has 4 steps that run in sequence. Each step is **idempotent** — safe to re-run. Already-processed items are skipped.

### Step 1: Ingest (`IngestionService`)

**What it does:** Fetches raw data from the Financial Modeling Prep API and stores it in SQLite.

**Flow:**
```
FMP API  ──→  FMPClient  ──→  IngestionService  ──→  DB
                                    │
                            data/transcripts/*.txt  (fallback)
```

**For each company (ticker):**
1. **Company profile** — Calls `GET /stable/profile?symbol=AAPL` → gets company name, sector
2. **Transcripts** — Calls `GET /stable/earning_call_transcript?symbol=AAPL&quarter=1&year=2026` for each target quarter
   - If the FMP endpoint is restricted (free plan), falls back to local `.txt` files in `data/transcripts/`
   - File naming convention: `{TICKER}_Q{quarter}_{year}.txt` (e.g., `AAPL_Q1_2026.txt`)
3. **Financial statements** — Fetches 3 statement types, merges them by period:
   - `GET /stable/income-statement?symbol=AAPL&period=quarter&limit=5`
   - `GET /stable/cash-flow-statement?symbol=AAPL&period=quarter&limit=5`
   - `GET /stable/balance-sheet-statement?symbol=AAPL&period=quarter&limit=5`

**Idempotency:** Checks DB before every API call. If a company/transcript/financial period already exists, it's skipped.

**Caching:** All FMP responses are cached to disk in `data/fmp_cache/` as JSON files. Subsequent runs use cached data instead of hitting the API. Delete the cache directory to force fresh fetches.

### Step 2: Extract (`ExtractionService` → `ClaimExtractor` → `LLMClient`)

**What it does:** Sends each transcript to Claude and extracts structured financial claims.

**Flow:**
```
DB (transcripts)  ──→  ClaimExtractor  ──→  Claude API  ──→  DB (claims)
```

**For each unprocessed transcript:**
1. Sends transcript text to Claude with a carefully crafted system prompt
2. Claude returns a JSON array of claims, each with:
   - `speaker`, `metric`, `metric_type`, `stated_value`, `unit`, `comparison_period`, `is_gaap`, `confidence`
3. Claims are validated (Pydantic), metric names are normalized (e.g., "total revenue" → "revenue", "FCF" → "free_cash_flow"), and duplicates are removed
4. Saved to the `claims` table

**Cost:** Each transcript costs ~$0.10-0.50 in Claude API tokens depending on length.

**Idempotency:** Only processes transcripts that have zero claims in the DB.

### Step 3: Verify (`VerificationService` → `VerificationEngine`)

**What it does:** Compares each claim against actual financial data. No external API calls — purely local computation.

**Flow:**
```
DB (claims + financial_data)  ──→  VerificationEngine  ──→  DB (verifications)
```

**For each unverified claim:**
1. **Resolve metric** — `MetricMapper` maps claim metric name to a DB column or derived calculation
   - Direct: `"revenue"` → `data.revenue`
   - Derived: `"gross_margin"` → `data.gross_profit / data.revenue * 100`
2. **Dispatch by type:**
   - `growth_rate` / `change` → Fetch current + comparison quarter, compute `(current - prior) / prior * 100`
   - `margin` → Compute ratio from current quarter data
   - `absolute` / `per_share` → Get raw value from current quarter, normalize units
3. **Normalize units** — Convert between billions/millions/raw dollars so stated and actual are comparable
4. **Score accuracy** — `accuracy = 1 - |stated - actual| / max(|stated|, |actual|)`
5. **Check misleading flags** — Rounding bias, GAAP/non-GAAP mismatch, segment vs. total
6. **Assign verdict** — Based on accuracy score and flags
7. **Generate explanation** — Human-readable text explaining the verdict

**Idempotency:** Only processes claims that don't already have a verification.

### Step 4: Analyze (`AnalysisService` → `DiscrepancyAnalyzer`)

**What it does:** Looks across all quarters for a company to find systematic patterns. No external API calls.

**Flow:**
```
DB (claims + verifications)  ──→  DiscrepancyAnalyzer  ──→  DB (discrepancy_patterns)
```

**Detects 5 pattern types** (see [Cross-Quarter Discrepancy Detection](#cross-quarter-discrepancy-detection-bonus) below).

**Idempotency:** Deletes old patterns for a company before writing new ones, so re-running always reflects the latest data.

---

## Running the Pipeline

All commands are run from the `backend/` directory with the virtual environment activated.

```bash
cd backend
source .venv/bin/activate
```

### Run Everything (Recommended First Time)

```bash
python -m scripts.run_pipeline
```

This runs all 4 steps for all configured tickers and quarters. Takes 2-5 minutes depending on how many transcripts need Claude extraction.

### Run Individual Steps

```bash
# Step 1 only: Fetch data from FMP (costs: FMP API calls)
python -m scripts.run_pipeline --step ingest

# Step 2 only: Extract claims via Claude (costs: Anthropic API tokens)
python -m scripts.run_pipeline --step extract

# Step 3 only: Verify claims (free — no API calls)
python -m scripts.run_pipeline --step verify

# Step 4 only: Discrepancy analysis (free — no API calls)
python -m scripts.run_pipeline --step analyze
```

### Target Specific Companies

```bash
# Only process Apple and Microsoft
python -m scripts.run_pipeline --tickers AAPL MSFT

# Only ingest data for NVDA
python -m scripts.run_pipeline --step ingest --tickers NVDA
```

### Pipeline Output

When you run the pipeline, you'll see logs like:

```
STEP 1: Ingesting data from Financial Modeling Prep
  Processing AAPL (Apple Inc.)
  Loaded local transcript AAPL_Q1_2026.txt
  Fetched transcript Q1 2026
  Financial data already exists, skipping FMP fetch
Ingestion complete in 3.2s: {'companies': 3, 'transcripts_fetched': 11, ...}

STEP 2: Extracting claims via Claude
  AAPL Q1 2026: extracted 14 raw → 12 valid → 10 unique claims
  ...
Extraction complete in 45.2s
LLM token usage: 52000 input, 8000 output

STEP 3: Verifying claims
Verification complete in 0.3s: {'verified': 28, 'approximately_correct': 15, ...}

STEP 4: Cross-quarter discrepancy analysis
  AAPL: trust=72, accuracy=64.3%, patterns=2, quarters=['Q1 2025', ...]
Analysis complete in 0.1s: 10 companies, 15 patterns detected

PIPELINE COMPLETE in 49.1s
  Steps run: ['ingest', 'extract', 'verify', 'analyze']
  Tickers: ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOG', 'META', 'JPM', 'JNJ', 'TSLA', 'CRM']
```

---

## Viewing Results (Streamlit UI)

### Starting Streamlit

```bash
# From the backend/ directory with venv activated
.venv/bin/streamlit run streamlit_app.py --server.port 8501 --server.headless true
```

Then open **http://localhost:8501** in your browser.

> **Port conflict?** If port 8501 is in use:
> ```bash
> lsof -ti:8501 | xargs kill -9 2>/dev/null
> .venv/bin/streamlit run streamlit_app.py --server.port 8501 --server.headless true
> ```

### What the UI Shows

**Three views** (selectable in sidebar):

1. **Dashboard** — All companies at a glance
   - Company cards with trust score, verdict breakdown, accuracy rate
   - Pattern badges (🔺🔄📉📊🎯) on each card
   - "View Details" button opens a popup dialog with full deep dive
   - Cross-company discrepancy pattern summary

2. **Company Deep Dive** — Select a company from dropdown
   - Trust score gauge
   - Quarter-to-quarter accuracy trend table with ↑↓ indicators
   - Verdict breakdown (pie chart or metrics)
   - Cross-quarter patterns with severity and evidence
   - Top 5 discrepancies (biggest mismatches)
   - All claims grouped by quarter with full verification details

3. **All Claims** — Browse every claim across all companies
   - Filterable by verdict, metric, company
   - Each claim shows: speaker, metric, stated vs actual, verdict, explanation

### Stopping Streamlit

```bash
# Kill the Streamlit process
lsof -ti:8501 | xargs kill -9
```

---

## Running Tests

### Run All Unit Tests (No API Keys Needed)

```bash
cd backend
source .venv/bin/activate

python -m pytest tests/unit/ -v
```

This runs **148 tests** covering:

| Test File | What It Tests | Count |
|-----------|---------------|-------|
| `test_financial_math.py` | Growth rates, margins, basis points, normalization, accuracy scoring | 25 |
| `test_metric_mapper.py` | Metric name → DB column resolution, derived metrics | 7 |
| `test_verification_engine.py` | Verdicts for growth, absolute, margin, per-share claims; misleading flags | 14 |
| `test_claim_extractor.py` | Alias normalization, dedup, LLM response parsing | 8 |
| `test_ingestion_service.py` | Idempotency checks, period parsing, financial data mapping | 10 |
| `test_extraction_service.py` | Orchestration, skip logic, dedup, error handling | 5 |
| `test_verification_service.py` | Orchestration, verdict counting, skip logic | 4 |
| `test_analysis_service.py` | Trust scoring, pattern persistence, re-analysis | 10 |
| `test_discrepancy_analyzer.py` | 5 pattern detectors (rounding, switching, inaccuracy, GAAP, emphasis) | 12 |
| `test_discrepancy_pattern_repo.py` | CRUD, grouped queries, cascading deletes | 5 |
| `test_facade.py` | PipelineFacade read queries, verdict filtering, decoupling, context manager | 20 |

All unit tests use an **in-memory SQLite database** and **mocked external clients** — no API keys, no network, runs in <1 second.

### Run Live FMP API Tests (Requires FMP_API_KEY)

```bash
python -m pytest tests/integration/test_fmp_live.py -v -m integration
```

These hit the real FMP API and verify:
- Profile endpoint returns correct fields
- Income statement, cash flow, balance sheet have expected fields
- Field names match what `IngestionService` expects
- Transcript endpoint behavior (returns None when restricted)

### Run End-to-End Pipeline Test (Requires Both API Keys)

```bash
python -m pytest tests/integration/test_pipeline_e2e.py -v -m integration
```

### Run All Tests (Including Integration)

```bash
python -m pytest tests/ -v -m ""
```

> **Note:** By default, `pytest` skips integration tests (configured in `pyproject.toml`). Use `-m integration` to include them, or `-m ""` to run everything.

### Test with Coverage

```bash
python -m pytest tests/unit/ -v --cov=app --cov-report=term-missing
```

---

## Adding a New Company

Want to add GOOG, META, or any other public company? Here's how:

### Option A: One-Off Command (Fastest)

```bash
# Ingest + extract + verify + analyze for just GOOG
python -m scripts.run_pipeline --tickers GOOG
```

This will:
1. Fetch GOOG's company profile from FMP
2. Try to fetch transcripts from FMP (or load from `data/transcripts/`)
3. Fetch the last 5 quarters of financial statements
4. Send each transcript to Claude for claim extraction
5. Verify all claims
6. Run cross-quarter analysis

### Option B: Add to Default Configuration

Edit `app/config.py`:

```python
target_tickers: list[str] = [
    "AAPL", "MSFT", "NVDA",
    "AMZN", "GOOG", "META",
    "JPM", "JNJ", "TSLA", "CRM",
    "NEW_TICKER",  # ← add here
]
```

Then run:
```bash
python -m scripts.run_pipeline
```

The pipeline is idempotent — it'll skip existing companies (already in DB) and only process the new ticker.

### Option C: With Local Transcripts

If the FMP transcript endpoint is restricted on your plan (common on free tier), you can provide local transcripts:

1. Create text files in `data/transcripts/`:
   ```
   data/transcripts/GOOG_Q4_2025.txt
   data/transcripts/GOOG_Q3_2025.txt
   ```

2. Each file should contain the full transcript text (just the content, no metadata).

3. Run the pipeline:
   ```bash
   python -m scripts.run_pipeline --tickers GOOG
   ```

The ingestion service automatically falls back to local files when FMP returns nothing.

### What if I Only Want to Re-Verify?

If you've changed verification logic and want to re-run verification without re-extracting claims:

```bash
# Delete existing verifications first (they're idempotent-by-existence)
# Then re-verify
python -m scripts.run_pipeline --step verify
```

> **Note:** The verify step skips claims that already have verifications. To re-verify, you'd need to clear the `verifications` table first. You can do this via the SQLite CLI:
> ```bash
> sqlite3 data/claim_auditor.db "DELETE FROM verifications;"
> python -m scripts.run_pipeline --step verify
> ```

---

## API Clients & How Data Flows

### FMP API Client (`app/clients/fmp_client.py`)

Wraps the Financial Modeling Prep [stable API](https://site.financialmodelingprep.com/developer/docs).

**Base URL:** `https://financialmodelingprep.com/stable`

**Endpoints called:**

| Method | Endpoint | Query Params | Returns |
|--------|----------|-------------|---------|
| `get_company_profile(ticker)` | `/profile` | `symbol=AAPL` | Company name, sector, etc. |
| `get_transcript(ticker, q, y)` | `/earning_call_transcript` | `symbol=AAPL&quarter=1&year=2026` | Transcript text + date |
| `get_income_statement(ticker)` | `/income-statement` | `symbol=AAPL&period=quarter&limit=5` | Revenue, expenses, EPS, etc. |
| `get_cash_flow_statement(ticker)` | `/cash-flow-statement` | `symbol=AAPL&period=quarter&limit=5` | Operating CF, CapEx, FCF |
| `get_balance_sheet(ticker)` | `/balance-sheet-statement` | `symbol=AAPL&period=quarter&limit=5` | Assets, liabilities, equity |

**Auth:** API key is passed as `?apikey=...` query parameter on every request.

**Caching:** All responses are cached to `data/fmp_cache/` as JSON files. Cache key = endpoint + params hash. Delete the cache to force fresh fetches.

**Error handling:** Each method wraps its call in try/except and returns `None` or `[]` on failure, with a warning log. The pipeline gracefully handles missing data.

### LLM Client (`app/clients/llm_client.py`)

Wraps the Anthropic Messages API for structured claim extraction.

**Model:** `claude-sonnet-4-20250514` (configurable via `claude_model` setting)

**How it works:**
1. System prompt defines the claim extraction format (JSON array schema)
2. User message includes the transcript text
3. Claude returns structured JSON
4. Response is parsed with 3 fallback strategies: raw JSON, markdown-fenced JSON, regex extraction

**Token tracking:** The client accumulates `total_input_tokens` and `total_output_tokens` across all calls, logged at the end of the extraction step.

### Base HTTP Client (`app/clients/base_client.py`)

Both `FMPClient` and any future HTTP clients inherit from `BaseHTTPClient`, which provides:
- **httpx** for synchronous HTTP requests
- **Disk cache** — deterministic filename from endpoint + params, JSON serialization
- **API key injection** — automatically adds `apikey` to query params
- **Logging** — debug-level logs for cache hits, GET requests
- **Timeout** — 30s default

---

## Verification Logic

The verification engine (`app/engines/verification_engine.py`) is the core of the system.

### Per-Claim Pipeline

```
Claim → Can we resolve the metric?
          │ No → UNVERIFIABLE
          │ Yes ↓
        What type of claim?
          ├─ growth_rate/change → Fetch current + prior quarter → compute actual growth %
          ├─ margin → Fetch current quarter → compute margin %
          └─ absolute/per_share → Fetch current quarter → normalize units → compare
          ↓
        Compute accuracy score
          ↓
        Check misleading flags (rounding, GAAP, segment)
          ↓
        Assign verdict (VERIFIED / APPROX / MISLEADING / INCORRECT)
          ↓
        Generate human-readable explanation
```

### Metric Mapper (`app/engines/metric_mapper.py`)

Maps metric names to financial data columns:

**Direct mappings** (claim metric → DB column):
- `revenue`, `net_income`, `eps_diluted`, `free_cash_flow`, `total_assets`, etc.

**Derived mappings** (claim metric → calculation):
- `gross_margin` → `gross_profit / revenue * 100`
- `operating_margin` → `operating_income / revenue * 100`
- `net_margin` → `net_income / revenue * 100`

**Special handling:**
- `capital_expenditure` returns absolute value (FMP stores it negative, transcripts state positive)

### Accuracy Scoring

```
accuracy = 1 - |stated - actual| / max(|stated|, |actual|)
```

Clamped to [0, 1]. A score of 0.98+ means "verified", 0.90+ means "approximately correct", etc.

### Trust Score (0–100)

Weighted formula per company or quarter:

```
raw = (verified × 1.0 + approx × 0.7 + misleading × -0.3 + incorrect × -1.0) / verifiable_count
trust = clamp((raw + 1) × 50, 0, 100)
```

- 80+ = Trustworthy
- 40-80 = Mixed
- Below 40 = Concerning

---

## Cross-Quarter Discrepancy Detection (Bonus)

The `DiscrepancyAnalyzer` (`app/engines/discrepancy_analyzer.py`) detects 5 types of systematic patterns:

| Pattern | Icon | Trigger | Severity |
|---------|------|---------|----------|
| **Consistent Rounding Up** | 🔺 | >70% of inexact claims round favorably | % of favorable roundings |
| **Metric Switching** | 🔄 | Most-emphasized metric changes across 3+ quarters | Fixed 0.5 |
| **Increasing Inaccuracy** | 📉 | Average accuracy declining over 3+ quarters | Accuracy drop magnitude |
| **GAAP/Non-GAAP Shifting** | 📊 | GAAP ratio changes >30% between quarters | Ratio change magnitude |
| **Selective Emphasis** | 🎯 | >90% positive growth claims in 2+ quarters | Fixed 0.6 |

Patterns are **persisted to the database** (`discrepancy_patterns` table) and displayed in the Streamlit UI.

---

## MCP Server — AI Agent Skill

The MCP (Model Context Protocol) server allows AI agents like Claude Code or Cursor to interact with the verifier programmatically.

### Architecture (Fully Decoupled)

```
mcp_server.py  ──imports only──→  app/facade.py  ──wires──→  services, repos, engines
```

The MCP server **never** imports models, repos, engines, or services directly. It only uses `PipelineFacade`, which returns plain dicts. If the internal pipeline changes, only the facade needs updating.

### Available Tools

| Tool | Arguments | What It Does |
|------|-----------|-------------|
| `list_companies()` | — | All companies with trust scores |
| `analyze_company(ticker)` | `"AAPL"` | Full analysis: trust, accuracy, patterns |
| `get_claims(ticker, verdict?)` | `"AAPL", "misleading"` | Claims, optionally filtered |
| `compare_quarters(ticker)` | `"AAPL"` | Per-quarter trends |
| `get_discrepancy_patterns(ticker)` | `"AAPL"` | Cross-quarter patterns |
| `run_pipeline(tickers, steps)` | `["GOOG"], "all"` | Execute pipeline steps |

### Running the MCP Server

```bash
# stdio transport (for Claude Code / Cursor integration)
python mcp_server.py

# SSE transport (for web-based agents)
python mcp_server.py --transport sse
```

### Configuring Claude Code / Cursor

Add to your MCP settings:

```json
{
  "mcpServers": {
    "claim-auditor": {
      "command": "python",
      "args": ["/path/to/claim-auditor/backend/mcp_server.py"],
      "env": {
        "FMP_API_KEY": "your-key",
        "ANTHROPIC_API_KEY": "your-key"
      }
    }
  }
}
```

Then you can ask Claude: *"List all companies in the claim auditor and show me AAPL's discrepancy patterns"*

---

## Deployment (Docker)

The project includes a `Dockerfile`, `docker-entrypoint.sh`, and `docker-compose.yml` for containerized deployment.

### Quick Start with Docker Compose

```bash
cd backend

# Set your API keys (or create a .env file)
export FMP_API_KEY=your_key
export ANTHROPIC_API_KEY=your_key

# Start both Streamlit UI and FastAPI server
docker compose up --build
```

This launches:
- **Streamlit UI** at `http://localhost:8501`
- **FastAPI API** at `http://localhost:8000`

Both services share the same `data/` volume for the SQLite database and FMP cache.

### Running Individual Services

```bash
# Streamlit only
docker compose up streamlit

# API only
docker compose up api
```

### Deploying to Cloud (Railway / Fly.io / Render)

The Docker image supports a `MODE` environment variable:
- `MODE=streamlit` (default) — runs the Streamlit UI
- `MODE=api` — runs the FastAPI server

Example for Railway:
1. Connect your GitHub repo
2. Set environment variables: `FMP_API_KEY`, `ANTHROPIC_API_KEY`, `MODE=streamlit`
3. Deploy — Railway auto-detects the Dockerfile

### Running the Pipeline in Docker

```bash
# Run pipeline inside the container
docker compose exec streamlit python -m scripts.run_pipeline
```

---

## Architecture Diagram

### High-Level Data Flow

```
┌─────────────┐     ┌─────────────┐
│   FMP API   │     │ Anthropic   │
│ (financials)│     │  Claude API │
└──────┬──────┘     └──────┬──────┘
       │                   │
       ▼                   ▼
┌──────────────┐   ┌──────────────┐
│  FMPClient   │   │  LLMClient   │
│ (+ cache)    │   │              │
└──────┬───────┘   └──────┬───────┘
       │                   │
       ▼                   ▼
┌──────────────────────────────────┐
│         Services Layer           │
│  ┌────────────┐ ┌──────────────┐ │
│  │ Ingestion  │ │ Extraction   │ │
│  │ Service    │ │ Service      │ │
│  └─────┬──────┘ └──────┬───────┘ │
│        │               │         │
│  ┌─────┴───────────────┴───────┐ │
│  │   Verification Service      │ │
│  └─────────────┬───────────────┘ │
│                │                  │
│  ┌─────────────┴───────────────┐ │
│  │    Analysis Service         │ │
│  └─────────────────────────────┘ │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│          SQLite Database         │
│  companies | transcripts         │
│  financial_data | claims         │
│  verifications | discrepancy_    │
│                  patterns        │
└──────────────┬───────────────────┘
               │
       ┌───────┼───────────┐
       ▼       ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│Streamlit │ │   CLI    │ │   MCP    │
│  UI      │ │run_      │ │ Server   │
│ :8501    │ │pipeline  │ │(AI agent)│
└──────────┘ └──────────┘ └──────────┘
```

### Decoupling via Facade

```
┌─────────────────────────────────────────────────┐
│              PipelineFacade                      │
│  (app/facade.py)                                │
│                                                  │
│  Wires up: clients → repos → engines → services │
│  Exposes:  list_companies(), get_claims(), ...   │
│  Returns:  plain dicts (never ORM models)        │
└─────────────────┬───────────────────────────────┘
                  │
      ┌───────────┼───────────────┐
      ▼           ▼               ▼
┌──────────┐ ┌──────────┐ ┌────────────┐
│  CLI     │ │Streamlit │ │ MCP Server │
│run_      │ │(optional)│ │(mcp_server │
│pipeline  │ │          │ │  .py)      │
└──────────┘ └──────────┘ └────────────┘
```

---

## Key Design Decisions

1. **SQLite** — Intentional simplicity. A few companies × a few quarters doesn't need Postgres. Zero config, easily deployed, single-file database.

2. **Pre-populated database** — The pipeline script runs the full pipeline once. The UI just reads results. No runtime API calls, no waiting, instant exploration.

3. **Streamlit** — Single Python file, free cloud deployment, clean data exploration. No frontend framework overhead.

4. **Claude for extraction** — Structured prompt that outputs typed JSON with: metric name, stated value, unit, comparison period, GAAP flag, confidence score, speaker role. Alias normalization maps "total revenue" → "revenue", "FCF" → "free_cash_flow", etc.

5. **Multi-tier verdicts** — Not binary true/false. Configurable thresholds (2%, 10%, 25%) capture the spectrum from "spot on" to "materially wrong".

6. **"Misleading" as first-class** — This is what separates it from a simple fact-checker. Favorable rounding, GAAP mixing, and cross-quarter behavioral patterns all get flagged.

7. **Full idempotency** — Every step checks for existing data before processing. Safe to re-run, safe to interrupt and resume.

8. **File-based API caching** — FMP responses are cached to disk as JSON. Saves API quota, makes development faster, enables offline testing.

9. **Local transcript fallback** — When the FMP transcript endpoint is restricted (common on free tier), the pipeline loads from local `.txt` files. This makes the project fully functional on a free FMP plan.

10. **Decoupled facade** — The `PipelineFacade` hides all internal wiring. External interfaces (CLI, Streamlit, MCP) never touch repos, engines, or models directly. Internal refactoring is safe.

11. **148 tests** — Comprehensive unit tests with realistic Apple-like financial data. In-memory DB, mocked clients, runs in <1 second.

---

## Scaling to Production

### Current State (Demo)
- **Batch processing**: Manual `run_pipeline.py` run
- **Static results**: UI displays pre-computed verifications
- **SQLite**: Sufficient for demo scale
- **10 companies**, ~40 transcripts, ~400+ claims

### What Would Change for Production

| Concern | Current | Production |
|---------|---------|------------|
| **Database** | SQLite file | PostgreSQL with indexes |
| **Processing** | Sequential, single-thread | Celery + Redis queue, async |
| **Scheduling** | Manual CLI run | Cron / EventBridge (daily) |
| **API** | Streamlit reads DB | REST API (FastAPI already scaffolded) |
| **Caching** | Disk JSON files | Redis |
| **Auth** | None | OAuth2, rate limiting |
| **Monitoring** | Logs | Prometheus + Grafana, Sentry |
| **LLM costs** | Pay-per-run | Cache extractions, batch calls |
| **Scale** | 10 companies | 1000+ companies |

### Cost Estimates at Scale (1000 Companies)

| Item | Monthly Cost |
|------|-------------|
| FMP API | $50–200 |
| Claude API | $500–2,000 |
| Managed Postgres | $50–200 |
| Compute (API + workers) | $100–500 |
| **Total** | **~$700–2,900/month** |

The **verification engine** is the core IP — it's the same at any scale. The delivery mechanism (batch vs. real-time, UI vs. API) is a product decision.
