"""Dependency injection / factory functions for FastAPI.

Every service is constructed here with its full dependency tree.
"""

from functools import lru_cache

from sqlalchemy.orm import Session

from app.clients.fmp_client import FMPClient
from app.clients.llm_client import LLMClient
from app.config import Settings
from app.engines.claim_extractor import ClaimExtractor
from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
from app.engines.metric_mapper import MetricMapper
from app.engines.verification_engine import VerificationEngine
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.financial_data_repo import FinancialDataRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.repositories.verification_repo import VerificationRepository
from app.services.analysis_service import AnalysisService
from app.services.extraction_service import ExtractionService
from app.services.ingestion_service import IngestionService
from app.services.verification_service import VerificationService


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ── Singletons (stateless, reusable) ────────────────────────────────────

@lru_cache
def get_fmp_client() -> FMPClient:
    return FMPClient(api_key=get_settings().fmp_api_key)


@lru_cache
def get_llm_client() -> LLMClient:
    s = get_settings()
    return LLMClient(api_key=s.anthropic_api_key, model=s.claude_model)


@lru_cache
def get_metric_mapper() -> MetricMapper:
    return MetricMapper()


@lru_cache
def get_claim_extractor() -> ClaimExtractor:
    return ClaimExtractor(get_llm_client())


@lru_cache
def get_discrepancy_analyzer() -> DiscrepancyAnalyzer:
    return DiscrepancyAnalyzer()


# ── Per-request (need a DB session) ─────────────────────────────────────

def get_ingestion_service(db: Session) -> IngestionService:
    return IngestionService(
        fmp_client=get_fmp_client(),
        company_repo=CompanyRepository(db),
        transcript_repo=TranscriptRepository(db),
        financial_repo=FinancialDataRepository(db),
    )


def get_extraction_service(db: Session) -> ExtractionService:
    return ExtractionService(
        claim_extractor=get_claim_extractor(),
        transcript_repo=TranscriptRepository(db),
        claim_repo=ClaimRepository(db),
    )


def get_verification_service(db: Session) -> VerificationService:
    return VerificationService(
        verification_engine=VerificationEngine(
            metric_mapper=get_metric_mapper(),
            financial_repo=FinancialDataRepository(db),
            settings=get_settings(),
        ),
        claim_repo=ClaimRepository(db),
        verification_repo=VerificationRepository(db),
    )


def get_analysis_service(db: Session) -> AnalysisService:
    return AnalysisService(
        discrepancy_analyzer=get_discrepancy_analyzer(),
        company_repo=CompanyRepository(db),
        claim_repo=ClaimRepository(db),
        verification_repo=VerificationRepository(db),
    )
