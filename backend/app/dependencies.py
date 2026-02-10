"""Dependency injection helpers for FastAPI.

This module provides FastAPI-compatible dependency functions that delegate
to the centralized DI container. This consolidates both DI patterns:
- FastAPI's Depends() system (for API routes)
- dependency-injector Container (for services, CLI, tests)

All service construction is now handled by app.container.AppContainer.
"""

from functools import lru_cache

from dependency_injector import providers
from sqlalchemy.orm import Session

from app.clients.fmp_client import FMPClient
from app.clients.llm_client import LLMClient
from app.config import Settings
from app.container import AppContainer
from app.services.analysis_service import AnalysisService
from app.services.extraction_service import ExtractionService
from app.services.ingestion_service import IngestionService
from app.services.verification_service import VerificationService


# ══════════════════════════════════════════════════════════════════════════
# CONTAINER SINGLETON
# ══════════════════════════════════════════════════════════════════════════

_container: AppContainer | None = None


def get_container() -> AppContainer:
    """Get or create the application container singleton."""
    global _container
    if _container is None:
        _container = AppContainer()
        _container.init_resources()  # Initialize DB schema
    return _container


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION & INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════════

@lru_cache
def get_settings() -> Settings:
    """Get application settings (cached singleton)."""
    return get_container().settings()


def get_fmp_client() -> FMPClient:
    """Get FMP API client (singleton)."""
    return get_container().fmp_client()


def get_llm_client() -> LLMClient:
    """Get LLM client (singleton)."""
    return get_container().llm_client()


# ══════════════════════════════════════════════════════════════════════════
# SERVICES (Per-Request)
# ══════════════════════════════════════════════════════════════════════════

def get_ingestion_service(db: Session) -> IngestionService:
    """Get ingestion service with current DB session."""
    container = get_container()
    # Override session for this request - use Object provider to pass the actual session
    with container.db_session.override(providers.Object(db)):
        return container.ingestion_service()


def get_extraction_service(db: Session) -> ExtractionService:
    """Get extraction service with current DB session."""
    container = get_container()
    with container.db_session.override(providers.Object(db)):
        return container.extraction_service()


def get_verification_service(db: Session) -> VerificationService:
    """Get verification service with current DB session."""
    container = get_container()
    with container.db_session.override(providers.Object(db)):
        return container.verification_service()


def get_analysis_service(db: Session) -> AnalysisService:
    """Get analysis service with current DB session."""
    container = get_container()
    with container.db_session.override(providers.Object(db)):
        return container.analysis_service()
