# Setup Guide

**Complete setup instructions for Docker, local development, testing, and deployment.**

---

## Table of Contents

1. [Quick Start (Docker)](#1-quick-start-docker)
2. [Local Development](#2-local-development)
3. [Environment Configuration](#3-environment-configuration)
4. [Running the Pipeline](#4-running-the-pipeline)
5. [Testing](#5-testing)
6. [Troubleshooting](#6-troubleshooting)
7. [Deployment](#7-deployment)

---

## 1. Quick Start (Docker)

**Time: 5 minutes**

### Prerequisites

- Docker & Docker Compose - [Download](https://www.docker.com/products/docker-desktop/)
- API Keys:
  - [FMP API](https://financialmodelingprep.com) (free tier: 250 requests/day)
  - [Anthropic API](https://console.anthropic.com) (pay-as-you-go)

### Setup

```bash
# Navigate to backend
cd claim-auditor/backend

# Configure API keys
cat > .env << EOF
FMP_API_KEY=your_fmp_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
EOF

# Run pipeline (populates database)
docker compose run streamlit python -m scripts.run_pipeline

# Launch UI
docker compose up streamlit
# → Open http://localhost:8501
```

---

## 2. Local Development

Without Docker:

```bash
cd claim-auditor/backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run pipeline
python -m scripts.run_pipeline

# Launch UI
streamlit run streamlit_app.py

# Or launch API
uvicorn app.main:app --reload --port 8000
```

---

## 3. Environment Configuration

### Required Variables

Create `backend/.env`:

```bash
FMP_API_KEY=your_key          # Financial data API
ANTHROPIC_API_KEY=your_key    # Claude for extraction
```

### Optional Variables

```bash
DATABASE_URL=sqlite:///./data/claim_auditor.db  # Database path
ANTHROPIC_MODEL=claude-sonnet-4-20250514        # LLM model
TARGET_TICKERS=AAPL,MSFT,AMZN                   # Default companies
LOG_LEVEL=INFO                                   # Logging level
```

### Verify Configuration

```bash
docker compose run streamlit python -c "from app.config import settings; print(settings)"
```

---

## 4. Running the Pipeline

### Full Pipeline

```bash
# With Docker
docker compose run streamlit python -m scripts.run_pipeline

# Without Docker
python -m scripts.run_pipeline
```

### Specific Steps

```bash
# Ingest only (fetch data from FMP)
docker compose run streamlit python -m scripts.run_pipeline --step ingest

# Extract only (LLM extraction)
docker compose run streamlit python -m scripts.run_pipeline --step extract

# Verify only (algorithmic verification)
docker compose run streamlit python -m scripts.run_pipeline --step verify

# Analyze only (pattern detection)
docker compose run streamlit python -m scripts.run_pipeline --step analyze
```

### Specific Companies

```bash
docker compose run streamlit python -m scripts.run_pipeline --tickers AAPL MSFT
```

### Pipeline Details

| Step | What It Does | Time | Cost |
|------|-------------|------|------|
| **ingest** | Fetch company data & financial statements | 30-60s | Free |
| **extract** | Extract claims via Claude AI | 1-3 min | $2-5 |
| **verify** | Compare claims vs actuals | 5-10s | Free |
| **analyze** | Detect patterns across quarters | 2-5s | Free |

---

## 5. Testing

### Run All Tests

```bash
# With Docker
docker compose run streamlit pytest

# Without Docker
pytest
```

### With Coverage

```bash
docker compose run streamlit pytest --cov=app --cov-report=term-missing

# Generate HTML report
docker compose run streamlit pytest --cov=app --cov-report=html
# Open htmlcov/index.html
```

### Specific Tests

```bash
# Single file
docker compose run streamlit pytest tests/unit/test_verification_engine.py

# Single function
docker compose run streamlit pytest tests/unit/test_verification_engine.py::test_verify_exact_match

# Verbose
docker compose run streamlit pytest -v

# Show print statements
docker compose run streamlit pytest -s
```

### Integration Tests

```bash
# Run integration tests (requires API keys, slow)
docker compose run streamlit pytest -m integration
```

---

## 6. Troubleshooting

### Docker Issues

**Container won't start:**
```bash
docker compose logs streamlit
docker compose build --no-cache
```

**Port already in use:**
```bash
lsof -i :8501  # macOS/Linux
netstat -ano | findstr :8501  # Windows
```

**Database locked:**
```bash
docker compose down
rm data/claim_auditor.db
docker compose run streamlit python -m scripts.run_pipeline
```

### API Issues

**FMP API errors:**
- Rate limit: 250/day on free tier → wait or upgrade
- Invalid key: regenerate in FMP dashboard
- Check: `curl "https://financialmodelingprep.com/api/v3/quote/AAPL?apikey=YOUR_KEY"`

**Anthropic API errors:**
- Invalid key: regenerate in Anthropic console
- Insufficient credits: add payment method
- Check model name in .env

### Pipeline Errors

**"No transcripts found":**
```bash
# Use local transcript files
mkdir -p data/transcripts
# Add files like: AAPL_Q1_2025.txt
```

**"Claims already extracted":**
```bash
# Pipeline skips existing work
# To re-extract, delete and re-run
rm data/claim_auditor.db
docker compose run streamlit python -m scripts.run_pipeline
```

### Development Issues

**Import errors:**
```bash
cd backend  # Must be in backend directory
pip install -r requirements.txt
```

**"ModuleNotFoundError: No module named 'app'":**
```bash
# Wrong (from root):
cd claim-auditor
python scripts/run_pipeline.py  # ❌

# Correct (from backend):
cd claim-auditor/backend
python -m scripts.run_pipeline  # ✅
```

---

## 7. Deployment

### Streamlit Cloud (Easiest)

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Deploy to Streamlit Cloud"
   git push origin main
   ```

2. **Deploy**
   - Visit [share.streamlit.io](https://share.streamlit.io)
   - Connect GitHub repo
   - Select `backend/streamlit_app.py`
   - Python version: 3.13

3. **Add Secrets**
   - Settings → Secrets
   ```toml
   FMP_API_KEY = "your_key"
   ANTHROPIC_API_KEY = "your_key"
   ```

**Limitations:** Read-only (can't run pipeline from UI), 1GB memory

---

### Railway (Full Stack)

1. **Create account** at [railway.app](https://railway.app)

2. **Deploy from GitHub**
   - New Project → Deploy from GitHub
   - Select repo (Railway auto-detects Dockerfile)

3. **Configure Environment**
   ```
   MODE=streamlit  # or MODE=api
   FMP_API_KEY=your_key
   ANTHROPIC_API_KEY=your_key
   ```

4. **Add Postgres Database**
   - New → Database → PostgreSQL
   - Railway auto-links and sets DATABASE_URL

**Cost:** ~$5-20/month

---

### Docker Hub (Self-Hosted)

```bash
# Build and push
cd backend
docker build -t your-username/claim-auditor:latest .
docker push your-username/claim-auditor:latest

# Deploy on any server
ssh your-server
docker pull your-username/claim-auditor:latest
docker run -p 8501:8501 \
  -e MODE=streamlit \
  -e FMP_API_KEY=your_key \
  -e ANTHROPIC_API_KEY=your_key \
  your-username/claim-auditor:latest
```

---

### Environment Variables for Deployment

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `MODE` | Yes | streamlit | `streamlit` or `api` |
| `FMP_API_KEY` | Yes | - | From FMP dashboard |
| `ANTHROPIC_API_KEY` | Yes | - | From Anthropic console |
| `DATABASE_URL` | No | SQLite | For Postgres: `postgresql://...` |
| `PORT` | No | 8501 (UI) / 8000 (API) | Auto-set by platforms |

---

### Production Checklist

- [ ] Use Postgres, not SQLite
- [ ] Add connection pooling
- [ ] Enable structured logging (JSON)
- [ ] Add rate limiting (if exposing API)
- [ ] Set up monitoring (Sentry, Datadog)
- [ ] Configure backups
- [ ] Use secret manager (not .env)
- [ ] Add health checks
- [ ] Set CORS origins (not `*`)
- [ ] Enable HTTPS only
- [ ] Set up CI/CD

---

## Quick Reference

### Common Commands

```bash
# Docker
docker compose run streamlit python -m scripts.run_pipeline
docker compose up streamlit
docker compose up api
docker compose run streamlit pytest

# Local
python -m scripts.run_pipeline
streamlit run streamlit_app.py
uvicorn app.main:app --reload
pytest
```

### File Locations

| File | Location | Purpose |
|------|----------|---------|
| Database | `backend/data/claim_auditor.db` | SQLite database |
| API cache | `backend/data/fmp_cache/` | FMP API responses |
| Transcripts | `backend/data/transcripts/` | Local .txt files |
| Config | `backend/.env` | API keys, settings |

---

## Getting Help

1. **Check logs:** `docker compose logs streamlit --tail 50`
2. **Review troubleshooting** section above
3. **Reset and retry:**
   ```bash
   docker compose down
   rm data/claim_auditor.db
   docker compose build --no-cache
   docker compose run streamlit python -m scripts.run_pipeline
   ```

---

**Next:** See [README.md](../README.md) for overview or [ARCHITECTURE_GUIDE.md](ARCHITECTURE_GUIDE.md) for technical deep dive.
