"""WhatsApp notification sender for Desigo building alarms.

Delivers formatted plant alerts to a WhatsApp group via n8n webhook.
Uses httpx.AsyncClient (async-first rule).
"""

from __future__ import annotations

import logging
import os

import httpx

from app.plant.models import AlarmSeverity, DesigoBuildingAlarm

logger = logging.getLogger(__name__)

# Configuration from environment / settings
WHATSAPP_WEBHOOK_URL: str = os.getenv("WHATSAPP_WEBHOOK_URL", "")
WHATSAPP_GROUP_ID: str = os.getenv("WHATSAPP_GROUP_ID", "")

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


def format_plant_alert(alarm: DesigoBuildingAlarm) -> str:
    """Format a building alarm into a WhatsApp-ready message string.

    Returns a human-readable multi-line message with emoji severity
    prefix and key alarm details.
    """
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


async def send_plant_alert(alarm: DesigoBuildingAlarm) -> bool:
    """Send a formatted plant alert to the WhatsApp group via webhook.

    Behaviour:
    - POST JSON payload to WHATSAPP_WEBHOOK_URL
    - On failure: retry ONCE (except non_critical alarms -- no retry)
    - Returns True if delivered, False otherwise

    The payload matches the n8n webhook schema:
      { "message": "...", "group_id": "...", "severity": "critical" }
    """
    webhook_url = WHATSAPP_WEBHOOK_URL
    group_id = WHATSAPP_GROUP_ID

    if not webhook_url:
        logger.warning("WHATSAPP_WEBHOOK_URL not configured; skipping notification for alarm %s", alarm.id)
        return False

    message = format_plant_alert(alarm)
    payload = {
        "message": message,
        "group_id": group_id,
        "severity": alarm.severity.value,
    }

    max_attempts = 1 if alarm.severity == AlarmSeverity.NON_CRITICAL else 2

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
                logger.info(
                    "Plant alert sent for alarm %s (attempt %d/%d)",
                    alarm.id,
                    attempt,
                    max_attempts,
                )
                return True
        except Exception:
            logger.warning(
                "WhatsApp webhook attempt %d/%d failed for alarm %s",
                attempt,
                max_attempts,
                alarm.id,
                exc_info=True,
            )

    logger.error("All WhatsApp delivery attempts exhausted for alarm %s", alarm.id)
    return False
