# Claim Auditor

**Automated earnings verification system that fact-checks executive claims from earnings calls.**

Executives make 30-50 quantitative claims per earnings call. This system extracts them via LLM, verifies against SEC data, and detects patterns of misleading communication.

**🔗 [Live Demo](https://claim-auditor.streamlit.app/)**\
**🎥 [Demo Video](https://youtu.be/coming-soon)** *(Coming soon!)*

---

## Problem & Solution

### The Problem

During quarterly earnings calls, executives make claims like:
- *"Revenue grew 15% year-over-year"*
- *"Operating margins expanded to 28%"*
- *"Free cash flow was $4.2 billion"*

**But:**
- Often inaccurate (stated 15%, actual was 12.3%)
- Sometimes misleading (GAAP vs non-GAAP switching, favorable rounding)
- Systematically biased (consistent patterns across quarters)

Manual verification is impractical—requires cross-referencing multiple financial statements, unit conversions, and pattern detection.

### The Solution

Automated 4-stage pipeline:

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   INGEST     │ → │   EXTRACT    │ → │   VERIFY     │ → │   ANALYZE    │
│              │   │              │   │              │   │              │
│ Fetch data   │   │ LLM extracts │   │ Compare vs   │   │ Detect cross-│
│ from FMP API │   │ structured   │   │ actual data  │   │ quarter      │
│ & store in   │   │ claims from  │   │ & assign     │   │ patterns of  │
│ SQLite       │   │ transcripts  │   │ verdicts     │   │ deception    │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

**Output:** Trust scores (0-100), verdict breakdowns, discrepancy patterns, and a web dashboard.

---

## Key Features

### 1. Multi-Tier Verdict System

Not just true/false—captures nuance:

| Verdict | Threshold | Example |
|---------|-----------|---------|
| ✅ Correct | Within 2% | Stated 15.1%, actual 15.0% |
| ≈ Mostly Correct | Within 10% | Stated 15%, actual 13.8% |
| ⚠️ Misleading | 10-25% off OR flagged | Stated 15%, actual 11.2% |
| ❌ Incorrect | >25% off | Stated 15%, actual 9.8% |
| ❓ Cannot Verify | No data | Segment claim without segment data |

### 2. Pattern Detection

Detects systematic deception across quarters:
- **Consistent rounding up** (>70% of claims favor company)
- **Metric switching** (emphasizing different metrics each quarter)
- **Increasing inaccuracy** (accuracy declining over time)
- **GAAP shifting** (switching between GAAP and non-GAAP)
- **Selective emphasis** (only mentioning positive metrics)

### 3. Multiple Interfaces

- **Streamlit Dashboard** - Visual exploration
- **REST API** - Programmatic access (12 endpoints)
- **CLI** - Pipeline execution
- **MCP Server** - AI agent integration

### 4. Smart Transcript Fallback (Three-Tier Strategy)

When transcript data is unavailable from FMP API:

1. **Tier 1:** Fetch from FMP API (primary source)
2. **Tier 2:** Load from local files (`data/transcripts/`)
3. **Tier 3:** Generate with LLM based on financial data (automatic fallback)

The system automatically generates realistic earnings call transcripts using Claude when needed, ensuring no company is left without claims to audit.

### 5. Production-Ready

- **333+ tests** passing (unit + integration + E2E)
- **6-layer clean architecture** with dependency injection
- **Service-controlled transactions** (atomicity, rollback, data consistency)
- **Structured logging** (JSON/human-readable modes)
- **Health checks** (Kubernetes-ready probes)
- **API versioning** (/api/v1/) with backward compatibility
- **Input validation** (Pydantic models prevent injection attacks)
- **Database migrations** (Alembic for safe schema evolution)
- **Docker-first** deployment (same image for UI/API)
- **Comprehensive docs** (readme, architecture, setup, API guide)

---

## Quick Start (5 Minutes)

### Prerequisites

- Docker & Docker Compose
- API keys: [FMP](https://financialmodelingprep.com) (free) + [Anthropic](https://console.anthropic.com)

### Setup

```bash
cd claim-auditor/backend

# 1. Configure API keys
cat > .env << EOF
FMP_API_KEY=your_fmp_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
EOF

# 2. Run pipeline (populate database)
docker compose run streamlit python -m scripts.run_pipeline

# 3. Launch UI
docker compose up streamlit
```

**Access:** http://localhost:8501

---

## Project Structure

```
claim-auditor/
├── README.md                    ← You are here
├── docs/                        ← Documentation
│   ├── ARCHITECTURE_GUIDE.md          → Deep dive: layers, design decisions
│   ├── SETUP_GUIDE.md                 → Setup & deployment guide
│   ├── API_USAGE_GUIDE.md                   → REST API guide with examples
│   └── MCP_GUIDE.md                   → AI agent integration
│
└── backend/
    ├── Dockerfile               ← Container definition
    ├── docker-compose.yml       ← Multi-service orchestration
    ├── requirements.txt         ← Python dependencies
    │
    ├── app/                     ← Core application
    │   ├── main.py              ← FastAPI application entry point
    │   ├── facade.py            ← Single entry point (hides complexity)
    │   ├── container.py         ← Dependency injection container
    │   ├── logging_config.py    ← Structured logging setup
    │   ├── health.py            ← Health check endpoints
    │   │
    │   ├── clients/             ← External API wrappers
    │   │   ├── fmp_client.py    → Financial data API
    │   │   └── llm_client.py    → Claude AI
    │   │
    │   ├── services/            ← Workflow orchestration
    │   │   ├── ingestion_service.py
    │   │   ├── extraction_service.py
    │   │   ├── verification_service.py
    │   │   └── analysis_service.py
    │   │
    │   ├── engines/             ← Core business logic
    │   │   ├── claim_extractor.py
    │   │   ├── verification_engine.py  ← 400+ lines, core algorithm
    │   │   ├── metric_mapper.py
    │   │   └── discrepancy_analyzer.py
    │   │
    │   ├── domain/              ← Pure business rules (zero dependencies)
    │   │   ├── metrics.py       → Metric definitions
    │   │   ├── verdicts.py      → Verdict assignment logic
    │   │   └── scoring.py       → Trust score formulas
    │   │
    │   ├── repositories/        ← Database abstraction
    │   ├── models/              ← SQLAlchemy ORM (database tables)
    │   ├── schemas/             ← Pydantic (API contracts + validation)
    │   │   └── pipeline.py      → Pipeline request validation
    │   └── api/                 ← REST API endpoints
    │       ├── pipeline.py      → Pipeline operations
    │       ├── companies.py     → Company endpoints
    │       ├── claims.py        → Claim endpoints
    │       └── transcripts.py   → Transcript endpoints
    │
    ├── alembic/                 ← Database migrations
    │   ├── versions/            → Migration scripts
    │   └── env.py               → Alembic configuration
    │
    ├── streamlit_app.py         ← Web dashboard
    ├── mcp_server.py            ← AI agent integration
    ├── scripts/run_pipeline.py ← CLI entry point
    │
    ├── data/
    │   ├── claim_auditor.db     ← SQLite database
    │   ├── fmp_cache/           ← API response cache
    │   └── transcripts/         ← Local transcript files
    │
    └── tests/
        ├── unit/                ← Fast tests (313+ tests, <3s)
        ├── api/                 ← API endpoint tests
        └── integration/         ← Live API tests
```

---

## Usage

### Run Pipeline

```bash
# With Docker (recommended)
docker compose run streamlit python -m scripts.run_pipeline

# Run specific step
docker compose run streamlit python -m scripts.run_pipeline --step extract

# Target specific companies
docker compose run streamlit python -m scripts.run_pipeline --tickers AAPL MSFT
```

### Launch Interfaces

```bash
# Streamlit Dashboard
docker compose up streamlit
# → http://localhost:8501

# REST API
docker compose up api
# → http://localhost:8000/docs (interactive Swagger UI)

# Both
docker compose up
```

### Run Tests

```bash
# All tests
docker compose run streamlit pytest

# With coverage
docker compose run streamlit pytest --cov=app --cov-report=term-missing

# Specific test file
docker compose run streamlit pytest tests/unit/test_verification_engine.py
```

---

## REST API

**Base URL (v1):** http://localhost:8000/api/v1
**Legacy:** http://localhost:8000/api (backward compatible)

### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/companies/` | List all companies with stats |
| `GET /api/v1/companies/{ticker}` | Full analysis for one company |
| `GET /api/v1/claims/` | List claims (filterable by verdict/metric/ticker) |
| `GET /api/v1/transcripts/` | List transcripts |
| `GET /api/v1/pipeline/status` | Pipeline status (counts) |
| `POST /api/v1/pipeline/ingest` | Fetch data from FMP API |
| `POST /api/v1/pipeline/extract` | Extract claims via LLM |
| `POST /api/v1/pipeline/verify` | Verify claims against data |
| `POST /api/v1/pipeline/analyze` | Detect discrepancy patterns |
| `POST /api/v1/pipeline/run-all` | Execute full pipeline |
| `GET /health` | Basic health check |
| `GET /health/detailed` | Health check with dependencies |
| `GET /health/ready` | Kubernetes readiness probe |
| `GET /health/live` | Kubernetes liveness probe |

### Examples

```bash
# Get all companies
curl http://localhost:8000/api/v1/companies/

# Analyze Amazon
curl http://localhost:8000/api/v1/companies/AMZN

# Get misleading claims
curl "http://localhost:8000/api/v1/claims/?verdict=MISLEADING"

# Check health
curl http://localhost:8000/health/detailed

# Trigger ingestion
curl -X POST http://localhost:8000/api/v1/pipeline/ingest \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL"], "quarters": [[2025, 4]]}'
```

**Full docs:** Visit http://localhost:8000/docs for interactive API documentation

**More examples:** [docs/API_USAGE_GUIDE.md](docs/API_USAGE_GUIDE.md) - Comprehensive API guide with curl/Python/JavaScript examples

**Setup guide:** [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) - Comprehensive setup, deployment, and troubleshooting

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.13 |
| **Web Framework** | FastAPI (API), Streamlit (UI) |
| **LLM** | Claude Sonnet 4.5 (Anthropic) |
| **Financial Data** | Financial Modeling Prep API |
| **Database** | SQLite (dev), PostgreSQL-ready |
| **ORM** | SQLAlchemy 2.0 |
| **Migrations** | Alembic |
| **Validation** | Pydantic 2.0 |
| **Logging** | structlog (JSON/human-readable) |
| **Dependency Injection** | dependency-injector |
| **Testing** | pytest, pytest-cov (331+ tests) |
| **Deployment** | Docker, docker-compose |
| **CI/CD** | GitHub Actions (can be added) |

---

## Architecture Highlights

### System Architecture (High Level)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Multiple Interfaces                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Streamlit │  │ REST API │  │ CLI      │  │ MCP Server   │   │
│  │ Dashboard │  │ (FastAPI)│  │ Scripts  │  │ (AI Agents)  │   │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └──────┬───────┘   │
└────────┼─────────────┼─────────────┼───────────────┼───────────┘
         │             │             │               │
         └─────────────┴─────────────┴───────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      PipelineFacade                              │
│                  (Single entry point)                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     Service Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Ingestion    │  │ Extraction   │  │ Verification │          │
│  │ Service      │  │ Service      │  │ Service      │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼─────────────────┐
│              Engines + Repositories + Clients                    │
│  ┌────────────┐  ┌──────────────┐  ┌────────────┐              │
│  │ Verification│ │ Financial    │  │ FMP Client │              │
│  │ Engine     │  │ Data Repo    │  │ (API)      │              │
│  └────────────┘  └──────────────┘  └────────────┘              │
│  ┌────────────┐  ┌──────────────┐  ┌────────────┐              │
│  │ Claim      │  │ Claim Repo   │  │ LLM Client │              │
│  │ Extractor  │  │              │  │ (Claude)   │              │
│  └────────────┘  └──────────────┘  └────────────┘              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│              Domain Layer (Pure business rules)                  │
│         Verdicts • Scoring • Metrics (zero dependencies)         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                 Database (SQLite / Postgres)                     │
│  Companies • Transcripts • Claims • Verifications • Patterns     │
└─────────────────────────────────────────────────────────────────┘
```

### Clean 6-Layer Architecture

```
Presentation (UI/API/CLI/MCP)
    ↓
Facade (Single entry point)
    ↓
Services (Orchestration)
    ↓
Engines + Repos + Clients (Business logic + Data + External APIs)
    ↓
Domain (Pure rules, zero dependencies)
    ↓
Infrastructure (Database, ORM, Config)
```

### Key Patterns

- **Facade Pattern** - Single entry point, hides complexity
- **Repository Pattern** - Database abstraction (easy to swap SQLite → Postgres)
- **Dependency Injection** - Clean testing, loose coupling
- **Domain-Driven Design** - Business rules isolated from infrastructure
- **Versioned Prompts** - LLM prompts in files, not hardcoded

### Why This Architecture?

1. **Testability** - Business logic tested without database/APIs (230 tests run in <2s)
2. **Flexibility** - Swap implementations without breaking other layers
3. **Clarity** - Bug in verdicts? Check `domain/verdicts.py` (30 lines, not 3000)

**Full details:** See [ARCHITECTURE_GUIDE.md](docs/ARCHITECTURE_GUIDE.md)

---

## Development

### Local Setup (Without Docker)

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your keys

# Run pipeline
python -m scripts.run_pipeline

# Launch UI
streamlit run streamlit_app.py
```

### Adding a New Company

```bash
# Option 1: Run pipeline for specific ticker
docker compose run streamlit python -m scripts.run_pipeline --tickers TSLA

# Option 2: Add to default list
# Edit app/config.py → target_tickers list
```

### Database Migrations

```bash
# Check current migration status
alembic current

# Create new migration after model changes
alembic revision --autogenerate -m "add new column"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

**More details:** See [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md#5-database-migrations)

### Testing

```bash
# Unit tests only (fast)
pytest tests/unit/

# Integration tests (requires API keys)
pytest -m integration

# Specific test file
pytest tests/unit/test_verification_engine.py -v

# With coverage
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

---

## Documentation

| File | Purpose |
|------|---------|
| **README.md** | This file - quick overview and getting started |
| **[docs/ARCHITECTURE_GUIDE.md](docs/ARCHITECTURE_GUIDE.md)** | Deep dive: 6-layer architecture, design decisions, production features |
| **[docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)** | Setup, deployment, database migrations, troubleshooting |
| **[docs/API_USAGE_GUIDE.md](docs/API_USAGE_GUIDE.md)** | REST API guide with curl/Python/JavaScript examples |
| **[docs/MCP_GUIDE.md](docs/MCP_GUIDE.md)** | AI agent integration (Claude Code, Cursor) |

---

## MCP Server (AI Agent Integration)

Expose claim auditor as tools for AI agents (Claude Code, Cursor, custom agents).

**Quick start:**
```bash
cd backend
python mcp_server.py
```

**Available tools:**
- `list_companies()` - Get all companies with trust scores
- `analyze_company(ticker)` - Full analysis
- `get_claims(ticker, verdict?)` - Claims with optional filtering
- `compare_quarters(ticker)` - Quarter-by-quarter trends
- `get_discrepancy_patterns(ticker)` - Systematic bias detection
- `run_pipeline(tickers, steps)` - Execute pipeline

**Full setup:** See [MCP_GUIDE.md](docs/MCP_GUIDE.md) for configuration, usage examples, and troubleshooting.

---

## For Reviewers

### Trade-offs Made

| Decision | Why | Alternative Considered |
|----------|-----|----------------------|
| SQLite vs Postgres | Dev simplicity, easy to demo | Postgres for production scale |
| Deterministic verification | Explainability, testing | LLM-based (inconsistent) |
| Local LLM for extraction | Claude API quality | Open-source (less accurate) |
| Pydantic 2.0 | Fast validation | Manual validation (error-prone) |

### What I'd Do Differently at Scale

**Infrastructure:**
- Postgres + connection pooling (SQLite doesn't scale)
- Redis for distributed caching (in-memory doesn't work across processes)
- Celery for async pipeline (long-running tasks)
- Rate limiting on API (currently unlimited)
- Message queue (RabbitMQ/Kafka) for event-driven architecture

**Architecture & Code Quality:**
- Reduce architectural debt (current setup was rapidly prototyped)
- Async operations throughout (currently synchronous for simplicity)
- OpenRouter integration (one source for multiple LLM providers, easy model switching)
- More comprehensive per-file documentation (1:1 markdown for each Python file)

**Features & UX:**
- Custom React/Vue UI (currently using Streamlit for rapid development)
- UI-based company addition (currently CLI/script only)
- Real-time pipeline status updates (WebSocket)
- User authentication and multi-tenancy

---

## License

MIT

---

## Contact

For questions or feedback:
- Open an issue on GitHub
- Or reach out directly

---

**Built with:** Python • FastAPI • Streamlit • Claude AI • Docker
