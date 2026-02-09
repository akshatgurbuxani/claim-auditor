# Claim Auditor Pipeline - Complete Explanation

## Overview

The pipeline has **4 main steps** that run sequentially:

```
1. INGEST   → Fetch data from FMP API and local files
2. EXTRACT  → Use Claude to extract claims from transcripts
3. VERIFY   → Compare extracted claims against financial data
4. ANALYZE  → Find patterns of discrepancies
```

---

## Data Sources: What Comes From Where?

### 🔴 FMP API (Financial Modeling Prep) - STRUCTURED DATA

**What you GET from FMP (even on free tier):**
- ✅ **Company Profiles** - Company name, sector, industry
- ✅ **Income Statements** - Revenue, net income, operating income, EPS, EBITDA, etc.
- ✅ **Cash Flow Statements** - Operating cash flow, free cash flow, capex, etc.
- ✅ **Balance Sheets** - Total assets, debt, cash, shareholders' equity, etc.

**What you CANNOT get from FMP (requires paid subscription):**
- ❌ **Earnings Call Transcripts** - The actual text of what executives said

**Example of FMP Financial Data (AMZN Q4 2025):**
```json
{
  "revenue": 213400000000,        // $213.4B
  "netIncome": 21200000000,       // $21.2B
  "operatingIncome": 25000000000, // $25.0B
  "operatingCashFlow": 54500000000, // $54.5B
  "freeCashFlow": 14900000000,    // $14.9B
  "totalAssets": 576900000000,
  "totalDebt": 128100000000,
  "eps": 2.04,
  ...
}
```

### 🟢 Local Files - UNSTRUCTURED DATA

**Location:** `backend/data/transcripts/`

**Naming Convention:** `{TICKER}_Q{quarter}_{year}.txt`

Examples:
- `AMZN_Q4_2025.txt`
- `META_Q2_2026.txt`

**Content:** Plain text transcripts of earnings calls with executive quotes:

```text
Amazon.com, Inc. Q4 FY2025 Earnings Call Transcript
Date: January 30, 2026

Andy Jassy, CEO:
Revenue was $170.8 billion, up 11% year over year...

Brian Olsavsky, CFO:
Operating income for the quarter was $18.6 billion...
```

---

## Pipeline Flow: Step-by-Step

### STEP 1: INGEST (`app/services/ingestion_service.py`)

**Goal:** Get both structured financial data and unstructured transcripts

```python
# For each company and quarter:

# 1. Try to fetch transcript from FMP API
transcript = fmp_client.get_transcript('AMZN', 3, 2026)

# 2. If FMP returns 404 or "Restricted Endpoint", fall back to local file
if transcript is None:
    transcript = load_local_file('data/transcripts/AMZN_Q3_2026.txt')

# 3. Fetch structured financial data from FMP API
income_stmt = fmp_client.get_income_statement('AMZN', period='quarter', limit=5)
cashflow_stmt = fmp_client.get_cash_flow_statement('AMZN', ...)
balance_sheet = fmp_client.get_balance_sheet('AMZN', ...)

# 4. Store everything in SQLite database
db.save(transcript)  # Unstructured text
db.save(financial_data)  # Structured numbers
```

**What gets stored in database:**

| Table | Content | Source |
|-------|---------|--------|
| `companies` | Ticker, name, sector | FMP API (profile endpoint) |
| `transcripts` | Full text of earnings calls | Local `.txt` files (FMP API restricted) |
| `financial_data` | Revenue, income, cash flow, balance sheet | FMP API (statement endpoints) |

**Key Insight:**
- The **transcripts** (unstructured text) come from local files because your FMP API tier doesn't support that endpoint
- The **financial data** (structured numbers) comes from FMP API because those endpoints work on free tier

---

### STEP 2: EXTRACT (`app/services/extraction_service.py`)

**Goal:** Use Claude AI to extract specific quantitative claims from the unstructured transcript text

