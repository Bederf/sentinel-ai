"""Telegram Message Sender — outbound Telegram Bot API wrapper.

Isolates all Telegram API details (sendMessage, answerCallbackQuery,
editMessageReplyMarkup) from flow handlers.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration is missing."""


@dataclass
class InlineButton:
    """A single inline keyboard button."""

    label: str  # Text shown on button
    callback_data: str  # Max 64 bytes: "{flow}:{action}:{value}"


@dataclass
class InlineKeyboard:
    """Inline keyboard with rows of buttons."""

    rows: list[list[InlineButton]] = field(default_factory=list)

    def to_telegram(self) -> dict:
        """Convert to Telegram API inline_keyboard format."""
        return {
            "inline_keyboard": [
                [{"text": btn.label, "callback_data": btn.callback_data} for btn in row] for row in self.rows
            ]
        }


class TelegramMessageSender:
    """Wraps outbound Telegram Bot API calls."""

    def __init__(self, bot_token: str):
        self._token = bot_token
        self._base = f"https://api.telegram.org/bot{bot_token}"

    async def send_text(
        self,
        chat_id: str,
        text: str,
        keyboard: InlineKeyboard | None = None,
        parse_mode: str = "HTML",
    ) -> dict:
        """Send a text message, optionally with an inline keyboard."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if keyboard:
            payload["reply_markup"] = keyboard.to_telegram()

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self._base}/sendMessage", json=payload)
            result = resp.json()
            if not result.get("ok"):
                logger.error("Telegram sendMessage failed: %s", result)
            return result

    async def send_voice(
        self,
        chat_id: str,
        audio_path: str,
        caption: str | None = None,
    ) -> dict:
        """Send a voice/audio message using Telegram's sendAudio API.

        Args:
            chat_id: Target chat ID
            audio_path: Local path to the audio file (OGG/Opus preferred, MP3 also works)
            caption: Optional text caption shown above audio

        Returns:
            Telegram API response dict
        """
        if not os.path.exists(audio_path):
            logger.error("Audio file not found: %s", audio_path)
            return {"ok": False, "error": "audio_file_not_found"}

        # Determine mime type from extension
        ext = audio_path.lower().split(".")[-1]
        mime_types = {"ogg": "audio/ogg", "mp3": "audio/mpeg", "oga": "audio/ogg", "opus": "audio/opus"}
        mime_type = mime_types.get(ext, "audio/mpeg")

        with open(audio_path, "rb") as f:
            audio_data = f.read()

        payload: dict[str, Any] = {
            "chat_id": chat_id,
        }
        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = "HTML"

        files: dict[str, Any] = {
            "audio": (os.path.basename(audio_path), audio_data, mime_type),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}/sendAudio",
                data=payload,
                files=files,
            )
            result = resp.json()
            if not result.get("ok"):
                logger.error("Telegram sendAudio failed: %s", result)
            return result

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
    ) -> None:
        """Dismiss the loading spinner on a button tap."""
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self._base}/answerCallbackQuery", json=payload)
            result = resp.json()
            if not result.get("ok"):
                logger.warning("Telegram answerCallbackQuery failed: %s", result)

    async def edit_message_reply_markup(
        self,
        chat_id: str,
        message_id: int,
        keyboard: InlineKeyboard | None = None,
    ) -> None:
        """Remove or replace buttons after a selection is made."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if keyboard:
            payload["reply_markup"] = keyboard.to_telegram()
        else:
            # Remove keyboard entirely
            payload["reply_markup"] = {"inline_keyboard": []}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self._base}/editMessageReplyMarkup", json=payload)
            result = resp.json()
            if not result.get("ok"):
                logger.warning("Telegram editMessageReplyMarkup failed: %s", result)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_sender_instance: TelegramMessageSender | None = None


def get_telegram_sender() -> TelegramMessageSender:
    """Return singleton TelegramMessageSender.

    Raises ConfigurationError if telegram_bot_token is not configured.
    """
    global _sender_instance
    if _sender_instance is None:
        token = settings.telegram_bot_token
        if not token:
            raise ConfigurationError(
                "telegram_bot_token is not configured. Set TELEGRAM_BOT_TOKEN in your environment."
            )
        _sender_instance = TelegramMessageSender(token)
    return _sender_instance
