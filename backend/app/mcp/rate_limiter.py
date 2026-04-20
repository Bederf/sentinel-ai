"""
MCP Tool Rate Limiter, Concurrency Semaphore, and Execution Timeouts (P4).

In-memory sliding window rate limiter keyed by (identity, tool_category).
Per-identity concurrency semaphore limits in-flight tool calls.
Mirrors the pattern from ``startup/middleware.py`` admin rate limiter.
"""

import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from app.config.settings import settings
from app.mcp.tool_permissions import MUTATING_TOOLS

logger = logging.getLogger(__name__)

# Tool category classification
_SEARCH_TOOLS = {"search_alarms", "code_search"}

# Sliding window: (identity, category) -> [timestamps]
_request_log: dict[tuple[str, str], list[float]] = defaultdict(list)

# Category-specific timeout overrides (seconds)
_TOOL_TIMEOUT_OVERRIDES: dict[str, int] = {
    "code_search": 60,
    "code_fetch": 60,
    "discover_tridonic_gateway": 60,
}


def _get_tool_category(tool_name: str) -> str:
    """Classify a tool into a rate-limit category."""
    if tool_name in MUTATING_TOOLS:
        return "mutate"
    if tool_name in _SEARCH_TOOLS:
        return "search"
    return "read"


def _get_category_limit(category: str) -> int:
    """Get the per-minute limit for a category."""
    if category == "mutate":
        return settings.mcp_mutate_rate_limit
    if category == "search":
        return max(settings.mcp_read_rate_limit // 2, 10)  # Half of read limit
    return settings.mcp_read_rate_limit


def _prune_window(timestamps: list[float], window_seconds: float = 60.0) -> list[float]:
    """Remove entries older than the window."""
    cutoff = time.monotonic() - window_seconds
    return [t for t in timestamps if t > cutoff]


def check_rate_limit(
    identity: str,
    tool_name: str,
) -> tuple[bool, str | None, int | None]:
    """Check whether the identity is within rate limits for this tool.

    Args:
        identity: User ID or client identifier.
        tool_name: Name of the MCP tool being called.

    Returns:
        ``(allowed, reason, retry_after_seconds)``
        - ``(True, None, None)`` if allowed
        - ``(False, reason_string, seconds_to_wait)`` if rate-limited
    """
    category = _get_tool_category(tool_name)
    limit = _get_category_limit(category)
    key = (identity, category)

    # Prune old entries
    _request_log[key] = _prune_window(_request_log[key])

    if len(_request_log[key]) >= limit:
        # Calculate retry_after from oldest entry in window
        oldest = _request_log[key][0]
        retry_after = max(1, int(60 - (time.monotonic() - oldest)))
        reason = f"Rate limit exceeded for {category} tools: {limit}/min (identity={identity})"
        logger.warning("MCP rate limit: %s tool=%s", reason, tool_name)
        return False, reason, retry_after

    # Record this request
    _request_log[key].append(time.monotonic())
    return True, None, None


def get_tool_timeout(tool_name: str) -> int:
    """Get the execution timeout for a tool in seconds."""
    return _TOOL_TIMEOUT_OVERRIDES.get(tool_name, settings.mcp_tool_timeout_seconds)


# ---------------------------------------------------------------------------
# Per-identity concurrency semaphore
# ---------------------------------------------------------------------------

_MAX_CONCURRENT_PER_IDENTITY = 5
_identity_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_semaphore(identity: str) -> asyncio.Semaphore:
    """Get or create the concurrency semaphore for an identity."""
    if identity not in _identity_semaphores:
        _identity_semaphores[identity] = asyncio.Semaphore(_MAX_CONCURRENT_PER_IDENTITY)
    return _identity_semaphores[identity]


@asynccontextmanager
async def acquire_concurrency_permit(identity: str):
    """Acquire a concurrency permit for tool execution.

    Usage::

        async with acquire_concurrency_permit(user_id):
            result = await handler(**kwargs)

    Releases the permit in all cases (success, timeout, exception).
    """
    sem = _get_semaphore(identity)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=30.0)
    except TimeoutError:
        raise RuntimeError(f"Concurrency limit reached for identity={identity} (max={_MAX_CONCURRENT_PER_IDENTITY})")
    try:
        yield
    finally:
        sem.release()


def reset_rate_limits() -> None:
    """Clear all rate limit and concurrency state. Used in tests."""
    _request_log.clear()
    _identity_semaphores.clear()
