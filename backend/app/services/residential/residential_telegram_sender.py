"""ResidentialTelegramSender — outbound Telegram wrapper for home bot.

Uses SENTINEL_HOME_BOT_TOKEN (@Sentinelaihomebot) to send residential
alerts. Strictly separate from commercial SENTRY_BOT_TOKEN.

Phase 214 — Wave 2
"""

from __future__ import annotations

import logging

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


class ResidentialTelegramSender:
    """
    Sends messages via @Sentinelaihomebot (home bot token).
    Wraps TelegramMessageSender with residential bot credentials.
    Never uses SENTRY_BOT_TOKEN — commercial and residential
    are strictly separated.
    """

    def __init__(self) -> None:
        token = settings.sentinel_home_bot_token
        if not token:
            logger.error("ResidentialTelegramSender: SENTINEL_HOME_BOT_TOKEN is not configured")
            self._token = ""
            self._base = ""
            self._client: httpx.AsyncClient | None = None
            return

        self._token = token
        self._base = f"https://api.telegram.org/bot{token}"
        self._client = httpx.AsyncClient(timeout=30.0)

    def _is_configured(self) -> bool:
        """Returns True if the home bot token is configured."""
        return bool(self._token)

    async def send_alert(
        self,
        chat_id: int,
        message: str,
        severity: str,  # "P1" | "P2"
        platform: str,  # "SOLARMAN" | "Victron VRM"
    ) -> bool:
        """
        Send a severity-coded alert to the residential user.

        Format:
          P1 → "🚨 P1: [message]"
          P2 → "⚠️ P2: [message]"
        """
        if not self._is_configured():
            return False

        prefix = "🚨" if severity == "P1" else "⚠️"
        text = f"{prefix} {severity}: [{platform}] {message}"

        return await self.send_text(chat_id, text)

    async def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
        reply_to_message_id: int | None = None,
    ) -> bool:
        """Send a plain text message. Returns True on success, False on failure."""
        if not self._is_configured():
            return False

        payload: dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self._base}/sendMessage", json=payload)
                result = resp.json()
                if not result.get("ok"):
                    logger.error("ResidentialTelegramSender sendMessage failed: %s", result)
                    return False
                return True
        except Exception as exc:
            logger.error("ResidentialTelegramSender send_text error: %s", exc)
            return False

    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        """Delete a message. Returns True on success, False on failure."""
        if not self._is_configured():
            return False

        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self._base}/deleteMessage", json=payload)
                result = resp.json()
                if not result.get("ok"):
                    logger.error("ResidentialTelegramSender deleteMessage failed: %s", result)
                    return False
                return True
        except Exception as exc:
            logger.error("ResidentialTelegramSender delete_message error: %s", exc)
            return False

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
    ) -> bool:
        """Answer a callback query (dismiss spinner or show alert). Returns True on success."""
        if not self._is_configured():
            return False

        payload: dict = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self._base}/answerCallbackQuery", json=payload)
                result = resp.json()
                if not result.get("ok"):
                    logger.warning("ResidentialTelegramSender answerCallbackQuery failed: %s", result)
                    return False
                return True
        except Exception as exc:
            logger.error("ResidentialTelegramSender answer_callback_query error: %s", exc)
            return False
