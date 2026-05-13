"""Focus room overstay notifier.

Sends operator alerts when a focus room exceeds the allowed occupancy window.
Telegram via sentry CLI (concierge-targeted with inline confirm buttons);
WhatsApp via NotificationService.broadcast_alert() (Phase 102).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config.settings import settings
from app.services.sentry_integration.alert_notifier import alert_notifier
from app.services.telegram_message_sender import InlineButton, InlineKeyboard, get_telegram_sender

logger = logging.getLogger(__name__)


def _resolve_site_label(site_id: str) -> str:
    """Return human-readable site/building label for alerts."""
    try:
        from app.core.site_resolver import get_registered_sites

        for site in get_registered_sites():
            if site.get("code") == site_id:
                return site.get("name") or site_id
    except Exception:
        pass
    return site_id


async def _send_focus_alert_telegram(
    *,
    site_id: str,
    room_code: str,
    site_label: str,
    max_allowed_minutes: int,
    cooldown_minutes: int,
) -> dict[str, Any]:
    """Send focus overstay alert to concierge via Telegram with inline confirm buttons."""
    from app.services.space_booking_simulator import get_block_booking_config

    config = get_block_booking_config(site_id)
    # Fall back to SENTRY_FM_CHAT_ID if per-site Telegram ID not configured
    target_chat = (
        config.concierge_telegram_chat_id
        if config and config.concierge_telegram_chat_id
        else (os.getenv("SENTRY_FM_CHAT_ID") or "").strip()
        or str(getattr(settings, "sentry_fm_chat_id", "") or "").strip()
        or str(getattr(settings, "telegram_alert_chat_id", "") or "").strip()
    )
    if not target_chat:
        return {"success": False, "reason": "No Telegram chat ID configured for focus alerts"}

    message = f"""⚠️ FOCUS ROOM OVERSTAY ALERT

Site: {site_label}
Room: {room_code}
Occupancy exceeded {max_allowed_minutes} minutes.
LED/relay is ON.
Cooldown: LED remains ON for {cooldown_minutes} minutes after room becomes vacant.

Is anyone still in this room?"""

    kb = InlineKeyboard(
        rows=[
            [InlineButton("✅ Still occupied", f"focus:occupied:{room_code}")],
            [InlineButton("❌ Room empty now", f"focus:empty:{room_code}")],
        ]
    )

    try:
        sender = get_telegram_sender()
        result = await sender.send_text(target_chat, message, keyboard=kb, parse_mode="HTML")
        ok = result.get("ok", False)
        return {"success": ok, "message_id": result.get("result", {}).get("message_id")}
    except Exception as exc:
        logger.warning("Focus overstay Telegram send failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def send_focus_overstay_alert(
    *,
    site_id: str,
    room_code: str,
    max_allowed_minutes: int,
    cooldown_minutes: int,
) -> dict:
    """Dispatch a focus overstay alert via Telegram (concierge-targeted) + WhatsApp via NotificationService."""
    site_label = _resolve_site_label(site_id)

    try:
        # 1) Telegram via sentry CLI — concierge-targeted with inline confirm buttons
        telegram_result = await _send_focus_alert_telegram(
            site_id=site_id,
            room_code=room_code,
            site_label=site_label,
            max_allowed_minutes=max_allowed_minutes,
            cooldown_minutes=cooldown_minutes,
        )
        telegram_ok = telegram_result.get("success", False)

        # 2) WhatsApp via Twilio directly (not broadcast_alert — that duplicates Telegram)
        whatsapp_ok = False
        whatsapp_result: dict = {}
        whatsapp_to = (settings.twilio_whatsapp_to or "").strip()
        whatsapp_from = (settings.twilio_whatsapp_from or "").strip()
        if whatsapp_to and whatsapp_from:
            try:
                from twilio.rest import Client as TwilioClient

                account_sid = getattr(settings, "twilio_account_sid", None)
                auth_token = getattr(settings, "twilio_auth_token", None)
                if account_sid and auth_token:
                    twilio_client = TwilioClient(account_sid, auth_token)
                    body = (
                        f"⚠️ Focus Room Overstay Alert\n"
                        f"Site: {site_label}\n"
                        f"Room: {room_code}\n"
                        f"Occupancy exceeded {max_allowed_minutes} minutes.\n"
                        f"LED/relay is ON.\n"
                        f"Cooldown: LED remains ON for {cooldown_minutes} minutes after room becomes vacant."
                    )
                    msg = twilio_client.messages.create(
                        body=body,
                        from_=whatsapp_from,
                        to=whatsapp_to,
                    )
                    whatsapp_ok = bool(msg.sid)
                    whatsapp_result = {"success": whatsapp_ok, "sid": msg.sid}
                else:
                    whatsapp_result = {"success": False, "error": "Twilio credentials not configured"}
            except Exception as wa_exc:
                logger.warning("Focus overstay WhatsApp via Twilio failed: %s", wa_exc)
                whatsapp_result = {"success": False, "error": str(wa_exc)}
        else:
            whatsapp_result = {"success": False, "error": "whatsapp_not_configured"}

        success = telegram_ok or whatsapp_ok
        result = {
            "success": success,
            "telegram_sent": telegram_ok,
            "telegram_result": telegram_result,
            "whatsapp_sent": whatsapp_ok,
            "whatsapp_result": whatsapp_result,
        }
        if success:
            logger.info("Focus overstay alert sent: site=%s room=%s result=%s", site_id, room_code, result)
        else:
            logger.warning("Focus overstay alert failed: site=%s room=%s result=%s", site_id, room_code, result)
        return result
    except Exception as exc:
        logger.warning("Focus overstay notifier exception: site=%s room=%s err=%s", site_id, room_code, exc)
        return {"success": False, "error": str(exc)}
