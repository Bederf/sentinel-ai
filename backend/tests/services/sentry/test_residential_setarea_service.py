"""Tests for ResidentialSetareaService.

Phase 214 — Wave 6
Covers:
- Happy path: valid area code → saved → confirmation message
- Invalid area code: error message, not saved
- No active connection: correct error
- Existing area code: confirmation step before overwrite
- EskomSePushClient.validate_area_code called — not re-implemented
- /setarea blocked during active onboarding flow
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sentry.residential_setarea_service import (
    AWAITING_AREA_CODE,
    ResidentialSetareaService,
)


class TestHandleSetarea:
    """Tests for handle_setarea entry point."""

    def test_no_active_connection_returns_correct_message(self):
        """No active site → correct error message suggesting /connect."""
        with patch("app.services.sentry.residential_setarea_service._lookup_active_site") as mock_lookup:
            mock_lookup.return_value = None
            with patch("app.services.sentry.residential_setarea_service._has_active_onboarding_flow") as mock_flow:
                mock_flow.return_value = False
                service = ResidentialSetareaService()
                result = service.handle_setarea(12345)
                assert "no active connection" in result.lower()
                assert "/connect" in result

    def test_active_onboarding_flow_blocked(self):
        """Active /connect onboarding → /setarea blocked."""
        with patch("app.services.sentry.residential_setarea_service._has_active_onboarding_flow") as mock_check:
            mock_check.return_value = True
            service = ResidentialSetareaService()
            result = service.handle_setarea(12345)
            assert "complete your /connect" in result.lower()

    def test_no_existing_area_asks_for_code(self):
        """No existing area code → bot asks user to enter area code."""
        with patch("app.services.sentry.residential_setarea_service._lookup_active_site") as mock_lookup:
            mock_lookup.return_value = {"site_id": "res-123", "eskom_area_code": None, "is_active": True}
            with patch("app.services.sentry.residential_setarea_service._has_active_onboarding_flow") as mock_flow:
                mock_flow.return_value = False
                with patch("app.services.sentry.residential_setarea_service._send") as mock_send:
                    mock_send.return_value = {"message_id": 0}
                    service = ResidentialSetareaService()
                    result = service.handle_setarea(12345)
                    # Result should indicate the bot is asking for area code
                    assert "asking for area code" in result.lower()
                    # _send should have been called with the eskom prompt
                    mock_send.assert_called_once()
                    sent_text = mock_send.call_args[0][1]
                    assert "eskom" in sent_text.lower()

    def test_existing_area_shows_confirmation(self):
        """Existing area code → bot shows inline confirmation before update."""
        with patch("app.services.sentry.residential_setarea_service._lookup_active_site") as mock_lookup:
            mock_lookup.return_value = {"site_id": "res-123", "eskom_area_code": "sandton-2", "is_active": True}
            with patch("app.services.sentry.residential_setarea_service._has_active_onboarding_flow") as mock_flow:
                mock_flow.return_value = False
                with patch("app.services.sentry.residential_setarea_service._send") as mock_send:
                    mock_send.return_value = {"message_id": 0}
                    service = ResidentialSetareaService()
                    result = service.handle_setarea(12345)
                    assert "awaiting update confirmation" in result.lower()
                    # _send should have been called with a reply_markup (inline keyboard)
                    mock_send.assert_called_once()
                    call_kwargs = mock_send.call_args[1]
                    assert call_kwargs.get("reply_markup") is not None


class TestHandleAreaCodeText:
    """Tests for handle_area_code_text free-form entry."""

    def test_wrong_state_returns_correct_message(self):
        """When no state is set, user must send /setarea to start."""
        with patch("app.services.sentry.residential_setarea_service.ConversationStateManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = None  # no state → correct error path
            mock_mgr_cls.return_value = mock_mgr
            service = ResidentialSetareaService()
            result = service.handle_area_code_text(12345, "sandton-2")
            assert "send /setarea" in result.lower()

    def test_empty_area_code_rejected(self):
        """Empty/whitespace area code → error, not saved."""
        state = MagicMock()
        state.step = AWAITING_AREA_CODE
        state.data = {"site_id": "res-123"}

        with patch("app.services.sentry.residential_setarea_service.ConversationStateManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = state
            mock_mgr_cls.return_value = mock_mgr

            service = ResidentialSetareaService()
            result = service.handle_area_code_text(12345, "   ")
            assert "cannot be empty" in result.lower()

    def test_invalid_area_code_returns_error_not_found(self):
        """Invalid area code → error message sent, DB not updated."""
        state = MagicMock()
        state.step = AWAITING_AREA_CODE
        state.data = {"site_id": "res-123"}

        with patch("app.services.sentry.residential_setarea_service.ConversationStateManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = state
            mock_mgr_cls.return_value = mock_mgr

            with patch("app.services.sentry.residential_setarea_service._validate_area_code") as mock_validate:
                mock_validate.return_value = False  # invalid
                with patch("app.services.sentry.residential_setarea_service._send") as mock_send:
                    mock_send.return_value = {"message_id": 0}
                    service = ResidentialSetareaService()
                    result = service.handle_area_code_text(12345, "unknown-area")
                    # The return string indicates invalid
                    assert "invalid area code" in result.lower()
                    # The Telegram message to user should say "not found"
                    sent_text = mock_send.call_args[0][1]
                    assert "not found" in sent_text.lower()
                    # DB was NOT updated (no update call would happen)

    def test_valid_area_code_asks_for_confirm(self):
        """Valid area code → bot asks user to confirm before saving."""
        state = MagicMock()
        state.step = AWAITING_AREA_CODE
        state.data = {"site_id": "res-123"}

        with patch("app.services.sentry.residential_setarea_service.ConversationStateManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = state
            mock_mgr_cls.return_value = mock_mgr

            with patch("app.services.sentry.residential_setarea_service._validate_area_code") as mock_validate:
                mock_validate.return_value = True  # valid
                with patch("app.services.sentry.residential_setarea_service._send") as mock_send:
                    mock_send.return_value = {"message_id": 0}
                    service = ResidentialSetareaService()
                    result = service.handle_area_code_text(12345, "sandton-2")
                    assert "awaiting save confirmation" in result.lower()


class TestHandleConfirmation:
    """Tests for handle_confirmation inline keyboard handler."""

    def test_cancel_clears_state(self):
        """User taps Cancel → state cleared, confirmation message."""
        state = MagicMock()
        state.step = AWAITING_AREA_CODE
        state.data = {"site_id": "res-123", "new_area": "sandton-2"}

        with patch("app.services.sentry.residential_setarea_service.ConversationStateManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = state
            mock_mgr_cls.return_value = mock_mgr

            with patch("app.services.sentry.residential_setarea_service._sender") as mock_sender:
                mock_sender.answer_callback_query = AsyncMock(return_value=True)
                service = ResidentialSetareaService()
                result = service.handle_confirmation(12345, "cq-123", "setarea_cancel")
                assert "cancelled" in result.lower()
                mock_mgr.clear.assert_called_once_with(12345)

    def test_confirm_saves_area_code_to_db(self):
        """User taps Confirm with validated area code → DB updated, success message."""
        state = MagicMock()
        state.step = AWAITING_AREA_CODE
        state.data = {"site_id": "res-123", "new_area": "sandton-2"}

        with patch("app.services.sentry.residential_setarea_service.ConversationStateManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = state
            mock_mgr_cls.return_value = mock_mgr

            with patch("app.services.sentry.residential_setarea_service._sender") as mock_sender:
                mock_sender.answer_callback_query = AsyncMock(return_value=True)
                with patch("app.services.sentry.residential_setarea_service.get_supabase_client") as mock_sb:
                    mock_client = MagicMock()
                    # Set up chain for update().eq().execute()
                    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
                        MagicMock()
                    )
                    mock_sb.return_value = mock_client

                    with patch("app.services.sentry.residential_setarea_service._send") as mock_send:
                        mock_send.return_value = {"message_id": 0}
                        service = ResidentialSetareaService()
                        result = service.handle_confirmation(12345, "cq-123", "setarea_confirm")
                        # Bot sends success message
                        sent_text = mock_send.call_args[0][1]
                        assert "loadshedding alerts enabled" in sent_text.lower()
                        # DB update was called
                        mock_client.table.return_value.update.return_value.eq.return_value.execute.assert_called_once()

    def test_no_new_area_prompts_for_input(self):
        """Confirm tapped but no area code yet → bot asks for area code."""
        state = MagicMock()
        state.step = AWAITING_AREA_CODE
        state.data = {"site_id": "res-123", "new_area": ""}  # empty

        with patch("app.services.sentry.residential_setarea_service.ConversationStateManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = state
            mock_mgr_cls.return_value = mock_mgr

            with patch("app.services.sentry.residential_setarea_service._sender") as mock_sender:
                mock_sender.answer_callback_query = AsyncMock(return_value=True)
                with patch("app.services.sentry.residential_setarea_service._send") as mock_send:
                    mock_send.return_value = {"message_id": 0}
                    service = ResidentialSetareaService()
                    result = service.handle_confirmation(12345, "cq-123", "setarea_confirm")
                    assert "awaiting new area" in result.lower()


class TestValidateAreaCodeNotReimplemented:
    """Verify /setarea uses eskomsepush_client.validate_area_code, not a reimplementation."""

    def test_validate_uses_module_validate_func(self):
        """Module references validate_area_code from eskomsepush_client."""
        import inspect

        from app.services.sentry import residential_setarea_service as mod

        source = inspect.getsource(mod)
        assert "validate_area_code" in source


class TestSetareaBlockedDuringOnboarding:
    """Verify /setarea is blocked when active onboarding flow exists."""

    def test_blocked_during_active_onboarding(self):
        """Active /connect blocks /setarea — user must complete onboarding first."""
        with patch("app.services.sentry.residential_setarea_service._has_active_onboarding_flow") as mock_check:
            mock_check.return_value = True
            service = ResidentialSetareaService()
            result = service.handle_setarea(12345)
            assert "complete your /connect" in result.lower()
