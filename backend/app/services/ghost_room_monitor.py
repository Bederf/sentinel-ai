"""Periodic ghost-room scanning for booked meeting rooms.

Notification logic (per booking):
  T+5 min (grace):   No movement → send FIRST notification → status=pending_inspection
  T+20 min (grace+15): Still no reply & no movement → send ONE reminder
  Concierge replies yes/no at any point → confirm & close. No more messages.

Max 2 notifications per booking (initial + reminder). Once concierge replies,
the finding reaches a terminal status and is never touched again.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from app.api.block_bookings import get_block_booking_config
from app.config.settings import settings
from app.core.site_resolver import get_registered_site_ids
from app.models.booking_record import BookingRecord
from app.services.block_booking_detector.booking_store import get_booking_store
from app.services.ghost_booking_detector import detect_ghost_booking
from app.services.ghost_room_notifier import send_ghost_booking_alert
from app.services.occupancy_store import (
    get_open_ghost_finding,
    mark_ghost_finding_reminder_sent,
)

logger = logging.getLogger(__name__)


# How long the concierge has to respond before we send a reminder
# Read from space settings API if available, fall back to config, then hardcoded default.
def _get_concierge_response_window() -> int:
    try:
        from app.api.space_settings import get_space_setting

        val = get_space_setting("concierge_response_window_minutes")
        if val is not None:
            return int(val)
    except Exception:
        pass
    return settings.concierge_response_window_minutes or 15


CONCIERGE_RESPONSE_WINDOW_MINUTES = 15  # kept as module-level fallback

# Terminal statuses — finding is closed, never touch again
_TERMINAL_STATUSES = {"confirmed_empty", "verified_occupied", "dismissed"}


def _make_naive(dt: datetime) -> datetime:
    """Strip timezone info for safe comparison with naive datetimes."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _booking_is_due(booking: BookingRecord, now: datetime) -> bool:
    grace = timedelta(minutes=settings.ghost_booking_grace_minutes or 15)
    start_n = _make_naive(booking.start_time)
    end_n = _make_naive(booking.end_time)
    now_n = _make_naive(now)
    return start_n + grace <= now_n <= end_n


def _enrich_config_with_concierge(config, site_id: str, room_code: str = ""):
    """Overlay concierge contact info from concierge_store if available.

    Falls back to the original BlockBookingConfig (block_booking_sites.json) if
    no concierge is found in the new store.
    """
    try:
        from app.services.concierge_store import find_concierge_for_room

        # Try to extract building code from room_code (e.g. FA1-Room-101 -> FA1)
        building_code = site_id
        if room_code and "-" in room_code:
            building_code = room_code.split("-")[0]

        concierge = find_concierge_for_room(site_id, building_code)
        if concierge:
            if concierge.email:
                config.concierge_email = concierge.email
            if concierge.mobile:
                config.concierge_whatsapp = f"whatsapp:{concierge.mobile}"
            logger.debug(
                "Using concierge %s for room %s (site=%s)",
                concierge.name,
                room_code,
                site_id,
            )
    except Exception as exc:
        logger.debug("Concierge store lookup failed, using block_booking config: %s", exc)
    return config


def _booking_room_code(booking: BookingRecord) -> str:
    return booking.room_name or booking.room_id


def _dates_to_scan(now: datetime) -> list[date]:
    dates = {now.date()}
    dates.add((now - timedelta(days=1)).date())
    return sorted(dates)


async def scan_due_ghost_bookings(now: datetime | None = None) -> dict[str, Any]:
    """Scan active bookings and notify concierge for unoccupied rooms."""
    now = now or datetime.utcnow()
    store = get_booking_store()
    site_ids = get_registered_site_ids() or [settings.space_default_site_id]

    created = 0
    notified = 0
    reminders = 0
    scanned = 0

    for site_id in site_ids:
        base_config = get_block_booking_config(site_id)
        site_name = site_id

        bookings: list[BookingRecord] = []
        for target_date in _dates_to_scan(now):
            bookings.extend(store.get_bookings_for_site(site_id, target_date))

        for booking in bookings:
            if not _booking_is_due(booking, now):
                continue

            scanned += 1
            room_code = _booking_room_code(booking)

            # Enrich config with concierge store data for this specific room
            import copy

            config = _enrich_config_with_concierge(copy.copy(base_config), site_id, room_code)

            # Try to detect a new ghost booking (returns None if finding already exists)
            finding = detect_ghost_booking(booking, now=now, room_code=room_code)
            if finding is not None:
                created += 1

            # Get current finding (newly created or existing)
            current = finding or get_open_ghost_finding(booking.id)
            if not current:
                continue

            # Terminal status — concierge already replied. Done.
            if current.status in _TERMINAL_STATUSES:
                continue

            # --- FIRST notification (status=open, not yet notified) ---
            if not current.notification_sent:
                result = await send_ghost_booking_alert(current, config, site_name=site_name)
                if result.get("success"):
                    notified += 1
                    logger.info(
                        "Ghost booking notified: site=%s room=%s booking=%s",
                        site_id,
                        current.room_code,
                        current.booking_id,
                    )
                continue

            # --- REMINDER (status=pending_inspection, 15 min elapsed, not yet reminded) ---
            if current.status == "pending_inspection" and not current.reminder_sent and current.notification_sent_at:
                sent_at = _make_naive(current.notification_sent_at)
                now_n = _make_naive(now)
                elapsed = (now_n - sent_at).total_seconds() / 60
                if elapsed >= _get_concierge_response_window():
                    result = await send_ghost_booking_alert(current, config, site_name=site_name, is_reminder=True)
                    if result.get("success"):
                        mark_ghost_finding_reminder_sent(
                            current.id,
                            whatsapp_message_id=result.get("whatsapp_message_id"),
                        )
                        reminders += 1
                        logger.info(
                            "Ghost booking reminder sent: site=%s room=%s booking=%s",
                            site_id,
                            current.room_code,
                            current.booking_id,
                        )

    return {
        "timestamp": now.isoformat(),
        "bookings_scanned": scanned,
        "ghost_findings_created": created,
        "notifications_sent": notified,
        "reminders_sent": reminders,
    }
