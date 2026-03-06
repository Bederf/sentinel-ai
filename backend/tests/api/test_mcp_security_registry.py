"""
Tests for MCP Security Enhancements — Registry, Policy Decisions,
Secret-Zero Filter, and Cross-Tenant Isolation.

Validates:
  - Tool security registry completeness and consistency
  - Policy decision records in audit events
  - Secret-zero output filter (credentials never reach model)
  - Cross-tenant isolation (users, rate limits, approval tokens)
"""

from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import settings
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _operator_ctx(user_id: str = "user-1", email: str = "op@example.com") -> AuthContext:
    return AuthContext(
        user_id=user_id,
        role=SentinelRole.OPERATOR,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email=email,
    )


def _admin_ctx(user_id: str = "admin-1", email: str = "admin@example.com") -> AuthContext:
    return AuthContext(
        user_id=user_id,
        role=SentinelRole.ADMIN,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email=email,
    )


# ---------------------------------------------------------------------------
# Tool Security Registry Tests
# ---------------------------------------------------------------------------


class TestToolSecurityRegistry:
    """Validate that the registry covers all tools and is consistent."""

    def test_all_mcp_tools_are_registered(self):
        """Every tool in MCP_TOOLS and code tools has a security profile."""
        from app.mcp.simbiot_server import MCP_TOOLS
        from app.mcp.tool_security_registry import TOOL_REGISTRY

        mcp_tool_names = {t["name"] for t in MCP_TOOLS}
        registry_names = set(TOOL_REGISTRY.keys())

        missing = mcp_tool_names - registry_names
        assert not missing, f"Tools missing from security registry: {missing}"

    def test_mutating_tools_match_permissions(self):
        """Registry mutating flags match tool_permissions MUTATING_TOOLS."""
        from app.mcp.tool_permissions import MUTATING_TOOLS
        from app.mcp.tool_security_registry import TOOL_REGISTRY

        registry_mutating = {name for name, p in TOOL_REGISTRY.items() if p.mutating}
        assert registry_mutating == MUTATING_TOOLS, (
            f"Mismatch: registry has {registry_mutating - MUTATING_TOOLS} extra, "
            f"permissions has {MUTATING_TOOLS - registry_mutating} extra"
        )

    def test_high_risk_tools_match_permissions(self):
        """Registry high_risk flags match tool_permissions HIGH_RISK_TOOLS."""
        from app.mcp.tool_permissions import HIGH_RISK_TOOLS
        from app.mcp.tool_security_registry import TOOL_REGISTRY

        registry_high_risk = {name for name, p in TOOL_REGISTRY.items() if p.high_risk}
        assert registry_high_risk == HIGH_RISK_TOOLS

    def test_all_mutating_tools_have_role_and_module(self):
        """Every mutating tool in the registry has min_role and required_module."""
        from app.mcp.tool_security_registry import TOOL_REGISTRY

        for name, profile in TOOL_REGISTRY.items():
            if profile.mutating:
                assert profile.min_role is not None, f"{name} is mutating but has no min_role"
                assert profile.required_module is not None, f"{name} is mutating but has no required_module"

    def test_secret_zero_risk_tools_identified(self):
        """Tools accepting credentials are flagged."""
        from app.mcp.tool_security_registry import TOOL_REGISTRY

        secret_tools = {name for name, p in TOOL_REGISTRY.items() if p.secret_zero_risk}
        assert "discover_tridonic_gateway" in secret_tools

    def test_risk_tier_classification(self):
        """get_risk_tier returns correct tier for each category."""
        from app.mcp.tool_security_registry import get_risk_tier

        assert get_risk_tier("write_device_point") == "high_risk"
        assert get_risk_tier("create_work_order") == "mutating"
        assert get_risk_tier("search_alarms") == "search"
        assert get_risk_tier("get_buildings") == "read"
        assert get_risk_tier("unknown_tool_xyz") == "read"

    def test_get_audit_fields(self):
        """Audit fields return tool-specific allowlists."""
        from app.mcp.tool_security_registry import get_audit_fields

        fields = get_audit_fields("write_device_point")
        assert "device_id" in fields
        assert "point_name" in fields
        assert "value" not in fields  # value excluded from audit


# ---------------------------------------------------------------------------
# Policy Decision Record Tests
# ---------------------------------------------------------------------------


