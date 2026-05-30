from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.sentry.residential_disconnect_service import ResidentialDisconnectService


class TestResidentialDisconnectService:
    @pytest.fixture
    def service(self):
        return ResidentialDisconnectService()

    def test_not_connected_returns_correct_message(self, service):
        with patch("httpx.get") as mock_get:
            mock_get.return_value.status_code = 404
            result = service.handle_disconnect(12345)
            assert "no active connection" in result.lower()

    def test_confirm_clears_state_and_calls_deactivate(self, service):
        with (
            patch("app.services.sentry.residential_disconnect_service._answer_callback"),
            patch("app.services.sentry.conversation_state.ConversationStateManager") as mock_mgr_cls,
            patch("httpx.post") as mock_post,
        ):
            mock_mgr = MagicMock()
            mock_mgr_cls.return_value = mock_mgr
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"status": "deactivated"}
            result = service.handle_disconnect_confirm(12345, "cq_id_abc")
            assert "disconnected" in result.lower()
            mock_mgr.clear.assert_called_once_with(12345)

    def test_cancel_returns_active_message(self, service):
        with patch("app.services.sentry.residential_disconnect_service._answer_callback"):
            result = service.handle_cancel(12345, "cq_id_xyz")
            assert "cancelled" in result.lower() or "still active" in result.lower()
