# API Usage Guide

**Complete guide to using the Claim Auditor REST API with examples in curl, Python, and JavaScript.**

---

## Table of Contents

1. [API Overview](#1-api-overview)
2. [Authentication](#2-authentication)
3. [Pipeline Endpoints](#3-pipeline-endpoints)
4. [Company Endpoints](#4-company-endpoints)
5. [Claim Endpoints](#5-claim-endpoints)
6. [Transcript Endpoints](#6-transcript-endpoints)
7. [Health Check Endpoints](#7-health-check-endpoints)
8. [Error Handling](#8-error-handling)
9. [Rate Limiting](#9-rate-limiting)
10. [Example Workflows](#10-example-workflows)

---

## 1. API Overview

### Base URL

```
Production:  https://your-domain.com/api/v1
Local:       http://localhost:8000/api/v1
```

### API Versioning

All endpoints are versioned under `/api/v1/`. Legacy routes at `/api/` still work but are deprecated.

### Content Type

All requests and responses use `application/json`.

### Interactive Documentation

Visit `/docs` for interactive Swagger UI:
- **Local:** http://localhost:8000/docs
- **Production:** https://your-domain.com/docs

---

## 2. Authentication

**Current version:** No authentication required (development mode)

**Production recommendation:** Add API key authentication:
```python
headers = {
    "Authorization": "Bearer your-api-key",
    "Content-Type": "application/json"
}
```

---

## 3. Pipeline Endpoints

### Run Pipeline Status

Get current pipeline status (counts for each stage).

**Endpoint:** `GET /api/v1/pipeline/status`

**Example (curl):**
```bash
curl http://localhost:8000/api/v1/pipeline/status
```

**Example (Python):**
```python
import requests

response = requests.get("http://localhost:8000/api/v1/pipeline/status")
status = response.json()

print(f"Companies: {status['companies']}")
print(f"Transcripts: {status['transcripts']}")
print(f"Unprocessed: {status['transcripts_unprocessed']}")
print(f"Claims: {status['claims']}")
print(f"Unverified: {status['claims_unverified']}")
```

**Response:**
```json
{
  "companies": 10,
  "transcripts": 42,
  "transcripts_unprocessed": 3,
  "claims": 1247,
  "claims_unverified": 12,
  "verifications": 1235
}
```

---

### Trigger Ingestion

Fetch financial data and transcripts for specified companies.

**Endpoint:** `POST /api/v1/pipeline/ingest`

**Request Body:**
```json
{
  "tickers": ["AAPL", "MSFT", "AMZN"],
  "quarters": [[2025, 4], [2025, 3]]
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/pipeline/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["AAPL", "MSFT"],
    "quarters": [[2025, 4]]
  }'
```

**Example (Python):**
```python
import requests

payload = {
    "tickers": ["AAPL", "MSFT"],
    "quarters": [[2025, 4], [2025, 3]]
}

response = requests.post(
    "http://localhost:8000/api/v1/pipeline/ingest",
    json=payload
)

result = response.json()
print(f"Status: {result['status']}")
print(f"Summary: {result['summary']}")
```

**Example (JavaScript):**
```javascript
const response = await fetch('http://localhost:8000/api/v1/pipeline/ingest', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    tickers: ['AAPL', 'MSFT'],
    quarters: [[2025, 4], [2025, 3]]
  })
});

const result = await response.json();
console.log('Status:', result.status);
console.log('Summary:', result.summary);
```

**Response:**
```json
{
  "status": "completed",
  "summary": {
    "companies_created": 2,
    "transcripts_fetched": 4,
    "financial_data_created": 24
  }
}
```

**Validation:**
- Tickers: max 20, alphabetic only, max 5 characters each
- Quarters: year 2020-2030, quarter 1-4, max 10 entries

**Error Response (422):**
```json
{
  "detail": [
    {
      "loc": ["body", "tickers", 0],
      "msg": "Invalid ticker: AAAAAAA (max 5 characters)",
      "type": "value_error"
    }
  ]
}
```

---

### Trigger Extraction

Extract claims from unprocessed transcripts via LLM.

**Endpoint:** `POST /api/v1/pipeline/extract`

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/pipeline/extract
```

**Example (Python):**
```python
response = requests.post("http://localhost:8000/api/v1/pipeline/extract")
result = response.json()

print(f"Claims extracted: {result['summary']['claims_extracted']}")
print(f"Transcripts processed: {result['summary']['transcripts_processed']}")
```

**Response:**
```json
{
  "status": "completed",
  "summary": {
    "transcripts_processed": 3,
    "claims_extracted": 87,
    "avg_claims_per_transcript": 29.0
  }
}
```

---

### Trigger Verification

Verify all unverified claims against financial data.

**Endpoint:** `POST /api/v1/pipeline/verify`

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/pipeline/verify
```

**Example (Python):**
```python
response = requests.post("http://localhost:8000/api/v1/pipeline/verify")
result = response.json()

print(f"Claims verified: {result['summary']['claims_verified']}")
print(f"Breakdown: {result['summary']['verdict_breakdown']}")
```

**Response:**
```json
{
  "status": "completed",
  "summary": {
    "claims_verified": 87,
    "verdict_breakdown": {
      "VERIFIED": 45,
      "APPROXIMATELY_CORRECT": 28,
      "MISLEADING": 8,
      "INCORRECT": 4,
      "UNVERIFIABLE": 2
    }
  }
}
```

---

### Trigger Analysis

Analyze all companies for discrepancy patterns.

**Endpoint:** `POST /api/v1/pipeline/analyze`

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/pipeline/analyze
```

**Example (Python):**
```python
response = requests.post("http://localhost:8000/api/v1/pipeline/analyze")
result = response.json()

print(f"Companies analyzed: {result['summary']['companies_analyzed']}")
print(f"Patterns detected: {result['summary']['total_patterns']}")
```

**Response:**
```json
{
  "status": "completed",
  "summary": {
    "companies_analyzed": 10,
    "total_patterns": 23
  }
}
```

---

### Run Full Pipeline

Execute complete pipeline: ingest → extract → verify → analyze.

**Endpoint:** `POST /api/v1/pipeline/run-all`

**Request Body:** (optional, uses defaults from settings if omitted)
```json
{
  "tickers": ["AAPL"],
  "quarters": [[2025, 4]]
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/pipeline/run-all \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL"]}'
```

**Example (Python):**
```python
payload = {"tickers": ["AAPL"], "quarters": [[2025, 4]]}
response = requests.post(
    "http://localhost:8000/api/v1/pipeline/run-all",
    json=payload
)

result = response.json()
print("Ingestion:", result['pipeline']['ingestion'])
print("Extraction:", result['pipeline']['extraction'])
print("Verification:", result['pipeline']['verification'])
print("Analysis:", result['pipeline']['analysis'])
```

**Response:**
```json
{
  "status": "completed",
  "pipeline": {
    "ingestion": {
      "companies_created": 1,
      "transcripts_fetched": 1,
      "financial_data_created": 12
    },
    "extraction": {
      "transcripts_processed": 1,
      "claims_extracted": 29
    },
    "verification": {
      "claims_verified": 29,
      "verdict_breakdown": {"VERIFIED": 18, "APPROXIMATELY_CORRECT": 8, "MISLEADING": 2, "INCORRECT": 1}
    },
    "analysis": {
      "companies_analyzed": 1,
      "total_patterns": 1
    }
  }
}
```

---

## 4. Company Endpoints

### List All Companies

Get all companies with verification statistics.

**Endpoint:** `GET /api/v1/companies/`

**Example (curl):**
```bash
curl http://localhost:8000/api/v1/companies/
```

**Example (Python):**
```python
response = requests.get("http://localhost:8000/api/v1/companies/")
companies = response.json()

for company in companies:
    print(f"{company['ticker']}: {company['trust_score']} trust score")
    print(f"  Accuracy: {company['accuracy_rate']:.2%}")
    print(f"  Claims: {company['total_claims']}")
```

**Response:**
```json
[
  {
    "id": 1,
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "sector": "Technology",
    "total_claims": 123,
    "verified_count": 78,
    "approximately_correct_count": 32,
    "misleading_count": 8,
    "incorrect_count": 3,
    "unverifiable_count": 2,
    "accuracy_rate": 0.8943,
    "trust_score": 87.2
  },
  ...
]
```

---

### Get Company Analysis

Get detailed analysis for a specific company including discrepancy patterns.

**Endpoint:** `GET /api/v1/companies/{ticker}`

**Example (curl):**
```bash
curl http://localhost:8000/api/v1/companies/AAPL
```

**Example (Python):**
```python
ticker = "AAPL"
response = requests.get(f"http://localhost:8000/api/v1/companies/{ticker}")
analysis = response.json()

print(f"Company: {analysis['company_name']}")
print(f"Trust Score: {analysis['trust_score']}")
print(f"Patterns detected: {len(analysis['patterns'])}")

for pattern in analysis['patterns']:
    print(f"\n{pattern['pattern_type']}: {pattern['severity']}")
    print(f"  {pattern['description']}")
```

**Response:**
```json
{
  "company_id": 1,
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "total_claims": 123,
  "verified_count": 78,
  "approximately_correct_count": 32,
  "misleading_count": 8,
  "incorrect_count": 3,
  "unverifiable_count": 2,
  "accuracy_rate": 0.8943,
  "trust_score": 87.2,
  "patterns": [
    {
      "pattern_type": "systematic_overstatement",
      "metric": "revenue",
      "severity": "moderate",
      "frequency": 3,
      "avg_deviation": 0.048,
      "description": "Consistently overstates revenue by 4.8% on average",
      "affected_quarters": ["2025 Q3", "2025 Q2", "2025 Q1"],
      "recommendation": "Revenue claims require additional scrutiny"
    }
  ]
}
```

---

## 5. Claim Endpoints

### List Claims

List claims with optional filtering.

**Endpoint:** `GET /api/v1/claims/`

**Query Parameters:**
- `ticker` - Filter by company ticker (e.g., "AAPL")
- `verdict` - Filter by verdict (e.g., "VERIFIED", "INCORRECT")
- `metric` - Filter by metric (e.g., "revenue", "earnings")
- `skip` - Pagination offset (default: 0)
- `limit` - Max results (default: 50, max: 200)

**Example (curl):**
```bash
# Get all claims for Apple
curl "http://localhost:8000/api/v1/claims/?ticker=AAPL"

# Get incorrect claims
curl "http://localhost:8000/api/v1/claims/?verdict=INCORRECT"

# Get revenue claims with pagination
curl "http://localhost:8000/api/v1/claims/?metric=revenue&skip=0&limit=20"
```

**Example (Python):**
```python
# Filter by ticker
params = {"ticker": "AAPL", "limit": 20}
response = requests.get("http://localhost:8000/api/v1/claims/", params=params)
claims = response.json()

for claim in claims:
    print(f"{claim['metric']}: {claim['stated_value']}")
    if claim['verification']:
        print(f"  Verdict: {claim['verification']['verdict']}")
        print(f"  Actual: {claim['verification']['actual_value']}")
```

**Response:**
```json
[
  {
    "id": 1,
    "transcript_id": 1,
    "speaker": "Tim Cook",
    "speaker_role": "CEO",
    "claim_text": "Revenue was $123.9 billion, up 6% year over year",
    "metric": "revenue",
    "metric_type": "absolute_value",
    "stated_value": 123900000000,
    "unit": "USD",
    "comparison_period": "YoY",
    "comparison_basis": "growth",
    "is_gaap": true,
    "segment": null,
    "confidence": "high",
    "context_snippet": "Q: Can you discuss revenue trends? A: Revenue was $123.9 billion...",
    "verification": {
      "id": 1,
      "claim_id": 1,
      "actual_value": 123945000000,
      "accuracy_score": 0.9996,
      "verdict": "VERIFIED",
      "explanation": "Stated $123.9B matches actual $123.945B (0.04% difference)",
      "financial_data_source": "income_statement",
      "financial_data_id": 1,
      "comparison_data_id": null,
      "misleading_flags": [],
      "misleading_details": null
    }
  }
]
```

---

### Get Specific Claim

Get detailed information for a specific claim.

**Endpoint:** `GET /api/v1/claims/{claim_id}`

**Example (curl):**
```bash
curl http://localhost:8000/api/v1/claims/1
```

**Example (Python):**
```python
claim_id = 1
response = requests.get(f"http://localhost:8000/api/v1/claims/{claim_id}")
claim = response.json()

print(f"Claim: {claim['claim_text']}")
print(f"Stated: {claim['stated_value']:,}")

if claim['verification']:
    v = claim['verification']
    print(f"Actual: {v['actual_value']:,}")
    print(f"Verdict: {v['verdict']}")
    print(f"Explanation: {v['explanation']}")
```

---

## 6. Transcript Endpoints

### List Transcripts

List all earnings call transcripts.

**Endpoint:** `GET /api/v1/transcripts/`

**Query Parameters:**
- `ticker` - Filter by company ticker (optional)

**Example (curl):**
```bash
# All transcripts
curl http://localhost:8000/api/v1/transcripts/

# Apple transcripts only
curl "http://localhost:8000/api/v1/transcripts/?ticker=AAPL"
```

**Example (Python):**
```python
# Filter by ticker
response = requests.get(
    "http://localhost:8000/api/v1/transcripts/",
    params={"ticker": "AAPL"}
)
transcripts = response.json()

for t in transcripts:
    print(f"{t['ticker']} Q{t['quarter']} {t['year']}: {t['claim_count']} claims")
```

**Response:**
```json
[
  {
    "id": 1,
    "company_id": 1,
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "quarter": 4,
    "year": 2025,
    "call_date": "2025-10-30",
    "claim_count": 29
  }
]
```

---

### Get Transcript

Get full transcript content.

**Endpoint:** `GET /api/v1/transcripts/{transcript_id}`

**Example (curl):**
```bash
curl http://localhost:8000/api/v1/transcripts/1
```

**Example (Python):**
```python
transcript_id = 1
response = requests.get(f"http://localhost:8000/api/v1/transcripts/{transcript_id}")
transcript = response.json()

print(f"Company: {transcript['company']['name']}")
print(f"Quarter: Q{transcript['quarter']} {transcript['year']}")
print(f"Full text:\n{transcript['full_text'][:500]}...")
```

**Response:**
```json
{
  "id": 1,
  "company_id": 1,
  "quarter": 4,
  "year": 2025,
  "call_date": "2025-10-30",
  "full_text": "Operator: Good day, and welcome to Apple's Q4 2025 earnings conference call...",
  "company": {
    "id": 1,
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "sector": "Technology"
  }
}
```

---

## 7. Health Check Endpoints

### Basic Health Check

Simple alive check.

**Endpoint:** `GET /health`

**Example (curl):**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "claim-auditor",
  "version": "1.0.0"
}
```

---

### Detailed Health Check

Check all dependencies (database, APIs).

**Endpoint:** `GET /health/detailed`

**Example (curl):**
```bash
curl http://localhost:8000/health/detailed
```

**Example (Python):**
```python
response = requests.get("http://localhost:8000/health/detailed")
health = response.json()

print(f"Overall Status: {health['status']}")
for service, check in health['checks'].items():
    status = "✓" if check['healthy'] else "✗"
    print(f"{status} {service}: {check['message']}")
```

**Response:**
```json
{
  "status": "healthy",
  "service": "claim-auditor",
  "version": "1.0.0",
  "checks": {
    "database": {
      "healthy": true,
      "message": "Database connected"
    },
    "fmp_api": {
      "healthy": true,
      "message": "FMP API accessible"
    },
    "claude_api": {
      "healthy": true,
      "message": "Claude API key configured"
    }
  }
}
```

---

### Kubernetes Probes

**Readiness Probe:** `GET /health/ready`
- Returns 200 if can serve traffic
- Returns 503 if dependencies unavailable

**Liveness Probe:** `GET /health/live`
- Returns 200 if application is alive
- Used to detect deadlocks

**Example (Kubernetes):**
```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## 8. Error Handling

### Standard Error Response

All errors follow this format:

```json
{
  "detail": "Error message or validation errors"
}
```

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Request completed successfully |
| 404 | Not Found | Company or claim doesn't exist |
| 422 | Validation Error | Invalid ticker format, out-of-range quarter |
| 500 | Server Error | Database error, external API failure |
| 503 | Service Unavailable | Dependencies down (readiness check) |

### Validation Errors (422)

```json
{
  "detail": [
    {
      "loc": ["body", "tickers", 0],
      "msg": "Invalid ticker: AAAAAAA (max 5 characters)",
      "type": "value_error"
    },
    {
      "loc": ["body", "quarters", 0, 0],
      "msg": "Invalid year: 2050 (must be between 2020-2030)",
      "type": "value_error"
    }
  ]
}
```

### Example (Python error handling):

```python
try:
    response = requests.post(
        "http://localhost:8000/api/v1/pipeline/ingest",
        json={"tickers": ["INVALID123"]}
    )
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 422:
        errors = e.response.json()['detail']
        for error in errors:
            print(f"Validation error: {error['msg']}")
    elif e.response.status_code == 500:
        print("Server error:", e.response.json()['detail'])
```

---

## 9. Rate Limiting

**Current:** No rate limiting

**Production Recommendation:**
- Add rate limiting middleware (e.g., slowapi)
- Implement per-IP or per-API-key limits
- Example: 100 requests/minute per IP

```python
# Future implementation
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/v1/claims/")
@limiter.limit("100/minute")
def list_claims():
    ...
```

---

## 10. Example Workflows

### Workflow 1: Analyze a New Company

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# 1. Ingest data
print("Ingesting data...")
response = requests.post(f"{BASE_URL}/pipeline/ingest", json={
    "tickers": ["NVDA"],
    "quarters": [[2025, 4], [2025, 3]]
})
print(response.json())

# 2. Extract claims
print("Extracting claims...")
response = requests.post(f"{BASE_URL}/pipeline/extract")
print(response.json())

# 3. Verify claims
print("Verifying claims...")
response = requests.post(f"{BASE_URL}/pipeline/verify")
print(response.json())

# 4. Analyze patterns
print("Analyzing patterns...")
response = requests.post(f"{BASE_URL}/pipeline/analyze")
print(response.json())

# 5. Get results
print("Getting analysis...")
response = requests.get(f"{BASE_URL}/companies/NVDA")
analysis = response.json()

print(f"\nNVIDIA Trust Score: {analysis['trust_score']}")
print(f"Accuracy Rate: {analysis['accuracy_rate']:.2%}")
print(f"Patterns Detected: {len(analysis['patterns'])}")
```

---

### Workflow 2: Find All Misleading Claims

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# Get all misleading claims
response = requests.get(f"{BASE_URL}/claims/", params={
    "verdict": "MISLEADING",
    "limit": 200
})

claims = response.json()

print(f"Found {len(claims)} misleading claims:\n")

for claim in claims:
    print(f"Company: {claim['transcript_id']}")  # Would need to join with transcript
    print(f"Claim: {claim['claim_text']}")
    print(f"Stated: {claim['stated_value']}")

    if claim['verification']:
        v = claim['verification']
        print(f"Actual: {v['actual_value']}")
        print(f"Flags: {', '.join(v['misleading_flags'])}")
        print(f"Explanation: {v['explanation']}")
    print("-" * 80)
```

---

### Workflow 3: Monitor Pipeline Status

```python
import requests
import time

BASE_URL = "http://localhost:8000/api/v1"

def check_status():
    response = requests.get(f"{BASE_URL}/pipeline/status")
    return response.json()

# Initial status
status = check_status()
print(f"Initial: {status['claims_unverified']} claims to verify")

# Trigger verification
print("Starting verification...")
requests.post(f"{BASE_URL}/pipeline/verify")

# Poll until complete
while True:
    status = check_status()
    remaining = status['claims_unverified']
    print(f"Remaining: {remaining}")

    if remaining == 0:
        print("Verification complete!")
        break

    time.sleep(5)
```

---

## Next Steps
- **Architecture:** See [ARCHITECTURE_GUIDE.md](ARCHITECTURE_GUIDE.md)
- **Setup:** See [SETUP_GUIDE.md](SETUP_GUIDE.md)
