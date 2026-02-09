# Claim Auditor - Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                    │
└─────────────────────────────────────────────────────────────────────────────┘

        ┌──────────────────────┐              ┌──────────────────────┐
        │   FMP API (Free)     │              │  Local Files (.txt)  │
        │  ✅ Company Profile  │              │  ❌ Transcripts      │
        │  ✅ Income Stmt      │              │  (FMP API blocked)   │
        │  ✅ Cash Flow        │              │                      │
        │  ✅ Balance Sheet    │              │  AMZN_Q4_2025.txt    │
        │  ❌ Transcripts      │              │  META_Q2_2026.txt    │
        └──────────┬───────────┘              └──────────┬───────────┘
                   │                                     │
                   │                                     │
┌──────────────────▼─────────────────────────────────────▼─────────────────────┐
│                         STEP 1: INGEST                                        │
│                  (app/services/ingestion_service.py)                          │
│                                                                               │
│  • Fetch structured financial data from FMP API                              │
│  • Try FMP transcript API → Fails with "Restricted Endpoint"                 │
│  • Fall back to local .txt files                                             │
│  • Store both in SQLite database                                             │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   SQLite Database     │
                    │                       │
                    │  ┌─────────────────┐  │
                    │  │ companies       │  │  ← FMP API (profile)
                    │  │  - ticker       │  │
                    │  │  - name         │  │
                    │  │  - sector       │  │
                    │  └─────────────────┘  │
                    │                       │
                    │  ┌─────────────────┐  │
                    │  │ transcripts     │  │  ← Local .txt files
                    │  │  - full_text    │  │  (unstructured)
                    │  │  - quarter      │  │
                    │  │  - year         │  │
                    │  └─────────────────┘  │
                    │                       │
                    │  ┌─────────────────┐  │
                    │  │ financial_data  │  │  ← FMP API (statements)
                    │  │  - revenue      │  │  (structured)
                    │  │  - net_income   │  │
                    │  │  - op_income    │  │
                    │  │  - cash_flow    │  │
                    │  │  - etc...       │  │
                    │  └─────────────────┘  │
                    └───────────┬───────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                         STEP 2: EXTRACT                                       │
│                  (app/services/extraction_service.py)                         │
│                                                                               │
│  For each transcript in database:                                            │
│                                                                               │
│  1. Read unstructured transcript text                                        │
│     "Revenue was $170.8B, up 11% YoY..."                                     │
│                                                                               │
│  2. Send to Claude AI (Anthropic API)                                        │
│     ┌─────────────────────────────────────┐                                  │
│     │  Claude Sonnet 4.5                  │                                  │
│     │  "Extract all quantitative claims"  │                                  │
│     └─────────────────────────────────────┘                                  │
│                                                                               │
│  3. Claude returns structured JSON:                                          │
│     {                                                                         │
│       "speaker": "Andy Jassy",                                               │
│       "claim_text": "Revenue was $170.8B...",                                │
│       "metric": "revenue",                                                   │
│       "stated_value": 170800000000,                                          │
│       "unit": "usd",                                                         │
│       "confidence": 0.95                                                     │
│     }                                                                         │
│                                                                               │
│  4. Store claims in database                                                 │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   SQLite Database     │
                    │                       │
                    │  ┌─────────────────┐  │
                    │  │ claims          │  │  ← Claude AI extraction
                    │  │  - claim_text   │  │
                    │  │  - speaker      │  │
                    │  │  - metric       │  │
                    │  │  - stated_value │  │
                    │  │  - unit         │  │
                    │  │  - confidence   │  │
                    │  └─────────────────┘  │
                    └───────────┬───────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                         STEP 3: VERIFY                                        │
│                  (app/services/verification_service.py)                       │
│                                                                               │
│  For each claim:                                                              │
│                                                                               │
│  1. Get stated value from claim                                              │
│     Stated: $170.8B (what exec said)                                         │
│                                                                               │
│  2. Get actual value from financial_data                                     │
│     Actual: $213.4B (from FMP API)                                           │
│                                                                               │
│  3. Calculate accuracy                                                       │
│     accuracy = 1 - |stated - actual| / actual                                │
│     accuracy = 1 - |170.8 - 213.4| / 213.4                                   │
│     accuracy = 0.80 (80%)                                                    │
│                                                                               │
│  4. Assign verdict                                                           │
│     ┌─────────────────────────────────────┐                                  │
│     │ ≥ 98%  → Correct                   │                                  │
│     │ ≥ 90%  → Mostly Correct            │                                  │
│     │ ≥ 80%  → Misleading                │  ← This claim                    │
│     │ < 80%  → Incorrect                 │                                  │
│     │ No data → Cannot Verify            │                                  │
│     └─────────────────────────────────────┘                                  │
│                                                                               │
│  5. Store verification result                                                │
└───────────────────────────────┬───────────────────────────────────────────────┘
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
┌───────────────────────────────────────────────────────────────────────────────┐
│                         STEP 4: ANALYZE                                       │
│                  (app/services/analysis_service.py)                           │
│                                                                               │
│  Look for patterns across multiple quarters:                                 │
│  • Consistent rounding up                                                    │
│  • Metric switching (GAAP vs non-GAAP)                                       │
│  • Increasing inaccuracy over time                                           │
│  • Selective emphasis on good metrics                                        │
│                                                                               │
│  Example:                                                                    │
│  ┌────────────────────────────────────────────────────────────┐              │
│  │ Pattern: "consistent_rounding_up"                          │              │
│  │ Description: "CEO rounds revenue up by 2-3% each quarter"  │              │
│  │ Affected: ["Q1 2025", "Q2 2025", "Q3 2025"]               │              │
│  │ Severity: "medium"                                         │              │
│  └────────────────────────────────────────────────────────────┘              │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   SQLite Database     │
                    │                       │
                    │  ┌─────────────────┐  │
                    │  │ discrepancy_    │  │  ← Pattern detection
                    │  │   patterns      │  │
                    │  │  - pattern_type │  │
                    │  │  - description  │  │
                    │  │  - quarters     │  │
                    │  │  - severity     │  │
                    │  └─────────────────┘  │
                    └───────────┬───────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                         STREAMLIT UI                                          │
│                                                                               │
│  Dashboard showing:                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐        │
│  │  AMZN - Amazon.com, Inc.                    Trust Score: 35/100  │        │
│  │  ────────────────────────────────────────────────────────────────│        │
│  │  Total Claims: 93                                                │        │
│  │  Correct: 0  │  Mostly: 3  │  Misleading: 8  │  Incorrect: 13   │        │
│  │  Cannot Verify: 69                                               │        │
│  │                                                                  │        │
│  │  Q3 2026: 24 claims  │  Q2 2026: 20 claims  │  Q1 2026: 25     │        │
│  └──────────────────────────────────────────────────────────────────┘        │
└───────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
                          KEY INSIGHTS
═══════════════════════════════════════════════════════════════════════════════

1. TWO TYPES OF DATA:

   STRUCTURED (numbers):        UNSTRUCTURED (text):
   ✅ From FMP API              ❌ FMP API blocked
   • Revenue: $213.4B           → Use local .txt files
   • Net Income: $21.2B         • "Revenue was $170.8B..."
   • Operating Income: $25.0B   • "Net income was $15.6B..."
   • Cash Flow: $54.5B

═══════════════════════════════════════════════════════════════════════════════
