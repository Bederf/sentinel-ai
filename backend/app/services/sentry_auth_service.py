"""
Sentry JWT Authentication Service

Manages JWT token generation and refresh for Sentry bot to access SENTINEL API endpoints.
Runs as a service in the background, automatically refreshing tokens before expiry.
"""

import asyncio
import logging
import httpx
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Global JWT token holder (in-memory cache)
_jwt_cache = {
    "token": None,
    "expires_at": None,
    "last_refresh": None,
}


class SentryAuthService:
    """Manages JWT authentication for Sentry bot."""

    def __init__(
        self,
        api_url: str = "http://localhost:9095",
        sentry_username: Optional[str] = None,
        sentry_password: Optional[str] = None,
    ):
        """
        Initialize Sentry auth service.

        Args:
            api_url: SENTINEL backend API URL
            sentry_username: Sentry service account username (from env or init)
            sentry_password: Sentry service account password (from env or init)
        """
        self.api_url = api_url.rstrip("/")
        self.sentry_username = sentry_username or self._get_from_env("SENTRY_BOT_USERNAME")
        self.sentry_password = sentry_password or self._get_from_env("SENTRY_BOT_PASSWORD")
        self.refresh_interval = 60 * 60  # Refresh every hour
        self._refresh_task: Optional[asyncio.Task] = None

    @staticmethod
    def _get_from_env(key: str) -> Optional[str]:
        """Get value from environment."""
        import os

        return os.getenv(key)

    async def login(self) -> bool:
        """
        Authenticate Sentry bot and get JWT token.

        Returns:
            True if login successful, False otherwise
        """
        if not self.sentry_username or not self.sentry_password:
            logger.error(
                "Sentry bot credentials not configured. Set SENTRY_BOT_USERNAME and SENTRY_BOT_PASSWORD in .env"
            )
            return False

        try:
            url = f"{self.api_url}/api/auth/login"
            payload = {
                "username": self.sentry_username,
                "password": self.sentry_password,
            }

            async with httpx.AsyncClient(timeout=10) as client:
                logger.info(f"Sentry bot logging in as {self.sentry_username}...")
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)

                    # Store token and expiry time
                    _jwt_cache["token"] = token
                    _jwt_cache["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)
                    _jwt_cache["last_refresh"] = datetime.utcnow()

                    logger.info(f"✓ Sentry bot JWT token obtained (expires in {expires_in}s)")
                    return True
                elif response.status_code == 401:
                    logger.error(f"Sentry bot login failed: Invalid credentials for {self.sentry_username}")
                    return False
                else:
                    logger.error(f"Sentry bot login error ({response.status_code}): {response.text}")
                    return False

        except httpx.HTTPError as e:
            logger.error(f"Sentry bot login HTTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Sentry bot login unexpected error: {e}")
            return False

    def get_token(self) -> Optional[str]:
        """
        Get current JWT token.

        Returns token if valid, None if expired or unavailable.
        """
        token = _jwt_cache.get("token")
        expires_at = _jwt_cache.get("expires_at")

        if not token or not expires_at:
            return None

        # Check if token is expired (with 60s buffer)
        if datetime.utcnow() >= (expires_at - timedelta(seconds=60)):
            logger.warning("Sentry JWT token expired or expiring soon")
            return None

        return token

    async def get_token_or_refresh(self) -> Optional[str]:
        """
        Get current token, refreshing if needed.

        Returns:
            Valid JWT token or None if refresh failed
        """
        token = self.get_token()

        if not token:
            # Token missing or expired, refresh
            if await self.login():
                return _jwt_cache.get("token")
            else:
                return None

        return token

    async def start_background_refresh(self):
        """Start background task that refreshes token periodically."""
        if self._refresh_task:
            logger.warning("Refresh task already running")
            return

        logger.info("Starting Sentry JWT token refresh task...")
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop_background_refresh(self):
        """Stop background refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
            logger.info("Stopped Sentry JWT token refresh task")

    async def _refresh_loop(self):
        """Background loop that refreshes token periodically."""
        try:
            while True:
                await asyncio.sleep(self.refresh_interval)
                logger.debug("Refreshing Sentry JWT token...")
                if await self.login():
                    logger.debug("Sentry JWT token refreshed successfully")
                else:
                    logger.warning("Failed to refresh Sentry JWT token")
        except asyncio.CancelledError:
            logger.info("Sentry token refresh loop cancelled")
            raise


# Global service instance
_sentry_auth_service: Optional[SentryAuthService] = None


def initialize_sentry_auth(
    api_url: str = "http://localhost:9095",
    sentry_username: Optional[str] = None,
    sentry_password: Optional[str] = None,
) -> SentryAuthService:
    """
    Initialize global Sentry auth service.

    Should be called on app startup (in events.py).
    """
    global _sentry_auth_service

    _sentry_auth_service = SentryAuthService(
        api_url=api_url,
        sentry_username=sentry_username,
        sentry_password=sentry_password,
    )

    logger.info("Sentry auth service initialized")
    return _sentry_auth_service


def get_sentry_auth_service() -> Optional[SentryAuthService]:
    """Get global Sentry auth service instance."""
    return _sentry_auth_service


async def get_sentry_jwt_token() -> Optional[str]:
    """
    Get valid JWT token for Sentry bot API calls.

    Automatically refreshes if expired.
    """
    service = get_sentry_auth_service()
    if not service:
        logger.error("Sentry auth service not initialized")
        return None

    return await service.get_token_or_refresh()


def get_sentry_jwt_headers() -> dict:
    """
    Get HTTP headers dict with Sentry JWT token.

    Returns headers with Authorization header, or empty dict if token unavailable.
    """
    token = _jwt_cache.get("token")

    if not token:
        logger.warning("Sentry JWT token not available, requests may fail with 401")
        return {}

    return {"Authorization": f"Bearer {token}"}
