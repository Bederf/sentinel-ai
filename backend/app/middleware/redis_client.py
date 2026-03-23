"""
Redis client for distributed locks and caching.

Used for:
- Decision execution locks (60s TTL)
- Session state caching
- Rate limiting (via slowapi)
"""

import logging
from typing import Optional

import redis.asyncio as redis
from redis.asyncio import Redis

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Global redis client instance
_redis_client: Optional[Redis] = None


async def get_redis_client() -> Redis:
    """Get or create async Redis client."""
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = await redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_inactivity_timeout=10,
            )
            # Test connection
            await _redis_client.ping()
            logger.info(f"Redis client connected to {settings.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            # Return a stub client that always fails gracefully
            return _StubRedisClient()

    return _redis_client


class _StubRedisClient:
    """Stub Redis client for when Redis is unavailable."""

    async def set(self, key: str, value: str, **kwargs) -> bool:
        """Stub set returns False (lock not acquired)."""
        logger.warning(f"Redis unavailable: stub set({key}) returning False")
        return False

    async def get(self, key: str) -> Optional[str]:
        """Stub get returns None."""
        return None

    async def delete(self, key: str) -> int:
        """Stub delete returns 0 (no keys deleted)."""
        return 0

    async def ping(self) -> bool:
        """Stub ping returns False."""
        return False

    async def close(self):
        """Stub close is no-op."""
        pass


# Create a singleton instance for use in endpoints
# This will be initialized lazily on first use
class _LazyRedisClient:
    """Lazy-initializing Redis client wrapper."""

    def __init__(self):
        self._client = None

    async def _ensure_client(self):
        """Ensure client is initialized."""
        if self._client is None:
            self._client = await get_redis_client()

    async def set(self, key: str, value: str, nx: bool = False, ex: int = None) -> bool:
        """Set a key with optional NX (only if not exists) and EX (expire in seconds)."""
        await self._ensure_client()
        return await self._client.set(key, value, nx=nx, ex=ex)

    async def get(self, key: str) -> Optional[str]:
        """Get a key value."""
        await self._ensure_client()
        return await self._client.get(key)

    async def delete(self, key: str) -> int:
        """Delete a key. Returns number of keys deleted."""
        await self._ensure_client()
        return await self._client.delete(key)

    async def ping(self) -> bool:
        """Ping Redis."""
        await self._ensure_client()
        return await self._client.ping()

    async def close(self):
        """Close connection."""
        if self._client:
            await self._client.close()


redis_client = _LazyRedisClient()
