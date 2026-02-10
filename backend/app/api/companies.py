"""Company endpoints — list companies and get company analysis.

Provides API endpoints for:
- Listing all companies with verification statistics
- Getting detailed analysis for a specific company

All endpoints use structured logging and proper validation.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_analysis_service
from app.logging_config import get_logger
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.schemas.company import CompanyWithStats
from app.schemas.discrepancy import CompanyAnalysis
from app.utils.scoring import compute_verdict_counts, compute_accuracy, compute_trust_score

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=List[CompanyWithStats])
def list_companies(db: Session = Depends(get_db)) -> List[CompanyWithStats]:
    """List all companies with aggregate verification statistics.

    Computes verification stats, accuracy rate, and trust score for each company
    based on all claims and their verification results.

    Args:
        db: Database session.

    Returns:
        List of companies with verification statistics.

    Raises:
        HTTPException: If database query fails.
    """
    logger.info("companies_list_requested")

    try:
        repo = CompanyRepository(db)
        claim_repo = ClaimRepository(db)
        companies = repo.get_all()

        results: List[CompanyWithStats] = []
        for c in companies:
            claims = claim_repo.get_for_company(c.id)
            v = compute_verdict_counts(claims)
            accuracy = compute_accuracy(v)
            trust = compute_trust_score(v)

            results.append(CompanyWithStats(
                id=c.id,
                ticker=c.ticker,
                name=c.name,
                sector=c.sector,
                total_claims=len(claims),
                verified_count=v["verified"],
                approximately_correct_count=v["approximately_correct"],
                misleading_count=v["misleading"],
                incorrect_count=v["incorrect"],
                unverifiable_count=v["unverifiable"],
                accuracy_rate=round(accuracy, 4),
                trust_score=round(trust, 1),
            ))

        logger.info("companies_list_completed", count=len(results))
        return results

    except Exception as e:
        logger.error("companies_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list companies: {str(e)}")


@router.get("/{ticker}", response_model=CompanyAnalysis)
def get_company_analysis(ticker: str, db: Session = Depends(get_db)) -> CompanyAnalysis:
    """Get comprehensive analysis for a specific company.

    Includes all verification statistics, detected discrepancy patterns,
    and detailed analysis of claims and their verification results.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL').
        db: Database session.

    Returns:
        Comprehensive company analysis with patterns.

    Raises:
        HTTPException: If company not found or analysis fails.
    """
    ticker = ticker.upper()
    logger.info("company_analysis_requested", ticker=ticker)

    try:
        company = CompanyRepository(db).get_by_ticker(ticker)
        if not company:
            logger.warning("company_not_found", ticker=ticker)
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

        svc = get_analysis_service(db)
        analysis = svc.analyze_company(company.id)

        logger.info(
            "company_analysis_completed",
            ticker=ticker,
            patterns=len(analysis.patterns),
        )
        return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error("company_analysis_failed", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to analyze company: {str(e)}"
        )
