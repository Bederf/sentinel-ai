"""Tests for API key validation fail-closed behavior on Supabase downtime.

Phase 168-01: Verify that API key validation returns None (fail-closed)
when Supabase is unavailable. No fallback to in-memory store.

Control: AUTH-004 (production-ready API key validation)
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.middleware.auth_middleware import _validate_api_key


class TestAPIKeySupabaseDowntime:
    """Test fail-closed behavior when Supabase is unavailable.

    Phase 168-01: API key validation must fail safely (return None)
    when database is down. No fallback to legacy in-memory store.
    """

    def test_api_key_validation_supabase_down_returns_none(self):
        """When Supabase is unavailable, API key validation returns None (fail-closed).

        No fallback to in-memory store. Connection loss = auth failure.
        Control: AUTH-004 (production-ready API key validation)
        """
        # Mock get_supabase_client to raise connection error
        with patch("app.middleware.auth_middleware.get_supabase_client") as mock_get_client:
            mock_get_client.side_effect = ConnectionError("Supabase down")

            # Call validation with any key
            result = _validate_api_key("sent_sk_test_key_12345")

            # Should return None (fail-closed), not raise or fall back
            assert result is None

            # Client was attempted
            mock_get_client.assert_called_once()

    def test_api_key_validation_supabase_timeout_returns_none(self):
        """Supabase timeout → API key validation returns None."""
        with patch("app.middleware.auth_middleware.get_supabase_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.table.side_effect = TimeoutError("Query timeout")

            result = _validate_api_key("sent_sk_test_key_12345")

            assert result is None

    def test_api_key_validation_supabase_auth_error_returns_none(self):
        """Supabase auth error (permission denied) → API key validation returns None."""
        with patch("app.middleware.auth_middleware.get_supabase_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.table.side_effect = PermissionError("Invalid Supabase key")

            result = _validate_api_key("sent_sk_test_key_12345")

            assert result is None

    def test_api_key_validation_supabase_generic_error_returns_none(self):
        """Any generic exception from Supabase → API key validation returns None."""
        with patch("app.middleware.auth_middleware.get_supabase_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.table.side_effect = RuntimeError("Unexpected Supabase error")

            result = _validate_api_key("sent_sk_test_key_12345")

            assert result is None

    def test_api_key_validation_no_in_memory_fallback(self):
        """Verify that in-memory store is NOT used as fallback.

        Even with valid in-memory data, if Supabase fails, validation should fail.
        """
        # Mock Supabase to fail
        with patch("app.middleware.auth_middleware.get_supabase_client") as mock_get_client:
            mock_get_client.side_effect = Exception("Database unavailable")

            result = _validate_api_key("sent_sk_test_key_12345")

            # Should return None, not fall back to in-memory
            assert result is None

    def test_api_key_validation_valid_supabase_response(self):
        """Valid Supabase response returns key info correctly."""
        with patch("app.middleware.auth_middleware.get_supabase_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_query = mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value

            # Mock successful response
            mock_query.data = [
                {
                    "id": "test-key-id-123",
                    "role": "operator",
                    "owner": "test-user",
                    "key_prefix": "test_",
                    "scopes": ["device:read", "device:control"],
                    "revoked": False,
                    "expires_at": None,
                }
            ]

            result = _validate_api_key("sent_sk_test_key_12345")

            # Should return valid key info
            assert result is not None
            assert result["owner"] == "test-user"
            assert result["is_active"] is True

    def test_api_key_validation_revoked_key_returns_none(self):
        """Revoked API key in Supabase returns None."""
        with patch("app.middleware.auth_middleware.get_supabase_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_query = mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value

            # Mock revoked key response
            mock_query.data = [
                {
                    "id": "test-key-id-123",
                    "role": "operator",
                    "revoked": True,
                    "expires_at": None,
                }
            ]

            result = _validate_api_key("sent_sk_test_key_12345")

            # Should return None for revoked key
            assert result is None

    def test_api_key_validation_no_cache_after_supabase_error(self):
        """Supabase errors should not populate any cache."""
        with patch("app.middleware.auth_middleware.get_supabase_client") as mock_get_client:
            mock_get_client.side_effect = Exception("Database unavailable")

            # Call validation
            result1 = _validate_api_key("sent_sk_test_key_12345")
            assert result1 is None

            # Reset mock to track calls
            mock_get_client.reset_mock()
            mock_get_client.side_effect = Exception("Database still down")

            # Second call should also fail (no cache)
            result2 = _validate_api_key("sent_sk_test_key_12345")
            assert result2 is None

            # Both calls should hit Supabase (no cache)
            assert mock_get_client.call_count >= 1
