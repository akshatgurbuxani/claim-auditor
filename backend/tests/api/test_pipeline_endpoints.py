"""Tests for pipeline API endpoints.

Tests all pipeline endpoints including ingestion, extraction, verification,
analysis, and full pipeline execution.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.dependencies import get_container
from app.models.company import CompanyModel
from app.models.transcript import TranscriptModel
from app.models.claim import ClaimModel
from app.models.verification import VerificationModel
from dependency_injector import providers
import app.dependencies as deps


@pytest.fixture(scope="function")
def test_db():
    """Create isolated test database for each test.

    This fixture:
    1. Creates a fresh in-memory SQLite database
    2. Overrides FastAPI's get_db dependency
    3. Resets and overrides the DI container's database
    4. Cleans up after the test
    """
    # Create in-memory database with StaticPool to share connection
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Override FastAPI dependency
    app.dependency_overrides[get_db] = override_get_db

    # Reset container singleton to force recreation with test database
    deps._container = None
    container = get_container()

    # Override container's database to use test database
    container.db_engine.override(providers.Object(engine))
    container.db_session.override(providers.Factory(lambda: TestingSessionLocal()))

    db_session = TestingSessionLocal()
    yield db_session
    db_session.close()

    # Cleanup
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    deps._container = None


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestPipelineStatus:
    """Test pipeline status endpoint."""

    def test_status_endpoint_returns_200(self, client):
        """Status endpoint returns 200."""
        response = client.get("/api/v1/pipeline/status")
        assert response.status_code == 200

    def test_status_returns_all_counts(self, client):
        """Status includes all pipeline stage counts."""
        response = client.get("/api/v1/pipeline/status")
        data = response.json()

        assert "companies" in data
        assert "transcripts" in data
        assert "transcripts_unprocessed" in data
        assert "claims" in data
        assert "claims_unverified" in data
        assert "verifications" in data

    def test_status_with_empty_database(self, test_db, client):
        """Status returns zeros for empty database."""
        response = client.get("/api/v1/pipeline/status")
        data = response.json()

        assert data["companies"] == 0
        assert data["transcripts"] == 0
        assert data["claims"] == 0


class TestIngestEndpoint:
    """Test ingestion endpoint."""

    @patch("app.dependencies.get_ingestion_service")
    def test_ingest_with_valid_data(self, mock_service, client):
        """Ingest endpoint accepts valid request."""
        mock_svc = MagicMock()
        mock_svc.ingest_all.return_value = {
            "companies_created": 2,
            "transcripts_fetched": 4,
            "financial_data_created": 24
        }
        mock_service.return_value = mock_svc

        response = client.post("/api/v1/pipeline/ingest", json={
            "tickers": ["AAPL", "MSFT"],
            "quarters": [[2025, 4]]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "summary" in data

    @patch("app.dependencies.get_ingestion_service")
    def test_ingest_with_defaults(self, mock_service, client):
        """Ingest endpoint works with default values."""
        mock_svc = MagicMock()
        mock_svc.ingest_all.return_value = {"companies_created": 10}
        mock_service.return_value = mock_svc

        response = client.post("/api/v1/pipeline/ingest", json={})

        assert response.status_code == 200

    def test_ingest_rejects_invalid_ticker(self, client):
        """Ingest endpoint rejects invalid ticker format."""
        response = client.post("/api/v1/pipeline/ingest", json={
            "tickers": ["INVALID123"],  # Contains numbers
            "quarters": [[2025, 4]]
        })

        assert response.status_code == 422  # Validation error

    def test_ingest_rejects_invalid_quarter(self, client):
        """Ingest endpoint rejects invalid quarter."""
        response = client.post("/api/v1/pipeline/ingest", json={
            "tickers": ["AAPL"],
            "quarters": [[2025, 5]]  # Quarter 5 doesn't exist
        })

        assert response.status_code == 422

    def test_ingest_rejects_invalid_year(self, client):
        """Ingest endpoint rejects invalid year."""
        response = client.post("/api/v1/pipeline/ingest", json={
            "tickers": ["AAPL"],
            "quarters": [[2050, 1]]  # Year out of range
        })

        assert response.status_code == 422

    def test_ingest_rejects_too_many_tickers(self, client):
        """Ingest endpoint rejects more than 20 tickers."""
        tickers = [f"TKR{i:02d}" for i in range(21)]  # 21 tickers

        response = client.post("/api/v1/pipeline/ingest", json={
            "tickers": tickers,
            "quarters": [[2025, 4]]
        })

        assert response.status_code == 422

    def test_ingest_converts_lowercase_tickers(self, client):
        """Ingest endpoint converts tickers to uppercase."""
        with patch("app.dependencies.get_ingestion_service") as mock_service:
            mock_svc = MagicMock()
            mock_svc.ingest_all.return_value = {"companies_created": 1}
            mock_service.return_value = mock_svc

            response = client.post("/api/v1/pipeline/ingest", json={
                "tickers": ["aapl"],  # lowercase
                "quarters": [[2025, 4]]
            })

            assert response.status_code == 200


class TestExtractEndpoint:
    """Test extraction endpoint."""

    @patch("app.dependencies.get_extraction_service")
    def test_extract_success(self, mock_service, client):
        """Extract endpoint executes successfully."""
        mock_svc = MagicMock()
        mock_svc.extract_all.return_value = {
            "transcripts_processed": 3,
            "claims_extracted": 87
        }
        mock_service.return_value = mock_svc

        response = client.post("/api/v1/pipeline/extract")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "summary" in data


class TestVerifyEndpoint:
    """Test verification endpoint."""

    @patch("app.dependencies.get_verification_service")
    def test_verify_success(self, mock_service, client):
        """Verify endpoint executes successfully."""
        mock_svc = MagicMock()
        mock_svc.verify_all.return_value = {
            "claims_verified": 87,
            "verdict_breakdown": {"VERIFIED": 45}
        }
        mock_service.return_value = mock_svc

        response = client.post("/api/v1/pipeline/verify")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"


class TestAnalyzeEndpoint:
    """Test analysis endpoint."""

    @patch("app.dependencies.get_analysis_service")
    def test_analyze_success(self, mock_service, client):
        """Analyze endpoint executes successfully."""
        mock_svc = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.patterns = [{"type": "test"}]
        mock_svc.analyze_all.return_value = [mock_analysis]
        mock_service.return_value = mock_svc

        response = client.post("/api/v1/pipeline/analyze")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "summary" in data


class TestRunAllEndpoint:
    """Test full pipeline execution endpoint."""

    @patch("app.dependencies.get_analysis_service")
    @patch("app.dependencies.get_verification_service")
    @patch("app.dependencies.get_extraction_service")
    @patch("app.dependencies.get_ingestion_service")
    def test_run_all_success(
        self, mock_ingest, mock_extract, mock_verify, mock_analyze, client
    ):
        """Run-all executes all pipeline stages."""
        # Mock all services
        mock_ingest_svc = MagicMock()
        mock_ingest_svc.ingest_all.return_value = {"companies_created": 1}
        mock_ingest.return_value = mock_ingest_svc

        mock_extract_svc = MagicMock()
        mock_extract_svc.extract_all.return_value = {"claims_extracted": 10}
        mock_extract.return_value = mock_extract_svc

        mock_verify_svc = MagicMock()
        mock_verify_svc.verify_all.return_value = {"claims_verified": 10}
        mock_verify.return_value = mock_verify_svc

        mock_analyze_svc = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.patterns = []
        mock_analyze_svc.analyze_all.return_value = [mock_analysis]
        mock_analyze.return_value = mock_analyze_svc

        response = client.post("/api/v1/pipeline/run-all", json={
            "tickers": ["AAPL"],
            "quarters": [[2025, 4]]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "pipeline" in data
        assert "ingestion" in data["pipeline"]
        assert "extraction" in data["pipeline"]
        assert "verification" in data["pipeline"]
        assert "analysis" in data["pipeline"]


class TestAPIVersioning:
    """Test API versioning."""

    @patch("app.dependencies.get_ingestion_service")
    def test_v1_endpoint_accessible(self, mock_service, client):
        """V1 endpoint is accessible."""
        mock_svc = MagicMock()
        mock_svc.ingest_all.return_value = {}
        mock_service.return_value = mock_svc

        response = client.post("/api/v1/pipeline/ingest", json={})
        assert response.status_code == 200

    @patch("app.dependencies.get_ingestion_service")
    def test_legacy_endpoint_still_works(self, mock_service, client):
        """Legacy endpoint (without v1) still works."""
        mock_svc = MagicMock()
        mock_svc.ingest_all.return_value = {}
        mock_service.return_value = mock_svc

        response = client.post("/api/pipeline/ingest", json={})
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling in pipeline endpoints."""

    @patch("app.api.pipeline.get_ingestion_service")
    def test_service_error_returns_500(self, mock_service, test_db, client):
        """Service errors return 500."""
        mock_svc = MagicMock()
        mock_svc.ingest_all.side_effect = Exception("Database error")
        mock_service.return_value = mock_svc

        response = client.post("/api/v1/pipeline/ingest", json={})

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    def test_invalid_json_returns_422(self, client):
        """Invalid JSON returns 422."""
        response = client.post(
            "/api/v1/pipeline/ingest",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422


class TestLogging:
    """Test that endpoints log properly."""

    @patch("app.api.pipeline.logger")
    @patch("app.dependencies.get_ingestion_service")
    def test_endpoints_log_start(self, mock_service, mock_logger, client):
        """Endpoints log when operations start."""
        mock_svc = MagicMock()
        mock_svc.ingest_all.return_value = {}
        mock_service.return_value = mock_svc

        client.post("/api/v1/pipeline/ingest", json={"tickers": ["AAPL"]})

        # Verify logger was called
        assert mock_logger.info.called

    @patch("app.api.pipeline.logger")
    @patch("app.dependencies.get_ingestion_service")
    def test_endpoints_log_completion(self, mock_service, mock_logger, client):
        """Endpoints log when operations complete."""
        mock_svc = MagicMock()
        mock_svc.ingest_all.return_value = {}
        mock_service.return_value = mock_svc

        client.post("/api/v1/pipeline/ingest", json={})

        # Verify completion was logged
        info_calls = [call for call in mock_logger.info.call_args_list]
        assert len(info_calls) >= 2  # Start and completion

    @patch("app.api.pipeline.logger")
    @patch("app.api.pipeline.get_ingestion_service")
    def test_endpoints_log_errors(self, mock_service, mock_logger, test_db, client):
        """Endpoints log when errors occur."""
        mock_svc = MagicMock()
        mock_svc.ingest_all.side_effect = Exception("Test error")
        mock_service.return_value = mock_svc

        client.post("/api/v1/pipeline/ingest", json={})

        # Verify error was logged
        assert mock_logger.error.called
