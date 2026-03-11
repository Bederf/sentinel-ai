"""Send block booking alert notifications to the concierge."""

from __future__ import annotations

import logging
from datetime import datetime

from app.models.booking_record import BlockBookingAlert, BlockBookingConfig
from app.services.block_booking_detector.booking_store import (
    get_booking_store,
)
from app.services.n8n_service import get_n8n_service

logger = logging.getLogger(__name__)


def format_alert_message(alert: BlockBookingAlert, site_name: str = "") -> str:
    """Format a block booking alert as a human-readable notification message."""
    date_str = alert.overlap_window_start.strftime("%A, %d %B %Y")

    room_lines = []
    for room in alert.rooms:
        room_lines.append(f"  - {room}")
    rooms_text = "\n".join(room_lines)

    time_start = alert.overlap_window_start.strftime("%H:%M")
    time_end = alert.overlap_window_end.strftime("%H:%M")

    site_label = site_name or alert.site_id
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    msg = (
        f"Block Booking Detected — {site_label}\n\n"
        f"{alert.organiser_name} ({alert.organiser_email}) "
        f"holds {alert.room_count} rooms for the same time slot on {date_str}:\n"
        f"{rooms_text}\n"
        f"Window: {time_start} - {time_end}\n\n"
        "Please contact the organiser to confirm which rooms are genuinely "
        "required. SENTINEL is flagging the anomaly only and is not cancelling "
        "or changing any bookings.\n\n"
        f"SENTINEL · {site_label} · {timestamp}"
    )
    return msg


async def _send_email_notification(
    alert: BlockBookingAlert,
    config: BlockBookingConfig,
    message: str,
    site_name: str,
) -> bool:
    """Send the block-booking alert to n8n for concierge email delivery."""
    if not config.concierge_email:
        return False

    site_label = site_name or alert.site_id
    subject = f"Block booking alert: {alert.room_count} rooms held by {alert.organiser_name or alert.organiser_email}"
    result = await get_n8n_service().trigger_webhook(
        webhook_path="space-block-booking-alert",
        payload={
            "site_id": alert.site_id,
            "site_name": site_label,
            "alert_id": alert.id,
            "to_email": config.concierge_email,
            "subject": subject,
            "message": message,
            "organiser_email": alert.organiser_email,
            "organiser_name": alert.organiser_name,
            "room_count": alert.room_count,
            "rooms": alert.rooms,
            "window_start": alert.overlap_window_start.isoformat(),
            "window_end": alert.overlap_window_end.isoformat(),
        },
    )
    if not result.get("success"):
        logger.warning(
            "Block booking alert n8n dispatch failed: organiser=%s reason=%s",
            alert.organiser_email,
            result.get("reason") or result.get("status_code"),
        )
        return False

    logger.info(
        "Block booking concierge email queued via n8n: site=%s organiser=%s to=%s",
        site_label,
        alert.organiser_email,
        config.concierge_email,
    )
    return True


async def send_block_booking_alert(
    alert: BlockBookingAlert,
    config: BlockBookingConfig,
    site_name: str = "",
) -> bool:
    """Send a notification to the concierge about a detected block booking.

    Sends the concierge email via n8n. Falls back to the event bus so existing
    notification plumbing still receives the event if n8n is unavailable.
    """
    message = format_alert_message(alert, site_name)
    store = get_booking_store()

    try:
        if await _send_email_notification(alert, config, message, site_name):
            store.mark_alert_notified(alert.id)
            return True
    except Exception as exc:
        logger.error("Failed to send block booking concierge email: %s", exc)

    try:
        from app.services.event_bus import Importance, SentinelEvent, get_event_bus

        bus = get_event_bus()
        event = SentinelEvent(
            event_type="space.block_booking_detected",
            source="block_booking_detector",
            payload={
                "alert_id": alert.id,
                "organiser_email": alert.organiser_email,
                "organiser_name": alert.organiser_name,
                "room_count": alert.room_count,
                "rooms": alert.rooms,
                "date": alert.overlap_window_start.strftime("%Y-%m-%d"),
                "message": message,
            },
            importance=Importance.HIGH,
            site_id=alert.site_id,
            site_name=site_name,
        )
        await bus.emit(event)

        store.mark_alert_notified(alert.id)

        logger.info(
            "Block booking alert sent for %s (%d rooms)",
            alert.organiser_email,
            alert.room_count,
        )
        return True

    except Exception as exc:
        logger.error("Failed to send block booking alert: %s", exc)
        return False
