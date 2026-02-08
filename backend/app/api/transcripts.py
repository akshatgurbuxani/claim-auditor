"""Transcript endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.company_repo import CompanyRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.schemas.transcript import Transcript, TranscriptSummary

router = APIRouter()


@router.get("/", response_model=list[TranscriptSummary])
def list_transcripts(
    ticker: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List transcripts, optionally filtered by ticker."""
    repo = TranscriptRepository(db)

    if ticker:
        company = CompanyRepository(db).get_by_ticker(ticker.upper())
        if not company:
            raise HTTPException(404, f"Company {ticker} not found")
        transcripts = repo.get_for_company(company.id)
    else:
        transcripts = repo.get_all(limit=200)

    return [
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


@router.get("/{transcript_id}", response_model=Transcript)
def get_transcript(transcript_id: int, db: Session = Depends(get_db)):
    repo = TranscriptRepository(db)
    t = repo.get(transcript_id)
    if not t:
        raise HTTPException(404, "Transcript not found")
    return t
