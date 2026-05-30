from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.sentry.conversation_state import ConversationStateManager


class TestConversationStateManager:
    @pytest.fixture
    def mgr(self):
        return ConversationStateManager()

    def test_set_and_get(self, mgr):
        state = ConversationStateManager.ConversationState(
            flow="residential_onboarding",
            step="awaiting_email",
            data={"platform": "solarman"},
            created_at="",
            updated_at="",
        )
        mgr.set(123, state)
        result = mgr.get(123)
        assert result is not None
        assert result.flow == "residential_onboarding"
        assert result.step == "awaiting_email"
        assert result.data["platform"] == "solarman"

    def test_clear(self, mgr):
        state = ConversationStateManager.ConversationState(
            flow="residential_onboarding",
            step="awaiting_email",
            data={},
            created_at="",
            updated_at="",
        )
        mgr.set(456, state)
        mgr.clear(456)
        assert mgr.get(456) is None

    def test_memory_fallback_on_redis_failure(self):
        with patch("redis.from_url") as mock_redis:
            mock_instance = MagicMock()
            mock_instance.get.side_effect = Exception("redis down")
            mock_instance.setex.side_effect = Exception("redis down")
            mock_redis.return_value = mock_instance
            mgr = ConversationStateManager()
            state = ConversationStateManager.ConversationState(
                flow="test", step="s1", data={}, created_at="", updated_at=""
            )
            mgr.set(789, state)
            result = mgr.get(789)
            assert result is not None
            assert result.flow == "test"

    def test_credentials_not_in_state_after_clear(self, mgr):
        state = ConversationStateManager.ConversationState(
            flow="residential_onboarding",
            step="awaiting_password",
            data={"email": "a@b.com", "password": "secret123"},
            created_at="",
            updated_at="",
        )
        mgr.set(999, state)
        # After auth the handler calls clear() — verify password is gone
        mgr.clear(999)
        assert mgr.get(999) is None
