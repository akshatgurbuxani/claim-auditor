"""Dependency Injection Container.

Centralized definition of all application dependencies using dependency-injector.
Makes wiring explicit, simplifies testing, and follows SOLID principles.

Usage::

    from app.container import AppContainer

    container = AppContainer()
    container.init_resources()  # Initialize DB, etc.

    # Get services
    ingestion_svc = container.ingestion_service()
    extraction_svc = container.extraction_service()

    # Or inject into functions
    @inject
    def my_function(ingestion_svc: IngestionService = Provide[AppContainer.ingestion_service]):
        ingestion_svc.ingest_all(...)
"""

from pathlib import Path

from dependency_injector import containers, providers

from app.clients.fmp_client import FMPClient
from app.clients.llm_client import LLMClient
from app.config import Settings
from app.database import Base, build_engine, build_session_factory
from app.engines.claim_extractor import ClaimExtractor
from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
from app.engines.metric_mapper import MetricMapper
from app.engines.verification_engine import VerificationEngine
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.discrepancy_pattern_repo import DiscrepancyPatternRepository
from app.repositories.financial_data_repo import FinancialDataRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.repositories.verification_repo import VerificationRepository
from app.services.analysis_service import AnalysisService
from app.services.extraction_service import ExtractionService
from app.services.ingestion_service import IngestionService
from app.services.verification_service import VerificationService


def _init_database(engine):
    """Initialize database schema."""
    Base.metadata.create_all(bind=engine)
    return engine


def _get_cache_dir(settings: Settings) -> Path:
    """Compute cache directory from database URL."""
    db_path = Path(settings.database_url.replace("sqlite:///", ""))
    cache_dir = db_path.parent / "fmp_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_transcript_dir() -> Path:
    """Get transcript directory."""
    transcript_dir = Path(__file__).resolve().parent.parent / "data" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    return transcript_dir


class AppContainer(containers.DeclarativeContainer):
    """Application Dependency Injection Container.

    Defines all application dependencies in one place:
    - Configuration (Settings)
    - Database (engine, sessions)
    - Repositories (data access)
    - Clients (external APIs)
    - Engines (business logic)
    - Services (orchestration)

    Benefits:
    - Explicit dependencies (no hidden imports)
    - Easy to mock for testing
    - Centralized configuration
    - Follows Dependency Inversion Principle
    """

    # ══════════════════════════════════════════════════════════════════
    # CONFIGURATION
    # ══════════════════════════════════════════════════════════════════

    config = providers.Configuration()

    settings = providers.Singleton(Settings)

    # ══════════════════════════════════════════════════════════════════
    # DATABASE
    # ══════════════════════════════════════════════════════════════════

    db_engine = providers.Singleton(
        build_engine,
        database_url=settings.provided.database_url,
        echo=False,
    )

    db_initialized = providers.Resource(
        _init_database,
        engine=db_engine,
    )

    session_factory = providers.Singleton(
        build_session_factory,
        engine=db_engine,
    )

    # Single scoped session per container instance (Resource pattern)
    # Session is created once when container initializes and closed on shutdown
    db_session = providers.Resource(
        lambda factory: factory(),
        factory=session_factory,
    )

    # ══════════════════════════════════════════════════════════════════
    # REPOSITORIES (Data Access Layer)
    # ══════════════════════════════════════════════════════════════════

    company_repo = providers.Factory(
        CompanyRepository,
        db=db_session,
    )

    transcript_repo = providers.Factory(
        TranscriptRepository,
        db=db_session,
    )

    financial_data_repo = providers.Factory(
        FinancialDataRepository,
        db=db_session,
    )

    claim_repo = providers.Factory(
        ClaimRepository,
        db=db_session,
    )

    verification_repo = providers.Factory(
        VerificationRepository,
        db=db_session,
    )

    discrepancy_pattern_repo = providers.Factory(
        DiscrepancyPatternRepository,
        db=db_session,
    )

    # ══════════════════════════════════════════════════════════════════
    # EXTERNAL CLIENTS (Infrastructure)
    # ══════════════════════════════════════════════════════════════════

    cache_dir = providers.Factory(
        _get_cache_dir,
        settings=settings,
    )

    fmp_client = providers.Singleton(
        FMPClient,
        api_key=settings.provided.fmp_api_key,
        cache_dir=cache_dir,
        retry_max_attempts=settings.provided.retry_max_attempts,
    )

    llm_client = providers.Singleton(
        LLMClient,
        api_key=settings.provided.anthropic_api_key,
        model=settings.provided.claude_model,
        retry_max_attempts=settings.provided.retry_max_attempts,
    )

    # ══════════════════════════════════════════════════════════════════
    # ENGINES (Business Logic Layer)
    # ══════════════════════════════════════════════════════════════════

    claim_extractor = providers.Factory(
        ClaimExtractor,
        llm_client=llm_client,
    )

    metric_mapper = providers.Factory(
        MetricMapper,
    )

    verification_engine = providers.Factory(
        VerificationEngine,
        metric_mapper=metric_mapper,
        financial_repo=financial_data_repo,
        settings=settings,
    )

    discrepancy_analyzer = providers.Factory(
        DiscrepancyAnalyzer,
    )

    # ══════════════════════════════════════════════════════════════════
    # SERVICES (Orchestration Layer)
    # ══════════════════════════════════════════════════════════════════

    transcript_dir = providers.Factory(_get_transcript_dir)

    ingestion_service = providers.Factory(
        IngestionService,
        db=db_session,
        fmp_client=fmp_client,
        company_repo=company_repo,
        transcript_repo=transcript_repo,
        financial_repo=financial_data_repo,
        transcript_dir=transcript_dir,
        settings=settings,
    )

    extraction_service = providers.Factory(
        ExtractionService,
        db=db_session,
        claim_extractor=claim_extractor,
        transcript_repo=transcript_repo,
        claim_repo=claim_repo,
    )

    verification_service = providers.Factory(
        VerificationService,
        db=db_session,
        verification_engine=verification_engine,
        claim_repo=claim_repo,
        verification_repo=verification_repo,
    )

    analysis_service = providers.Factory(
        AnalysisService,
        db=db_session,
        discrepancy_analyzer=discrepancy_analyzer,
        company_repo=company_repo,
        claim_repo=claim_repo,
        verification_repo=verification_repo,
        pattern_repo=discrepancy_pattern_repo,
    )
