"""Agent Rate Limiter & Circuit Breaker — Phase 120-04: Agent Security Middleware.

Per-identity sliding window rate limiter with quota tiers, and a circuit breaker
with loop detection for agent tool calls. Both classes follow the existing
service-level circuit breaker pattern (app.services.circuit_breaker) but are
scoped to agent identity rather than downstream dependency.

Rate limiter enforces:
- Tool calls per minute (sliding window)
- Token consumption per minute
- Concurrent execution slots
- Email sends per hour
- Shell executions per hour (0 = always denied for bots)

Circuit breaker trips on:
- 5 failures within 60 seconds
- 3 consecutive retries of the same tool call key
- >10 calls in 10 seconds to the same endpoint (loop detection)

States: CLOSED (normal) → OPEN (tripped) → HALF_OPEN (cooldown elapsed, test one)

# TODO(production): Replace with Redis-backed store when scaling to
# multiple workers. Key structure:
#   sentinel:confirmations:{session_id} → token_hash (TTL 60s)
#   sentinel:breaker:{agent_id} → state JSON (TTL 5min)
#   sentinel:ratelimit:{identity}:{window} → counter (TTL = window)
"""

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------


class QuotaTier(StrEnum):
    """Rate limit tier applied to an identity."""

    PER_USER = "PER_USER"
    PER_AGENT = "PER_AGENT"
    PER_BOT = "PER_BOT"