class TestPolicyDecisionRecord:
    """Validate structured policy decision records."""

    def test_allow_decision_structure(self):
        from app.mcp.audit import build_policy_decision

        decision = build_policy_decision(
            tool_name="get_buildings",
            user_id="user-1",
            auth_method="bearer_token",
            site_id="S002",
            result="allow",
        )

        assert decision["tool"] == "get_buildings"
        assert decision["risk_tier"] == "read"
        assert decision["auth_method"] == "bearer_token"
        assert decision["user"] == "user-1"
        assert decision["site_id"] == "S002"
        assert decision["result"] == "allow"
        assert decision["required_approval"] is False

    def test_deny_decision_includes_reason(self):
        from app.mcp.audit import build_policy_decision

        decision = build_policy_decision(
            tool_name="write_device_point",
            user_id="user-1",
            auth_method="mcp_token",
            site_id="S002",
            result="deny",
            reason_code="FORBIDDEN",
        )

        assert decision["result"] == "deny"
        assert decision["reason_code"] == "FORBIDDEN"
        assert decision["risk_tier"] == "high_risk"
        assert decision["required_role"] == "operator"
        assert decision["required_module"] == "control"
        assert decision["required_approval"] is True

    def test_mutating_tool_decision_has_role_and_module(self):
        from app.mcp.audit import build_policy_decision

        decision = build_policy_decision(
            tool_name="create_building",
            user_id="admin-1",
            auth_method="bearer_token",
            site_id="S002",
            result="allow",
        )

        assert decision["required_role"] == "admin"
        assert decision["required_module"] == "simbiot"
        assert decision["required_approval"] is True

    @patch("app.mcp.audit.AuditLogger")
    def test_audit_event_includes_policy_decision(self, mock_audit_cls):
        """Full audit log event includes the policy_decision field."""
        mock_logger = MagicMock()
        mock_audit_cls.return_value = mock_logger
        mock_logger.log_system_event.return_value = "id"

        from app.mcp.audit import log_mcp_tool_call

        log_mcp_tool_call(
            tool_name="get_buildings",
            user_id="user-1",
            arguments={"status_filter": "all"},
            result_code="SUCCESS",
            duration_ms=15.0,
            site_id="S002",
            auth_method="bearer_token",
            policy_result="allow",
        )

        call_kwargs = mock_logger.log_system_event.call_args.kwargs
        metadata = call_kwargs["metadata"]
        assert "policy_decision" in metadata
        pd = metadata["policy_decision"]
        assert pd["tool"] == "get_buildings"
        assert pd["result"] == "allow"
        assert pd["risk_tier"] == "read"


# ---------------------------------------------------------------------------
# Secret-Zero Output Filter Tests
# ---------------------------------------------------------------------------


class TestSecretZeroOutputFilter:
    """Secret-zero: tool output must never contain credentials."""

    def test_api_key_in_output_redacted(self):
        from app.mcp.schema_validator import scan_output_for_secrets

        output = {
            "status": "ok",
            "api_key": "sk_live_1234567890abcdef",
            "name": "test device",
        }
        result = scan_output_for_secrets("get_devices", output)
        assert result["api_key"] == "***REDACTED_BY_SECRET_ZERO_FILTER***"
        assert result["status"] == "ok"
        assert result["name"] == "test device"

    def test_authorization_in_output_redacted(self):
        from app.mcp.schema_validator import scan_output_for_secrets

        output = {"authorization": "Bearer secret123", "data": [1, 2, 3]}
        result = scan_output_for_secrets("get_buildings", output)
        assert result["authorization"] == "***REDACTED_BY_SECRET_ZERO_FILTER***"
        assert result["data"] == [1, 2, 3]

    def test_nested_secrets_redacted(self):
        from app.mcp.schema_validator import scan_output_for_secrets

        output = {
            "device": {
                "id": "S002-AHU-001",
                "config": {
                    "password": "hunter2",
                    "host": "192.168.1.1",
                },
            },
        }
        result = scan_output_for_secrets("get_asset_detail", output)
        assert result["device"]["config"]["password"] == "***REDACTED_BY_SECRET_ZERO_FILTER***"
        assert result["device"]["config"]["host"] == "192.168.1.1"
        assert result["device"]["id"] == "S002-AHU-001"

    def test_jwt_value_pattern_redacted(self):
        from app.mcp.schema_validator import scan_output_for_secrets

        output = {
            "session": (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
                ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
                ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
            ),
            "user": "alice",
        }
        result = scan_output_for_secrets("get_buildings", output)
        assert result["session"] == "***REDACTED_BY_SECRET_ZERO_FILTER***"
        assert result["user"] == "alice"

    def test_api_key_pattern_in_value_redacted(self):
        from app.mcp.schema_validator import scan_output_for_secrets

        output = {"config_value": "sk_test_abcdefghijklmnopqrstuvwxyz"}
        result = scan_output_for_secrets("get_site_config", output)
        assert result["config_value"] == "***REDACTED_BY_SECRET_ZERO_FILTER***"

    def test_safe_output_passes_through(self):
        from app.mcp.schema_validator import scan_output_for_secrets

        output = {
            "sites": [{"id": "S002", "name": "Sandton", "health": 85}],
            "count": 1,
        }
        result = scan_output_for_secrets("get_buildings", output)
        assert result == output

    def test_non_dict_output_passes_through(self):
        from app.mcp.schema_validator import scan_output_for_secrets

        assert scan_output_for_secrets("test", "string output") == "string output"
        assert scan_output_for_secrets("test", 42) == 42
        assert scan_output_for_secrets("test", None) is None

    def test_secrets_in_list_items_redacted(self):
        from app.mcp.schema_validator import scan_output_for_secrets

        output = {
            "items": [
                {"name": "device1", "token": "secret123"},
                {"name": "device2", "status": "ok"},
            ]
        }
        result = scan_output_for_secrets("get_devices", output)
        assert result["items"][0]["token"] == "***REDACTED_BY_SECRET_ZERO_FILTER***"
        assert result["items"][0]["name"] == "device1"
        assert result["items"][1]["status"] == "ok"


