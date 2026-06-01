from __future__ import annotations

import logging

import httpx

from app.config.settings import settings
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# ── Telegram sender (home bot — never commercial) ─────────────────────────────

from app.services.residential.residential_telegram_sender import ResidentialTelegramSender  # noqa: E402

_sender = ResidentialTelegramSender()


# ── API headers for backend auth ─────────────────────────────────────────────


def _api_headers() -> dict:
    return {
        "X-Sentry-API-Key": settings.sentry_bot_api_key,
        "X-Sentry-Secret": settings.sentry_webhook_secret,
        "Content-Type": "application/json",
    }


def _send(chat_id: int, text: str, reply_markup: dict | None = None) -> dict | None:
    """Send text via ResidentialTelegramSender. Returns result dict on success."""
    try:
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(_sender.send_text(chat_id, text, reply_markup))
        return {"message_id": 0} if result else None
    except Exception as exc:
        logger.error("send failed: %s", exc)
        return None


def _answer_callback(callback_query_id: str) -> None:
    """Must be called FIRST on callback receipt to dismiss spinner."""
    try:
        import asyncio

        asyncio.get_event_loop().run_until_complete(_sender.answer_callback_query(callback_query_id))
    except Exception as exc:
        logger.warning("answerCallbackQuery failed: %s", exc)


def _confirmation_keyboard(yes_data: str = "disconnect:confirm") -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Yes, disconnect", "callback_data": yes_data},
                {"text": "Cancel", "callback_data": "confirm:cancel"},
            ]
        ]
    }


class ResidentialDisconnectService:
    def handle_disconnect(self, chat_id: int) -> str:
        """Called when user sends /disconnect. Returns message text."""
        site_id = f"res-{chat_id}"

        # Check if site exists and is active
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
        _send(
            chat_id,
            "Are you sure you want to disconnect?\nThis will stop all monitoring and alerts.",
            reply_markup=_confirmation_keyboard(),
        )
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

        # Lookup platform/deployment for post-deactivation cleanup
        try:
            supabase = get_supabase_client()
            row = (
                supabase.table("residential_sites")
                .select("platform,ha_deployment_type")
                .eq("site_id", site_id)
                .maybe_execute()
            )
            is_ha = row.data and row.data[0].get("platform") == "home_assistant" if row.data else False
            ha_deploy = row.data[0].get("ha_deployment_type") if (row and row.data) else None
        except Exception as exc:
            logger.warning("Could not check platform for site_id=%s: %s", site_id, exc)
            is_ha = False
            ha_deploy = None

        # Call deactivate endpoint
        try:
            r = httpx.post(
                f"http://localhost:9095/api/residential/deactivate/{site_id}",
                headers=_api_headers(),
                timeout=15,
            )
            if r.status_code in (200, 404):
                # Post-deactivation: for local HA, revoke WireGuard peer now (manual operator cleanup)
                if is_ha and ha_deploy == "local":
                    try:
                        from app.services.residential.wireguard_peer_manager import WireGuardPeerManager

                        WireGuardPeerManager().revoke_peer(site_id)
                    except Exception as exc:
                        logger.warning("WireGuard peer revoke failed for %s: %s", site_id, exc)
                    return (
                        "✅ Disconnected. SENTINEL will no longer monitor your system.\n\n"
                        "Also remove the SENTINEL peer from your\n"
                        "Home Assistant WireGuard Add-on to\n"
                        "complete the disconnection."
                    )
                return (
                    "✅ Disconnected. SENTINEL will no longer monitor your system.\n"
                    "Send /connect to reconnect at any time."
                )
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
