"""Pipeline endpoints — trigger ingestion, extraction, verification."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import get_db
from app.dependencies import (
    get_analysis_service,
    get_extraction_service,
    get_ingestion_service,
    get_settings,
    get_verification_service,
)
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.repositories.verification_repo import VerificationRepository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ingest")
def trigger_ingestion(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Fetch transcripts + financial data for all target companies."""
    svc = get_ingestion_service(db)
    summary = svc.ingest_all(
        tickers=settings.target_tickers,
        quarters=settings.target_quarters,
    )
    return {"status": "completed", "summary": summary}


@router.post("/extract")
def trigger_extraction(db: Session = Depends(get_db)):
    """Extract claims from unprocessed transcripts via LLM."""
    svc = get_extraction_service(db)
    summary = svc.extract_all()
    return {"status": "completed", "summary": summary}


@router.post("/verify")
def trigger_verification(db: Session = Depends(get_db)):
    """Verify all unverified claims against financial data."""
    svc = get_verification_service(db)
    summary = svc.verify_all()
    return {"status": "completed", "summary": summary}


@router.post("/run-all")
def run_full_pipeline(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Run complete pipeline: ingest → extract → verify."""
    results = {}

    logger.info("=== Step 1/3: Ingestion ===")
    ingest_svc = get_ingestion_service(db)
    results["ingestion"] = ingest_svc.ingest_all(
        tickers=settings.target_tickers,
        quarters=settings.target_quarters,
    )

    logger.info("=== Step 2/3: Extraction ===")
    extract_svc = get_extraction_service(db)
    results["extraction"] = extract_svc.extract_all()

    logger.info("=== Step 3/3: Verification ===")
    verify_svc = get_verification_service(db)
    results["verification"] = verify_svc.verify_all()

    return {"status": "completed", "pipeline": results}


@router.get("/status")
def pipeline_status(db: Session = Depends(get_db)):
    """Current counts for each stage of the pipeline."""
    companies = CompanyRepository(db).count()
    transcripts = TranscriptRepository(db).count()
    claims = ClaimRepository(db).count()
    verifications = VerificationRepository(db).count()
    unverified = len(ClaimRepository(db).get_unverified())
    unprocessed = len(TranscriptRepository(db).get_unprocessed())

    return {
        "companies": companies,
        "transcripts": transcripts,
        "transcripts_unprocessed": unprocessed,
        "claims": claims,
        "claims_unverified": unverified,
        "verifications": verifications,
    }
