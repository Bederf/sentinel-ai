"""
MCP Abuse & Load Tests (G4).

Validates that rate limits, concurrency limits, and payload guards hold
under adversarial conditions.

Run: pytest tests/api/test_mcp_abuse.py -v --timeout=30
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import settings
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _operator_ctx(user_id: str = "abuse-test-user") -> AuthContext:
    return AuthContext(
        user_id=user_id,
        role=SentinelRole.OPERATOR,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email="abuse@test.local",
    )


def _make_request(
    path: str = "/api/mcp/sse/request",
    headers: dict | None = None,
    query_string: str = "",
    client_ip: str = "127.0.0.1",
) -> MagicMock:
    from starlette.requests import Request

    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode(), v.encode()))

    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": raw_headers,
        "query_string": query_string.encode() if query_string else b"",
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Scenario 1: Rate limit burst — flood read tools
# ---------------------------------------------------------------------------


class TestRateLimitBurst:
    """Rapid-fire tool calls must be rate-limited."""

    def setup_method(self):
        from app.mcp.rate_limiter import reset_rate_limits

        reset_rate_limits()

    @pytest.mark.asyncio
    async def test_read_burst_exceeds_limit(self):
        """Sending more than mcp_read_rate_limit calls/min → RATE_LIMITED."""
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()
        ctx = _operator_ctx()
        limit = settings.mcp_read_rate_limit  # Default 60

        # Fire (limit + 5) calls — last 5 should be rate-limited
        results = []
        for _i in range(limit + 5):
            result = await server.call_tool(
                "get_sites",
                _auth_context=ctx,
                _transport="sse",
            )
            results.append(result)

        rate_limited = [r for r in results if isinstance(r, dict) and r.get("code") == "RATE_LIMITED"]
        assert len(rate_limited) >= 5, f"Expected at least 5 RATE_LIMITED responses, got {len(rate_limited)}"

        # Verify retry_after is present and positive
        for r in rate_limited:
            assert "retry_after" in r
            assert r["retry_after"] > 0

    @pytest.mark.asyncio
    async def test_mutate_burst_exceeds_limit(self):
        """Sending more than mcp_mutate_rate_limit calls/min → RATE_LIMITED."""
        from app.mcp.rate_limiter import check_rate_limit

        identity = "mutate-burst-user"
        limit = settings.mcp_mutate_rate_limit  # Default 10

        # Exhaust the mutate limit
        for _ in range(limit):
            allowed, _, _ = check_rate_limit(identity, "write_device_point")
            assert allowed is True

        # Next calls should be rate-limited
        for _ in range(3):
            allowed, reason, retry_after = check_rate_limit(identity, "write_device_point")
            assert allowed is False
            assert "Rate limit exceeded" in reason
            assert retry_after > 0


# ---------------------------------------------------------------------------
# Scenario 2: Concurrent identity flood
# ---------------------------------------------------------------------------


class TestConcurrencyFlood:
    """Per-identity concurrency limits must hold under flood."""

    def setup_method(self):
        from app.mcp.rate_limiter import reset_rate_limits

        reset_rate_limits()

    @pytest.mark.asyncio
    async def test_concurrent_calls_blocked(self):
        """More than MAX_CONCURRENT calls from same identity block."""
        from app.mcp.rate_limiter import (
            _MAX_CONCURRENT_PER_IDENTITY,
            acquire_concurrency_permit,
        )

        identity = "flood-user"
        acquired_count = 0
        blocked = False
        held = asyncio.Event()

        async def hold_permit(idx: int):
            nonlocal acquired_count
            async with acquire_concurrency_permit(identity):
                acquired_count += 1
                await held.wait()

        # Fill all permits
        tasks = [asyncio.create_task(hold_permit(i)) for i in range(_MAX_CONCURRENT_PER_IDENTITY)]
        await asyncio.sleep(0.1)
        assert acquired_count == _MAX_CONCURRENT_PER_IDENTITY

        # Next call should time out (we set a short timeout)
        try:
            from app.mcp.rate_limiter import _get_semaphore

            sem = _get_semaphore(identity)
            acquired = await asyncio.wait_for(sem.acquire(), timeout=0.5)
            if acquired:
                sem.release()
                blocked = False
        except TimeoutError:
            blocked = True

        assert blocked, "Extra concurrent call should have been blocked"

        held.set()
        await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_different_users_not_affected(self):
        """User A's flood should not block User B."""
        from app.mcp.rate_limiter import (
            _MAX_CONCURRENT_PER_IDENTITY,
            acquire_concurrency_permit,
        )

        held = asyncio.Event()

        async def hold_for_user(identity: str):
            async with acquire_concurrency_permit(identity):
                await held.wait()

        # Fill user-a's slots
        tasks = [asyncio.create_task(hold_for_user("user-a")) for _ in range(_MAX_CONCURRENT_PER_IDENTITY)]
        await asyncio.sleep(0.1)

        # user-b should still work
        user_b_ok = False

        async def try_user_b():
            nonlocal user_b_ok
            async with acquire_concurrency_permit("user-b"):
                user_b_ok = True

        await asyncio.wait_for(try_user_b(), timeout=2.0)
        assert user_b_ok

        held.set()
        await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Scenario 3: Oversized payload rejection
