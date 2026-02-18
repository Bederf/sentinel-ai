"""
Telegram notification provider — wraps existing sentrybot CLI integration.

Uses subprocess to call sentrybot for Telegram message delivery.
Phase 102: Direct technician notifications (in addition to FM group broadcast).
"""

import os
import subprocess
import logging

from .base_provider import BaseNotificationProvider, NotificationResult

logger = logging.getLogger(__name__)


class TelegramProvider(BaseNotificationProvider):
    """Send notifications via Telegram using sentrybot CLI."""

    def __init__(self):
        self.bot_token = os.getenv("CLAWD_BOT_TOKEN", "")
        self.webhook_secret = os.getenv("CLAWD_WEBHOOK_SECRET", "")

    @property
    def channel_name(self) -> str:
        return "telegram"

    @property
    def provider_name(self) -> str:
        return "sentrybot"

    def is_enabled(self) -> bool:
        """Check if sentrybot is available and configured."""
        return bool(self.bot_token and self.webhook_secret)

    async def test_connection(self) -> bool:
        """Test if sentrybot CLI is available."""
        try:
            result = subprocess.run(
                ["sentrybot", "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("sentrybot CLI not available")
            return False

    async def send(
        self,
        recipient: str,
        title: str,
        body: str,
        **kwargs
    ) -> NotificationResult:
        """Send Telegram message via sentrybot CLI.

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
                error_message="Telegram provider not configured (missing CLAWD_BOT_TOKEN)"
            )

        try:
            # Format message
            message = f"{title}\n\n{body}"

            # Call sentrybot
            result = subprocess.run(
                [
                    "sentrybot", "message", "send",
                    "--channel", "telegram",
                    "--target", str(recipient),
                    "--message", message,
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info(f"Telegram message sent to {recipient}")
                return NotificationResult(
                    success=True,
                    message_id=f"telegram-{recipient}",
                    provider_response={"stdout": result.stdout}
                )
            else:
                error = result.stderr or "Unknown error"
                logger.error(f"sentrybot error: {error}")
                return NotificationResult(
                    success=False,
                    error_code="send_failed",
                    error_message=error,
                    provider_response={"stderr": result.stderr}
                )

        except subprocess.TimeoutExpired:
            return NotificationResult(
                success=False,
                error_code="timeout",
                error_message="sentrybot request timed out after 30 seconds"
            )
        except FileNotFoundError:
            return NotificationResult(
                success=False,
                error_code="not_found",
                error_message="sentrybot CLI not found in PATH"
            )
        except Exception as e:
            logger.error(f"Telegram provider error: {e}")
            return NotificationResult(
                success=False,
                error_code="exception",
                error_message=str(e)
            )
