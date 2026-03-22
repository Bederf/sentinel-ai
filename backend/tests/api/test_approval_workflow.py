"""Tests for approval workflow role-based access control.

Tests verify that role-based access control boundaries are properly
enforced on approval endpoints.

Controls: POLICY-002 (Human Oversight Requirements)
"""

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

from app.models.auth import SentinelRole, AuthContext  # noqa: E402


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
