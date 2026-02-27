"""Generic Redis session store with in-memory fallback.

Write-through pattern: always update in-memory dict AND Redis.
Read: try Redis first, fall back to in-memory.

Used by DiagnosisFlowEngine and FeedbackCollectionService to persist
sessions across restarts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class RedisSessionStore:
    """Generic write-through session store (Redis + in-memory fallback).

    Args:
        prefix: Redis key prefix (e.g. "bms:diagnosis")
        ttl_seconds: TTL for Redis keys
        deserializer: Optional callable to reconstruct objects from dicts
    """

    def __init__(
        self,
        prefix: str,
        ttl_seconds: int = 3600,
        deserializer: Optional[Callable[[dict], Any]] = None,
    ) -> None:
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds
        self._deserializer = deserializer
        self._redis = None
        self._redis_checked = False
        self._memory: Dict[str, Any] = {}
        self._memory_expiry: Dict[str, datetime] = {}

    def _get_redis(self):
        """Lazy Redis connection with fallback."""
        if self._redis is not None:
            return self._redis
        if self._redis_checked:
            return None
        if not settings.redis_enabled:
            self._redis_checked = True
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
            logger.info("RedisSessionStore(%s) connected to Redis", self._prefix)
            return self._redis
        except Exception as e:
            logger.warning(
                "RedisSessionStore(%s) Redis unavailable, using memory fallback: %s",
                self._prefix,
                e,
            )
            self._redis_checked = True
            self._redis = None
            return None

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}:{session_id}"

    def put(self, session_id: str, data: Any) -> None:
        """Store session data (write-through)."""
        # Serialize
        if hasattr(data, "to_dict"):
            serialized = data.to_dict()
        elif isinstance(data, dict):
            serialized = data
        else:
            serialized = data

        json_str = json.dumps(serialized, default=str)

        # Always update in-memory
        self._memory[session_id] = data
        self._memory_expiry[session_id] = datetime.utcnow() + timedelta(seconds=self._ttl_seconds)

        # Write to Redis
        redis_client = self._get_redis()
        if redis_client:
            try:
                redis_client.setex(self._key(session_id), self._ttl_seconds, json_str)
            except Exception as e:
                logger.warning("RedisSessionStore(%s) write failed: %s", self._prefix, e)

    def get(self, session_id: str) -> Optional[Any]:
        """Retrieve session data. Returns original object or deserialized dict."""
        # Try in-memory first (fastest)
        if session_id in self._memory:
            expiry = self._memory_expiry.get(session_id)
            if expiry and datetime.utcnow() > expiry:
                self._memory.pop(session_id, None)
                self._memory_expiry.pop(session_id, None)
            else:
                return self._memory[session_id]

        # Try Redis
        redis_client = self._get_redis()
        if redis_client:
            try:
                raw = redis_client.get(self._key(session_id))
                if raw:
                    data = json.loads(raw)
                    # Reconstruct object if deserializer provided
                    if self._deserializer:
                        obj = self._deserializer(data)
                    else:
                        obj = data
                    # Cache in memory
                    self._memory[session_id] = obj
                    self._memory_expiry[session_id] = datetime.utcnow() + timedelta(seconds=self._ttl_seconds)
                    return obj
            except Exception as e:
                logger.warning("RedisSessionStore(%s) read failed: %s", self._prefix, e)

        return None

    def delete(self, session_id: str) -> None:
        """Remove session data."""
        self._memory.pop(session_id, None)
        self._memory_expiry.pop(session_id, None)

        redis_client = self._get_redis()
        if redis_client:
            try:
                redis_client.delete(self._key(session_id))
            except Exception as e:
                logger.warning("RedisSessionStore(%s) delete failed: %s", self._prefix, e)

    def keys(self) -> list[str]:
        """Return all active session IDs (from memory only — best effort)."""
        now = datetime.utcnow()
        return [sid for sid, expiry in self._memory_expiry.items() if expiry > now and sid in self._memory]
