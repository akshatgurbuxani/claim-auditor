"""Company endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_analysis_service
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.schemas.company import Company, CompanyWithStats
from app.schemas.discrepancy import CompanyAnalysis
from app.utils.scoring import compute_verdict_counts, compute_accuracy, compute_trust_score

router = APIRouter()


@router.get("/", response_model=list[CompanyWithStats])
def list_companies(db: Session = Depends(get_db)):
    """All companies with aggregate verification stats."""
    repo = CompanyRepository(db)
    claim_repo = ClaimRepository(db)
    companies = repo.get_all()

    results: list[CompanyWithStats] = []
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

    return results


@router.get("/{ticker}", response_model=CompanyAnalysis)
def get_company_analysis(ticker: str, db: Session = Depends(get_db)):
    """Full analysis for a single company."""
    company = CompanyRepository(db).get_by_ticker(ticker.upper())
    if not company:
        raise HTTPException(404, f"Company {ticker} not found")
    svc = get_analysis_service(db)
    return svc.analyze_company(company.id)
