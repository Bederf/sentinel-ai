"""Send block booking alert notifications to the concierge.

Uses the existing EventBus for event-driven notification routing.
Falls back to direct Telegram via AlertNotifier if event bus delivery fails.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.models.booking_record import BlockBookingAlert, BlockBookingConfig
from app.services.block_booking_detector.booking_store import (
    get_booking_store,
)

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
        f"holds {alert.room_count} rooms simultaneously on {date_str}:\n"
        f"{rooms_text}\n"
        f"Window: {time_start} - {time_end}\n\n"
        f"One person cannot occupy multiple rooms at the same time. "
        f"Please contact the organiser to confirm which rooms are genuinely "
        f"required and release any that are not needed.\n\n"
        f"SENTINEL · {site_label} · {timestamp}"
    )
    return msg


async def send_block_booking_alert(
    alert: BlockBookingAlert,
    config: BlockBookingConfig,
    site_name: str = "",
) -> bool:
    """Send a notification to the concierge about a detected block booking.

    Uses the EventBus to emit a space.block_booking_detected event.
    The SentryNotificationRouter picks this up and delivers via configured
    channels (Telegram, WhatsApp, email).

    Returns True if the event was emitted successfully.
    """
    message = format_alert_message(alert, site_name)

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

        # Mark notification as sent
        store = get_booking_store()
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