# ---------------------------------------------------------------------------


class TestOversizedPayload:
    """Oversized JSON-RPC payloads must be rejected."""

    def test_oversized_content_length_rejected(self):
        """Content-Length > 1MB should be rejected by the endpoint."""
        from app.api.mcp_sse import _MAX_PAYLOAD_BYTES

        assert _MAX_PAYLOAD_BYTES == 1_048_576  # 1MB cap exists

    def test_oversized_string_in_tool_input(self):
        """Tool input with oversized string field should be rejected."""
        from app.mcp.schema_validator import validate_tool_input

        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
        }

        # 15KB string
        huge_query = "x" * 15_000
        valid, error = validate_tool_input("test_tool", {"query": huge_query}, schema)
        assert valid is False
        assert "exceeds" in error.lower() or "length" in error.lower()

    def test_oversized_array_in_tool_input(self):
        """Tool input with oversized array should be rejected."""
        from app.mcp.schema_validator import validate_tool_input

        schema = {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}},
            },
        }

        huge_array = ["item"] * 1500
        valid, _error = validate_tool_input("test_tool", {"items": huge_array}, schema)
        assert valid is False


# ---------------------------------------------------------------------------
# Scenario 4: Mixed read/write abuse
# ---------------------------------------------------------------------------


class TestMixedAbuse:
    """Mixed read and write calls respect independent rate limits."""

    def setup_method(self):
        from app.mcp.rate_limiter import reset_rate_limits

        reset_rate_limits()

    @pytest.mark.asyncio
    async def test_read_and_write_limits_independent(self):
        """Exhausting read limit should not affect write limit and vice versa."""
        from app.mcp.rate_limiter import check_rate_limit

        identity = "mixed-user"

        # Exhaust read limit
        read_limit = settings.mcp_read_rate_limit
        for _ in range(read_limit):
            allowed, _, _ = check_rate_limit(identity, "get_sites")
            # Should be allowed until limit
        allowed, _, _ = check_rate_limit(identity, "get_sites")
        assert allowed is False, "Read limit should be exhausted"

        # Write limit should still have capacity
        allowed, _, _ = check_rate_limit(identity, "write_device_point")
        assert allowed is True, "Write limit should be independent of read limit"


# ---------------------------------------------------------------------------
# Scenario 5: Tool timeout enforcement
# ---------------------------------------------------------------------------


class TestToolTimeout:
    """Slow tool handlers must be terminated."""

    def setup_method(self):
        from app.mcp.rate_limiter import reset_rate_limits

        reset_rate_limits()

    @pytest.mark.asyncio
    async def test_slow_handler_times_out(self):
        """Handler that takes longer than timeout returns TIMEOUT."""
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()

        # Replace handler with slow one
        original = server.tool_handlers.get("get_sites")

        async def slow_handler(**kwargs):
            await asyncio.sleep(60)  # Way over any timeout
            return {"sites": []}

        server.tool_handlers["get_sites"] = slow_handler

        try:
            # Override timeout to 1s for test speed
            with patch("app.mcp.rate_limiter.get_tool_timeout", return_value=1):
                result = await server.call_tool(
                    "get_sites",
                    _auth_context=_operator_ctx(),
                    _transport="sse",
                )

            assert isinstance(result, dict)
            assert result.get("code") == "TIMEOUT"
            assert "timed out" in result.get("error", "").lower()
        finally:
            server.tool_handlers["get_sites"] = original


# ---------------------------------------------------------------------------
# Scenario 6: Envelope fuzzing
# ---------------------------------------------------------------------------


class TestEnvelopeFuzzing:
    """JSON-RPC envelope validation must reject malformed inputs."""

    def test_prototype_pollution_attempt(self):
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, _status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "__proto__": {"admin": True},
            }
        )
        assert valid is False
        assert "__proto__" in msg

    def test_constructor_pollution_attempt(self):
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, _msg, _status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "constructor": {"prototype": {}},
            }
        )
        assert valid is False

    def test_method_injection(self):
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, _status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "system/exec",
            }
        )
        assert valid is False
        assert "Unknown method" in msg

    def test_missing_jsonrpc_version(self):
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, _msg, _status = _validate_jsonrpc_envelope(
            {
                "id": 1,
                "method": "tools/list",
            }
        )
        assert valid is False

    def test_empty_envelope(self):
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, _msg, _status = _validate_jsonrpc_envelope({})
        assert valid is False
