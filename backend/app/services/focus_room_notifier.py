"""Focus room overstay notifier.

Sends operator alerts when a focus room exceeds the allowed occupancy window.
Primary Telegram path uses Sentry bot; WhatsApp uses configured WhatsApp service.
"""

from __future__ import annotations

import logging

from app.core.site_resolver import get_registered_sites
from app.config.settings import settings
from app.services.sentry_integration.alert_notifier import alert_notifier

logger = logging.getLogger(__name__)


def _resolve_site_label(site_id: str) -> str:
    """Return human-readable site/building label for alerts."""
    try:
        for site in get_registered_sites():
            if site.get("code") == site_id:
                return site.get("name") or site_id
    except Exception:
        pass
    return site_id


async def send_focus_overstay_alert(
    *,
    site_id: str,
    room_code: str,
    max_allowed_minutes: int,
    cooldown_minutes: int,
) -> dict:
    """Dispatch a focus overstay alert via Sentry Telegram + WhatsApp."""
    site_label = _resolve_site_label(site_id)
    title = "Focus Room Overstay Alert"
    body = (
        f"Site: {site_label}\n"
        f"Room: {room_code}\n"
        f"Rule: Occupancy exceeded {max_allowed_minutes} minutes.\n"
        f"Action: Concierge follow-up required. LED/relay ON.\n"
        f"Cooldown: LED remains ON for {cooldown_minutes} minutes after room becomes vacant."
    )

    try:
        # 1) Telegram via Sentry bot notifier
        telegram_ok = alert_notifier.send_alert_sync(
            {
                "severity": "warning",
                "site_name": site_label,
                "zone_name": room_code,
                "equipment_name": "Focus Room Occupancy",
                "equipment_type": "focus_room",
                "equipment_code": room_code,
                "message": (
                    f"Occupancy exceeded {max_allowed_minutes} minutes. "
                    f"LED/relay ON. Cooldown {cooldown_minutes} minutes after vacancy."
                ),
            }
        )

        # 2) WhatsApp via n8n SENTINEL — WhatsApp Send workflow
        whatsapp_ok = False
        whatsapp_result: dict = {}
        whatsapp_to = (settings.twilio_whatsapp_to or "").replace("whatsapp:", "").strip()
        if whatsapp_to:
            try:
                from app.services.n8n_service import get_n8n_service

                whatsapp_result = await get_n8n_service().trigger_webhook(
                    webhook_path="whatsapp-send",
                    payload={"to": whatsapp_to, "message": f"*{title}*\n\n{body}"},
                )
                whatsapp_ok = bool(whatsapp_result.get("success"))
            except Exception as wa_exc:
                logger.warning("Focus overstay WhatsApp via n8n failed: %s", wa_exc)
                whatsapp_result = {"success": False, "error": str(wa_exc)}
        else:
            whatsapp_result = {"success": False, "error": "whatsapp_not_configured"}

        success = telegram_ok or whatsapp_ok
        result = {
            "success": success,
            "telegram_sent": telegram_ok,
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
