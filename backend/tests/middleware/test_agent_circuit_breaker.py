"""Unit tests for Phase 120-04: Agent Rate Limiter & Circuit Breaker.

Tests the per-identity rate limiter (tool calls, tokens, email, shell,
concurrent slots) and the circuit breaker (failure threshold, retry loop,
endpoint loop detection, half-open recovery, force reset).

Uses unittest.mock.patch on time.time to control timestamps for
time-dependent tests (half-open recovery, loop detection).
"""

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("LIGHTWEIGHT_APP", "1")

import time
from unittest.mock import patch

import pytest

from app.middleware.agent_security.circuit_breaker import (
    AgentRateLimiter,
    BreakerState,
    CircuitBreaker,
    QuotaTier,
)

# ---------------------------------------------------------------------------
# Fixtures — fresh instances per test to avoid cross-test contamination
# ---------------------------------------------------------------------------


@pytest.fixture
def limiter() -> AgentRateLimiter:
    """Fresh rate limiter instance per test."""
    return AgentRateLimiter()


@pytest.fixture
def breaker() -> CircuitBreaker:
    """Fresh circuit breaker instance per test."""
    return CircuitBreaker()


# ---------------------------------------------------------------------------
# 1. test_rate_limiter_allows_within_quota
# ---------------------------------------------------------------------------


def test_rate_limiter_allows_within_quota(limiter: AgentRateLimiter):
    """First N calls within the PER_USER limit (30/min) all succeed."""
    for i in range(30):
        result = limiter.check_tool_call("user-1", QuotaTier.PER_USER)
        assert result.allowed, f"Call {i + 1} should be allowed"
        assert result.retry_after_seconds is None


# ---------------------------------------------------------------------------
# 2. test_rate_limiter_blocks_over_quota
# ---------------------------------------------------------------------------


def test_rate_limiter_blocks_over_quota(limiter: AgentRateLimiter):
    """Call 31 times at PER_USER tier — 31st is blocked."""
    for _ in range(30):
        limiter.check_tool_call("user-1", QuotaTier.PER_USER)

    result = limiter.check_tool_call("user-1", QuotaTier.PER_USER)
    assert not result.allowed
    assert "Rate limit exceeded" in result.reason
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds > 0


# ---------------------------------------------------------------------------
# 3. test_rate_limiter_shell_denied_for_bots
# ---------------------------------------------------------------------------


def test_rate_limiter_shell_denied_for_bots(limiter: AgentRateLimiter):
    """PER_BOT tier shell is always denied (limit=0)."""
    result = limiter.check_shell("bot-1", QuotaTier.PER_BOT)
    assert not result.allowed
    assert "limit=0" in result.reason
    assert "PER_BOT" in result.reason


# ---------------------------------------------------------------------------
# 4. test_rate_limiter_email_hourly_limit
# ---------------------------------------------------------------------------


def test_rate_limiter_email_hourly_limit(limiter: AgentRateLimiter):
    """21st email in an hour is blocked for PER_USER (limit=20/hr)."""
    for i in range(20):
        result = limiter.check_email("user-2", QuotaTier.PER_USER)
        assert result.allowed, f"Email {i + 1} should be allowed"

    result = limiter.check_email("user-2", QuotaTier.PER_USER)
    assert not result.allowed
    assert "Rate limit exceeded" in result.reason
    assert "email" in result.reason


# ---------------------------------------------------------------------------
# 5. test_rate_limiter_concurrent_slots
# ---------------------------------------------------------------------------


def test_rate_limiter_concurrent_slots(limiter: AgentRateLimiter):
    """Acquire 4 slots at PER_USER (max 3) — 4th is blocked."""
    for i in range(3):
        result = limiter.acquire_concurrent_slot("user-3", QuotaTier.PER_USER)
        assert result.allowed, f"Slot {i + 1} should be acquired"

    result = limiter.acquire_concurrent_slot("user-3", QuotaTier.PER_USER)
    assert not result.allowed
    assert "Concurrent limit reached" in result.reason
    assert "3/3" in result.reason

    # Release one and try again
    limiter.release_concurrent_slot("user-3", QuotaTier.PER_USER)
    result = limiter.acquire_concurrent_slot("user-3", QuotaTier.PER_USER)
    assert result.allowed


# ---------------------------------------------------------------------------
# 6. test_circuit_breaker_closed_by_default
# ---------------------------------------------------------------------------


def test_circuit_breaker_closed_by_default(breaker: CircuitBreaker):
    """Fresh breaker is CLOSED and allows requests."""
    result = breaker.check("agent-new")
    assert result.allowed
    assert result.state == BreakerState.CLOSED
    assert "closed" in result.reason.lower()


# ---------------------------------------------------------------------------
# 7. test_circuit_breaker_trips_on_failures
# ---------------------------------------------------------------------------


