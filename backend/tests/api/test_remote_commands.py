"""Regression tests for remote_commands security fixes.

C-1: Role escalation via X-User-Role header injection.

Verifies that _extract_user() ignores the X-User-Role header and
reads the role exclusively from request.state.auth (JWT-verified).
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

from app.api.remote_commands import _extract_user  # noqa: E402
from app.models.auth import AuthContext, SentinelRole  # noqa: E402


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
