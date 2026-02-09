"""Retry utilities with exponential backoff and jitter.

Usage:
    @with_retry(max_attempts=3, retry_on=(httpx.HTTPStatusError,))
    def fetch_data():
        return client.get("/api/data")
"""

import logging
import random
import time
from functools import wraps
from typing import Callable, Tuple, Type

logger = logging.getLogger(__name__)


def with_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_on: Tuple[Type[Exception], ...] = (Exception,),
    reraise_on: Tuple[Type[Exception], ...] = (),
):
    """Retry decorator with exponential backoff and jitter.

    Args:
        max_attempts: Maximum number of attempts (including first try)
        initial_delay: Starting delay in seconds (doubled each retry)
        max_delay: Cap on delay duration
        exponential_base: Multiplier for each retry (typically 2.0)
        jitter: Add randomness to prevent thundering herd
        retry_on: Exception types that trigger retry
        reraise_on: Exception types that abort immediately (no retry)

    Returns:
        Decorated function that retries on failure

    Example:
        >>> @with_retry(
        ...     max_attempts=3,
        ...     retry_on=(httpx.HTTPStatusError,),
        ...     reraise_on=(httpx.HTTPError,)
        ... )
        ... def fetch_profile(ticker):
        ...     return client.get(f"/profile?symbol={ticker}")
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            last_exception = None

            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except reraise_on:
                    # Don't retry these exceptions
                    raise
                except retry_on as exc:
                    last_exception = exc
                    attempt += 1

                    if attempt >= max_attempts:
                        logger.error(
                            "Max retries (%d) exceeded for %s: %s",
                            max_attempts,
                            getattr(func, "__name__", "unknown"),
                            exc,
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        initial_delay * (exponential_base ** (attempt - 1)), max_delay
                    )

                    # Add jitter to prevent thundering herd
                    if jitter:
                        delay *= 0.5 + random.random()

                    logger.warning(
                        "Retry %d/%d for %s after %.2fs: %s",
                        attempt,
                        max_attempts,
                        getattr(func, "__name__", "unknown"),
                        delay,
                        exc,
                    )
                    time.sleep(delay)

            # This should never be reached
            func_name = getattr(func, "__name__", "unknown")
            raise RuntimeError(
                f"Retry logic error in {func_name}: "
                f"exhausted {max_attempts} attempts but no exception raised"
            )

        return wrapper

    return decorator
