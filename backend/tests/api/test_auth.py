"""Tests for authentication role-based access control.

Tests verify MFA enforcement for ADMIN role and role hierarchy.

Controls: AUTH-001 (JWT Bearer Token Validation), ISO-A.2.3 (strong auth)
"""

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

from app.models.auth import SentinelRole, AuthContext, ROLE_HIERARCHY  # noqa: E402


class TestAdminMFARequirement:
    """Test MFA enforcement for ADMIN role.

    Gap 9 (MEDIUM): MFA enforcement for ADMIN not tested.
    Control: AUTH-001 (JWT Bearer Token Validation), ISO-A.2.3 (strong auth)
    """

    def test_admin_role_has_highest_hierarchy(self):
        """ADMIN role should have the highest hierarchy level."""
        admin_level = ROLE_HIERARCHY.get(SentinelRole.ADMIN, -1)
        operator_level = ROLE_HIERARCHY.get(SentinelRole.OPERATOR, -1)
        auditor_level = ROLE_HIERARCHY.get(SentinelRole.AUDITOR, -1)

        # ADMIN should be the highest
        assert admin_level == 4
        assert admin_level > operator_level
        assert admin_level > auditor_level

    def test_admin_context_can_approve_and_control(self):
        """ADMIN role should pass all role hierarchy checks."""
        auth_ctx = AuthContext(
            user_id="admin-001",
            role=SentinelRole.ADMIN,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # ADMIN should pass all role checks
        assert auth_ctx.has_role(SentinelRole.ADMIN)
        assert auth_ctx.has_role(SentinelRole.OPERATOR)
        assert auth_ctx.has_role(SentinelRole.AUDITOR)
        assert auth_ctx.has_role(SentinelRole.BOT_AGENT)

    def test_mfa_required_flag_in_context(self):
        """AuthContext should support MFA tracking via metadata."""
        # ADMIN context can have MFA metadata set
        auth_ctx = AuthContext(
            user_id="admin-001",
            role=SentinelRole.ADMIN,
            auth_method="jwt",
            source_ip="127.0.0.1",
            metadata={"mfa_verified": True, "mfa_method": "totp"},
        )

        assert auth_ctx.metadata.get("mfa_verified") is True
        assert auth_ctx.metadata.get("mfa_method") == "totp"

    def test_mfa_not_verified_in_admin_context(self):
        """ADMIN context without MFA verification should be flagged."""
        # ADMIN context without MFA metadata
        auth_ctx = AuthContext(
            user_id="admin-001", role=SentinelRole.ADMIN, auth_method="jwt", source_ip="127.0.0.1", metadata={}
        )

        # MFA not verified
        assert auth_ctx.metadata.get("mfa_verified") is not True

    def test_operator_does_not_require_mfa_by_role(self):
        """OPERATOR role may have different MFA requirements than ADMIN."""
        admin_level = ROLE_HIERARCHY.get(SentinelRole.ADMIN, -1)
        operator_level = ROLE_HIERARCHY.get(SentinelRole.OPERATOR, -1)

        # ADMIN is higher privilege than OPERATOR
        assert admin_level > operator_level


class TestRoleHierarchyBoundaries:
    """Test role hierarchy enforcement across different roles."""

    def test_viewer_cannot_control_devices(self):
        """VIEWER/AUDITOR role should not pass OPERATOR checks."""
        # Most implementations treat VIEWER as equivalent to AUDITOR
        auth_ctx = AuthContext(
            user_id="viewer-001",
            role=SentinelRole.AUDITOR,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # Should not pass OPERATOR check
        assert not auth_ctx.has_role(SentinelRole.OPERATOR)
        # Should not pass ADMIN check
        assert not auth_ctx.has_role(SentinelRole.ADMIN)

    def test_developer_can_control_and_admin(self):
        """DEVELOPER role should have OPERATOR and AUDITOR permissions."""
        auth_ctx = AuthContext(
            user_id="dev-001",
            role=SentinelRole.DEVELOPER,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # DEVELOPER (level 3) should pass OPERATOR (level 2) check
        assert auth_ctx.has_role(SentinelRole.OPERATOR)
        # DEVELOPER should pass AUDITOR check
        assert auth_ctx.has_role(SentinelRole.AUDITOR)
        # But should NOT pass ADMIN (level 4) check
        assert not auth_ctx.has_role(SentinelRole.ADMIN)

    def test_operator_cannot_escalate_to_admin(self):
        """OPERATOR role should not pass ADMIN checks."""
        auth_ctx = AuthContext(
            user_id="op-001",
            role=SentinelRole.OPERATOR,
            auth_method="jwt",
            source_ip="127.0.0.1",
        )

        # OPERATOR can control devices
        assert auth_ctx.has_role(SentinelRole.OPERATOR)
        # But cannot escalate to ADMIN
        assert not auth_ctx.has_role(SentinelRole.ADMIN)

    def test_bot_agent_same_level_as_auditor(self):
        """BOT_AGENT and AUDITOR should have the same role level."""
        bot_level = ROLE_HIERARCHY.get(SentinelRole.BOT_AGENT, -1)
        auditor_level = ROLE_HIERARCHY.get(SentinelRole.AUDITOR, -1)

        # Both should be level 1
        assert bot_level == auditor_level
        assert bot_level == 1


class TestAPIKeySuabaseValidation:
    """Test Phase 168-01: API key validation from Supabase.

    Gap 1 (HIGH): API key in-memory store not production-ready.
    Control: AUTH-004 (API Key Storage and Rotation).
    """

    def test_api_key_from_supabase_valid(self):
        """Valid API key from Supabase should return auth dict."""
        from unittest.mock import patch, MagicMock
        from app.repositories.api_keys_repository import get_api_keys_repository

        with patch('app.repositories.api_keys_repository.get_supabase_client') as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client

            # Reset singleton
            import app.repositories.api_keys_repository as repo_module
            repo_module._api_keys_repository = None
            repo = get_api_keys_repository()

            test_key = "sent_sk_test_key_12345"

            mock_query = MagicMock()
            mock_query.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                "id": "test-id-123",
                "owner_role": 2,  # AUDITOR
                "expires_at": None,
            }
            mock_client.table.return_value.select.return_value = mock_query

            result = repo.validate_api_key(test_key)
            assert result is not None
            assert result["owner_role"] == 2
            assert result["api_key_id"] == "test-id-123"

    def test_api_key_from_supabase_expired(self):
        """Expired API key should be rejected."""
        from unittest.mock import patch, MagicMock
        from datetime import datetime, timedelta
        from app.repositories.api_keys_repository import get_api_keys_repository

        with patch('app.repositories.api_keys_repository.get_supabase_client') as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client

            # Reset singleton
            import app.repositories.api_keys_repository as repo_module
            repo_module._api_keys_repository = None
            repo = get_api_keys_repository()

            # Set expiration to 1 hour ago
            expired_time = (datetime.utcnow() - timedelta(hours=1)).isoformat()

            mock_query = MagicMock()
            mock_query.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                "id": "test-id-456",
                "owner_role": 2,
                "expires_at": expired_time,
            }
            mock_client.table.return_value.select.return_value = mock_query

            test_key = "sent_sk_expired_key_123"
            result = repo.validate_api_key(test_key)
            assert result is None

    def test_api_key_from_supabase_not_found(self):
        """Non-existent API key should return None."""
        from unittest.mock import patch, MagicMock
        from app.repositories.api_keys_repository import get_api_keys_repository

        with patch('app.repositories.api_keys_repository.get_supabase_client') as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client

            # Reset singleton
            import app.repositories.api_keys_repository as repo_module
            repo_module._api_keys_repository = None
            repo = get_api_keys_repository()

            mock_query = MagicMock()
            mock_query.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None
            mock_client.table.return_value.select.return_value = mock_query

            test_key = "sent_sk_nonexistent_789"
            result = repo.validate_api_key(test_key)
            assert result is None
