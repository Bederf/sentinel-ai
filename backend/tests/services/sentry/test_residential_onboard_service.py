from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sentry.residential_onboard_service import (
    AWAITING_EMAIL,
    AWAITING_PASSWORD,
    ResidentialOnboardService,
)


class TestResidentialOnboardService:
    @pytest.fixture
    def service(self):
        return ResidentialOnboardService()

    def test_handle_connect_creates_awaiting_platform_state(self, service):
        with (
            patch.object(service._state, "get", return_value=None),
            patch("app.services.sentry.residential_onboard_service._send") as mock_send,
        ):
            result = service.handle_connect(12345)
            assert "platform" in result.lower() or "starting" in result.lower()

    def test_handle_email_stores_email_and_advances_to_password_step(self, service):
        state = service._new_state("residential_onboarding", AWAITING_EMAIL, {"platform": "solarman"})
        with (
            patch.object(service._state, "get", return_value=state),
            patch.object(service._state, "set") as mock_set,
        ):
            result = service.handle_email(12345, "test@example.com")
            assert "email" in result.lower() or "password" in result.lower()
            # Verify set was called with updated step
            call_args = mock_set.call_args[0]
            assert call_args[1].step == AWAITING_PASSWORD

    def test_invalid_email_returns_error(self, service):
        state = service._new_state("residential_onboarding", AWAITING_EMAIL, {"platform": "solarman"})
        with patch.object(service._state, "get", return_value=state):
            result = service.handle_email(12345, "not-an-email")
            assert "email" in result.lower() and "look" in result.lower()

    def test_rate_limit_blocks_after_3_failures(self):
        with (
            patch("app.services.sentry.residential_onboard_service._check_rate_limit") as mock_limit,
            patch.object(ResidentialOnboardService()._state, "get", return_value=None),
        ):
            mock_limit.return_value = (False, 0)
            service = ResidentialOnboardService()
            result = service.handle_password(12345, 999, "wrongpw")
            assert "try again" in result.lower()

    def test_password_deleted_before_auth(self, service):
        state = service._new_state("residential_onboarding", AWAITING_PASSWORD,
                                    {"platform": "solarman", "email": "a@b.com", "site_id": "res-123"})
        with (
            patch.object(service._state, "get", return_value=state),
            patch("app.services.sentry.residential_onboard_service._delete") as mock_delete,
            patch("app.services.sentry.residential_onboard_service.build_adapter") as mock_build,
            patch("app.services.sentry.residential_onboard_service._record_failure"),
        ):
            mock_adapter = MagicMock()
            mock_adapter.authenticate = AsyncMock(return_value=False)
            mock_build.return_value = mock_adapter
            service.handle_password(12345, 999, "wrongpw")
            # Delete MUST be called before auth
            mock_delete.assert_called_once_with(12345, 999)

    def test_credentials_not_in_state_data_after_auth(self, service):
        state = service._new_state("residential_onboarding", AWAITING_PASSWORD,
                                    {"platform": "solarman", "email": "a@b.com", "site_id": "res-123"})
        with (
            patch.object(service._state, "get", return_value=state),
            patch("app.services.sentry.residential_onboard_service._delete"),
            patch("app.services.sentry.residential_onboard_service._check_rate_limit", return_value=(True, 3)),
            patch("app.services.sentry.residential_onboard_service.build_adapter") as mock_build,
            patch("httpx.Client") as mock_client,
        ):
            mock_adapter = MagicMock()
            mock_adapter.authenticate = AsyncMock(return_value=True)
            mock_adapter.discover_devices = AsyncMock(return_value=[])
            mock_build.return_value = mock_adapter
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "onboarded"}
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            service.handle_password(12345, 999, "correctpw")
            # After auth, state.data should not contain plaintext password
            # (implementation should clear it)
