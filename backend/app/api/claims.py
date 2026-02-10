"""Claim endpoints — list and retrieve claims with verification results.

Provides API endpoints for:
- Listing claims with optional filtering by ticker, verdict, or metric
- Getting detailed claim information with verification

All endpoints use structured logging and proper validation.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.logging_config import get_logger
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.schemas.claim import ClaimWithVerification
from app.schemas.verification import Verification

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=List[ClaimWithVerification])
def list_claims(
    ticker: Optional[str] = None,
    verdict: Optional[str] = None,
    metric: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
) -> List[ClaimWithVerification]:
    """List claims with optional filtering.

    Supports filtering by:
    - ticker: Filter claims for specific company
    - verdict: Filter by verification verdict (VERIFIED, INCORRECT, etc.)
    - metric: Filter by metric name (revenue, earnings, etc.)
    - skip/limit: Pagination support

    Args:
        ticker: Optional company ticker symbol (e.g., 'AAPL').
        verdict: Optional verification verdict filter.
        metric: Optional metric name filter.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return (max 200).
        db: Database session.

    Returns:
        List of claims with verification results.

    Raises:
        HTTPException: If company not found or query fails.
    """
    logger.info(
        "claims_list_requested",
        ticker=ticker,
        verdict=verdict,
        metric=metric,
        skip=skip,
        limit=limit,
    )

    try:
        repo = ClaimRepository(db)

        if ticker:
            ticker = ticker.upper()
            company = CompanyRepository(db).get_by_ticker(ticker)
            if not company:
                logger.warning("company_not_found", ticker=ticker)
                raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
            claims = repo.get_for_company(company.id)
        elif verdict:
            claims = repo.get_by_verdict(verdict, limit=limit)
        else:
            claims = repo.get_all(skip=skip, limit=limit)

        # Post-filter by metric if provided
        if metric:
            claims = [c for c in claims if c.metric == metric]

        results = [
            ClaimWithVerification(
                id=c.id,
                transcript_id=c.transcript_id,
                speaker=c.speaker,
                speaker_role=c.speaker_role,
                claim_text=c.claim_text,
                metric=c.metric,
                metric_type=c.metric_type,
                stated_value=c.stated_value,
                unit=c.unit,
                comparison_period=c.comparison_period,
                comparison_basis=c.comparison_basis,
                is_gaap=c.is_gaap,
                segment=c.segment,
                confidence=c.confidence,
                context_snippet=c.context_snippet,
                verification=Verification(
                    id=c.verification.id,
                    claim_id=c.verification.claim_id,
                    actual_value=c.verification.actual_value,
                    accuracy_score=c.verification.accuracy_score,
                    verdict=c.verification.verdict,
                    explanation=c.verification.explanation,
                    financial_data_source=c.verification.financial_data_source,
                    financial_data_id=c.verification.financial_data_id,
                    comparison_data_id=c.verification.comparison_data_id,
                    misleading_flags=c.verification.misleading_flags or [],
                    misleading_details=c.verification.misleading_details,
                ) if c.verification else None,
            )
            for c in claims
        ]

        logger.info("claims_list_completed", count=len(results))
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error("claims_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list claims: {str(e)}")


@router.get("/{claim_id}", response_model=ClaimWithVerification)
def get_claim(claim_id: int, db: Session = Depends(get_db)) -> ClaimWithVerification:
    """Get detailed information for a specific claim.

    Includes full claim details and verification results if available.

    Args:
        claim_id: Unique claim identifier.
        db: Database session.

    Returns:
        Claim with verification results.

    Raises:
        HTTPException: If claim not found or query fails.
    """
    logger.info("claim_get_requested", claim_id=claim_id)

    try:
        repo = ClaimRepository(db)
        c = repo.get_with_verification(claim_id)
        if not c:
            logger.warning("claim_not_found", claim_id=claim_id)
            raise HTTPException(status_code=404, detail="Claim not found")

        result = ClaimWithVerification(
            id=c.id,
            transcript_id=c.transcript_id,
            speaker=c.speaker,
            speaker_role=c.speaker_role,
            claim_text=c.claim_text,
            metric=c.metric,
            metric_type=c.metric_type,
            stated_value=c.stated_value,
            unit=c.unit,
            comparison_period=c.comparison_period,
            comparison_basis=c.comparison_basis,
            is_gaap=c.is_gaap,
            segment=c.segment,
            confidence=c.confidence,
            context_snippet=c.context_snippet,
            verification=Verification(
                id=c.verification.id,
                claim_id=c.verification.claim_id,
                actual_value=c.verification.actual_value,
                accuracy_score=c.verification.accuracy_score,
                verdict=c.verification.verdict,
                explanation=c.verification.explanation,
                financial_data_source=c.verification.financial_data_source,
                financial_data_id=c.verification.financial_data_id,
                comparison_data_id=c.verification.comparison_data_id,
                misleading_flags=c.verification.misleading_flags or [],
                misleading_details=c.verification.misleading_details,
            ) if c.verification else None,
        )

        logger.info("claim_get_completed", claim_id=claim_id)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("claim_get_failed", claim_id=claim_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get claim: {str(e)}")