```python
# For each transcript in database:

# 1. Send transcript text to Claude API
prompt = """
Extract all quantitative financial claims from this earnings transcript.
For each claim, identify:
- What metric was mentioned (revenue, net_income, etc.)
- What value was stated
- Who said it (CEO, CFO, etc.)
- What period it refers to
...
"""

response = claude.messages.create(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": prompt + transcript_text}]
)

# 2. Claude returns structured JSON with extracted claims
claims = [
    {
        "claim_text": "Revenue was $170.8 billion, up 11% year over year",
        "speaker": "Andy Jassy",
        "metric": "revenue",
        "stated_value": 170800000000,
        "unit": "usd",
        "comparison_period": "year_over_year",
        ...
    },
    {
        "claim_text": "Operating income for the quarter was $18.6 billion",
        "speaker": "Brian Olsavsky",
        "metric": "operating_income",
        "stated_value": 18600000000,
        "unit": "usd",
        ...
    }
]

# 3. Store claims in database
db.save_all(claims)
```

**Example of what Claude extracts:**

From this text:
> "Revenue was $170.8 billion, up 11% year over year from Q4 2024's revenue of $153.9 billion"

Claude extracts:
```json
{
  "speaker": "Andy Jassy",
  "claim_text": "Revenue was $170.8 billion, up 11% year over year...",
  "metric": "revenue",
  "stated_value": 170800000000,
  "unit": "usd",
  "comparison_period": "year_over_year",
  "comparison_basis": "Q4 2024: $153.9B",
  "confidence": 0.95
}
```

**What gets stored:**

| Table | Content | Source |
|-------|---------|--------|
| `claims` | Extracted claims with structured metadata | Claude AI parsing transcript text |

---

### STEP 3: VERIFY (`app/services/verification_service.py`)

**Goal:** Compare what executives said (claims) against actual financial data

```python
# For each claim:

# 1. Look up the corresponding financial data
claim = {
    "metric": "revenue",
    "stated_value": 170800000000,  # $170.8B (what exec said)
    "quarter": 4,
    "year": 2025
}

# 2. Find actual value from financial_data table
actual = db.query(FinancialData).filter(
    company='AMZN',
    quarter=4,
    year=2025
).first()

actual_revenue = 213400000000  # $213.4B (from FMP API)

# 3. Calculate accuracy
accuracy = 1 - abs(stated - actual) / actual
# accuracy = 1 - abs(170.8 - 213.4) / 213.4 = 0.80 (80%)

# 4. Assign verdict based on accuracy
if accuracy >= 0.98:
    verdict = "verified"  # Correct
elif accuracy >= 0.90:
    verdict = "approximately_correct"  # Mostly Correct
elif accuracy >= 0.80:
    verdict = "misleading"  # Misleading
else:
    verdict = "incorrect"  # Incorrect

# 5. Store verification result
db.save(verification={
    "claim_id": claim.id,
    "actual_value": 213400000000,
    "accuracy_score": 0.80,
    "verdict": "misleading",
    "explanation": "Stated revenue of $170.8B differs significantly from...",
})
```

**Why many claims show "Cannot Verify":**

The transcript files I created have **synthetic numbers** that don't match the **real financial data** from FMP API.

Example mismatch:
- **Transcript says:** "Revenue was $170.8 billion" (my made-up number)
- **FMP API says:** Revenue was $213.4 billion (real data)
- **Result:** Marked as "Misleading" or "Cannot Verify"

**What gets stored:**

| Table | Content | Source |
|-------|---------|--------|
| `verifications` | Verdict, accuracy score, explanation | Comparison of claim vs financial_data |

---

### STEP 4: ANALYZE (`app/services/analysis_service.py`)

**Goal:** Find patterns of repeated discrepancies across quarters

```python
# Look for patterns like:
# - Consistently rounding up numbers
# - Switching between GAAP and non-GAAP metrics
# - Increasing inaccuracy over time
# - Selective emphasis on good metrics

analyzer = DiscrepancyAnalyzer()
patterns = analyzer.analyze(claims_with_verifications)

# Example pattern found:
pattern = {
    "type": "consistent_rounding_up",
    "description": "CEO consistently rounds revenue up by 2-3%",
    "affected_quarters": ["Q1 2025", "Q2 2025", "Q3 2025"],
    "severity": "medium"
}
```

