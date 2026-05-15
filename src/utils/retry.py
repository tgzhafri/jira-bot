"""
Retry utilities with exponential backoff and rate-limit handling.

Provides a decorator and helper for resilient HTTP requests that
gracefully handle transient failures and Atlassian API rate limits.
"""

import logging
import time
from functools import wraps
from typing import Callable, Optional, Tuple, Type, Union

logger = logging.getLogger(__name__)

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 60.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0


class RateLimitError(Exception):
    """Raised when API returns 429 Too Many Requests."""

    def __init__(self, retry_after: Optional[float] = None):
        self.retry_after = retry_after
        msg = "Rate limited by API"
        if retry_after:
            msg += f" (retry after {retry_after}s)"
        super().__init__(msg)


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
) -> float:
    """Calculate exponential backoff delay for a given attempt.

    Args:
        attempt: Zero-based attempt number.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        backoff_factor: Multiplier for each subsequent attempt.

    Returns:
        Delay in seconds (capped at max_delay).
    """
    delay = base_delay * (backoff_factor ** attempt)
    return min(delay, max_delay)


def retry_on_failure(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator for retrying a function with exponential backoff.

    Handles rate-limit errors (RateLimitError) by respecting the
    Retry-After value. Other retryable exceptions use exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial backoff delay in seconds.
        max_delay: Maximum backoff delay in seconds.
        backoff_factor: Multiplier per attempt.
        retryable_exceptions: Tuple of exception types to retry on.

    Returns:
        Decorated function with retry behavior.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    # Respect Retry-After header if available
                    delay = e.retry_after if e.retry_after else calculate_backoff_delay(
                        attempt, base_delay, max_delay, backoff_factor
                    )
                    logger.warning(
                        "Rate limited on attempt %d/%d for %s, "
                        "waiting %.1fs",
                        attempt + 1,
                        max_retries + 1,
                        func.__name__,
                        delay,
                    )
                    time.sleep(delay)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    delay = calculate_backoff_delay(
                        attempt, base_delay, max_delay, backoff_factor
                    )
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s. "
                        "Retrying in %.1fs",
                        attempt + 1,
                        max_retries + 1,
                        func.__name__,
                        str(e),
                        delay,
                    )
                    time.sleep(delay)

            raise last_exception

        return wrapper

    return decorator
