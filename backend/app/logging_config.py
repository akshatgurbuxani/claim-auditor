"""Structured logging configuration using structlog.

Provides JSON-formatted logs suitable for production log aggregation systems
(Datadog, ELK, CloudWatch, etc.) while maintaining human-readable format for development.

Usage::

    from app.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("processing_company", ticker="AAPL", claims=23)
    # Output: {"event": "processing_company", "ticker": "AAPL", "claims": 23, "timestamp": "...", ...}
"""

import logging
import sys
from typing import Any

import structlog


def setup_logging(json_logs: bool = False, log_level: str = "INFO") -> None:
    """Configure structured logging for the application.

    Args:
        json_logs: If True, output JSON format. If False, use human-readable format.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    # Configure standard library logging to work with structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Common processors for all environments
    common_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        # Production: JSON format for log aggregation
        processors = common_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Human-readable colored output
        processors = common_processors + [
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """Get a structured logger instance.

    Args:
        name: Logger name, typically __name__ of the module.

    Returns:
        Structured logger instance with bound context.
    """
    return structlog.get_logger(name)