**What gets stored:**

| Table | Content | Source |
|-------|---------|--------|
| `discrepancy_patterns` | Cross-quarter patterns | Analysis of verification results |

---

## Database Schema Summary

```
companies (from FMP API)
  └── transcripts (from local .txt files)
        └── claims (extracted by Claude AI)
              └── verifications (computed by comparing to financial_data)
  └── financial_data (from FMP API)

discrepancy_patterns (computed from verifications)
```

---

## API Keys & Restrictions

### What Works on Free Tier:

✅ **FMP API (Free Tier)**
- Company profiles: `GET /profile?symbol=AMZN`
- Income statements: `GET /income-statement?symbol=AMZN&period=quarter`
- Cash flow statements: `GET /cash-flow-statement?...`
- Balance sheets: `GET /balance-sheet-statement?...`

✅ **Anthropic API (Pay-as-you-go)**
- Claude Sonnet for claim extraction
- Costs ~$0.15 per transcript analyzed

### What DOESN'T Work:

❌ **FMP Transcript Endpoint (Paid Subscription Required)**
- `GET /earning_call_transcript?symbol=AMZN&quarter=3&year=2026`
- Returns: `"Restricted Endpoint: This endpoint is not available under your current subscription"`
- **Solution:** We use local `.txt` files as fallback

---

## Why the 404 Fix Was Important

**Before my fix:**
```python
# In base_client.py
if status_code == 404:
    resp.raise_for_status()  # ❌ This triggers retry logic!
```

The retry decorator saw `HTTPStatusError` and retried 3 times:
- Request 1: 404 Not Found (wait 1s)
- Request 2: 404 Not Found (wait 2s)
- Request 3: 404 Not Found (wait 4s)
- **Total wasted:** 7 seconds + 3 API calls per missing transcript

**After my fix:**
```python
# In base_client.py
if status_code >= 400:
    return None  # ✅ No retry, just return None immediately
```

Now:
- Request 1: 404 Not Found → return None immediately
- **Total:** 0.1 seconds + 1 API call
- Fallback to local file happens instantly

---

## Example End-to-End Flow

### Input:
1. **FMP API Financial Data (AMZN Q4 2025):**
   - Revenue: $213.4B (actual)
   - Net Income: $21.2B (actual)

2. **Local Transcript File (`AMZN_Q4_2025.txt`):**
   ```
   Andy Jassy: Revenue was $170.8 billion...
   Brian Olsavsky: Net income was $15.6 billion...
   ```

### Processing:

1. **INGEST:**
   - ✅ Fetched financial data from FMP API → `financial_data` table
   - ✅ Loaded transcript from local file → `transcripts` table

2. **EXTRACT (Claude AI):**
   - Claim 1: "Revenue was $170.8 billion" → `claims` table
   - Claim 2: "Net income was $15.6 billion" → `claims` table

3. **VERIFY:**
   - Claim 1: $170.8B stated vs $213.4B actual → 80% accuracy → **Misleading**
   - Claim 2: $15.6B stated vs $21.2B actual → 74% accuracy → **Incorrect**

4. **ANALYZE:**
   - Pattern: CEO consistently understates revenue → **Low Trust Score**

### Output:
- **Dashboard shows:**
  - AMZN: 93 claims, 3 mostly correct, 8 misleading, 13 incorrect, 69 cannot verify
  - Trust Score: 35/100 (Low)

---

## How to Improve Results

### Option 1: Use Real Transcript Data
Replace my synthetic transcripts with real ones that match FMP financial data

### Option 2: Upgrade FMP API
Pay for FMP subscription to get real transcript API access

### Option 3: Adjust Transcript Numbers
Edit the `.txt` files to match the actual financial data from FMP