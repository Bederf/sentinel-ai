"""Telegram notification provider — direct Bot API via httpx."""

import logging
import os

import httpx

from .base_provider import BaseNotificationProvider, NotificationResult

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


class TelegramProvider(BaseNotificationProvider):
    """Send notifications via Telegram Bot API."""

    def __init__(self):
        from app.config.settings import settings

        self.bot_token = settings.telegram_bot_token or os.getenv("SENTRY_BOT_TOKEN", "")
        self.default_chat_id = settings.telegram_alert_chat_id or ""

    @property
    def channel_name(self) -> str:
        return "telegram"

    @property
    def provider_name(self) -> str:
        return "telegram_bot_api"

    def is_enabled(self) -> bool:
        return bool(self.bot_token)

    async def test_connection(self) -> bool:
        if not self.is_enabled():
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{TELEGRAM_API_BASE}{self.bot_token}/getMe")
                return resp.status_code == 200
        except Exception:
            return False

    def send_budget_alert(self, site_id: str, current: int, budget: int, pct: float) -> None:
        """Fire-and-forget budget alert via ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor

        body = (
            f"Site: {site_id}\n"
            f"Usage: {current:,} / {budget:,} tokens ({pct:.0f}%)\n"
            f"Background LLM calls will be blocked at 100%."
        )
        payload = {
            "chat_id": self.default_chat_id or "",
            "text": f"⚠️ SENTINEL Token Budget Alert\n\n{body}",
            "parse_mode": "Markdown",
        }

        def _send():
            try:
                import httpx

                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(
                        f"{TELEGRAM_API_BASE}{self.bot_token}/sendMessage",
                        json=payload,
                    )
                    resp.raise_for_status()
                    logger.info("Budget alert sent to %s for %s", self.default_chat_id, site_id)
            except Exception as e:
                logger.warning("Failed to send budget alert Telegram: %s", e)

        if self.is_enabled():
            ThreadPoolExecutor(max_workers=1).submit(_send)

    async def send(self, recipient: str, title: str, body: str, **kwargs) -> NotificationResult:
        if not self.is_enabled():
            return NotificationResult(
                success=False,
                error_code="not_configured",
                error_message="Telegram provider not configured (missing bot token)",
            )

        chat_id = recipient or self.default_chat_id
        if not chat_id:
            return NotificationResult(
                success=False,
                error_code="no_recipient",
                error_message="No chat_id provided and no default configured",
            )

        try:
            message = f"*{title}*\n\n{body}"
            url = f"{TELEGRAM_API_BASE}{self.bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

                message_id = str(data.get("result", {}).get("message_id", "unknown"))
                logger.info(f"Telegram message sent to {chat_id}, message_id: {message_id}")

                try:
                    from app.services.ai_usage_tracker import usage_tracker

                    usage_tracker.record_message("telegram", source="alert")
                except Exception:
                    pass

                return NotificationResult(
                    success=True,
                    message_id=message_id,
                    provider_response=data,
                )

        except httpx.TimeoutException:
            return NotificationResult(
                success=False,
                error_code="timeout",
                error_message="Telegram API request timed out",
            )
        except Exception as e:
            logger.error(f"Telegram provider error: {e}")
            return NotificationResult(success=False, error_code="exception", error_message=str(e))
