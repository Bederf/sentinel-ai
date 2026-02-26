"""
Telegram notification provider — wraps existing sentry CLI integration.

Uses subprocess to call sentry gateway for Telegram message delivery.
Phase 102: Direct technician notifications (in addition to FM group broadcast).
"""

import os
import subprocess
import logging

from .base_provider import BaseNotificationProvider, NotificationResult
from app.services.sentry_integration.config import get_sentry_bot_cli

logger = logging.getLogger(__name__)


class TelegramProvider(BaseNotificationProvider):
    """Send notifications via Telegram using sentry CLI."""

    def __init__(self):
        self.bot_token = os.getenv("SENTRY_BOT_TOKEN", "")
        self.webhook_secret = os.getenv("SENTRY_WEBHOOK_SECRET", "")
        self._cli_command = get_sentry_bot_cli()

    @property
    def channel_name(self) -> str:
        return "telegram"

    @property
    def provider_name(self) -> str:
        return "sentry"

    def is_enabled(self) -> bool:
        """Check if sentry CLI is available and configured."""
        return bool(self.bot_token and self.webhook_secret)

    async def test_connection(self) -> bool:
        """Test if sentry CLI is available."""
        try:
            result = subprocess.run([self._cli_command, "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("%s CLI not available", self._cli_command)
            return False

    async def send(self, recipient: str, title: str, body: str, **kwargs) -> NotificationResult:
        """Send Telegram message via sentry CLI.

        Args:
            recipient: Telegram user ID or chat ID
            title: Message title
            body: Message body
            **kwargs: Additional parameters (unused for Telegram)

        Returns:
            NotificationResult with success status
        """
        if not self.is_enabled():
            return NotificationResult(
                success=False,
                error_code="not_configured",
                error_message="Telegram provider not configured (missing SENTRY_BOT_TOKEN)",
            )

        try:
            # Format message
            message = f"{title}\n\n{body}"

            # Call sentry CLI
            result = subprocess.run(
                [
                    self._cli_command,
                    "message",
                    "send",
                    "--channel",
                    "telegram",
                    "--target",
                    str(recipient),
                    "--message",
                    message,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info(f"Telegram message sent to {recipient}")
                return NotificationResult(
                    success=True, message_id=f"telegram-{recipient}", provider_response={"stdout": result.stdout}
                )
            else:
                error = result.stderr or "Unknown error"
                logger.error(f"sentry CLI error: {error}")
                return NotificationResult(
                    success=False,
                    error_code="send_failed",
                    error_message=error,
                    provider_response={"stderr": result.stderr},
                )

        except subprocess.TimeoutExpired:
            return NotificationResult(
                success=False, error_code="timeout", error_message="sentry bot request timed out after 30 seconds"
            )
        except FileNotFoundError:
            return NotificationResult(
                success=False, error_code="not_found", error_message=f"{self._cli_command} CLI not found in PATH"
            )
        except Exception as e:
            logger.error(f"Telegram provider error: {e}")
            return NotificationResult(success=False, error_code="exception", error_message=str(e))
