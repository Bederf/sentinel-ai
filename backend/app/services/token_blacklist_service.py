"""Token blacklist service using Redis.

Stores revoked JWT tokens by their jti (JWT ID) claim.
Tokens are automatically removed from Redis when their TTL expires.

Phase 65-02: Token Security & Rate Limiting

Usage:
    from app.services.token_blacklist_service import token_blacklist

    # Blacklist a token
    token_blacklist.blacklist_token(jti, ttl_seconds=900)

    # Check if token is blacklisted
    if token_blacklist.is_blacklisted(jti):
        raise HTTPException(401, "Token revoked")
"""

import logging
from typing import Optional

from app.config.settings import settings
from app.services.cache_service import cache

logger = logging.getLogger(__name__)


class TokenBlacklistService:
    """Redis-backed token blacklist with automatic TTL cleanup.

    Tokens are stored with TTL matching their remaining lifetime,
    so they auto-expire from Redis without manual cleanup.
    """

    def __init__(self):
        self._enabled = settings.redis_enabled

    def _get_redis_key(self, jti: str) -> str:
        """Get Redis key for a blacklisted token.

        Args:
            jti: JWT ID claim

        Returns:
            Redis key string
        """
        return f"token:blacklist:{jti}"

    def blacklist_token(self, jti: str, ttl_seconds: int) -> bool:
        """Add a token to the blacklist.

        Args:
            jti: JWT ID claim
            ttl_seconds: Time-to-live in seconds (should match token remaining lifetime)

        Returns:
            True if successfully blacklisted, False otherwise
        """
        if not self._enabled:
            logger.debug("Redis disabled - skipping blacklist write")
            return False

        try:
            key = self._get_redis_key(jti)
            # Store with TTL so token auto-expires
            cache.set(key, "revoked", ttl=ttl_seconds)
            logger.info(f"Blacklisted token {jti} (TTL: {ttl_seconds}s)")
            return True
        except Exception as e:
            logger.error(f"Failed to blacklist token {jti}: {e}")
            return False

    def is_blacklisted(self, jti: str) -> bool:
        """Check if a token is blacklisted.

        Args:
            jti: JWT ID claim

        Returns:
            True if token is blacklisted, False otherwise
        """
        if not self._enabled:
            # Graceful degradation: if Redis unavailable, assume not blacklisted
            # This allows the system to continue operating with token expiration
            return False

        try:
            key = self._get_redis_key(jti)
            result = cache.get(key)
            return result is not None
        except Exception as e:
            logger.warning(f"Blacklist check failed for {jti}: {e}")
            return False


# Singleton instance
token_blacklist = TokenBlacklistService()