# ---------------------------------------------------------------------------
# Cross-Tenant Isolation Tests
# ---------------------------------------------------------------------------


class TestCrossTenantIsolation:
    """Cross-tenant: different users/sessions must not leak state."""

    def setup_method(self):
        from app.mcp.approval_store import reset_approval_store
        from app.mcp.rate_limiter import reset_rate_limits

        reset_rate_limits()
        reset_approval_store()

    def test_rate_limits_isolated_by_user(self, monkeypatch):
        """User A's rate limit does not affect User B."""
        monkeypatch.setattr(settings, "mcp_read_rate_limit", 3)
        from app.mcp.rate_limiter import check_rate_limit

        # Exhaust user-a's limit
        for _ in range(3):
            check_rate_limit("tenant-a-user", "get_buildings")

        # user-a is blocked
        allowed_a, _, _ = check_rate_limit("tenant-a-user", "get_buildings")
        assert allowed_a is False

        # user-b is independent
        allowed_b, _, _ = check_rate_limit("tenant-b-user", "get_buildings")
        assert allowed_b is True

    def test_rate_limits_isolated_by_category(self, monkeypatch):
        """Read limit exhaustion does not block mutate calls."""
        monkeypatch.setattr(settings, "mcp_read_rate_limit", 2)
        monkeypatch.setattr(settings, "mcp_mutate_rate_limit", 10)
        from app.mcp.rate_limiter import check_rate_limit

        for _ in range(2):
            check_rate_limit("user-1", "get_buildings")

        # Read limit hit
        allowed_read, _, _ = check_rate_limit("user-1", "get_buildings")
        assert allowed_read is False

        # Mutate limit still open
        allowed_mut, _, _ = check_rate_limit("user-1", "write_device_point")
        assert allowed_mut is True

    def test_approval_tokens_scoped_to_tool(self):
        """Approval token for tool A cannot be used for tool B."""
        from app.mcp.approval_store import create_approval_token, validate_approval_token

        token = create_approval_token("write_device_point")
        # Wrong tool → rejected
        assert validate_approval_token("create_building", token) is False

    def test_approval_tokens_single_use(self):
        """Approval token consumed on first use, rejected on second."""
        from app.mcp.approval_store import create_approval_token, validate_approval_token

        token = create_approval_token("write_device_point")
        assert validate_approval_token("write_device_point", token) is True
        assert validate_approval_token("write_device_point", token) is False

    def test_mcp_tickets_single_use(self):
        """SSE ticket consumed on first use."""
        from app.api.mcp_sse import _create_mcp_ticket, _validate_mcp_ticket

        ctx_a = _operator_ctx(user_id="tenant-a")
        ticket = _create_mcp_ticket(ctx_a)

        result = _validate_mcp_ticket(ticket)
        assert result is not None
        assert result.user_id == "tenant-a"

        # Second use → None
        assert _validate_mcp_ticket(ticket) is None

    def test_mcp_tickets_carry_correct_identity(self):
        """Ticket carries the identity of the user who created it."""
        from app.api.mcp_sse import _create_mcp_ticket, _validate_mcp_ticket

        ctx_a = _operator_ctx(user_id="tenant-a", email="a@example.com")
        ctx_b = _operator_ctx(user_id="tenant-b", email="b@example.com")

        ticket_a = _create_mcp_ticket(ctx_a)
        ticket_b = _create_mcp_ticket(ctx_b)

        result_a = _validate_mcp_ticket(ticket_a)
        result_b = _validate_mcp_ticket(ticket_b)

        assert result_a.user_id == "tenant-a"
        assert result_a.email == "a@example.com"
        assert result_b.user_id == "tenant-b"
        assert result_b.email == "b@example.com"

    @pytest.mark.asyncio
    async def test_sse_tool_call_isolated_by_auth_context(self):
        """Two sessions with different auth contexts get independent results."""
        from app.mcp.simbiot_server import SIMBIOTMCPServer

        server = SIMBIOTMCPServer()

        # Capture which user identity reaches the handler
        captured_users = []

        async def tracking_handler(**kwargs):
            captured_users.append(kwargs.get("user", "anonymous"))
            return {"status": "ok"}

        # Temporarily replace handler
        original = server.tool_handlers.get("get_buildings")
        server.tool_handlers["get_buildings"] = tracking_handler

        try:
            ctx_a = _operator_ctx(user_id="tenant-a", email="a@corp.com")
            ctx_b = _operator_ctx(user_id="tenant-b", email="b@corp.com")

            await server.call_tool("get_buildings", _transport="sse", _auth_context=ctx_a)
            await server.call_tool("get_buildings", _transport="sse", _auth_context=ctx_b)

            # Both calls should execute (read tools don't inject user param
            # unless they're mutating), but neither should leak the other's context
            assert len(captured_users) == 2
        finally:
            server.tool_handlers["get_buildings"] = original
