"""Session tracking service for auth refresh sessions.

Sessions are keyed by refresh token JTI and allow targeted revocation.
Primary store is Redis; if unavailable, an in-memory fallback is used.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class SessionService:
    """Manage user sessions and support revocation flows."""

    def __init__(self) -> None:
        self._redis = None
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._ttl_seconds = settings.jwt_refresh_token_ttl_days * 24 * 60 * 60

    def _get_redis(self):
        if self._redis is not None:
            return self._redis
        if not settings.redis_enabled:
            return None
        try:
            import redis

            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis.ping()
            return self._redis
        except Exception as e:
            logger.warning("Session Redis unavailable, using memory fallback: %s", e)
            self._redis = None
            return None

    @staticmethod
    def _session_key(user_id: str, session_id: str) -> str:
        return f"session:{user_id}:{session_id}"

    @staticmethod
    def _session_index_key(user_id: str) -> str:
        return f"session:index:{user_id}"

    @staticmethod
    def _iso_now() -> str:
        return datetime.utcnow().isoformat()

    def create_session(
        self,
        user_id: str,
        ip: Optional[str],
        user_agent: Optional[str],
        token_jti: str,
    ) -> str:
        """Create and persist a session entry."""
        session_id = str(uuid.uuid4())
        record = {
            "session_id": session_id,
            "user_id": user_id,
            "ip": ip or "unknown",
            "user_agent": user_agent or "",
            "token_jti": token_jti,
            "created_at": self._iso_now(),
            "revoked": False,
            "revoked_at": None,
        }
        redis_client = self._get_redis()
        if redis_client:
            key = self._session_key(user_id, session_id)
            idx = self._session_index_key(user_id)
            redis_client.setex(key, self._ttl_seconds, json.dumps(record))
            redis_client.sadd(idx, session_id)
            redis_client.expire(idx, self._ttl_seconds)
        else:
            record["expires_at"] = (
                datetime.utcnow() + timedelta(seconds=self._ttl_seconds)
            ).isoformat()
            self._memory[self._session_key(user_id, session_id)] = record
        return session_id

    def _read_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        redis_client = self._get_redis()
        key = self._session_key(user_id, session_id)
        if redis_client:
            raw = redis_client.get(key)
            return json.loads(raw) if raw else None
        record = self._memory.get(key)
        if not record:
            return None
        expires_at = record.get("expires_at")
        if expires_at and datetime.utcnow() > datetime.fromisoformat(expires_at):
            self._memory.pop(key, None)
            return None
        return record

    def _write_session(self, user_id: str, session_id: str, data: Dict[str, Any]) -> None:
        redis_client = self._get_redis()
        key = self._session_key(user_id, session_id)
        if redis_client:
            redis_client.setex(key, self._ttl_seconds, json.dumps(data))
            return
        self._memory[key] = data

    def get_active_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Return active (non-revoked) sessions for user."""
        redis_client = self._get_redis()
        sessions: List[Dict[str, Any]] = []
        if redis_client:
            idx = self._session_index_key(user_id)
            session_ids = list(redis_client.smembers(idx) or [])
            for session_id in session_ids:
                record = self._read_session(user_id, session_id)
                if not record:
                    redis_client.srem(idx, session_id)
                    continue
                if not record.get("revoked", False):
                    sessions.append(record)
        else:
            prefix = f"session:{user_id}:"
            for key, value in list(self._memory.items()):
                if not key.startswith(prefix):
                    continue
                record = self._read_session(user_id, value.get("session_id", ""))
                if record and not record.get("revoked", False):
                    sessions.append(record)

        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return sessions

    def revoke_session(self, user_id: str, session_id: str) -> bool:
        """Mark session revoked and blacklist its token JTI."""
        record = self._read_session(user_id, session_id)
        if not record:
            return False
        if record.get("revoked", False):
            return True

        record["revoked"] = True
        record["revoked_at"] = self._iso_now()
        self._write_session(user_id, session_id, record)

        jti = record.get("token_jti")
        if jti:
            try:
                from app.services.token_blacklist_service import token_blacklist

                token_blacklist.blacklist_token(jti, self._ttl_seconds)
            except Exception as e:
                logger.warning("Failed blacklisting session token %s: %s", jti, e)
        return True

    def revoke_all_sessions(self, user_id: str) -> int:
        """Revoke all active sessions for a user. Returns count revoked."""
        sessions = self.get_active_sessions(user_id)
        revoked_count = 0
        for session in sessions:
            session_id = session.get("session_id")
            if session_id and self.revoke_session(user_id, session_id):
                revoked_count += 1
        return revoked_count

    def find_session_by_token_jti(self, user_id: str, token_jti: str) -> Optional[Dict[str, Any]]:
        """Find a user session by refresh token JTI."""
        sessions = self.get_active_sessions(user_id)
        for session in sessions:
            if session.get("token_jti") == token_jti:
                return session
        return None


session_service = SessionService()
