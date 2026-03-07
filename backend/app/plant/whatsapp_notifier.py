"""WhatsApp notification sender for Desigo building alarms.

Delivers formatted plant alerts via Twilio WhatsApp API (primary)
or n8n webhook (fallback). Uses httpx.AsyncClient (async-first rule).
"""

from __future__ import annotations

import logging

import httpx

from app.plant.models import AlarmSeverity, DesigoBuildingAlarm

logger = logging.getLogger(__name__)

# Severity presentation map
_SEVERITY_FORMAT = {
    AlarmSeverity.VERY_CRITICAL: {
        "emoji": "\U0001f534\U0001f534",  # double red circle
        "label": "URGENT \u2014 Immediate response required",
    },
    AlarmSeverity.CRITICAL: {
        "emoji": "\U0001f534",  # single red circle
        "label": "Action required",
    },
    AlarmSeverity.NON_CRITICAL: {
        "emoji": "\U0001f7e1",  # yellow circle
        "label": "For attention",
    },
    AlarmSeverity.CLEARED: {
        "emoji": "\u2705",  # green checkmark
        "label": "Fault resolved",
    },
}

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"


def _get_settings():
    """Lazy import to avoid circular imports at module level."""
    from app.config.settings import get_settings

    return get_settings()


def format_plant_alert(alarm: DesigoBuildingAlarm) -> str:
    """Format a building alarm into a WhatsApp-ready message string."""
    fmt = _SEVERITY_FORMAT.get(alarm.severity, _SEVERITY_FORMAT[AlarmSeverity.NON_CRITICAL])
    emoji = fmt["emoji"]
    label = fmt["label"]

    lines = [
        f"{emoji} *{label}*",
        "",
        f"*Site:* {alarm.site_id}",
    ]
    if alarm.building:
        lines.append(f"*Building:* {alarm.building}")
    lines.extend(
        [
            f"*Equipment:* {alarm.equipment_description}",
            f"*Alarm:* {alarm.alarm_type}",
            f"*Status:* {alarm.status}",
            f"*Category:* {alarm.equipment_category}",
            f"*Received:* {alarm.received_at.strftime('%Y-%m-%d %H:%M')}",
        ]
    )
    return "\n".join(lines)


async def _send_via_twilio(message: str, settings) -> bool:
    """Send message via Twilio WhatsApp API.

    POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
    Basic Auth: account_sid:auth_token
    Form data: From, To, Body
    """
    url = f"{TWILIO_API_BASE}/{settings.twilio_account_sid}/Messages.json"
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    data = {
        "From": settings.twilio_whatsapp_from,
        "To": settings.twilio_whatsapp_to,
        "Body": message,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, data=data, auth=auth)
        resp.raise_for_status()
        result = resp.json()
        logger.info("Twilio message SID: %s, status: %s", result.get("sid"), result.get("status"))
        return True


async def _send_via_webhook(message: str, severity: str, settings) -> bool:
    """Send message via n8n webhook (fallback when Twilio not configured)."""
    payload = {
        "message": message,
        "group_id": settings.whatsapp_group_id,
        "severity": severity,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(settings.whatsapp_webhook_url, json=payload)
        resp.raise_for_status()
        return True


def _twilio_configured(settings) -> bool:
    """Check if Twilio credentials are present."""
    return bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_whatsapp_from
        and settings.twilio_whatsapp_to
    )


async def send_plant_alert(alarm: DesigoBuildingAlarm) -> bool:
    """Send a formatted plant alert via WhatsApp.

    Delivery priority:
    1. Twilio WhatsApp API (if TWILIO_ACCOUNT_SID configured)
    2. n8n webhook fallback (if WHATSAPP_WEBHOOK_URL configured)

    Retry: once on failure (except non_critical — no retry).
    """
    settings = _get_settings()
    use_twilio = _twilio_configured(settings)
    use_webhook = bool(settings.whatsapp_webhook_url)

    if not use_twilio and not use_webhook:
        logger.warning("No WhatsApp delivery configured; skipping notification for alarm %s", alarm.id)
        return False

    message = format_plant_alert(alarm)
    max_attempts = 1 if alarm.severity == AlarmSeverity.NON_CRITICAL else 2

    for attempt in range(1, max_attempts + 1):
        try:
            if use_twilio:
                await _send_via_twilio(message, settings)
            else:
                await _send_via_webhook(message, alarm.severity.value, settings)

            logger.info(
                "Plant alert sent via %s for alarm %s (attempt %d/%d)",
                "Twilio" if use_twilio else "webhook",
                alarm.id,
                attempt,
                max_attempts,
            )
            return True
        except Exception:
            logger.warning(
                "WhatsApp %s attempt %d/%d failed for alarm %s",
                "Twilio" if use_twilio else "webhook",
                attempt,
                max_attempts,
                alarm.id,
                exc_info=True,
            )

    logger.error("All WhatsApp delivery attempts exhausted for alarm %s", alarm.id)
    return False
