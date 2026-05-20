"""WhatsApp Conversation Manager — in-memory session state for staff onboarding."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MINUTES = 30


@dataclass
class WhatsAppSession:
    """State for WhatsApp onboarding or complaint flow."""

    phone: str
    site_id: str
    flow: str  # "onboarding" | "complaint"
    step: int = 0  # 0=name, 1=location
    name: str = ""
    location: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        self.last_activity = datetime.utcnow()

    def is_expired(self) -> bool:
        delta = datetime.utcnow() - self.last_activity
        return delta.total_seconds() > SESSION_TIMEOUT_MINUTES * 60


class WhatsAppConversationManager:
    """Manages in-memory WhatsApp sessions keyed by phone number."""

    def __init__(self) -> None:
        self._sessions: dict[str, WhatsAppSession] = {}

    def get_session(self, phone: str) -> WhatsAppSession | None:
        session = self._sessions.get(phone)
        if session and session.is_expired():
            logger.info("WhatsApp session expired for %s", phone)
            del self._sessions[phone]
            return None
        return session

    def create_session(self, phone: str, site_id: str, flow: str = "onboarding") -> WhatsAppSession:
        session = WhatsAppSession(phone=phone, site_id=site_id, flow=flow)
        self._sessions[phone] = session
        return session

    def end_session(self, phone: str) -> None:
        self._sessions.pop(phone, None)


_mgr = WhatsAppConversationManager()


def get_whatsapp_conversation_manager() -> WhatsAppConversationManager:
    return _mgr