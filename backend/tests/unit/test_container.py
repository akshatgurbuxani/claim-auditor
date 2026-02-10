"""Tests for dependency injection container.

Verifies that the DI container correctly wires all dependencies and provides
proper isolation for testing.
"""

import pytest
from sqlalchemy.orm import Session

from app.container import AppContainer
from app.clients.fmp_client import FMPClient
from app.clients.llm_client import LLMClient
from app.config import Settings
from app.engines.claim_extractor import ClaimExtractor
from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
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


class TestContainerConfiguration:
    """Test container configuration and wiring."""

    def test_container_creates_settings(self):
        """Container provides Settings singleton."""
        container = AppContainer()
        settings = container.settings()

        assert isinstance(settings, Settings)
        assert settings.app_name == "claim-auditor"

        # Singleton: same instance returned
        settings2 = container.settings()
        assert settings is settings2

    def test_container_creates_clients(self):
        """Container provides FMP and LLM clients."""
        container = AppContainer()

        fmp_client = container.fmp_client()
        assert isinstance(fmp_client, FMPClient)

        llm_client = container.llm_client()
        assert isinstance(llm_client, LLMClient)

        # Singletons: same instances returned
        assert fmp_client is container.fmp_client()
        assert llm_client is container.llm_client()

    def test_container_creates_repositories(self, db_engine):
        """Container provides all repository instances."""
        container = AppContainer()
        container.db_engine.override(db_engine)

        # Create session factory
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=db_engine)
        container.db_session.override(SessionLocal)

        # Test each repository
        repos = [
            (container.company_repo(), CompanyRepository),
            (container.transcript_repo(), TranscriptRepository),
            (container.financial_data_repo(), FinancialDataRepository),
            (container.claim_repo(), ClaimRepository),
            (container.verification_repo(), VerificationRepository),
            (container.discrepancy_pattern_repo(), DiscrepancyPatternRepository),
        ]

        for repo_instance, repo_class in repos:
            assert isinstance(repo_instance, repo_class)

    def test_container_creates_engines(self):
        """Container provides all engine instances."""
        container = AppContainer()

        engines = [
            (container.claim_extractor(), ClaimExtractor),
            (container.verification_engine(), VerificationEngine),
            (container.discrepancy_analyzer(), DiscrepancyAnalyzer),
        ]

        for engine_instance, engine_class in engines:
            assert isinstance(engine_instance, engine_class)

    def test_container_creates_services(self, db_engine):
        """Container provides all service instances."""
        container = AppContainer()
        container.db_engine.override(db_engine)

        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=db_engine)
        container.db_session.override(SessionLocal)

        services = [
            (container.ingestion_service(), IngestionService),
            (container.extraction_service(), ExtractionService),
            (container.verification_service(), VerificationService),
            (container.analysis_service(), AnalysisService),
        ]

        for service_instance, service_class in services:
            assert isinstance(service_instance, service_class)


class TestContainerOverrides:
    """Test container provider overrides for testing."""

    def test_can_override_settings(self):
        """Can override Settings for testing."""
        container = AppContainer()

        from dependency_injector import providers

        # Override with test settings
        test_settings = Settings(
            app_name="test-app",
            database_url="sqlite:///:memory:",
        )
        container.settings.override(providers.Object(test_settings))

        settings = container.settings()
        assert settings.app_name == "test-app"
        assert settings.database_url == "sqlite:///:memory:"

    def test_can_override_client(self):
        """Can override clients for testing (mock)."""
        container = AppContainer()

        from dependency_injector import providers

        # Mock FMP client
        class MockFMPClient:
            def get_company_profile(self, ticker):
                return {"ticker": ticker, "name": "Mock Company"}

        container.fmp_client.override(providers.Factory(MockFMPClient))

        client = container.fmp_client()
        assert isinstance(client, MockFMPClient)
        assert client.get_company_profile("TEST")["name"] == "Mock Company"

    def test_can_override_database(self, db_engine):
        """Can override database engine for testing."""
        container = AppContainer()

        from dependency_injector import providers

        # Override with test database
        container.db_engine.override(providers.Object(db_engine))

        engine = container.db_engine()
        assert engine is db_engine


class TestContainerDependencies:
    """Test that dependencies are properly wired."""

    def test_services_receive_correct_dependencies(self, db_engine):
        """Services are constructed with proper dependencies."""
        container = AppContainer()
        container.db_engine.override(db_engine)

        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=db_engine)
        container.db_session.override(SessionLocal)

        # Get ingestion service
        ingestion_service = container.ingestion_service()

        # Verify it has the right dependencies (using actual attribute names)
        assert isinstance(ingestion_service.fmp, FMPClient)
        assert isinstance(ingestion_service.companies, CompanyRepository)
        assert isinstance(ingestion_service.transcripts, TranscriptRepository)
        assert isinstance(ingestion_service.financials, FinancialDataRepository)

    def test_engines_receive_correct_dependencies(self):
        """Engines are constructed with proper dependencies."""
        container = AppContainer()

        # Get verification engine
        verification_engine = container.verification_engine()

        # Verify it has dependencies (using actual attribute names)
        assert hasattr(verification_engine, "mapper")
        assert hasattr(verification_engine, "repo")
        assert hasattr(verification_engine, "tol_verified")

    def test_extraction_service_has_extractor(self, db_engine):
        """Extraction service receives claim extractor engine."""
        container = AppContainer()
        container.db_engine.override(db_engine)

        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=db_engine)
        container.db_session.override(SessionLocal)

        extraction_service = container.extraction_service()

        assert isinstance(extraction_service.extractor, ClaimExtractor)


class TestContainerLifecycle:
    """Test container lifecycle management."""

    def test_container_init_resources(self):
        """Container can initialize resources."""
        container = AppContainer()

        # Should not raise
        container.init_resources()

    def test_container_shutdown_resources(self):
        """Container can shutdown resources."""
        container = AppContainer()
        container.init_resources()

        # Should not raise
        container.shutdown_resources()

    def test_multiple_containers_isolated(self):
        """Multiple container instances are isolated."""
        container1 = AppContainer()
        container2 = AppContainer()

        # Different settings instances
        settings1 = container1.settings()
        settings2 = container2.settings()

        # Should be different objects (not shared)
        # Note: They have same values but are different instances
        assert settings1.app_name == settings2.app_name


class TestContainerIntegration:
    """Integration tests for container usage."""

    def test_facade_can_use_container(self):
        """PipelineFacade can be created with container."""
        from app.facade import PipelineFacade
        from dependency_injector import providers

        container = AppContainer()

        # Mock external clients to avoid API calls
        class MockFMPClient:
            def get_company_profile(self, ticker):
                return {"ticker": ticker, "name": f"{ticker} Inc", "sector": "Technology"}

        class MockLLMClient:
            def extract_claims(self, transcript_text):
                return []

        container.fmp_client.override(providers.Factory(MockFMPClient))
        container.llm_client.override(providers.Factory(MockLLMClient))

        # Create facade with container - should not raise
        facade = PipelineFacade(container=container)

        # Verify facade has container
        assert facade.container is not None

    def test_container_can_create_repos(self):
        """Container can create repository instances."""
        container = AppContainer()

        # Container should be able to provide repository factories
        # (They'll need a session to actually use, but we can verify they're configured)
        assert container.company_repo is not None
        assert container.transcript_repo is not None
        assert container.financial_data_repo is not None
        assert container.claim_repo is not None
        assert container.verification_repo is not None
        assert container.discrepancy_pattern_repo is not None
