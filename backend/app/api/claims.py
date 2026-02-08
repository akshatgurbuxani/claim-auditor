"""Claim endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.schemas.claim import ClaimWithVerification
from app.schemas.verification import Verification

router = APIRouter()


@router.get("/", response_model=list[ClaimWithVerification])
def list_claims(
    ticker: Optional[str] = None,
    verdict: Optional[str] = None,
    metric: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """List claims with optional filters."""
    repo = ClaimRepository(db)

    if ticker:
        company = CompanyRepository(db).get_by_ticker(ticker.upper())
        if not company:
            raise HTTPException(404, f"Company {ticker} not found")
        claims = repo.get_for_company(company.id)
    elif verdict:
        claims = repo.get_by_verdict(verdict, limit=limit)
    else:
        claims = repo.get_all(skip=skip, limit=limit)

    # Post-filter by metric if provided
    if metric:
        claims = [c for c in claims if c.metric == metric]

    return [
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


@router.get("/{claim_id}", response_model=ClaimWithVerification)
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    repo = ClaimRepository(db)
    c = repo.get_with_verification(claim_id)
    if not c:
        raise HTTPException(404, "Claim not found")

    return ClaimWithVerification(
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
