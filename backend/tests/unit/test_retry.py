"""Unit tests for retry logic with exponential backoff."""

import pytest
import time
from unittest.mock import Mock

from app.utils.retry import with_retry


class CustomError(Exception):
    pass


class NonRetryableError(Exception):
    pass


def test_retry_succeeds_on_first_attempt():
    """No retry needed when function succeeds."""
    mock_func = Mock(return_value="success")
    decorated = with_retry(max_attempts=3)(mock_func)

    result = decorated()

    assert result == "success"
    assert mock_func.call_count == 1


def test_retry_succeeds_after_failures():
    """Function succeeds after 2 failures."""
    mock_func = Mock(side_effect=[CustomError(), CustomError(), "success"])
    decorated = with_retry(
        max_attempts=3,
        initial_delay=0.01,  # Fast for testing
        retry_on=(CustomError,),
    )(mock_func)

    result = decorated()

    assert result == "success"
    assert mock_func.call_count == 3


def test_retry_exhausts_max_attempts():
    """Raises after max attempts exceeded."""
    mock_func = Mock(side_effect=CustomError("persistent failure"))
    decorated = with_retry(
        max_attempts=3,
        initial_delay=0.01,
        retry_on=(CustomError,),
    )(mock_func)

    with pytest.raises(CustomError, match="persistent failure"):
        decorated()

    assert mock_func.call_count == 3


def test_retry_reraises_immediately():
    """Non-retryable exceptions raise immediately."""
    mock_func = Mock(side_effect=NonRetryableError("do not retry"))
    decorated = with_retry(
        max_attempts=3,
        retry_on=(CustomError,),
        reraise_on=(NonRetryableError,),
    )(mock_func)

    with pytest.raises(NonRetryableError, match="do not retry"):
        decorated()

    assert mock_func.call_count == 1  # No retries


def test_retry_exponential_backoff():
    """Delays increase exponentially."""
    start = time.time()
    mock_func = Mock(side_effect=[CustomError(), CustomError(), "success"])
    decorated = with_retry(
        max_attempts=3,
        initial_delay=0.1,
        exponential_base=2.0,
        jitter=False,  # Disable jitter for predictable timing
        retry_on=(CustomError,),
    )(mock_func)

    result = decorated()
    elapsed = time.time() - start

    assert result == "success"
    # First retry: 0.1s, second retry: 0.2s → total ~0.3s
    assert 0.25 < elapsed < 0.40, f"Expected ~0.3s, got {elapsed:.2f}s"


def test_retry_with_jitter():
    """Jitter adds randomness to delay."""
    call_count = [0]

    @with_retry(
        max_attempts=3,
        initial_delay=0.05,
        jitter=True,
        retry_on=(CustomError,),
    )
    def flaky_func():
        call_count[0] += 1
        if call_count[0] < 3:
            raise CustomError()
        return "success"

    # We can't easily test jitter without mocking time.sleep,
    # so just verify it doesn't break
    result = flaky_func()
    assert result == "success"
    assert call_count[0] == 3


def test_retry_respects_max_delay():
    """Delay is capped at max_delay."""
    mock_func = Mock(side_effect=[CustomError()] * 10 + ["success"])
    decorated = with_retry(
        max_attempts=11,
        initial_delay=10.0,
        max_delay=0.1,  # Cap at 0.1s
        exponential_base=2.0,
        jitter=False,
        retry_on=(CustomError,),
    )(mock_func)

    start = time.time()
    result = decorated()
    elapsed = time.time() - start

    assert result == "success"
    # 10 retries * 0.1s max_delay = ~1.0s
    assert elapsed < 1.5, f"Expected <1.5s with max_delay, got {elapsed:.2f}s"
