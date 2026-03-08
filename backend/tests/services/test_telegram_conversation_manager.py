"""Tests for TelegramConversationManager."""

from datetime import datetime, timedelta

from app.services.telegram_conversation_manager import (
    SESSION_TIMEOUT_MINUTES,
    ConversationSession,
    TelegramConversationManager,
)
from app.services.telegram_intent_classifier import TelegramIntent


class TestConversationSession:
    def test_touch_updates_last_activity(self):
        session = ConversationSession(
            chat_id="123",
            intent=TelegramIntent.CLIENT_COMPLAINT,
            flow="client_complaint",
        )
        old_time = session.last_activity
        # Manually set to past
        session.last_activity = datetime.utcnow() - timedelta(seconds=10)
        session.touch()
        assert session.last_activity > old_time

    def test_not_expired_within_timeout(self):
        session = ConversationSession(
            chat_id="123",
            intent=TelegramIntent.CLIENT_COMPLAINT,
            flow="client_complaint",
        )
        assert not session.is_expired()

    def test_expired_after_timeout(self):
        session = ConversationSession(
            chat_id="123",
            intent=TelegramIntent.CLIENT_COMPLAINT,
            flow="client_complaint",
        )
        session.last_activity = datetime.utcnow() - timedelta(minutes=SESSION_TIMEOUT_MINUTES + 1)
        assert session.is_expired()


class TestTelegramConversationManager:
    def test_create_and_get_session(self):
        mgr = TelegramConversationManager()
        session = mgr.create_session("chat-1", TelegramIntent.CLIENT_COMPLAINT, "client_complaint")
        assert session.chat_id == "chat-1"
        assert session.flow == "client_complaint"

        retrieved = mgr.get_session("chat-1")
        assert retrieved is not None
        assert retrieved.chat_id == "chat-1"

    def test_get_session_missing(self):
        mgr = TelegramConversationManager()
        assert mgr.get_session("nonexistent") is None

    def test_get_session_expired_returns_none(self):
        mgr = TelegramConversationManager()
        session = mgr.create_session("chat-1", TelegramIntent.CLIENT_COMPLAINT, "client_complaint")
        session.last_activity = datetime.utcnow() - timedelta(minutes=SESSION_TIMEOUT_MINUTES + 1)
        mgr._sessions["chat-1"] = session

        assert mgr.get_session("chat-1") is None
        assert "chat-1" not in mgr._sessions  # auto-cleaned

    def test_end_session(self):
        mgr = TelegramConversationManager()
        mgr.create_session("chat-1", TelegramIntent.CLIENT_COMPLAINT, "client_complaint")
        mgr.end_session("chat-1")
        assert mgr.get_session("chat-1") is None

    def test_end_session_nonexistent(self):
        mgr = TelegramConversationManager()
        mgr.end_session("nonexistent")  # should not raise

    def test_create_replaces_existing(self):
        mgr = TelegramConversationManager()
        mgr.create_session("chat-1", TelegramIntent.CLIENT_COMPLAINT, "client_complaint")
        mgr.create_session("chat-1", TelegramIntent.WO_UPDATE, "wo_update")
        session = mgr.get_session("chat-1")
        assert session.flow == "wo_update"

    def test_update_session_touches(self):
        mgr = TelegramConversationManager()
        session = mgr.create_session("chat-1", TelegramIntent.CLIENT_COMPLAINT, "client_complaint")
        old = session.last_activity
        session.last_activity = datetime.utcnow() - timedelta(seconds=30)
        mgr.update_session(session)
        updated = mgr.get_session("chat-1")
        assert updated.last_activity > old - timedelta(seconds=1)

    def test_cleanup_expired(self):
        mgr = TelegramConversationManager()

        # Active session
        mgr.create_session("active", TelegramIntent.CLIENT_COMPLAINT, "client_complaint")

        # Expired session
        expired = mgr.create_session("expired", TelegramIntent.WO_UPDATE, "wo_update")
        expired.last_activity = datetime.utcnow() - timedelta(minutes=SESSION_TIMEOUT_MINUTES + 5)
        mgr._sessions["expired"] = expired

        count = mgr.cleanup_expired()
        assert count == 1
        assert mgr.get_session("active") is not None
        assert mgr.get_session("expired") is None

    def test_cleanup_returns_zero_when_none_expired(self):
        mgr = TelegramConversationManager()
        mgr.create_session("chat-1", TelegramIntent.CLIENT_COMPLAINT, "client_complaint")
        assert mgr.cleanup_expired() == 0
