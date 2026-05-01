"""Sensor offline notifier.

Sends Telegram-only alerts when a room sensor stops sending heartbeats.
Used by the generic space sensor health monitor (not focus-room specific).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.core.site_resolver import get_registered_sites

logger = logging.getLogger(__name__)

# Throttle to prevent repeated Telegram spam even if DB room_current_state
# is missing (can cause multiple "was_online=true" checks).
_last_offline_alert_at: dict[str, datetime] = {}


def _resolve_site_label(site_id: str) -> str:
    """Return human-readable site/building label for alerts."""
    try:
        for site in get_registered_sites():
            if site.get("code") == site_id:
                return site.get("name") or site_id
    except Exception:
        pass
    return site_id


async def send_sensor_offline_alert(
    *,
    site_id: str,
    room_code: str,
    sensor_id: str,
    silence_minutes: int,
    min_interval_minutes: int = 30,
) -> dict:
    """Send a Telegram alert for an offline sensor (throttled)."""

    key = f"{site_id}:{room_code}:{sensor_id}"
    now = datetime.utcnow()
    last = _last_offline_alert_at.get(key)
    if last and (now - last) < timedelta(minutes=max(1, min_interval_minutes)):
        return {"success": True, "skipped": True, "reason": "offline_alert_throttled"}

    site_label = _resolve_site_label(site_id)
    title = "Sensor Offline Alert"
    body = (
        f"Site: {site_label}\n"
        f"Room: {room_code}\n"
        f"Sensor: {sensor_id}\n"
        f"Issue: No occupancy heartbeat for {silence_minutes}+ minutes.\n"
        f"Action: Check node power/network and sensor health."
    )

    from app.models.notification import AlertLevel
    from app.services.notification_service import notification_service

    send_result = await notification_service.send_alert_direct(title=title, body=body, alert_level=AlertLevel.WARNING)
    if send_result["success"]:
        _last_offline_alert_at[key] = now
    return {"success": send_result["success"], "error": send_result.get("error")}
