"""Pipeline endpoints — trigger ingestion, extraction, verification.

Provides API endpoints to execute the earnings call verification pipeline stages:
- Ingestion: Fetch financial data and transcripts
- Extraction: Extract claims via LLM
- Verification: Verify claims against actual data
- Analysis: Detect discrepancy patterns

All endpoints use structured logging and proper validation.
"""

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
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
from app.logging_config import get_logger
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.repositories.verification_repo import VerificationRepository
from app.schemas.pipeline import (
    PipelineIngestRequest,
    PipelineResponse,
    PipelineStatusResponse,
)

logger = get_logger(__name__)
router = APIRouter()


@router.post("/ingest", response_model=PipelineResponse)
def trigger_ingestion(
    request: PipelineIngestRequest = PipelineIngestRequest(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Fetch transcripts + financial data for specified companies.

    Args:
        request: Ingestion request with optional tickers and quarters.
        db: Database session.
        settings: Application settings.

    Returns:
        Pipeline response with ingestion summary.

    Raises:
        HTTPException: If ingestion fails.
    """
    tickers = request.tickers or settings.target_tickers
    quarters = request.quarters or settings.target_quarters

    logger.info(
        "pipeline_ingestion_started",
        tickers=tickers,
        num_tickers=len(tickers),
        num_quarters=len(quarters),
    )

    try:
        svc = get_ingestion_service(db)
        summary = svc.ingest_all(tickers=tickers, quarters=quarters)

        logger.info(
            "pipeline_ingestion_completed",
            tickers=tickers,
            summary=summary,
        )

        return {"status": "completed", "summary": summary}
    except Exception as e:
        logger.error("pipeline_ingestion_failed", error=str(e), tickers=tickers)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/extract", response_model=PipelineResponse)
def trigger_extraction(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Extract claims from unprocessed transcripts via LLM.

    Args:
        db: Database session.

    Returns:
        Pipeline response with extraction summary.

    Raises:
        HTTPException: If extraction fails.
    """
    logger.info("pipeline_extraction_started")

    try:
        svc = get_extraction_service(db)
        summary = svc.extract_all()

        logger.info("pipeline_extraction_completed", summary=summary)

        return {"status": "completed", "summary": summary}
    except Exception as e:
        logger.error("pipeline_extraction_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@router.post("/verify", response_model=PipelineResponse)
def trigger_verification(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Verify all unverified claims against financial data.

    Args:
        db: Database session.

    Returns:
        Pipeline response with verification summary.

    Raises:
        HTTPException: If verification fails.
    """
    logger.info("pipeline_verification_started")

    try:
        svc = get_verification_service(db)
        summary = svc.verify_all()

        logger.info("pipeline_verification_completed", summary=summary)

        return {"status": "completed", "summary": summary}
    except Exception as e:
        logger.error("pipeline_verification_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.post("/analyze", response_model=PipelineResponse)
def trigger_analysis(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Analyze all companies for discrepancy patterns.

    Args:
        db: Database session.

    Returns:
        Pipeline response with analysis summary.

    Raises:
        HTTPException: If analysis fails.
    """
    logger.info("pipeline_analysis_started")

    try:
        svc = get_analysis_service(db)
        analyses = svc.analyze_all()

        summary = {
            "companies_analyzed": len(analyses),
            "total_patterns": sum(len(a.patterns) for a in analyses),
        }

        logger.info("pipeline_analysis_completed", summary=summary)

        return {"status": "completed", "summary": summary}
    except Exception as e:
        logger.error("pipeline_analysis_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/run-all", response_model=PipelineResponse)
def run_full_pipeline(
    request: PipelineIngestRequest = PipelineIngestRequest(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Run complete pipeline: ingest → extract → verify → analyze.

    Args:
        request: Pipeline request with optional tickers and quarters.
        db: Database session.
        settings: Application settings.

    Returns:
        Pipeline response with results from all stages.

    Raises:
        HTTPException: If any pipeline stage fails.
    """
    tickers = request.tickers or settings.target_tickers
    quarters = request.quarters or settings.target_quarters

    logger.info(
        "full_pipeline_started",
        tickers=tickers,
        num_tickers=len(tickers),
        num_quarters=len(quarters),
    )

    results: Dict[str, Any] = {}

    try:
        # Step 1: Ingestion
        logger.info("pipeline_step", step="ingestion", stage="1/4")
        ingest_svc = get_ingestion_service(db)
        results["ingestion"] = ingest_svc.ingest_all(tickers=tickers, quarters=quarters)

        # Step 2: Extraction
        logger.info("pipeline_step", step="extraction", stage="2/4")
        extract_svc = get_extraction_service(db)
        results["extraction"] = extract_svc.extract_all()

        # Step 3: Verification
        logger.info("pipeline_step", step="verification", stage="3/4")
        verify_svc = get_verification_service(db)
        results["verification"] = verify_svc.verify_all()

        # Step 4: Analysis
        logger.info("pipeline_step", step="analysis", stage="4/4")
        analysis_svc = get_analysis_service(db)
        analyses = analysis_svc.analyze_all()
        results["analysis"] = {
            "companies_analyzed": len(analyses),
            "total_patterns": sum(len(a.patterns) for a in analyses),
        }

        logger.info("full_pipeline_completed", tickers=tickers, results=results)

        return {"status": "completed", "pipeline": results}

    except Exception as e:
        logger.error("full_pipeline_failed", error=str(e), tickers=tickers)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


@router.get("/status", response_model=PipelineStatusResponse)
def pipeline_status(db: Session = Depends(get_db)) -> Dict[str, int]:
    """Current counts for each stage of the pipeline.

    Args:
        db: Database session.

    Returns:
        Status counts for all pipeline stages.
    """
    companies = CompanyRepository(db).count()
    transcripts = TranscriptRepository(db).count()
    claims = ClaimRepository(db).count()
    verifications = VerificationRepository(db).count()
    unverified = len(ClaimRepository(db).get_unverified())
    unprocessed = len(TranscriptRepository(db).get_unprocessed())

    status = {
        "companies": companies,
        "transcripts": transcripts,
        "transcripts_unprocessed": unprocessed,
        "claims": claims,
        "claims_unverified": unverified,
        "verifications": verifications,
    }

    logger.info("pipeline_status_requested", status=status)

    return status