class BreakerState(StrEnum):
    """Circuit breaker state machine states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RateLimitResult:
    """Outcome of a rate limit check."""

    allowed: bool
    reason: str
    retry_after_seconds: float | None = None


@dataclass
class BreakerCheckResult:
    """Outcome of a circuit breaker check."""

    allowed: bool
    state: BreakerState
    reason: str


# ---------------------------------------------------------------------------
# Quota definitions per tier
# ---------------------------------------------------------------------------

# Structure: { tier: { resource: (limit, window_seconds) } }
_QUOTA_DEFS: dict[QuotaTier, dict[str, tuple]] = {
    QuotaTier.PER_USER: {
        "tool_calls": (30, 60),  # 30 calls per minute
        "tokens": (50_000, 60),  # 50K tokens per minute
        "concurrent": (3, 0),  # 3 concurrent slots (window unused)
        "email": (20, 3600),  # 20 emails per hour
        "shell": (10, 3600),  # 10 shell executions per hour
    },
    QuotaTier.PER_AGENT: {
        "tool_calls": (60, 60),
        "tokens": (100_000, 60),
        "concurrent": (5, 0),
        "email": (10, 3600),
        "shell": (5, 3600),
    },
    QuotaTier.PER_BOT: {
        "tool_calls": (120, 60),
        "tokens": (200_000, 60),
        "concurrent": (10, 0),
        "email": (50, 3600),
        "shell": (0, 3600),  # 0 = always denied for bots
    },
}


# ---------------------------------------------------------------------------
# AgentRateLimiter
# ---------------------------------------------------------------------------


class AgentRateLimiter:
    """Per-identity sliding window rate limiter for agent tool calls.

    Maintains in-memory timestamp lists per (identity, resource) pair.
    Old entries are pruned on each check to implement sliding windows.
    """

    def __init__(self) -> None:
        # { (identity, resource): [timestamp, ...] }
        self._windows: dict[tuple, list[float]] = {}
        # { (identity, resource): accumulated_count } for tokens (additive)
        self._token_windows: dict[tuple, list[tuple]] = {}
        # { identity: current_count } for concurrent slots
        self._concurrent: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_tool_call(self, identity: str, tier: QuotaTier) -> RateLimitResult:
        """Check whether a tool call is allowed under the tier quota."""
        limit, window = _QUOTA_DEFS[tier]["tool_calls"]
        return self._check_sliding_window(identity, "tool_calls", limit, window)

    def check_tokens(self, identity: str, tier: QuotaTier, token_count: int) -> RateLimitResult:
        """Check whether token consumption is within quota."""
        limit, window = _QUOTA_DEFS[tier]["tokens"]
        return self._check_token_window(identity, limit, window, token_count)

    def check_email(self, identity: str, tier: QuotaTier) -> RateLimitResult:
        """Check whether an email send is allowed under the tier quota."""
        limit, window = _QUOTA_DEFS[tier]["email"]
        return self._check_sliding_window(identity, "email", limit, window)

    def check_shell(self, identity: str, tier: QuotaTier) -> RateLimitResult:
        """Check whether a shell execution is allowed.

        PER_BOT tier has limit=0, so shell is always denied for bots.
        """
        limit, window = _QUOTA_DEFS[tier]["shell"]
        if limit == 0:
            return RateLimitResult(
                allowed=False,
                reason=f"Shell execution denied for tier {tier.value} (limit=0)",
                retry_after_seconds=None,
            )
        return self._check_sliding_window(identity, "shell", limit, window)

    def acquire_concurrent_slot(self, identity: str, tier: QuotaTier) -> RateLimitResult:
        """Try to acquire a concurrent execution slot."""
        limit, _ = _QUOTA_DEFS[tier]["concurrent"]
        current = self._concurrent.get(identity, 0)
        if current >= limit:
            return RateLimitResult(
                allowed=False,
                reason=(f"Concurrent limit reached: {current}/{limit} for tier {tier.value}"),
                retry_after_seconds=1.0,
            )
        self._concurrent[identity] = current + 1
        return RateLimitResult(allowed=True, reason="Slot acquired")

    def release_concurrent_slot(self, identity: str, tier: QuotaTier) -> None:
        """Release a concurrent execution slot."""
        current = self._concurrent.get(identity, 0)
        if current > 0:
            self._concurrent[identity] = current - 1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_sliding_window(
        self,
        identity: str,
        resource: str,
        limit: int,
        window: float,
    ) -> RateLimitResult:
        """Generic sliding window check. Records a timestamp if allowed."""
        now = time.time()
        key = (identity, resource)
        timestamps = self._windows.setdefault(key, [])

        # Prune entries outside the window
        cutoff = now - window
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= limit:
            # Calculate retry_after: time until the oldest entry expires
            oldest = timestamps[0]
            retry_after = oldest + window - now
            return RateLimitResult(
                allowed=False,
                reason=(
                    f"Rate limit exceeded: {len(timestamps)}/{limit} {resource} in {window}s for identity {identity}"
                ),
                retry_after_seconds=max(retry_after, 0.1),
            )

        # Record the call
        timestamps.append(now)
        return RateLimitResult(allowed=True, reason="Within quota")

    def _check_token_window(
        self,
        identity: str,
        limit: int,
        window: float,
        token_count: int,
    ) -> RateLimitResult:
        """Sliding window for token consumption (additive counts)."""
        now = time.time()
        key = (identity, "tokens")
        entries = self._token_windows.setdefault(key, [])

        # Prune entries outside the window
        cutoff = now - window
        entries[:] = [(t, c) for t, c in entries if t > cutoff]

        current_total = sum(c for _, c in entries)
        if current_total + token_count > limit:
            # Calculate retry_after
            if entries:
                oldest_ts = entries[0][0]
                retry_after = oldest_ts + window - now
            else:
                retry_after = window
            return RateLimitResult(
                allowed=False,
                reason=(
                    f"Token limit exceeded: {current_total}+{token_count} > "
                    f"{limit} tokens in {window}s for identity {identity}"
                ),
                retry_after_seconds=max(retry_after, 0.1),
            )

        # Record the consumption
        entries.append((now, token_count))
        return RateLimitResult(allowed=True, reason="Within token quota")


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Per-agent circuit breaker with loop detection.

    Trips on:
    - 5 failures within 60 seconds
    - 3 consecutive retries of the same tool call key
    - >10 calls in 10 seconds to the same endpoint (loop detection)

    Auto-recovers to HALF_OPEN after 300s cooldown. One successful call
    in HALF_OPEN transitions back to CLOSED.
    """

    FAILURE_THRESHOLD = 5
    FAILURE_WINDOW = 60.0  # seconds
    RETRY_THRESHOLD = 3
    LOOP_THRESHOLD = 10
    LOOP_WINDOW = 10.0  # seconds
    COOLDOWN_SECONDS = 300.0  # 5 min auto-recovery

    def __init__(self) -> None:
        # Per-agent state
        self._states: dict[str, BreakerState] = {}
        self._opened_at: dict[str, float] = {}
        self._failure_timestamps: dict[str, list[float]] = {}
        # { agent_id: { tool_call_key: consecutive_retry_count } }
        self._retry_counts: dict[str, dict[str, int]] = {}
        # { (agent_id, tool_call_key): [timestamp, ...] } for loop detection
        self._call_timestamps: dict[tuple, list[float]] = {}
        # Reason for the trip (for diagnostics)
        self._trip_reasons: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, agent_id: str) -> BreakerCheckResult:
        """Check if the agent is allowed to proceed.

        Handles automatic OPEN → HALF_OPEN transition after cooldown.
        """
        state = self._get_state(agent_id)

        if state == BreakerState.CLOSED:
            return BreakerCheckResult(
                allowed=True,
                state=BreakerState.CLOSED,
                reason="Circuit closed — normal operation",
            )

        if state == BreakerState.OPEN:
            # Check if cooldown has elapsed
            opened_at = self._opened_at.get(agent_id, 0.0)
            elapsed = time.time() - opened_at
            if elapsed >= self.COOLDOWN_SECONDS:
                self._states[agent_id] = BreakerState.HALF_OPEN
                logger.info(
                    "agent_breaker.half_open agent_id=%s elapsed=%.1fs",
                    agent_id,
                    elapsed,
                )
                return BreakerCheckResult(
                    allowed=True,
                    state=BreakerState.HALF_OPEN,
                    reason="Cooldown elapsed — testing one request",
                )
            remaining = self.COOLDOWN_SECONDS - elapsed
            trip_reason = self._trip_reasons.get(agent_id, "unknown")
            return BreakerCheckResult(
                allowed=False,
                state=BreakerState.OPEN,
                reason=(f"Circuit open ({trip_reason}). Retry in {remaining:.0f}s"),
            )

        # HALF_OPEN: allow one test request
        return BreakerCheckResult(
            allowed=True,
            state=BreakerState.HALF_OPEN,
            reason="Half-open — probing with one request",
        )

    def record_success(self, agent_id: str) -> None:
        """Record a successful call. HALF_OPEN → CLOSED transition."""
        state = self._get_state(agent_id)
        if state == BreakerState.HALF_OPEN:
            self._states[agent_id] = BreakerState.CLOSED
            self._failure_timestamps.pop(agent_id, None)
            self._retry_counts.pop(agent_id, None)
            self._trip_reasons.pop(agent_id, None)
            logger.info(
                "agent_breaker.closed agent_id=%s (probe succeeded)",
                agent_id,
            )

    def record_failure(self, agent_id: str) -> None:
        """Record a failed call. May trip the breaker."""
        now = time.time()
        state = self._get_state(agent_id)

        # HALF_OPEN probe failed → back to OPEN
        if state == BreakerState.HALF_OPEN:
            self._trip(agent_id, now, "half_open probe failed")
            return

        # Add to failure window
        timestamps = self._failure_timestamps.setdefault(agent_id, [])
        timestamps.append(now)

        # Prune failures outside window
        cutoff = now - self.FAILURE_WINDOW
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self.FAILURE_THRESHOLD:
            self._trip(
                agent_id,
                now,
                f"{len(timestamps)} failures in {self.FAILURE_WINDOW}s",
            )

    def record_retry(self, agent_id: str, tool_call_key: str) -> None:
        """Record a retry of the same tool call. 3 retries → trip."""
        retries = self._retry_counts.setdefault(agent_id, {})
        retries[tool_call_key] = retries.get(tool_call_key, 0) + 1

        if retries[tool_call_key] >= self.RETRY_THRESHOLD:
            self._trip(
                agent_id,
                time.time(),
                f"retry loop: {retries[tool_call_key]} retries of {tool_call_key}",
            )

    def record_call(self, agent_id: str, tool_call_key: str) -> None:
        """Record a call for loop detection. >10 in 10s → trip."""
        now = time.time()
        key = (agent_id, tool_call_key)
        timestamps = self._call_timestamps.setdefault(key, [])
        timestamps.append(now)

        # Prune outside loop window
        cutoff = now - self.LOOP_WINDOW
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) > self.LOOP_THRESHOLD:
            self._trip(
                agent_id,
                now,
                f"loop detected: {len(timestamps)} calls to {tool_call_key} in {self.LOOP_WINDOW}s",
            )

    def force_reset(self, agent_id: str) -> None:
        """Admin manual reset — CLOSED + all counters cleared."""
        self._states[agent_id] = BreakerState.CLOSED
        self._opened_at.pop(agent_id, None)
        self._failure_timestamps.pop(agent_id, None)
        self._retry_counts.pop(agent_id, None)
        self._trip_reasons.pop(agent_id, None)
        # Clean up call timestamps for this agent
        keys_to_remove = [k for k in self._call_timestamps if k[0] == agent_id]
        for k in keys_to_remove:
            del self._call_timestamps[k]
        logger.info(
            "agent_breaker.force_reset agent_id=%s → CLOSED",
            agent_id,
        )

    def get_status(self, agent_id: str) -> dict:
        """Get breaker status for an agent (diagnostics/health endpoint)."""
        state = self._get_state(agent_id)
        return {
            "agent_id": agent_id,
            "state": state.value,
            "recent_failures": len(self._failure_timestamps.get(agent_id, [])),
            "trip_reason": self._trip_reasons.get(agent_id),
            "cooldown_seconds": self.COOLDOWN_SECONDS,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_state(self, agent_id: str) -> BreakerState:
        """Get current state for an agent, defaulting to CLOSED."""
        return self._states.get(agent_id, BreakerState.CLOSED)

    def _trip(self, agent_id: str, now: float, reason: str) -> None:
        """Transition to OPEN state."""
        self._states[agent_id] = BreakerState.OPEN
        self._opened_at[agent_id] = now
        self._trip_reasons[agent_id] = reason
        logger.warning(
            "agent_breaker.open agent_id=%s reason=%s",
            agent_id,
            reason,
        )


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

rate_limiter = AgentRateLimiter()
circuit_breaker = CircuitBreaker()
