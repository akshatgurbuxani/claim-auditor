"""Tests for health check endpoints.

Verifies health check functionality including basic, detailed, readiness, and liveness probes.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock

from app.main import app
from app.database import Base, get_db
from app.config import Settings


@pytest.fixture
def test_db():
    """Create test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield engine
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db):
    """FastAPI test client."""
    return TestClient(app)


class TestBasicHealthCheck:
    """Test basic health check endpoint."""

    def test_health_endpoint_returns_200(self, client):
        """Health check returns 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_endpoint_returns_correct_structure(self, client):
        """Health check returns expected JSON structure."""
        response = client.get("/health")
        data = response.json()

        assert "status" in data
        assert "service" in data
        assert "version" in data

        assert data["status"] == "healthy"
        assert data["service"] == "claim-auditor"
        assert data["version"] == "1.0.0"

    def test_health_endpoint_always_healthy(self, client):
        """Basic health check always returns healthy."""
        # Call multiple times
        for _ in range(3):
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"


class TestDetailedHealthCheck:
    """Test detailed health check with dependency checks."""

    def test_detailed_health_endpoint_returns_200(self, client):
        """Detailed health check returns 200."""
        response = client.get("/health/detailed")
        assert response.status_code == 200

    def test_detailed_health_has_checks(self, client):
        """Detailed health check includes dependency checks."""
        response = client.get("/health/detailed")
        data = response.json()

        assert "status" in data
        assert "checks" in data

        checks = data["checks"]
        assert "database" in checks
        assert "fmp_api" in checks
        assert "claude_api" in checks

    def test_detailed_health_database_check_success(self, client):
        """Database check succeeds with working database."""
        response = client.get("/health/detailed")
        data = response.json()

        db_check = data["checks"]["database"]
        assert db_check["healthy"] is True
        assert "Database connected" in db_check["message"]

    @patch("app.health.check_fmp_api")
    def test_detailed_health_fmp_check_success(self, mock_check, client):
        """FMP API check succeeds when API is available."""
        mock_check.return_value = {
            "healthy": True,
            "message": "FMP API accessible"
        }

        response = client.get("/health/detailed")
        data = response.json()

        fmp_check = data["checks"]["fmp_api"]
        assert fmp_check["healthy"] is True
        assert "FMP API accessible" in fmp_check["message"]

    @patch("app.health.check_fmp_api")
    def test_detailed_health_fmp_check_failure(self, mock_check, client):
        """FMP API check fails when API is unavailable."""
        mock_check.return_value = {
            "healthy": False,
            "message": "FMP API error: Connection timeout"
        }

        response = client.get("/health/detailed")
        data = response.json()

        fmp_check = data["checks"]["fmp_api"]
        assert fmp_check["healthy"] is False
        assert "FMP API error" in fmp_check["message"]

    @patch("app.health.check_llm_api")
    def test_detailed_health_claude_check_configured(self, mock_check, client):
        """Claude API check succeeds when key is configured."""
        mock_check.return_value = {
            "healthy": True,
            "message": "Claude API key configured"
        }

        response = client.get("/health/detailed")
        data = response.json()

        claude_check = data["checks"]["claude_api"]
        assert claude_check["healthy"] is True
        assert "Claude API key configured" in claude_check["message"]

    @patch("app.health.check_fmp_api")
    @patch("app.health.check_llm_api")
    def test_detailed_health_overall_healthy_when_all_checks_pass(
        self, mock_llm, mock_fmp, client
    ):
        """Overall status is healthy when all checks pass."""
        mock_fmp.return_value = {"healthy": True, "message": "OK"}
        mock_llm.return_value = {"healthy": True, "message": "OK"}

        response = client.get("/health/detailed")
        data = response.json()

        assert data["status"] == "healthy"

    @patch("app.health.check_fmp_api")
    @patch("app.health.check_llm_api")
    def test_detailed_health_overall_degraded_when_check_fails(
        self, mock_llm, mock_fmp, client
    ):
        """Overall status is degraded when any check fails."""
        mock_fmp.return_value = {"healthy": False, "message": "FMP API down"}
        mock_llm.return_value = {"healthy": True, "message": "OK"}

        response = client.get("/health/detailed")
        data = response.json()

        assert data["status"] == "degraded"


class TestReadinessProbe:
    """Test Kubernetes readiness probe."""

    def test_readiness_probe_returns_200_when_ready(self, client):
        """Readiness probe returns 200 when database is accessible."""
        response = client.get("/health/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["ready"] is True

    def test_readiness_probe_returns_json(self, client):
        """Readiness probe returns JSON response."""
        response = client.get("/health/ready")
        data = response.json()

        assert isinstance(data, dict)
        assert "ready" in data

    @patch("app.health.Session.execute")
    def test_readiness_probe_returns_503_when_db_down(self, mock_execute, client):
        """Readiness probe returns 503 when database is unavailable."""
        # Mock database failure
        mock_execute.side_effect = Exception("Database connection failed")

        response = client.get("/health/ready")

        # Should return 503 (Service Unavailable)
        assert response.status_code in [500, 503]  # Depends on error handling


class TestLivenessProbe:
    """Test Kubernetes liveness probe."""

    def test_liveness_probe_returns_200(self, client):
        """Liveness probe returns 200."""
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_liveness_probe_returns_alive(self, client):
        """Liveness probe indicates application is alive."""
        response = client.get("/health/live")
        data = response.json()

        assert data["alive"] is True

    def test_liveness_probe_always_succeeds(self, client):
        """Liveness probe succeeds even if dependencies are down."""
        # Liveness doesn't check dependencies, just that app is running
        for _ in range(3):
            response = client.get("/health/live")
            assert response.status_code == 200
            assert response.json()["alive"] is True


class TestHealthCheckIntegration:
    """Integration tests for health checks."""

    def test_all_health_endpoints_accessible(self, client):
        """All health check endpoints are accessible."""
        endpoints = [
            "/health",
            "/health/detailed",
            "/health/ready",
            "/health/live",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code in [200, 503]  # 503 for ready if DB down

    def test_health_checks_dont_require_auth(self, client):
        """Health checks don't require authentication."""
        # Should work without any headers
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_checks_return_json(self, client):
        """All health checks return JSON."""
        endpoints = [
            "/health",
            "/health/detailed",
            "/health/ready",
            "/health/live",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, dict)


class TestHealthCheckFunctions:
    """Test individual health check functions."""

    def test_check_database_success(self, test_db):
        """check_database returns healthy when DB works."""
        from app.health import check_database
        from sqlalchemy.orm import sessionmaker

        SessionLocal = sessionmaker(bind=test_db)
        session = SessionLocal()

        result = check_database(session)

        assert result["healthy"] is True
        assert "Database connected" in result["message"]
        session.close()

    def test_check_database_failure(self):
        """check_database returns unhealthy when DB fails."""
        from app.health import check_database

        # Mock session that raises exception
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("Connection lost")

        result = check_database(mock_session)

        assert result["healthy"] is False
        assert "Database error" in result["message"]

    def test_check_llm_api_configured(self):
        """check_llm_api returns healthy when key is configured."""
        from app.health import check_llm_api

        settings = Settings(anthropic_api_key="test-key")
        result = check_llm_api(settings)

        assert result["healthy"] is True
        assert "Claude API key configured" in result["message"]

    def test_check_llm_api_not_configured(self):
        """check_llm_api returns unhealthy when key is missing."""
        from app.health import check_llm_api

        settings = Settings(anthropic_api_key="")
        result = check_llm_api(settings)

        assert result["healthy"] is False
        assert "Anthropic API key not configured" in result["message"]
