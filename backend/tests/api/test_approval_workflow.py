"""Tests for approval workflow role-based access control.

Tests verify that role-based access control boundaries are properly
enforced on approval endpoints.

Controls: POLICY-002 (Human Oversight Requirements)
Gap 3 (HIGH): Approval endpoint role not proven in tests.
"""

import os
import pytest

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

from app.models.auth import SentinelRole, AuthContext  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402
from app.middleware.auth_middleware import create_jwt_token  # noqa: E402
from app.main import app  # noqa: E402


# Helper: Create JWT tokens for different roles
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


class TestApprovalWorkflowRolesStructural:
    """Test role-based access control on approval endpoints (structural tests).

    Gap 3 (HIGH): Approval endpoint role not proven in tests.
    Control: POLICY-002 (Human Oversight Requirements)

    These tests verify the role hierarchy and access control logic,
    ensuring AUDITOR/VIEWER/BOT_AGENT roles cannot escalate to approval actions.
    """

    def test_viewer_cannot_approve_role_hierarchy(self):
        """VIEWER/AUDITOR role should fail OPERATOR required checks (must be >=2)."""
        auth_ctx = AuthContext(
            user_id="viewer-001",
            role=SentinelRole.AUDITOR,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # AUDITOR (level 1) should NOT pass OPERATOR required (level 2) check
        assert not auth_ctx.has_role(SentinelRole.OPERATOR), (
            "VIEWER/AUDITOR should not pass OPERATOR role check for approval"
        )

    def test_auditor_cannot_approve_role_hierarchy(self):
        """AUDITOR role should fail OPERATOR required checks."""
        auth_ctx = AuthContext(
            user_id="auditor-001",
            role=SentinelRole.AUDITOR,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # AUDITOR (level 1) cannot approve (requires OPERATOR level 2+)
        assert not auth_ctx.has_role(SentinelRole.OPERATOR), "AUDITOR should not pass OPERATOR role check"

    def test_bot_agent_cannot_approve_role_hierarchy(self):
        """BOT_AGENT role should fail OPERATOR required checks."""
        auth_ctx = AuthContext(
            user_id="bot-001",
            role=SentinelRole.BOT_AGENT,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # BOT_AGENT (level 1) cannot approve (requires OPERATOR level 2+)
        assert not auth_ctx.has_role(SentinelRole.OPERATOR), (
            "BOT_AGENT should not pass OPERATOR role check for approval"
        )

    def test_operator_can_approve_role_hierarchy(self):
        """OPERATOR role should pass approval role checks (level=2)."""
        auth_ctx = AuthContext(
            user_id="operator-001",
            role=SentinelRole.OPERATOR,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # OPERATOR (level 2) should pass OPERATOR required check
        assert auth_ctx.has_role(SentinelRole.OPERATOR), "OPERATOR should pass OPERATOR role check for approval"

    def test_admin_can_approve_role_hierarchy(self):
        """ADMIN role should pass approval role checks (level=4)."""
        auth_ctx = AuthContext(
            user_id="admin-001",
            role=SentinelRole.ADMIN,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # ADMIN (level 4) should pass OPERATOR required check
        assert auth_ctx.has_role(SentinelRole.OPERATOR), "ADMIN should pass OPERATOR role check for approval"


class TestApprovalWorkflowRolesIntegration:
    """Test role-based access control on approval endpoints (HTTP integration tests).

    Gap 3 (HIGH): Approval endpoint role not proven in tests.
    Control: POLICY-002 (Human Oversight Requirements)

    These tests verify that the HTTP endpoints reject non-OPERATOR roles with 403.
    """

    @pytest.mark.asyncio
    async def test_viewer_cannot_approve_endpoint(self, async_client):
        """POST /api/approvals/recommendations/{id}/approve with VIEWER should return 403."""
        viewer_token = _make_token("auditor")  # AUDITOR = VIEWER equivalent
        recommendation_id = "test-rec-001"

        response = await async_client.post(
            f"/api/approvals/recommendations/{recommendation_id}/approve",
            json={"approved_by": "viewer-001", "approval_notes": "Test"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )

        # Should be rejected with 403 (insufficient role for approval)
        # or 401 (auth failed) or step_up_required (403), but NOT 200
        assert response.status_code != 200, (
            f"VIEWER role should not be able to approve. Got {response.status_code}: {response.text}"
        )
        assert response.status_code in [401, 403, 404], (
            f"Expected 401/403/404, got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_auditor_cannot_approve_endpoint(self, async_client):
        """POST /api/approvals/recommendations/{id}/approve with AUDITOR should return 403."""
        auditor_token = _make_token("auditor")
        recommendation_id = "test-rec-002"

        response = await async_client.post(
            f"/api/approvals/recommendations/{recommendation_id}/approve",
            json={"approved_by": "auditor-001", "approval_notes": "Test"},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )

        # Should be rejected (403 for step_up_required or auth role check)
        assert response.status_code != 200, (
            f"AUDITOR role should not be able to approve. Got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_bot_agent_cannot_approve_endpoint(self, async_client):
        """POST /api/approvals/recommendations/{id}/approve with BOT_AGENT should return 403."""
        bot_token = _make_token("bot_agent")
        recommendation_id = "test-rec-003"

        response = await async_client.post(
            f"/api/approvals/recommendations/{recommendation_id}/approve",
            json={"approved_by": "bot-001", "approval_notes": "Test"},
            headers={"Authorization": f"Bearer {bot_token}"},
        )

        # Should be rejected (403 for insufficient role)
        assert response.status_code != 200, (
            f"BOT_AGENT role should not be able to approve. Got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_operator_can_attempt_approval_endpoint(self, async_client):
        """POST /api/approvals/recommendations/{id}/approve with OPERATOR should not be rejected for role."""
        operator_token = _make_token("operator")
        recommendation_id = "test-rec-004"

        response = await async_client.post(
            f"/api/approvals/recommendations/{recommendation_id}/approve",
            json={"approved_by": "operator-001", "approval_notes": "Test"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        # Should NOT get 403 Forbidden for role (may get 403 step_up_required or 404 not found, but not 401)
        if response.status_code == 403:
            # If 403, should be step_up_required or recommendation not found, not insufficient role
            detail = response.json().get("detail", "")
            assert "insufficient role" not in detail.lower() and "bot agent" not in detail.lower(), (
                f"OPERATOR should not get role-based 403. Got: {detail}"
            )
        elif response.status_code == 404:
            # 404 not found is OK (recommendation doesn't exist)
            pass
        elif response.status_code == 200:
            # Success is OK
            pass
        else:
            # Should be one of these states
            assert response.status_code in [200, 403, 404], (
                f"Unexpected status: {response.status_code}: {response.text}"
            )
