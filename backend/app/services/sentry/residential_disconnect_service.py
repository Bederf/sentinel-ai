from __future__ import annotations

import json
import logging
import os

import requests as http_requests

logger = logging.getLogger(__name__)

def _bot_token() -> str:
    with open(os.path.expanduser("~/.sentry/gateway/sentry.json")) as f:
        return json.load(f)["channels"]["telegram"]["accounts"]["client"]["botToken"]

def _api_headers() -> dict:
    from app.config.settings import settings as _settings
    return {
        "X-Sentry-API-Key": _settings.sentry_bot_api_key,
        "X-Sentry-Secret": _settings.sentry_webhook_secret,
        "Content-Type": "application/json",
    }

def _send(chat_id: int, text: str, reply_markup=None) -> dict | None:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = http_requests.post(
            f"https://api.telegram.org/bot{_bot_token()}/sendMessage",
            json=payload, timeout=10,
        )
        r.raise_for_status()
        return r.json().get("result")
    except Exception as exc:
        logger.error("send failed: %s", exc)
        return None

def _answer_callback(callback_query_id: str) -> None:
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{_bot_token()}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("answerCallbackQuery failed: %s", exc)

def _confirmation_keyboard(yes_data: str = "disconnect:confirm") -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ Yes, disconnect", "callback_data": yes_data},
            {"text": "Cancel", "callback_data": "confirm:cancel"},
        ]]
    }

class ResidentialDisconnectService:
    def handle_disconnect(self, chat_id: int) -> str:
        """Called when user sends /disconnect. Returns message text."""
        site_id = f"res-{chat_id}"

        # Check if site exists and is active
        import httpx
        try:
            r = httpx.get(
                f"http://localhost:9095/api/residential/deactivate/{site_id}",
                headers=_api_headers(),
                timeout=10,
            )
            # 404 = not found = not connected
            if r.status_code == 404:
                return "No active connection found for this chat."
        except Exception as exc:
            logger.error("pre-check failed for chat_id=%s: %s", chat_id, exc)

        # Site exists — ask for confirmation
        _send(chat_id,
              "Are you sure you want to disconnect?\n"
              "This will stop all monitoring and alerts.",
              reply_markup=_confirmation_keyboard())
        return None  # message sent via _send

    def handle_disconnect_confirm(self, chat_id: int, callback_query_id: str) -> str:
        """Called when user taps 'Yes, disconnect'. Returns final message text."""
        _answer_callback(callback_query_id)

        site_id = f"res-{chat_id}"

        # Clear conversation state first
        try:
            from app.services.sentry.conversation_state import ConversationStateManager
            ConversationStateManager().clear(chat_id)
        except Exception as exc:
            logger.warning("state clear failed for chat_id=%s: %s", chat_id, exc)

        # Call deactivate endpoint
        import httpx
        try:
            r = httpx.post(
                f"http://localhost:9095/api/residential/deactivate/{site_id}",
                headers=_api_headers(),
                timeout=15,
            )
            if r.status_code in (200, 404):
                return ("✅ Disconnected. SENTINEL will no longer monitor your system.\n"
                        "Send /connect to reconnect at any time.")
            else:
                logger.error("deactivate failed for chat_id=%s: status=%s", chat_id, r.status_code)
                return "Failed to disconnect. Please try again or contact support."
        except Exception as exc:
            logger.error("deactivate exception for chat_id=%s: %s", chat_id, exc)
            return "Failed to disconnect. Please try again or contact support."

    def handle_cancel(self, chat_id: int, callback_query_id: str) -> str:
        """Called when user taps Cancel. Returns message text."""
        _answer_callback(callback_query_id)
        return "Cancelled. Your connection is still active."
