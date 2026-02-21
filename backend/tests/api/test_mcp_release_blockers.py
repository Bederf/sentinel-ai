"""
Tests for MCP Release Blockers (Blockers 1–5).

Validates:
  B1: JWT iss/aud validation
  B2: JSON-RPC envelope validation
  B3: SSE error leakage prevention
  B4: Concurrency semaphore per identity
  B5: MCP token expiry and rotation
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta

import pytest

from app.config.settings import settings
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _operator_ctx(user_id: str = "user-1") -> AuthContext:
    return AuthContext(
        user_id=user_id,
        role=SentinelRole.OPERATOR,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email="op@example.com",
    )


# ---------------------------------------------------------------------------
# B1: JWT iss/aud validation
# ---------------------------------------------------------------------------


class TestJWTIssuerAudience:
    """JWT tokens must have correct iss and aud claims."""

    def test_valid_token_passes(self):
        """Token with correct iss and aud passes validation."""
        from app.middleware.auth_middleware import create_jwt_token, validate_jwt_token

        token = create_jwt_token(
            user_id="user-1",
            email="test@example.com",
            role="operator",
            full_name="Test User",
        )
        payload = validate_jwt_token(token, required_token_type="access")
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["iss"] == settings.jwt_issuer
        assert payload["aud"] == settings.jwt_audience

    def test_wrong_issuer_rejected(self):
        """Token with wrong issuer is rejected."""
        import jwt as pyjwt

        secret = settings.jwt_secret_key or settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"
        payload = {
            "sub": "user-1",
            "email": "test@example.com",
            "role": "operator",
            "token_type": "access",
            "jti": str(uuid.uuid4()),
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iss": "evil.attacker",
            "aud": settings.jwt_audience,
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        from app.middleware.auth_middleware import validate_jwt_token

        result = validate_jwt_token(token, required_token_type="access")
        assert result is None

    def test_wrong_audience_rejected(self):
        """Token with wrong audience is rejected."""
        import jwt as pyjwt

        secret = settings.jwt_secret_key or settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"
        payload = {
            "sub": "user-1",
            "email": "test@example.com",
            "role": "operator",
            "token_type": "access",
            "jti": str(uuid.uuid4()),
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iss": settings.jwt_issuer,
            "aud": "wrong.audience",
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        from app.middleware.auth_middleware import validate_jwt_token

        result = validate_jwt_token(token, required_token_type="access")
        assert result is None

    def test_missing_audience_rejected(self):
        """Token missing aud claim is rejected."""
        import jwt as pyjwt

        secret = settings.jwt_secret_key or settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"
        payload = {
            "sub": "user-1",
            "email": "test@example.com",
            "role": "operator",
            "token_type": "access",
            "jti": str(uuid.uuid4()),
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iss": settings.jwt_issuer,
            # No "aud" field
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        from app.middleware.auth_middleware import validate_jwt_token

        result = validate_jwt_token(token, required_token_type="access")
        assert result is None

    def test_expired_token_rejected(self):
        """Expired token is rejected."""
        import jwt as pyjwt

        secret = settings.jwt_secret_key or settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"
        payload = {
            "sub": "user-1",
            "email": "test@example.com",
            "role": "operator",
            "token_type": "access",
            "jti": str(uuid.uuid4()),
            "iat": datetime.utcnow() - timedelta(hours=2),
            "exp": datetime.utcnow() - timedelta(hours=1),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        from app.middleware.auth_middleware import validate_jwt_token

        result = validate_jwt_token(token, required_token_type="access")
        assert result is None

    def test_valid_token_propagates_user_id(self):
        """Valid token propagates user_id into context."""
        from app.middleware.auth_middleware import create_jwt_token, validate_jwt_token

        token = create_jwt_token(
            user_id="user-42",
            email="alice@example.com",
            role="admin",
            full_name="Alice",
        )
        payload = validate_jwt_token(token, required_token_type="access")
        assert payload is not None
        assert payload["sub"] == "user-42"
        assert payload["email"] == "alice@example.com"


# ---------------------------------------------------------------------------
# B2: JSON-RPC envelope validation
# ---------------------------------------------------------------------------


class TestJSONRPCEnvelopeValidation:
    """JSON-RPC 2.0 envelope must be strictly validated."""

    def test_unknown_top_level_field_rejected(self):
        """Unknown fields in envelope get 400."""
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "__proto__": {"polluted": True},
            }
        )
        assert valid is False
        assert status == 400
        assert "__proto__" in msg

    def test_wrong_jsonrpc_version_rejected(self):
        """jsonrpc != '2.0' gets 400."""
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "1.0",
                "id": 1,
                "method": "tools/list",
            }
        )
        assert valid is False
        assert status == 400

    def test_unknown_method_rejected(self):
        """Method not in allowlist gets 400."""
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "system/exec",
            }
        )
        assert valid is False
        assert status == 400
        assert "Unknown method" in msg

    def test_params_not_object_rejected(self):
        """params as array gets 400."""
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": [1, 2, 3],
            }
        )
        assert valid is False
        assert status == 400
        assert "object" in msg

    def test_missing_id_rejected(self):
        """Request without id gets 400 (except notifications)."""
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "method": "tools/list",
            }
        )
        assert valid is False
        assert status == 400
        assert "id" in msg

    def test_notification_without_id_allowed(self):
        """notifications/initialized without id is allowed."""
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )
        assert valid is True

    def test_valid_envelope_passes(self):
        """Well-formed envelope passes."""
        from app.api.mcp_sse import _validate_jsonrpc_envelope

        valid, msg, status = _validate_jsonrpc_envelope(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_buildings"},
            }
        )
        assert valid is True
        assert msg is None


# ---------------------------------------------------------------------------
# B3: SSE error leakage prevention
# ---------------------------------------------------------------------------


class TestSSEErrorLeakage:
    """SSE errors must never expose internals."""

    @pytest.mark.asyncio
    async def test_tool_exception_returns_safe_error(self):
        """Forced exception returns 'internal_error' with request_id."""
        from app.api.mcp_sse import MCPServerSSE

        server = MCPServerSSE()

        # Replace handler with one that raises
        async def boom(**kwargs):
            raise RuntimeError(
                "/app/mcp/simbiot_server.py line 42: db connection failed at postgresql://user:pass@host"
            )

        server.server.tool_handlers["get_buildings"] = boom

        result = await server.handle_tools_call(
            {"name": "get_buildings", "arguments": {}},
            auth_ctx=_operator_ctx(),
        )

        assert result["isError"] is True
        text = result["content"][0]["text"]
        parsed = json.loads(text)

        # Must contain safe error code + request_id
        assert parsed["error"] == "internal_error"
        assert "request_id" in parsed

        # Must NOT contain any internals
        assert "/app/" not in text
        assert "Traceback" not in text
        assert "postgresql" not in text
        assert "pass@" not in text

    @pytest.mark.asyncio
    async def test_handle_request_exception_safe(self):
        """handle_request exception returns safe JSON-RPC error."""
        from app.api.mcp_sse import MCPServerSSE

        server = MCPServerSSE()

        # Patch handle_initialize to raise
        async def boom(params):
            raise ValueError("Bearer sk_live_secret123")

        server.handle_initialize = boom

        result = await server.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )

        assert "error" in result
        assert result["error"]["code"] == -32603
        assert result["error"]["message"] == "Internal error"
        # Must not contain the secret
        assert "sk_live" not in json.dumps(result)
        assert "Bearer" not in json.dumps(result)

    @pytest.mark.asyncio
    async def test_value_error_returns_invalid_request(self):
        """ValueError returns 'invalid_request', not the error message."""
        from app.api.mcp_sse import MCPServerSSE

        server = MCPServerSSE()

        async def bad_input(**kwargs):
            raise ValueError("Expected integer at /app/config/settings.py:42")

        server.server.tool_handlers["get_buildings"] = bad_input

        result = await server.handle_tools_call(
            {"name": "get_buildings", "arguments": {}},
            auth_ctx=_operator_ctx(),
        )

        text = result["content"][0]["text"]
        parsed = json.loads(text)
        assert parsed["error"] == "invalid_request"
        assert "/app/" not in text


# ---------------------------------------------------------------------------
# B4: Concurrency semaphore per identity
# ---------------------------------------------------------------------------


class TestConcurrencySemaphore:
    """Per-identity concurrency limits must be enforced."""

    def setup_method(self):
        from app.mcp.rate_limiter import reset_rate_limits

        reset_rate_limits()

    @pytest.mark.asyncio
    async def test_concurrent_calls_limited(self):
        """Concurrent calls beyond limit must wait."""
        from app.mcp.rate_limiter import _MAX_CONCURRENT_PER_IDENTITY, acquire_concurrency_permit

        acquired = []
        released = asyncio.Event()

        async def hold_permit(identity: str, index: int):
            async with acquire_concurrency_permit(identity):
                acquired.append(index)
                if index < _MAX_CONCURRENT_PER_IDENTITY:
                    # First N tasks hold permits until released
                    await released.wait()

        # Fill all permits
        tasks = []
        for i in range(_MAX_CONCURRENT_PER_IDENTITY):
            tasks.append(asyncio.create_task(hold_permit("user-1", i)))

        # Let them all acquire
        await asyncio.sleep(0.05)
        assert len(acquired) == _MAX_CONCURRENT_PER_IDENTITY

        # Next call should block
        extra_task = asyncio.create_task(hold_permit("user-1", 99))
        await asyncio.sleep(0.05)
        assert 99 not in acquired  # Still waiting

        # Release and let extra through
        released.set()
        await asyncio.gather(*tasks, extra_task)
        assert 99 in acquired

    @pytest.mark.asyncio
    async def test_semaphore_releases_on_exception(self):
        """Semaphore releases even if the handler raises."""
        from app.mcp.rate_limiter import _get_semaphore, acquire_concurrency_permit

        sem = _get_semaphore("user-exc")
        initial_value = sem._value

        with pytest.raises(ValueError):
            async with acquire_concurrency_permit("user-exc"):
                raise ValueError("boom")

        # Permit must be released
        assert sem._value == initial_value

    @pytest.mark.asyncio
    async def test_different_users_independent(self):
        """User A's permits don't block User B."""
        from app.mcp.rate_limiter import _MAX_CONCURRENT_PER_IDENTITY, acquire_concurrency_permit

        hold = asyncio.Event()

        async def fill_user(identity: str):
            async with acquire_concurrency_permit(identity):
                await hold.wait()

        # Fill user-a's permits
        tasks_a = [asyncio.create_task(fill_user("user-a")) for _ in range(_MAX_CONCURRENT_PER_IDENTITY)]
        await asyncio.sleep(0.05)

        # user-b should still be able to acquire
        acquired_b = False

        async def try_b():
            nonlocal acquired_b
            async with acquire_concurrency_permit("user-b"):
                acquired_b = True

        await asyncio.wait_for(try_b(), timeout=1.0)
        assert acquired_b is True

        hold.set()
        await asyncio.gather(*tasks_a)


# ---------------------------------------------------------------------------
# B5: MCP token expiry and rotation
# ---------------------------------------------------------------------------


class TestMCPTokenExpiry:
    """MCP shared tokens must support expiry and rotation."""

    def setup_method(self):
        from app.mcp.auth import _mcp_token_first_seen

        _mcp_token_first_seen.clear()

    def test_valid_current_token(self, monkeypatch):
        """Current token passes validation."""
        monkeypatch.setattr(settings, "mcp_auth_token", "current-secret-token")
        monkeypatch.setattr(settings, "mcp_auth_token_max_age_hours", 0)  # No expiry

        from app.mcp.auth import _validate_mcp_token

        assert _validate_mcp_token("current-secret-token") is True

    def test_wrong_token_rejected(self, monkeypatch):
        """Wrong token is rejected."""
        monkeypatch.setattr(settings, "mcp_auth_token", "correct-token")

        from app.mcp.auth import _validate_mcp_token

        assert _validate_mcp_token("wrong-token") is False

    def test_previous_token_accepted_during_rotation(self, monkeypatch):
        """Previous token accepted during rotation grace period."""
        monkeypatch.setattr(settings, "mcp_auth_token", "new-token")
        monkeypatch.setattr(settings, "mcp_auth_token_previous", "old-token")
        monkeypatch.setattr(settings, "mcp_auth_token_max_age_hours", 0)

        from app.mcp.auth import _validate_mcp_token

        assert _validate_mcp_token("old-token") is True

    def test_expired_token_rejected(self, monkeypatch):
        """Token exceeding max age is rejected."""
        monkeypatch.setattr(settings, "mcp_auth_token", "test-token")
        monkeypatch.setattr(settings, "mcp_auth_token_max_age_hours", 1)  # 1 hour

        from app.mcp.auth import _mcp_token_first_seen, _validate_mcp_token

        # Simulate token first seen 2 hours ago
        _mcp_token_first_seen["test-token"] = time.monotonic() - 7200

        assert _validate_mcp_token("test-token") is False

    def test_fresh_token_accepted(self, monkeypatch):
        """Token within max age is accepted."""
        monkeypatch.setattr(settings, "mcp_auth_token", "fresh-token")
        monkeypatch.setattr(settings, "mcp_auth_token_max_age_hours", 24)

        from app.mcp.auth import _validate_mcp_token

        assert _validate_mcp_token("fresh-token") is True
