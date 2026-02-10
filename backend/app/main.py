"""FastAPI application entry point with structured logging and health checks."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import claims, companies, pipeline, transcripts
from app.database import init_db
from app.health import router as health_router
from app.logging_config import get_logger, setup_logging

# Setup structured logging
setup_logging(
    json_logs=os.getenv("JSON_LOGS", "false").lower() == "true",
    log_level=os.getenv("LOG_LEVEL", "INFO"),
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for the FastAPI application."""
    logger.info("application_startup", version="1.0.0")
    init_db()
    logger.info("database_initialized")
    yield
    logger.info("application_shutdown")


app = FastAPI(
    title="Claim Auditor",
    description=(
        "Analyzes earnings call transcripts, extracts quantitative claims "
        "made by management, and verifies them against actual financial data."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — restricted for security
# In production, only allow specific domains
import os
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501,https://claim-auditor.streamlit.app").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

# Health checks (no versioning)
app.include_router(health_router, tags=["health"])

# API Versioning - v1 endpoints
API_V1_PREFIX = "/api/v1"

app.include_router(companies.router, prefix=f"{API_V1_PREFIX}/companies", tags=["companies"])
app.include_router(transcripts.router, prefix=f"{API_V1_PREFIX}/transcripts", tags=["transcripts"])
app.include_router(claims.router, prefix=f"{API_V1_PREFIX}/claims", tags=["claims"])
app.include_router(pipeline.router, prefix=f"{API_V1_PREFIX}/pipeline", tags=["pipeline"])

# Legacy routes (redirect to v1) - for backward compatibility
app.include_router(companies.router, prefix="/api/companies", tags=["companies (legacy)"], include_in_schema=False)
app.include_router(transcripts.router, prefix="/api/transcripts", tags=["transcripts (legacy)"], include_in_schema=False)
app.include_router(claims.router, prefix="/api/claims", tags=["claims (legacy)"], include_in_schema=False)
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline (legacy)"], include_in_schema=False)


@app.get("/")
def root():
    """Root endpoint - API information and available endpoints."""
    logger.info("root_endpoint_accessed")
    return {
        "service": "Claim Auditor API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "health_detailed": "/health/detailed",
        "api_version": "v1",
        "endpoints": {
            "companies": "/api/v1/companies/",
            "claims": "/api/v1/claims/",
            "transcripts": "/api/v1/transcripts/",
            "pipeline": "/api/v1/pipeline/status",
        },
        "legacy_endpoints_note": "Unversioned /api/* endpoints still work but are deprecated. Use /api/v1/* instead."
    }
