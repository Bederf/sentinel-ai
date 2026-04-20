"""Tests for step-up authentication — Phase 137-04.

Tests:
    - Session creation with valid PIN
    - Invalid PIN denied
    - Expired session denied
    - Rate limiting enforcement
    - Device ID extraction
    - require_step_up dependency behavior
"""

import time

import bcrypt
import pytest

from app.security.step_up import (
    STEP_UP_MAX_ATTEMPTS,
    _extract_device_id,
    _reset_sessions_for_testing,
    _set_pin_hash_for_testing,
    _step_up_sessions,
    create_step_up_session,
    has_valid_step_up_session,
    require_step_up,
    revoke_step_up_session,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Generate a known test PIN and its bcrypt hash
_TEST_PIN = "123456"
_TEST_PIN_HASH = bcrypt.hashpw(_TEST_PIN.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@pytest.fixture(autouse=True)
def clean_sessions():
    """Reset all sessions and rate limits before each test."""
    _reset_sessions_for_testing()
    _set_pin_hash_for_testing(_TEST_PIN_HASH)
    yield
    _reset_sessions_for_testing()
    _set_pin_hash_for_testing("")


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------


class TestCreateStepUpSession:
    """Tests for create_step_up_session."""

    def test_step_up_creates_session(self):
        """Valid PIN creates a step-up session."""
        result = create_step_up_session(
            user_id="user-001",
            device_id="device-abc",
            pin=_TEST_PIN,
        )
        assert result is True
        assert has_valid_step_up_session("user-001", "device-abc") is True

    def test_step_up_invalid_pin_denied(self):
        """Invalid PIN does not create a session."""
        result = create_step_up_session(
            user_id="user-001",
            device_id="device-abc",
            pin="wrong-pin",
        )
        assert result is False
        assert has_valid_step_up_session("user-001", "device-abc") is False

    def test_step_up_expired_session_denied(self):
        """Expired sessions are not valid."""
        # Create session with an already-expired timestamp
        _step_up_sessions[("user-001", "device-abc")] = time.time() - 1
        assert has_valid_step_up_session("user-001", "device-abc") is False

    def test_step_up_session_per_device(self):
        """Sessions are scoped to (user_id, device_id) pairs."""
        create_step_up_session("user-001", "device-a", _TEST_PIN)
        assert has_valid_step_up_session("user-001", "device-a") is True
        assert has_valid_step_up_session("user-001", "device-b") is False

    def test_step_up_session_per_user(self):
        """Different users have independent sessions."""
        create_step_up_session("user-001", "device-a", _TEST_PIN)
        assert has_valid_step_up_session("user-001", "device-a") is True
        assert has_valid_step_up_session("user-002", "device-a") is False

    def test_step_up_revoke_session(self):
        """Session can be explicitly revoked."""
        create_step_up_session("user-001", "device-a", _TEST_PIN)
        assert has_valid_step_up_session("user-001", "device-a") is True

        revoked = revoke_step_up_session("user-001", "device-a")
        assert revoked is True
        assert has_valid_step_up_session("user-001", "device-a") is False

    def test_step_up_revoke_nonexistent(self):
        """Revoking a nonexistent session returns False."""
        revoked = revoke_step_up_session("user-999", "device-z")
        assert revoked is False

    def test_step_up_no_pin_hash_configured(self):
        """503 raised if ADMIN_PIN_HASH not set."""
        _set_pin_hash_for_testing("")
        with pytest.raises(Exception) as exc_info:
            create_step_up_session("user-001", "device-a", _TEST_PIN)
        assert exc_info.value.status_code == 503

    def test_step_up_invalid_hash_format(self):
        """503 raised if ADMIN_PIN_HASH is malformed."""
        _set_pin_hash_for_testing("not-a-valid-bcrypt-hash")
        with pytest.raises(Exception) as exc_info:
            create_step_up_session("user-001", "device-a", _TEST_PIN)
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestStepUpRateLimit:
    """Tests for step-up rate limiting."""

    def test_rate_limit_after_max_attempts(self):
        """Rate limit triggers after STEP_UP_MAX_ATTEMPTS failed PINs."""
        # Make STEP_UP_MAX_ATTEMPTS failed attempts
        for _ in range(STEP_UP_MAX_ATTEMPTS):
            result = create_step_up_session("user-rate", "device-a", "wrong")
            assert result is False

        # Next attempt should be rate limited
        with pytest.raises(Exception) as exc_info:
            create_step_up_session("user-rate", "device-a", _TEST_PIN)
        assert exc_info.value.status_code == 429

    def test_rate_limit_per_user(self):
        """Rate limiting is per-user, not global."""
        # Exhaust rate limit for user-a
        for _ in range(STEP_UP_MAX_ATTEMPTS):
            create_step_up_session("user-a", "device-a", "wrong")

        # user-b should still work
        result = create_step_up_session("user-b", "device-a", _TEST_PIN)
        assert result is True


# ---------------------------------------------------------------------------
# Device ID extraction
# ---------------------------------------------------------------------------


class TestDeviceIdExtraction:
    """Tests for _extract_device_id."""

    def test_extract_from_header(self):
        """X-Device-Id header is preferred."""

        class _MockRequest:
            headers = {"X-Device-Id": "my-device-123"}
            cookies = {}

            class client:
                host = "127.0.0.1"

        device_id = _extract_device_id(_MockRequest())
        assert device_id == "my-device-123"

    def test_extract_from_cookie(self):
        """Falls back to device_id cookie."""

        class _MockRequest:
            headers = {}
            cookies = {"device_id": "cookie-device"}

            class client:
                host = "127.0.0.1"

        device_id = _extract_device_id(_MockRequest())
        assert device_id == "cookie-device"

    def test_extract_fallback_to_ip(self):
        """Falls back to client IP."""

        class _MockRequest:
            headers = {}
            cookies = {}

            class client:
                host = "10.0.0.5"

        device_id = _extract_device_id(_MockRequest())
        assert device_id == "10.0.0.5"


# ---------------------------------------------------------------------------
# require_step_up dependency
# ---------------------------------------------------------------------------


class TestRequireStepUpDependency:
    """Tests for the require_step_up FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_control_endpoint_requires_step_up(self):
        """Without a valid step-up session, 403 step_up_required is raised."""
        from unittest.mock import MagicMock

        from app.models.auth import AuthContext, SentinelRole

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.cookies = {}
        mock_request.url.path = "/api/device-controls/S002-FCU-203/execute"

        # Simulate authenticated user on request.state
        auth_ctx = AuthContext(
            user_id="user-001",
            role=SentinelRole.OPERATOR,
            auth_method="bearer_token",
            source_ip="127.0.0.1",
        )
        mock_request.state.auth = auth_ctx
        mock_request.client.host = "127.0.0.1"

        dep = require_step_up()
        with pytest.raises(Exception) as exc_info:
            await dep(mock_request)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "step_up_required"

    @pytest.mark.asyncio
    async def test_control_endpoint_passes_with_step_up(self):
        """With a valid step-up session, the dependency passes."""
        from unittest.mock import MagicMock

        from app.models.auth import AuthContext, SentinelRole

        # Create a step-up session
        create_step_up_session("user-001", "127.0.0.1", _TEST_PIN)

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.cookies = {}
        mock_request.url.path = "/api/device-controls/S002-FCU-203/execute"

        auth_ctx = AuthContext(
            user_id="user-001",
            role=SentinelRole.OPERATOR,
            auth_method="bearer_token",
            source_ip="127.0.0.1",
        )
        mock_request.state.auth = auth_ctx
        mock_request.client.host = "127.0.0.1"

        dep = require_step_up()
        result = await dep(mock_request)
        assert result is None  # Passed without exception

    @pytest.mark.asyncio
    async def test_step_up_not_bypassed_in_demo_mode(self):
        """Demo mode no longer bypasses step-up auth."""
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.cookies = {}
        mock_request.state = MagicMock(spec=[])  # No auth attribute

        import app.config.settings as settings_mod

        original_demo = settings_mod.settings.demo_mode
        settings_mod.settings.demo_mode = True

        try:
            dep = require_step_up()
            # Without auth context, step-up should fail (not be bypassed)
            with pytest.raises(Exception):
                await dep(mock_request)
        finally:
            settings_mod.settings.demo_mode = original_demo
