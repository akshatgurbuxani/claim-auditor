"""Transcript schemas."""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class TranscriptBase(BaseModel):
    company_id: int
    quarter: int
    year: int
    call_date: date
    full_text: str


class TranscriptCreate(TranscriptBase):
    pass


class Transcript(TranscriptBase):
    id: int

    model_config = {"from_attributes": True}


class TranscriptSummary(BaseModel):
    """Lightweight view without full text."""

    id: int
    company_id: int
    ticker: str
    company_name: str
    quarter: int
    year: int
    call_date: date
    claim_count: int = 0