def test_circuit_breaker_trips_on_failures(breaker: CircuitBreaker):
    """5 failures within 60s trips the breaker to OPEN."""
    for i in range(4):
        breaker.record_failure("agent-fail")
        result = breaker.check("agent-fail")
        assert result.allowed, f"Should still be closed after {i + 1} failures"

    # 5th failure → trip
    breaker.record_failure("agent-fail")
    result = breaker.check("agent-fail")
    assert not result.allowed
    assert result.state == BreakerState.OPEN
    assert "failures" in result.reason.lower() or "open" in result.reason.lower()


# ---------------------------------------------------------------------------
# 8. test_circuit_breaker_trips_on_retries
# ---------------------------------------------------------------------------


def test_circuit_breaker_trips_on_retries(breaker: CircuitBreaker):
    """3 retries of the same tool call key trips the breaker."""
    for i in range(2):
        breaker.record_retry("agent-retry", "tool:get_equipment")
        result = breaker.check("agent-retry")
        assert result.allowed, f"Should be closed after {i + 1} retries"

    # 3rd retry → trip
    breaker.record_retry("agent-retry", "tool:get_equipment")
    result = breaker.check("agent-retry")
    assert not result.allowed
    assert result.state == BreakerState.OPEN


# ---------------------------------------------------------------------------
# 9. test_circuit_breaker_trips_on_loop
# ---------------------------------------------------------------------------


def test_circuit_breaker_trips_on_loop(breaker: CircuitBreaker):
    """>10 calls in 10s to the same endpoint trips loop detection."""
    # All calls at the same timestamp to ensure they fall within the 10s window
    frozen_time = time.time()
    with patch("app.middleware.agent_security.circuit_breaker.time") as mock_time:
        mock_time.time.return_value = frozen_time

        # 10 calls is fine (threshold is >10)
        for i in range(10):
            breaker.record_call("agent-loop", "/api/equipment")
            result = breaker.check("agent-loop")
            assert result.allowed, f"Call {i + 1} should be allowed"

        # 11th call → trip
        breaker.record_call("agent-loop", "/api/equipment")
        result = breaker.check("agent-loop")
        assert not result.allowed
        assert result.state == BreakerState.OPEN


# ---------------------------------------------------------------------------
# 10. test_circuit_breaker_half_open_recovery
# ---------------------------------------------------------------------------


def test_circuit_breaker_half_open_recovery(breaker: CircuitBreaker):
    """After cooldown, one success transitions HALF_OPEN → CLOSED."""
    current_time = time.time()

    # Trip the breaker
    for _ in range(5):
        breaker.record_failure("agent-recover")
    result = breaker.check("agent-recover")
    assert result.state == BreakerState.OPEN

    # Fast-forward past cooldown (300s)
    with patch("app.middleware.agent_security.circuit_breaker.time") as mock_time:
        mock_time.time.return_value = current_time + 301

        # Check should transition to HALF_OPEN
        result = breaker.check("agent-recover")
        assert result.allowed
        assert result.state == BreakerState.HALF_OPEN

    # Record success → should go to CLOSED
    breaker.record_success("agent-recover")
    result = breaker.check("agent-recover")
    assert result.allowed
    assert result.state == BreakerState.CLOSED


# ---------------------------------------------------------------------------
# 11. test_circuit_breaker_half_open_failure
# ---------------------------------------------------------------------------


def test_circuit_breaker_half_open_failure(breaker: CircuitBreaker):
    """After cooldown, one failure sends HALF_OPEN back to OPEN."""
    current_time = time.time()

    # Trip the breaker
    for _ in range(5):
        breaker.record_failure("agent-backoff")
    result = breaker.check("agent-backoff")
    assert result.state == BreakerState.OPEN

    # Fast-forward past cooldown
    with patch("app.middleware.agent_security.circuit_breaker.time") as mock_time:
        mock_time.time.return_value = current_time + 301

        # Check → HALF_OPEN
        result = breaker.check("agent-backoff")
        assert result.state == BreakerState.HALF_OPEN

    # Record failure → back to OPEN
    breaker.record_failure("agent-backoff")
    result = breaker.check("agent-backoff")
    assert not result.allowed
    assert result.state == BreakerState.OPEN


# ---------------------------------------------------------------------------
# 12. test_circuit_breaker_force_reset
# ---------------------------------------------------------------------------


def test_circuit_breaker_force_reset(breaker: CircuitBreaker):
    """Admin force_reset returns breaker to CLOSED with cleared counters."""
    # Trip the breaker
    for _ in range(5):
        breaker.record_failure("agent-admin")
    result = breaker.check("agent-admin")
    assert result.state == BreakerState.OPEN

    # Force reset
    breaker.force_reset("agent-admin")

    result = breaker.check("agent-admin")
    assert result.allowed
    assert result.state == BreakerState.CLOSED

    # Verify counters are cleared — status shows 0 recent failures
    status = breaker.get_status("agent-admin")
    assert status["recent_failures"] == 0
    assert status["trip_reason"] is None
