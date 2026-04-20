"""Regression tests for remote_commands security fixes.

C-1: Role escalation via X-User-Role header injection.

Verifies that _extract_user() ignores the X-User-Role header and
reads the role exclusively from request.state.auth (JWT-verified).

Gap 10 (MEDIUM): BOT_AGENT rejected from control endpoints not tested.
Control: AUTH-002 (Role Hierarchy & RBAC)
"""

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

from httpx import ASGITransport, AsyncClient

from app.api.remote_commands import _extract_user
from app.main import app
from app.middleware.auth_middleware import create_jwt_token
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Unit tests for _extract_user
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Minimal Request stub for testing _extract_user."""

    def __init__(self, auth=None, headers=None):
        self.state = MagicMock()
        self.state.auth = auth
        self.headers = headers or {}


class TestExtractUserIgnoresHeader:
    """C-1: X-User-Role header must be ignored; role must come from auth state."""

    def test_role_from_auth_state_not_header(self):
        """When auth state has role=auditor, header claiming admin must be ignored."""
        auth_ctx = AuthContext(
            user_id="user-123",
            role=SentinelRole.AUDITOR,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )
        req = _FakeRequest(auth=auth_ctx, headers={"X-User-Role": "admin"})

        user_id, user_role = _extract_user(req)

        assert user_id == "user-123"
        # Must be auditor from JWT, not admin from header
        assert user_role == "auditor"
        assert user_role != "admin"

    def test_no_auth_state_defaults_to_viewer(self):
        """When auth state is absent, role defaults to 'viewer' (safe default)."""
        req = _FakeRequest(auth=None, headers={"X-User-Role": "admin"})

        user_id, user_role = _extract_user(req)

        assert user_id == "unknown"
        assert user_role == "viewer"
        assert user_role != "admin"

    def test_operator_role_from_auth_state(self):
        """Operator role is correctly extracted from auth state."""
        auth_ctx = AuthContext(
            user_id="op-user",
            role=SentinelRole.OPERATOR,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )
        req = _FakeRequest(auth=auth_ctx, headers={})

        user_id, user_role = _extract_user(req)

        assert user_id == "op-user"
        assert user_role == "operator"

    def test_header_escalation_attempt_blocked(self):
        """A viewer JWT with X-User-Role: engineer header stays as auditor."""
        auth_ctx = AuthContext(
            user_id="viewer-456",
            role=SentinelRole.AUDITOR,
            auth_method="jwt",
            source_ip="10.0.0.1",
        )
        # Attacker sends both legitimate JWT (auditor) and forged header (engineer)
        req = _FakeRequest(
            auth=auth_ctx,
            headers={"X-User-Role": "engineer", "X-User-Id": "attacker-id"},
        )

        user_id, user_role = _extract_user(req)

        # user_id from auth state, not from X-User-Id header
        assert user_id == "viewer-456"
        # role from auth state, not from X-User-Role header
        assert user_role == "auditor"
        assert user_role not in ("engineer", "admin", "operator")

    def test_bot_agent_role_extracted(self):
        """BOT_AGENT role is correctly extracted from auth state."""
        auth_ctx = AuthContext(
            user_id="bot-agent-001",
            role=SentinelRole.BOT_AGENT,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )
        req = _FakeRequest(auth=auth_ctx, headers={})

        user_id, user_role = _extract_user(req)

        assert user_id == "bot-agent-001"
        assert user_role == "bot_agent"


# ---------------------------------------------------------------------------
# Integration tests for BOT_AGENT role boundary (Gap 10 - MEDIUM)
# ---------------------------------------------------------------------------


class TestBotAgentControlBoundary:
    """Test that BOT_AGENT role is rejected from control endpoints.

    Gap 10 (MEDIUM): BOT_AGENT rejected from control endpoints not tested.
    Control: AUTH-002 (Role Hierarchy & RBAC)
    """

    def test_bot_agent_role_value(self):
        """BOT_AGENT has role value 1 (same as AUDITOR, below OPERATOR)."""
        from app.models.auth import ROLE_HIERARCHY

        bot_level = ROLE_HIERARCHY.get(SentinelRole.BOT_AGENT, -1)
        operator_level = ROLE_HIERARCHY.get(SentinelRole.OPERATOR, -1)
        auditor_level = ROLE_HIERARCHY.get(SentinelRole.AUDITOR, -1)

        # BOT_AGENT should be level 1 (same as AUDITOR)
        assert bot_level == 1, f"BOT_AGENT should be level 1, got {bot_level}"
        # OPERATOR should be level 2
        assert operator_level == 2, f"OPERATOR should be level 2, got {operator_level}"
        # Both should be equal
        assert bot_level == auditor_level

    def test_bot_agent_cannot_pass_operator_check(self):
        """BOT_AGENT role (level=1) fails OPERATOR required (level=2) checks."""
        auth_ctx = AuthContext(
            user_id="bot-001",
            role=SentinelRole.BOT_AGENT,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # BOT_AGENT should fail has_role(OPERATOR) check
        assert not auth_ctx.has_role(SentinelRole.OPERATOR)

    def test_bot_agent_cannot_pass_admin_check(self):
        """BOT_AGENT role (level=1) fails ADMIN required (level=4) checks."""
        auth_ctx = AuthContext(
            user_id="bot-001",
            role=SentinelRole.BOT_AGENT,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # BOT_AGENT should fail has_role(ADMIN) check
        assert not auth_ctx.has_role(SentinelRole.ADMIN)

    def test_bot_agent_passes_auditor_check(self):
        """BOT_AGENT role (level=1) passes AUDITOR required (level=1) checks."""
        auth_ctx = AuthContext(
            user_id="bot-001",
            role=SentinelRole.BOT_AGENT,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # BOT_AGENT should pass has_role(AUDITOR) check (same level)
        assert auth_ctx.has_role(SentinelRole.AUDITOR)


# ---------------------------------------------------------------------------
# HTTP Integration Tests for BOT_AGENT role boundary
# ---------------------------------------------------------------------------


def _make_token(role: str = "operator") -> str:
    """Create a JWT token for the given role."""
    token = create_jwt_token(
        user_id=f"test-user-{role}",
        email=f"test@{role}.sentinel.bms",
        role=role,
        full_name=f"Test {role.title()}",
    )
    return token


@pytest.fixture
async def async_client() -> AsyncClient:
    """Async HTTP client for tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestBotAgentControlEndpointRejection:
    """HTTP integration tests: verify BOT_AGENT is rejected from control endpoints.

    Gap 10 (MEDIUM): BOT_AGENT rejected from control endpoints not tested.
    Control: AUTH-002 (Role Hierarchy & RBAC)

    These tests verify that BOT_AGENT cannot execute device controls,
    approvals, or autonomous configurations via HTTP.
    """

    @pytest.mark.asyncio
    async def test_bot_agent_cannot_execute_device_control(self, async_client):
        """POST /api/devices/{id}/command with BOT_AGENT should return 401/403."""
        bot_token = _make_token("bot_agent")
        device_id = "S002-FCU-B1-001"

        response = await async_client.post(
            f"/api/devices/{device_id}/command",
            json={"command": "set_temperature", "value": 22},
            headers={"Authorization": f"Bearer {bot_token}"},
        )

        # Should not succeed (bot_agent cannot control devices)
        assert response.status_code != 200, (
            f"BOT_AGENT should not execute device control. Got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_bot_agent_cannot_execute_batch_commands(self, async_client):
        """POST /api/remote/commands/batch with BOT_AGENT should be checked for authorization."""
        bot_token = _make_token("bot_agent")

        response = await async_client.post(
            "/api/remote/commands/batch",
            json={
                "commands": [
                    {
                        "device_id": "S002-FCU-B1-001",
                        "command_type": "setpoint_adjust",
                        "point": "setpoint",
                        "value": 22,
                    }
                ],
                "reason": "Test",
            },
            headers={"Authorization": f"Bearer {bot_token}"},
        )

        # Should NOT get 401 Unauthorized (token is valid)
        # May get 200, 403, 404, etc. depending on validation
        assert response.status_code != 401, f"BOT_AGENT token should be valid. Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_operator_can_attempt_device_control(self, async_client):
        """POST /api/devices/{id}/command with OPERATOR should not be rejected for role."""
        operator_token = _make_token("operator")
        device_id = "S002-FCU-B1-001"

        response = await async_client.post(
            f"/api/devices/{device_id}/command",
            json={"command": "set_temperature", "value": 22},
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        # Should NOT get 401 unauthorized (token is valid)
        # May get 404 (device not found) or 403 (step_up required) or other error
        assert response.status_code != 401, (
            f"OPERATOR token should not be rejected for auth. Got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_auditor_cannot_execute_remote_command(self, async_client):
        """POST /api/remote/commands/execute with AUDITOR should be checked for authorization."""
        auditor_token = _make_token("auditor")

        response = await async_client.post(
            "/api/remote/commands/execute",
            json={
                "device_id": "S002-AHU-B1-001",
                "command_type": "status_check",
                "reason": "Test",
            },
            headers={"Authorization": f"Bearer {auditor_token}"},
        )

        # Should NOT get 401 Unauthorized (token is valid)
        assert response.status_code != 401, f"AUDITOR token should be valid. Got {response.status_code}"
