"""Plant alert notification dispatcher.

Routes Desigo building alarms through the unified NotificationService,
which delivers to each technician's preferred channel (Telegram, WhatsApp, SMS).
"""

from __future__ import annotations

import logging

from app.models.notification import AlertLevel
from app.plant.models import AlarmSeverity, DesigoBuildingAlarm

logger = logging.getLogger(__name__)

_SEVERITY_TO_ALERT_LEVEL = {
    AlarmSeverity.VERY_CRITICAL: AlertLevel.CRITICAL,
    AlarmSeverity.CRITICAL: AlertLevel.CRITICAL,
    AlarmSeverity.NON_CRITICAL: AlertLevel.WARNING,
    AlarmSeverity.CLEARED: AlertLevel.INFO,
}

# Re-export format_plant_alert from old module for backward compat
from app.plant.whatsapp_notifier import format_plant_alert  # noqa: E402


async def send_plant_alert(alarm: DesigoBuildingAlarm) -> bool:
    """Send a formatted plant alert via the unified notification system."""
    from app.services.notification_service import notification_service

    message = format_plant_alert(alarm)
    alert_level = _SEVERITY_TO_ALERT_LEVEL.get(alarm.severity, AlertLevel.WARNING)

    result = await notification_service.broadcast_alert(
        title=f"Plant Alert — {alarm.severity.value}",
        body=message,
        alert_level=alert_level,
        notification_type="plant_alert",
    )

    if result["success"]:
        logger.info("Plant alert sent for alarm %s to %d recipients", alarm.id, result["recipients_notified"])
    else:
        logger.error("Plant alert delivery failed for alarm %s: %s", alarm.id, result["errors"])

    return result["success"]


async def send_raw_message(message: str) -> bool:
    """Send a pre-formatted message (e.g. flood summary)."""
    from app.services.notification_service import notification_service

    result = await notification_service.broadcast_alert(
        title="Plant Alert",
        body=message,
        alert_level=AlertLevel.WARNING,
        notification_type="plant_alert",
    )
    return result["success"]
