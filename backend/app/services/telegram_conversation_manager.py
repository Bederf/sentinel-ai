"""Telegram Conversation Manager — in-memory session state.

Manages per-chat conversation sessions with 30-minute expiry.
Sessions are keyed by chat_id (single user during testing phase).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.services.telegram_intent_classifier import TelegramIntent

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MINUTES = 30


@dataclass
class ConversationSession:
    """State for an active conversation flow."""

    chat_id: str
    intent: TelegramIntent
    flow: str  # "client_complaint", "technician_report", "wo_update", "ad_hoc_fault"
    current_step: int = 0
    answers: dict[str, str] = field(default_factory=dict)
    equipment_id: Optional[str] = None
    checklist_type: Optional[str] = None  # "ahu_weekly", "fcu_weekly", etc.
    wo_id: Optional[str] = None
    wo_codes: list[str] = field(default_factory=list)  # WOs created during flow
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        """Update last_activity timestamp."""
        self.last_activity = datetime.utcnow()

    def is_expired(self) -> bool:
        """Check if session has exceeded timeout."""
        delta = datetime.utcnow() - self.last_activity
        return delta.total_seconds() > SESSION_TIMEOUT_MINUTES * 60


class TelegramConversationManager:
    """Manages in-memory conversation sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}

    def get_session(self, chat_id: str) -> Optional[ConversationSession]:
        """Get active session for a chat, or None if expired/missing."""
        session = self._sessions.get(chat_id)
        if session and session.is_expired():
            logger.info("Session expired for chat %s (flow=%s)", chat_id, session.flow)
            del self._sessions[chat_id]
            return None
        return session

    def create_session(
        self,
        chat_id: str,
        intent: TelegramIntent,
        flow: str,
        equipment_id: Optional[str] = None,
    ) -> ConversationSession:
        """Create a new session, replacing any existing one."""
        session = ConversationSession(
            chat_id=chat_id,
            intent=intent,
            flow=flow,
            equipment_id=equipment_id,
        )
        self._sessions[chat_id] = session
        logger.info("Created session for chat %s: flow=%s", chat_id, flow)
        return session

    def update_session(self, session: ConversationSession) -> None:
        """Persist session updates (touch + store)."""
        session.touch()
        self._sessions[session.chat_id] = session

    def end_session(self, chat_id: str) -> None:
        """Remove a session."""
        if chat_id in self._sessions:
            del self._sessions[chat_id]
            logger.info("Ended session for chat %s", chat_id)

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count removed."""
        expired = [cid for cid, s in self._sessions.items() if s.is_expired()]
        for cid in expired:
            del self._sessions[cid]
        if expired:
            logger.info("Cleaned up %d expired conversation sessions", len(expired))
        return len(expired)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_manager_instance: Optional[TelegramConversationManager] = None


def get_conversation_manager() -> TelegramConversationManager:
    """Return singleton TelegramConversationManager."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = TelegramConversationManager()
    return _manager_instance
