"""Utility functions for API error handling and retries."""

import asyncio
import logging
from typing import TypeVar, Callable, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_on_rate_limit(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs,
) -> T:
    """Retry a function with exponential backoff on rate limit errors.

    Args:
        func: Async or sync function to call
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay on each retry
        *args, **kwargs: Arguments to pass to func

    Returns:
        Result from successful function call

    Raises:
        Last exception if all retries fail
    """
    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            # Handle both async and sync functions
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            # Check if it's a rate limit error
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"Rate limit hit, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    delay *= backoff_factor
                else:
                    logger.error(f"Rate limit persists after {max_retries} retries")
                    raise e
            else:
                # Not a rate limit error, raise immediately
                raise e

    if last_error:
        raise last_error


def sync_retry_on_rate_limit(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    **kwargs,
) -> T:
    """Synchronous version of retry_on_rate_limit.

    Uses time.sleep instead of asyncio.sleep.
    """
    import time

    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"Rate limit hit, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    delay *= backoff_factor
                else:
                    logger.error(f"Rate limit persists after {max_retries} retries")
                    raise e
            else:
                raise e

    if last_error:
        raise last_error
