"""Transcript endpoints — list and retrieve earnings call transcripts.

Provides API endpoints for:
- Listing transcripts with optional filtering by ticker
- Getting full transcript content

All endpoints use structured logging and proper validation.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.logging_config import get_logger
from app.repositories.company_repo import CompanyRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.schemas.transcript import Transcript, TranscriptSummary

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=List[TranscriptSummary])
def list_transcripts(
    ticker: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[TranscriptSummary]:
    """List earnings call transcripts with optional company filter.

    Returns summary information for each transcript including company details,
    quarter/year, call date, and count of extracted claims.

    Args:
        ticker: Optional company ticker symbol to filter by (e.g., 'AAPL').
        db: Database session.

    Returns:
        List of transcript summaries.

    Raises:
        HTTPException: If company not found or query fails.
    """
    logger.info("transcripts_list_requested", ticker=ticker)

    try:
        repo = TranscriptRepository(db)

        if ticker:
            ticker = ticker.upper()
            company = CompanyRepository(db).get_by_ticker(ticker)
            if not company:
                logger.warning("company_not_found", ticker=ticker)
                raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
            transcripts = repo.get_for_company(company.id)
        else:
            transcripts = repo.get_all(limit=200)

        results = [
            TranscriptSummary(
                id=t.id,
                company_id=t.company_id,
                ticker=t.company.ticker,
                company_name=t.company.name,
                quarter=t.quarter,
                year=t.year,
                call_date=t.call_date,
                claim_count=len(t.claims) if t.claims else 0,
            )
            for t in transcripts
        ]

        logger.info("transcripts_list_completed", count=len(results))
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error("transcripts_list_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to list transcripts: {str(e)}"
        )


@router.get("/{transcript_id}", response_model=Transcript)
def get_transcript(transcript_id: int, db: Session = Depends(get_db)) -> Transcript:
    """Get full transcript content and metadata.

    Returns complete transcript including full text content, company information,
    quarter/year, and call date.

    Args:
        transcript_id: Unique transcript identifier.
        db: Database session.

    Returns:
        Full transcript with content.

    Raises:
        HTTPException: If transcript not found or query fails.
    """
    logger.info("transcript_get_requested", transcript_id=transcript_id)

    try:
        repo = TranscriptRepository(db)
        t = repo.get(transcript_id)
        if not t:
            logger.warning("transcript_not_found", transcript_id=transcript_id)
            raise HTTPException(status_code=404, detail="Transcript not found")

        logger.info("transcript_get_completed", transcript_id=transcript_id)
        return t

    except HTTPException:
        raise
    except Exception as e:
        logger.error("transcript_get_failed", transcript_id=transcript_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get transcript: {str(e)}"
        )
