"""Token blacklist service using Redis with local cache fallback.

Stores revoked JWT tokens by their jti (JWT ID) claim.
Tokens are automatically removed from Redis when their TTL expires.

Local cache fallback ensures tokens explicitly revoked remain blocked
even during Redis outages — the fail-open gap only affects tokens
that were never revoked (the safe case).

Phase 65-02: Token Security & Rate Limiting
Phase 61.9: Local cache fallback (Redis outage hardening)

Usage:
    from app.services.token_blacklist_service import token_blacklist

    # Blacklist a token
    token_blacklist.blacklist_token(jti, ttl_seconds=900)

    # Check if token is blacklisted
    if token_blacklist.is_blacklisted(jti):
        raise HTTPException(401, "Token revoked")

    # On startup — warm local cache from Redis
    await token_blacklist.warm_cache()
"""

import logging
import time
from typing import Any

from app.config.settings import settings
from app.services.cache_service import cache

logger = logging.getLogger(__name__)

# Key prefix for blacklist entries in Redis
_BL_PREFIX = "token:blacklist:"


class TokenBlacklistService:
    """Redis-backed token blacklist with local in-process cache.

    Local cache is the primary source of truth for tokens explicitly
    revoked during this process's lifetime. Redis is the persistent
    store and source of truth across restarts.

    Fail-open behavior (only for tokens NOT in local cache):
    - Redis down → local cache miss → returns False (accept token)
    - This is safe because the only tokens that bypass blacklist are
      those never revoked, which is the correct default.
    """

    def __init__(self):
        self._enabled = settings.redis_enabled
        # Local in-process cache: jti -> expiry timestamp (float)
        self._local_cache: dict[str, float] = {}

    def _get_redis_key(self, jti: str) -> str:
        """Get Redis key for a blacklisted token."""
        return f"{_BL_PREFIX}{jti}"

    def blacklist_token(self, jti: str, ttl_seconds: int) -> bool:
        """Add a token to the blacklist (local cache + Redis).

        Args:
            jti: JWT ID claim
            ttl_seconds: Time-to-live in seconds (should match remaining token lifetime)

        Returns:
            True if successfully blacklisted, False otherwise
        """
        if ttl_seconds <= 0:
            # Token already expired or invalid TTL — nothing to persist
            return True

        expiry = time.time() + ttl_seconds

        # Always write local cache first (zero-latency, always available)
        self._local_cache[jti] = expiry

        if not self._enabled:
            logger.debug("Redis disabled — token cached locally only")
            return True

        try:
            key = self._get_redis_key(jti)
            cache.set(key, "revoked", ttl=ttl_seconds)
            logger.info(f"Blacklisted token {jti} (TTL: {ttl_seconds}s)")
            return True
        except Exception as e:
            logger.warning(f"Redis blacklist write failed for {jti} (local cache updated): {e}")
            return False

    def is_blacklisted(self, jti: str) -> bool:
        """Check if a token is blacklisted (local cache → Redis).

        Args:
            jti: JWT ID claim

        Returns:
            True if token is blacklisted, False otherwise
        """
        now = time.time()

        # Check local cache first (zero-latency, always available)
        if jti in self._local_cache:
            if now < self._local_cache[jti]:
                return True
            # Expired — evict from local cache
            del self._local_cache[jti]

        # If Redis is disabled, only local cache was populated
        if not self._enabled:
            return False

        # Check Redis
        try:
            key = self._get_redis_key(jti)
            result = cache.get(key)
            return result is not None
        except Exception as e:
            logger.debug(f"Redis blacklist check failed for {jti}: {e}")
            # Fail-open: if Redis is unreachable, we can't confirm revocation
            # This only affects tokens that were never explicitly blacklisted
            return False

    async def warm_cache(self) -> int:
        """Populate local cache from Redis on startup.

        Loads all active blacklist entries so process restart doesn't
        create a revocation gap for tokens that were already revoked.

        Returns:
            Number of entries loaded into local cache
        """
        if not self._enabled:
            logger.info("warm_cache skipped — Redis disabled")
            return 0

        client = cache._get_client()
        if not client:
            logger.warning("warm_cache: Redis not available, starting cold")
            return 0

        try:
            count = 0
            # scan_iter is synchronous — use iter() with next()
            for key in client.scan_iter(match=f"{_BL_PREFIX}*", count=500):
                ttl = client.ttl(key)
                if ttl > 0:
                    jti = key.removeprefix(_BL_PREFIX)
                    self._local_cache[jti] = time.time() + ttl
                    count += 1

            logger.info(f"warm_cache: loaded {count} blacklist entries")
            return count
        except Exception as e:
            logger.warning(f"warm_cache failed — starting cold: {e}")
            return 0

    def get_stats(self) -> dict[str, Any]:
        """Return blacklist stats for monitoring."""
        now = time.time()
        # Evict expired entries while counting
        expired = [jti for jti, exp in self._local_cache.items() if now >= exp]
        for jti in expired:
            del self._local_cache[jti]

        return {
            "local_cache_size": len(self._local_cache),
            "redis_enabled": self._enabled,
        }


# Singleton instance
token_blacklist = TokenBlacklistService()
