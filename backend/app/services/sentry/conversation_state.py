from __future__ import annotations

import json
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import redis

from app.config.settings import settings


class ConversationStateManager:
    """
    Redis-backed conversation state for multi-step Telegram flows.
    Key: conv:{chat_id}
    TTL: 600s (10-minute idle timeout)
    Pattern: sync redis.from_url() — matches session_service.py exactly.
    """

    TTL_SECONDS = 600
    KEY_PREFIX = "conv:"

    @dataclass
    class ConversationState:
        flow: str  # e.g. "residential_onboarding"
        step: str  # e.g. "awaiting_email"
        data: dict  # Accumulated data (credentials cleared after auth)
        created_at: str
        updated_at: str

    def __init__(self) -> None:
        self._redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._memory: dict[int, tuple[dict, float]] = {}  # chat_id → (state_dict, expiry)

    def _key(self, chat_id: int) -> str:
        return f"{self.KEY_PREFIX}{chat_id}"

    def _now(self) -> float:
        return time.time()

    def get(self, chat_id: int) -> ConversationState | None:
        """Get state if present and not expired. Checks memory fallback if Redis unavailable."""
        key = self._key(chat_id)
        try:
            raw = self._redis.get(key)
            if raw:
                self._redis.expire(key, self.TTL_SECONDS)
                d = json.loads(raw)
                return self.ConversationState(**d)
        except Exception:
            pass
        # Memory fallback
        if chat_id in self._memory:
            state_dict, expiry = self._memory[chat_id]
            if time.time() < expiry:
                return self.ConversationState(**state_dict)
            del self._memory[chat_id]
        return None

    def set(self, chat_id: int, state: ConversationState) -> None:
        """Set state with TTL. Clears memory fallback if present."""
        key = self._key(chat_id)
        state.updated_at = datetime.now(UTC).isoformat()
        if state.created_at == "":
            state.created_at = state.updated_at
        payload = json.dumps(asdict(state))
        try:
            self._redis.setex(key, self.TTL_SECONDS, payload)
            if chat_id in self._memory:
                del self._memory[chat_id]
        except Exception:
            self._memory[chat_id] = (asdict(state), time.time() + self.TTL_SECONDS)

    def clear(self, chat_id: int) -> None:
        """Delete state. Used after auth step and after onboarding completes."""
        key = self._key(chat_id)
        with suppress(Exception):
            self._redis.delete(key)
        self._memory.pop(chat_id, None)

    def extend_ttl(self, chat_id: int) -> None:
        """Extend TTL on state refresh (called on each user interaction)."""
        key = self._key(chat_id)
        with suppress(Exception):
            self._redis.expire(key, self.TTL_SECONDS)
