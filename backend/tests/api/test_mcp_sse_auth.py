"""
Tests for MCP SSE endpoint authentication and module gating.

Validates:
  - Token-based auth (MCP shared token, JWT Bearer, query param)
  - Demo mode localhost bypass
  - Module gating for mutating tools
  - Role-based access control for mutating tools
  - Real user identity propagation (replaces "mcp_tool")
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest

from app.config.settings import settings
from app.mcp.auth import _validate_mcp_token, extract_mcp_token, require_mcp_auth
from app.mcp.tool_permissions import (
    MCP_TOOL_MIN_ROLE,
    MCP_TOOL_MODULE_REQUIREMENTS,
    MUTATING_TOOLS,
    check_mcp_tool_access,
    extract_site_id_from_args,
)
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    path: str = "/api/mcp/sse",
    method: str = "GET",
    headers: dict | None = None,
    query_string: str = "",
    client_ip: str = "127.0.0.1",
) -> MagicMock:
    """Build a mock FastAPI Request."""

    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode(), v.encode()))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": query_string.encode() if query_string else b"",
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }

    from starlette.requests import Request

    return Request(scope)


def _make_jwt(
    email: str = "user@example.com",
    role: str = "operator",
    user_id: str = "user-1",
    expired: bool = False,
) -> str:
    """Create a valid JWT token for testing."""
    secret = settings.jwt_secret_key or settings.supabase_key or "test-only-jwt-secret"
    delta = timedelta(minutes=-5) if expired else timedelta(minutes=15)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + delta,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def _demo_auth_ctx(ip: str = "127.0.0.1") -> AuthContext:
    return AuthContext(
        user_id="demo-user",
        role=SentinelRole.OPERATOR,
        auth_method="demo_mode",
        source_ip=ip,
        email="demo@sentinel.local",
    )


def _operator_auth_ctx(email: str = "op@example.com") -> AuthContext:
    return AuthContext(
        user_id="user-1",
        role=SentinelRole.OPERATOR,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email=email,
    )


def _admin_auth_ctx(email: str = "admin@example.com") -> AuthContext:
    return AuthContext(
        user_id="admin-1",
        role=SentinelRole.ADMIN,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email=email,
    )


def _auditor_auth_ctx(email: str = "auditor@example.com") -> AuthContext:
    return AuthContext(
        user_id="auditor-1",
        role=SentinelRole.AUDITOR,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email=email,
    )


# ---------------------------------------------------------------------------
# Token extraction tests
# ---------------------------------------------------------------------------


class TestExtractMCPToken:
    def test_from_query_param(self):
        req = _make_request(query_string="token=my-secret-token")
        assert extract_mcp_token(req) == "my-secret-token"

    def test_from_x_mcp_token_header(self):
        req = _make_request(headers={"X-MCP-Token": "header-token"})
        assert extract_mcp_token(req) == "header-token"

    def test_from_bearer_non_jwt(self):
        req = _make_request(headers={"Authorization": "Bearer simple-token-no-dots"})
        assert extract_mcp_token(req) == "simple-token-no-dots"

    def test_skips_jwt_bearer(self):
        jwt = _make_jwt()
        req = _make_request(headers={"Authorization": f"Bearer {jwt}"})
        # JWT has dots — should be skipped by MCP token extractor
        assert extract_mcp_token(req) is None

    def test_no_token(self):
        req = _make_request()
        assert extract_mcp_token(req) is None


# ---------------------------------------------------------------------------
# MCP token validation
# ---------------------------------------------------------------------------


class TestValidateMCPToken:
    def test_valid_token(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_auth_token", "correct-token")
        assert _validate_mcp_token("correct-token") is True

    def test_invalid_token(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_auth_token", "correct-token")
        assert _validate_mcp_token("wrong-token") is False

    def test_no_configured_token(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_auth_token", "")
        assert _validate_mcp_token("any-token") is False


# ---------------------------------------------------------------------------
# require_mcp_auth tests
# ---------------------------------------------------------------------------


class TestRequireMCPAuth:
    @pytest.mark.asyncio
    async def test_rejects_no_credentials_non_demo(self, monkeypatch):
        monkeypatch.setattr(settings, "demo_mode", False)
        monkeypatch.setattr(settings, "mcp_auth_token", "configured-token")

        req = _make_request(client_ip="192.168.1.100")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await require_mcp_auth(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_invalid_mcp_token(self, monkeypatch):
        monkeypatch.setattr(settings, "demo_mode", False)
        monkeypatch.setattr(settings, "mcp_auth_token", "correct-token")

        req = _make_request(query_string="token=wrong-token", client_ip="192.168.1.100")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await require_mcp_auth(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_accepts_valid_mcp_token(self, monkeypatch):
        monkeypatch.setattr(settings, "demo_mode", False)
        monkeypatch.setattr(settings, "mcp_auth_token", "valid-token-123")

        req = _make_request(query_string="token=valid-token-123", client_ip="192.168.1.100")

        ctx = await require_mcp_auth(req)
        assert ctx.user_id == "mcp-client"
        assert ctx.role == SentinelRole.OPERATOR
        assert ctx.auth_method == "mcp_token"

    @pytest.mark.asyncio
    async def test_accepts_jwt_bearer(self, monkeypatch):
        monkeypatch.setattr(settings, "demo_mode", False)
        jwt_token = _make_jwt(email="alice@example.com", role="admin", user_id="alice-1")

        req = _make_request(headers={"Authorization": f"Bearer {jwt_token}"})

        ctx = await require_mcp_auth(req)
        assert ctx.user_id == "alice-1"
        assert ctx.email == "alice@example.com"
        assert ctx.auth_method == "bearer_token"

    @pytest.mark.asyncio
    async def test_demo_mode_localhost_bypass(self, monkeypatch):
        monkeypatch.setattr(settings, "demo_mode", True)
        monkeypatch.setattr(settings, "mcp_auth_token", "")

        req = _make_request(client_ip="127.0.0.1")

        ctx = await require_mcp_auth(req)
        assert ctx.user_id == "demo-user"
        assert ctx.auth_method == "demo_mode"
        assert ctx.role == SentinelRole.OPERATOR

    @pytest.mark.asyncio
    async def test_demo_mode_non_localhost_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "demo_mode", True)
        monkeypatch.setattr(settings, "mcp_auth_token", "")

        req = _make_request(client_ip="192.168.1.100")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await require_mcp_auth(req)
        # Non-localhost with no token configured → 503 (service unavailable)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_503_when_no_token_configured_non_demo(self, monkeypatch):
        monkeypatch.setattr(settings, "demo_mode", False)
        monkeypatch.setattr(settings, "mcp_auth_token", "")

        req = _make_request(client_ip="192.168.1.100")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await require_mcp_auth(req)
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Tool permission tests
# ---------------------------------------------------------------------------


class TestToolPermissions:
    def test_mutating_tools_set_matches_module_requirements(self):
        assert set(MCP_TOOL_MODULE_REQUIREMENTS.keys()) == MUTATING_TOOLS

    def test_all_mutating_tools_have_min_role(self):
        for tool in MUTATING_TOOLS:
            assert tool in MCP_TOOL_MIN_ROLE, f"Tool '{tool}' missing from MCP_TOOL_MIN_ROLE"

    def test_extract_site_from_site_id(self):
        assert extract_site_id_from_args("create_building", {"site_id": "S002"}) == "S002"

    def test_extract_site_from_device_id(self):
        assert extract_site_id_from_args("write_device_point", {"device_id": "S002-CHILLER-B1-001"}) == "S002"

    def test_extract_site_returns_none_when_missing(self):
        assert extract_site_id_from_args("write_device_point", {}) is None


class TestCheckMCPToolAccess:
    def test_operator_can_write_device_point(self):
        ctx = _operator_auth_ctx()
        allowed, reason = check_mcp_tool_access("write_device_point", ctx, None)
        assert allowed is True
        assert reason == ""

    def test_auditor_cannot_write_device_point(self):
        ctx = _auditor_auth_ctx()
        allowed, reason = check_mcp_tool_access("write_device_point", ctx, None)
        assert allowed is False
        assert "Insufficient role" in reason

    def test_operator_cannot_create_site(self):
        ctx = _operator_auth_ctx()
        allowed, reason = check_mcp_tool_access("create_site", ctx, None)
        assert allowed is False
        assert "Insufficient role" in reason

    def test_admin_can_create_site(self):
        ctx = _admin_auth_ctx()
        allowed, reason = check_mcp_tool_access("create_site", ctx, None)
        assert allowed is True

    @patch("app.services.module_registry_service.module_registry")
    def test_module_inactive_blocks_tool(self, mock_registry):
        mock_registry.is_module_active.return_value = False
        ctx = _operator_auth_ctx()
        allowed, reason = check_mcp_tool_access("write_device_point", ctx, "S002")
        assert allowed is False
        assert "not active" in reason

    @patch("app.services.module_registry_service.module_registry")
    def test_module_active_allows_tool(self, mock_registry):
        mock_registry.is_module_active.return_value = True
        ctx = _admin_auth_ctx()
        allowed, reason = check_mcp_tool_access("create_building", ctx, "S002")
        assert allowed is True


# ---------------------------------------------------------------------------
# call_tool integration tests (simbiot_server)
# ---------------------------------------------------------------------------


class TestCallToolAuthGating:
    """Test that SIMBIOTMCPServer.call_tool respects auth context."""

    @pytest.mark.asyncio
    async def test_mutating_tool_without_auth_returns_error(self):
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()
        result = await server.call_tool("write_device_point", device_id="S002-AHU-001", point_name="temp", value=22)
        assert isinstance(result, dict)
        # Control policy gate fires before auth gate — in RECOMMEND mode, writes are blocked
        assert result.get("code") in ("UNAUTHORIZED", "CONTROL_MODE_BLOCKED", "CONTROL_ENGINE_UNAVAILABLE")

    @pytest.mark.asyncio
    async def test_mutating_tool_with_insufficient_role(self):
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()
        ctx = _auditor_auth_ctx()
        result = await server.call_tool(
            "write_device_point",
            device_id="S002-AHU-001",
            point_name="temp",
            value=22,
            _auth_context=ctx,
        )
        assert isinstance(result, dict)
        # Control policy gate fires before role check — in RECOMMEND mode, writes are blocked
        assert result.get("code") in ("FORBIDDEN", "CONTROL_MODE_BLOCKED", "CONTROL_ENGINE_UNAVAILABLE")

    @pytest.mark.asyncio
    async def test_read_only_tool_works_without_auth(self):
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()
        result = await server.call_tool("get_sites")
        # Should not be an auth error — read tools have no gate
        assert isinstance(result, dict)
        assert "error" not in result or result.get("code") not in ("UNAUTHORIZED", "FORBIDDEN")

    @pytest.mark.asyncio
    @patch("app.services.module_registry_service.module_registry")
    async def test_user_identity_propagated(self, mock_registry):
        """Verify that auth context email replaces hardcoded 'mcp_tool'."""
        mock_registry.is_module_active.return_value = True

        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()
        # Use admin to bypass user-level module access check
        ctx = _admin_auth_ctx(email="alice@example.com")

        # Patch the handler to capture the user kwarg.
        # Must include `user` in the signature so inspect.signature() finds it.
        captured = {}
        original_handler = server.tool_handlers.get("write_device_point")

        async def spy_handler(device_id="", point_name="", value=None, priority=8, user="mcp_tool"):
            captured["user"] = user
            captured["device_id"] = device_id
            return {"status": "ok"}

        server.tool_handlers["write_device_point"] = spy_handler

        try:
            # Mock control policy to SUPERVISED so write_device_point is allowed
            with patch("app.services.control_policy_engine.get_control_policy_engine") as mock_policy:
                from app.models.control_policy import ControlMode

                mock_engine = MagicMock()
                mock_engine.get_control_mode.return_value = ControlMode.SUPERVISED
                # evaluate_action is async and must return an envelope-like object
                mock_envelope = MagicMock()
                mock_envelope.policy_check_passed = True
                mock_envelope.requires_approval = False
                mock_envelope.envelope_id = "test-envelope"
                mock_engine.evaluate_action = AsyncMock(return_value=mock_envelope)
                mock_policy.return_value = mock_engine

                await server.call_tool(
                    "write_device_point",
                    device_id="S002-AHU-001",
                    point_name="temp",
                    value=22,
                    _auth_context=ctx,
                )
            assert captured.get("user") == "mcp:alice@example.com"
        finally:
            server.tool_handlers["write_device_point"] = original_handler


# ---------------------------------------------------------------------------
# I2: Host/Origin enforcement in development mode
# ---------------------------------------------------------------------------


class TestHostOriginEnforcement:
    """I2: Dev mode should reject non-localhost Host/Origin headers."""

    def test_localhost_host_allowed(self, monkeypatch):
        """Request with Host: localhost should pass."""
        monkeypatch.setattr(settings, "environment", "development")

        from app.api.mcp_sse import _validate_host_origin

        req = _make_request(headers={"Host": "localhost:9095"})
        # Should not raise
        _validate_host_origin(req)

    def test_127_host_allowed(self, monkeypatch):
        """Request with Host: 127.0.0.1 should pass."""
        monkeypatch.setattr(settings, "environment", "development")

        from app.api.mcp_sse import _validate_host_origin

        req = _make_request(headers={"Host": "127.0.0.1:9095"})
        _validate_host_origin(req)

    def test_external_host_rejected(self, monkeypatch):
        """Request with Host: evil.com in dev mode should be rejected."""
        monkeypatch.setattr(settings, "environment", "development")

        from fastapi import HTTPException

        from app.api.mcp_sse import _validate_host_origin

        req = _make_request(headers={"Host": "evil.com"})
        with pytest.raises(HTTPException) as exc_info:
            _validate_host_origin(req)
        assert exc_info.value.status_code == 403

    def test_external_origin_rejected(self, monkeypatch):
        """Request with Origin: https://evil.com in dev mode should be rejected."""
        monkeypatch.setattr(settings, "environment", "development")

        from fastapi import HTTPException

        from app.api.mcp_sse import _validate_host_origin

        req = _make_request(headers={"Origin": "https://evil.com", "Host": "localhost:9095"})
        with pytest.raises(HTTPException) as exc_info:
            _validate_host_origin(req)
        assert exc_info.value.status_code == 403

    def test_production_skips_host_check(self, monkeypatch):
        """Production mode should not enforce Host/Origin check."""
        monkeypatch.setattr(settings, "environment", "production")

        from app.api.mcp_sse import _validate_host_origin

        req = _make_request(headers={"Host": "evil.com"})
        # Should not raise in production
        _validate_host_origin(req)

    def test_localhost_origin_allowed(self, monkeypatch):
        """Request with Origin: http://localhost:9095 should pass."""
        monkeypatch.setattr(settings, "environment", "development")

        from app.api.mcp_sse import _validate_host_origin

        req = _make_request(headers={"Origin": "http://localhost:9095", "Host": "localhost:9095"})
        _validate_host_origin(req)
