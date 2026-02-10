# Setup Guide

**Complete setup instructions for Docker, local development, testing, and deployment.**

---

## Table of Contents

1. [Quick Start (Docker)](#1-quick-start-docker)
2. [Local Development](#2-local-development)
3. [Environment Configuration](#3-environment-configuration)
4. [Running the Pipeline](#4-running-the-pipeline)
5. [Database Migrations](#5-database-migrations)
6. [Testing](#6-testing)
7. [Troubleshooting](#7-troubleshooting)
8. [Deployment](#8-deployment)

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

## 5. Database Migrations

We use **Alembic** for database schema migrations. This allows us to evolve the database schema safely and track changes in version control.

### Understanding Migrations

**Why migrations?**
- Track database schema changes in version control
- Deploy schema changes safely
- Roll back failed migrations
- Share schema changes across team

**When do you need migrations?**
- Adding new columns to tables
- Changing column types or constraints
- Adding new tables
- Renaming tables or columns

### Basic Commands

```bash
# Check current migration status
alembic current

# View migration history
alembic history

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Roll back all migrations
alembic downgrade base
```

### Creating a Migration

When you modify database models:

```bash
# 1. Modify your models (e.g., app/models/company.py)
# class CompanyModel(Base):
#     ...
#     founded_year = Column(Integer)  # NEW COLUMN

# 2. Generate migration automatically
alembic revision --autogenerate -m "add founded_year to companies"

# 3. Review generated migration in alembic/versions/
# Check if autogenerate captured everything correctly

# 4. Apply migration
alembic upgrade head
```

### Manual Migrations

For complex changes, create manual migrations:

```bash
# Create blank migration
alembic revision -m "custom schema change"

# Edit generated file in alembic/versions/
# def upgrade():
#     op.execute("CREATE INDEX idx_custom ON table(column)")
#
# def downgrade():
#     op.execute("DROP INDEX idx_custom")

# Apply migration
alembic upgrade head
```

### Common Migration Scenarios

**Add a new column:**
```python
# In models/company.py
class CompanyModel(Base):
    ...
    market_cap = Column(Integer, nullable=True)  # NEW

# Generate and apply
alembic revision --autogenerate -m "add market_cap"
alembic upgrade head
```

**Rename a column:**
```bash
# Create manual migration (autogenerate doesn't detect renames)
alembic revision -m "rename company_name to name"

# Edit migration file:
# def upgrade():
#     op.alter_column('companies', 'company_name',
#                     new_column_name='name')
#
# def downgrade():
#     op.alter_column('companies', 'name',
#                     new_column_name='company_name')
```

**Add a new table:**
```python
# Create new model file
# Generate migration (autogenerate detects new tables)
alembic revision --autogenerate -m "add users table"
alembic upgrade head
```

### Docker Usage

```bash
# Check status
docker compose run streamlit alembic current

# Generate migration
docker compose run streamlit alembic revision --autogenerate -m "description"

# Apply migrations
docker compose run streamlit alembic upgrade head
```

### Migration Best Practices

1. **Always review autogenerated migrations** - Autogenerate can miss:
   - Column renames (sees as drop + add)
   - Data migrations
   - Complex index changes

2. **Test migrations on copy of production data** - Before deploying:
   ```bash
   # Create backup
   cp data/claim_auditor.db data/claim_auditor.backup.db

   # Test migration
   alembic upgrade head

   # If successful, deploy. If failed:
   alembic downgrade -1
   ```

3. **Never edit applied migrations** - Once pushed to production:
   - Create new migration to fix issues
   - Never modify existing migration files

4. **Include data migrations** - If you need to migrate data:
   ```python
   def upgrade():
       # Schema change
       op.add_column('companies', sa.Column('active', sa.Boolean))

       # Data migration
       op.execute("UPDATE companies SET active = TRUE WHERE ticker IS NOT NULL")
   ```

5. **Test rollback** - Always verify downgrade works:
   ```bash
   alembic upgrade head      # Apply
   alembic downgrade -1      # Roll back
   alembic upgrade head      # Re-apply
   ```

### Deployment Workflow

**Local development:**
```bash
# 1. Modify models
# 2. Generate migration
alembic revision --autogenerate -m "description"

# 3. Review and edit migration if needed
# 4. Test migration
alembic upgrade head

# 5. Commit migration file
git add alembic/versions/*.py
git commit -m "Add migration: description"
```

**Production deployment:**
```bash
# 1. Pull latest code
git pull origin main

# 2. Backup database
pg_dump production_db > backup_$(date +%Y%m%d).sql

# 3. Apply migrations
alembic upgrade head

# 4. Verify application works
curl /health/ready

# 5. If failed, rollback
alembic downgrade -1
```

### Troubleshooting

**"Can't locate revision":**
```bash
# Alembic database is out of sync
# Check current database version
alembic current

# Stamp database with correct version
alembic stamp head
```

**"Multiple head revisions":**
```bash
# You have branching migrations
# Merge branches
alembic merge heads -m "merge branches"
```

**"Table already exists":**
```bash
# Database wasn't created via migrations
# Stamp database to skip existing tables
alembic stamp head
```

---

## 6. Testing

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

## 7. Troubleshooting

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

## 8. Deployment

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
