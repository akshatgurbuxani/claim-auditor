"""Health check endpoints with dependency checking.

Provides comprehensive health checks for:
- Database connectivity
- External API availability (FMP, Claude)
- Application status
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clients.fmp_client import FMPClient
from app.clients.llm_client import LLMClient
from app.config import Settings
from app.database import get_db
from app.dependencies import get_settings
from app.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


def check_database(db: Session) -> Dict[str, Any]:
    """Check database connectivity.

    Args:
        db: Database session.

    Returns:
        Dict with status and optional error message.
    """
    try:
        # Simple query to verify connection
        db.execute(text("SELECT 1"))
        return {"healthy": True, "message": "Database connected"}
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {"healthy": False, "message": f"Database error: {str(e)}"}


def check_fmp_api(settings: Settings) -> Dict[str, Any]:
    """Check FMP API availability.

    Args:
        settings: Application settings with FMP API key.

    Returns:
        Dict with status and optional error message.
    """
    try:
        if not settings.fmp_api_key:
            return {"healthy": False, "message": "FMP API key not configured"}

        # Simple lightweight check - get profile for a known ticker
        from pathlib import Path
        cache_dir = Path("./data/fmp_cache")
        client = FMPClient(
            api_key=settings.fmp_api_key,
            cache_dir=cache_dir,
            retry_max_attempts=1,  # Fast fail for health check
        )
        # This uses cache if available, so it's fast
        client.get_company_profile("AAPL")
        return {"healthy": True, "message": "FMP API accessible"}
    except Exception as e:
        logger.warning("fmp_health_check_failed", error=str(e))
        return {"healthy": False, "message": f"FMP API error: {str(e)}"}


def check_llm_api(settings: Settings) -> Dict[str, Any]:
    """Check Claude API availability.

    Args:
        settings: Application settings with Claude API key.

    Returns:
        Dict with status and optional error message.
    """
    try:
        if not settings.anthropic_api_key:
            return {"healthy": False, "message": "Anthropic API key not configured"}

        # Note: We don't make actual API call in health check to avoid costs
        # Just verify key is configured
        return {"healthy": True, "message": "Claude API key configured"}
    except Exception as e:
        logger.warning("llm_health_check_failed", error=str(e))
        return {"healthy": False, "message": f"Claude API error: {str(e)}"}


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Basic health check - just app status.

    Returns:
        Simple health status.
    """
    return {"status": "healthy", "service": "claim-auditor", "version": "1.0.0"}


@router.get("/health/detailed")
def detailed_health_check(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Detailed health check with dependency status.

    Checks:
    - Application status
    - Database connectivity
    - FMP API availability
    - Claude API configuration

    Returns:
        Comprehensive health status for all dependencies.
    """

    checks = {
        "database": check_database(db),
        "fmp_api": check_fmp_api(settings),
        "claude_api": check_llm_api(settings),
    }

    all_healthy = all(check["healthy"] for check in checks.values())
    overall_status = "healthy" if all_healthy else "degraded"

    logger.info(
        "health_check_performed",
        status=overall_status,
        database=checks["database"]["healthy"],
        fmp_api=checks["fmp_api"]["healthy"],
        claude_api=checks["claude_api"]["healthy"],
    )

    return {
        "status": overall_status,
        "service": "claim-auditor",
        "version": "1.0.0",
        "checks": checks,
    }


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Kubernetes-style readiness probe.

    Returns 200 if app can serve traffic, 503 otherwise.

    Returns:
        Ready status.
    """
    try:
        db.execute(text("SELECT 1"))
        return {"ready": True}
    except Exception:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail={"ready": False, "reason": "Database unavailable"})


@router.get("/health/live")
def liveness_check() -> Dict[str, Any]:
    """Kubernetes-style liveness probe.

    Returns 200 if app is alive (not deadlocked).

    Returns:
        Live status.
    """
    return {"alive": True}
