"""Lightweight async circuit breaker for downstream service protection.

Prevents cascading failures when downstream dependencies (Supabase, ML models,
external services) are unhealthy. Each dependency gets its own breaker instance.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Dependency unhealthy, requests fail fast with fallback
- HALF_OPEN: Testing recovery, allow one request through

Transitions:
- CLOSED -> OPEN: failure_count >= failure_threshold within window
- OPEN -> HALF_OPEN: after recovery_timeout_seconds
- HALF_OPEN -> CLOSED: probe request succeeds
- HALF_OPEN -> OPEN: probe request fails

Usage:
    breaker = CircuitBreaker("supabase_decisions", failure_threshold=5)

    async def save_decision(data):
        if not breaker.allow_request():
            logger.warning("Circuit open for supabase_decisions, buffering locally")
            return fallback_value
        try:
            result = await repo.record_decision(data)
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-dependency circuit breaker with async support."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        failure_window_seconds: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.failure_window_seconds = failure_window_seconds

        self._state = CircuitState.CLOSED
        self._failure_timestamps: list[float] = []
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0
        self._success_count: int = 0
        self._total_failures: int = 0
        self._total_short_circuits: int = 0

    @property
    def state(self) -> CircuitState:
        """Current state, with automatic OPEN -> HALF_OPEN transition."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    f"[CIRCUIT] {self.name}: OPEN -> HALF_OPEN "
                    f"(recovery timeout {self.recovery_timeout_seconds}s elapsed)"
                )
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True  # Allow probe request
        # OPEN: fail fast
        self._total_short_circuits += 1
        return False

    def record_success(self) -> None:
        """Record a successful call. Closes circuit if half-open."""
        self._success_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_timestamps.clear()
            logger.info(f"[CIRCUIT] {self.name}: HALF_OPEN -> CLOSED (probe succeeded)")

    def record_failure(self) -> None:
        """Record a failed call. Opens circuit if threshold exceeded."""
        now = time.monotonic()
        self._total_failures += 1
        self._last_failure_time = now

        if self._state == CircuitState.HALF_OPEN:
            # Probe failed, back to open
            self._state = CircuitState.OPEN
            self._opened_at = now
            logger.warning(f"[CIRCUIT] {self.name}: HALF_OPEN -> OPEN (probe failed)")
            return

        # Add to failure window
        self._failure_timestamps.append(now)

        # Prune old failures outside window
        cutoff = now - self.failure_window_seconds
        self._failure_timestamps = [t for t in self._failure_timestamps if t > cutoff]

        if len(self._failure_timestamps) >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = now
            logger.warning(
                f"[CIRCUIT] {self.name}: CLOSED -> OPEN "
                f"({len(self._failure_timestamps)} failures in {self.failure_window_seconds}s)"
            )

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status for health endpoint."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_threshold": self.failure_threshold,
            "recent_failures": len(self._failure_timestamps),
            "total_failures": self._total_failures,
            "total_short_circuits": self._total_short_circuits,
            "recovery_timeout_s": self.recovery_timeout_seconds,
        }


async def call_with_breaker(
    breaker: CircuitBreaker,
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    fallback: T | None = None,
    timeout_seconds: float = 5.0,
    **kwargs: Any,
) -> T:
    """Execute an async function with circuit breaker and timeout protection.

    Args:
        breaker: CircuitBreaker instance for this dependency
        fn: Async function to call
        *args: Positional args for fn
        fallback: Value to return when circuit is open or call fails
        timeout_seconds: Max seconds to wait for fn
        **kwargs: Keyword args for fn

    Returns:
        Result of fn, or fallback if circuit open / call failed / timeout
    """
    if not breaker.allow_request():
        logger.debug(f"[CIRCUIT] {breaker.name}: short-circuited, returning fallback")
        return fallback  # type: ignore[return-value]

    try:
        result = await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout_seconds)
        breaker.record_success()
        return result
    except TimeoutError:
        breaker.record_failure()
        logger.warning(f"[CIRCUIT] {breaker.name}: timeout after {timeout_seconds}s")
        return fallback  # type: ignore[return-value]
    except Exception as e:
        breaker.record_failure()
        logger.warning(f"[CIRCUIT] {breaker.name}: call failed: {e}")
        return fallback  # type: ignore[return-value]


# =============================================================================
# Global breaker registry — one breaker per downstream dependency
# =============================================================================

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout_seconds: float = 30.0,
) -> CircuitBreaker:
    """Get or create a named circuit breaker."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=recovery_timeout_seconds,
        )
    return _breakers[name]


def get_all_breaker_statuses() -> list[dict[str, Any]]:
    """Get status of all registered circuit breakers (for /api/health)."""
    return [b.get_status() for b in _breakers.values()]
