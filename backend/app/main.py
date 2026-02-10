"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import claims, companies, pipeline, transcripts
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for the FastAPI application."""
    init_db()
    yield


app = FastAPI(
    title="Claim Auditor",
    description=(
        "Analyzes earnings call transcripts, extracts quantitative claims "
        "made by management, and verifies them against actual financial data."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — open for development; tighten for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(transcripts.router, prefix="/api/transcripts", tags=["transcripts"])
app.include_router(claims.router, prefix="/api/claims", tags=["claims"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])


@app.get("/")
def root():
    """Root endpoint - redirect to interactive docs."""
    return {
        "service": "Claim Auditor API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "companies": "/api/companies/",
            "claims": "/api/claims/",
            "transcripts": "/api/transcripts/",
            "pipeline": "/api/pipeline/status"
        }
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "claim-auditor"}
