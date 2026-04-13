"""Periodic ghost-room scanning for booked meeting rooms.

Notification logic (per booking):
  Start+grace:       No movement → send FIRST notification → status=pending_inspection
  Hour+grace:        For long bookings, send a fresh notification at each hour boundary + grace
  Alert+15 min:      If still no reply after the most recent fresh notification, send ONE reminder
  Concierge replies yes/no at any point → confirm & close. No more messages.

At most one fresh alert plus one reminder are sent per hourly booking window.
Once concierge replies, the finding reaches a terminal status and is never touched again.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from app.api.block_bookings import get_block_booking_config
from app.config.settings import settings
from app.core.site_resolver import get_connected_site_ids
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
    grace_minutes = _get_ghost_booking_grace_minutes()
    grace = timedelta(minutes=grace_minutes)
    start_n = _make_naive(booking.start_time)
    end_n = _make_naive(booking.end_time)
    now_n = _make_naive(now)
    return start_n + grace <= now_n <= end_n


def _get_ghost_booking_grace_minutes() -> int:
    try:
        from app.api.space_settings import get_space_setting

        configured = get_space_setting("ghost_booking_grace_minutes")
        return int(configured) if configured is not None else (settings.ghost_booking_grace_minutes or 5)
    except Exception:
        return settings.ghost_booking_grace_minutes or 5


def _booking_window_index(booking: BookingRecord, now: datetime) -> int | None:
    """Return the current hourly ghost-alert window index for a booking.

    Window 0 opens at booking_start + grace, window 1 at booking_start + 60 min + grace, etc.
    Returns None if the booking is not currently due.
    """
    if not _booking_is_due(booking, now):
        return None

    start_n = _make_naive(booking.start_time)
    now_n = _make_naive(now)
    due_anchor = start_n + timedelta(minutes=_get_ghost_booking_grace_minutes())
    elapsed_seconds = (now_n - due_anchor).total_seconds()
    return max(0, int(elapsed_seconds // 3600))


def _notification_window_index(booking: BookingRecord, notified_at: datetime | None) -> int | None:
    if notified_at is None:
        return None
    start_n = _make_naive(booking.start_time)
    notified_n = _make_naive(notified_at)
    due_anchor = start_n + timedelta(minutes=_get_ghost_booking_grace_minutes())
    elapsed_seconds = (notified_n - due_anchor).total_seconds()
    return max(0, int(elapsed_seconds // 3600))


def _should_send_new_hourly_alert(booking: BookingRecord, current, now: datetime) -> bool:
    """Send a fresh alert when the booking has advanced into a new hourly grace window."""
    current_window = _booking_window_index(booking, now)
    if current_window is None or not current.notification_sent:
        return False
    notified_window = _notification_window_index(booking, current.notification_sent_at)
    if notified_window is None:
        return False
    return current_window > notified_window


def _enrich_config_with_concierge(config, site_id: str, room_code: str = ""):
    """Overlay concierge contact info from concierge_store if available.

    Collects ALL active concierges for the building so every assigned concierge
    receives ghost booking alerts. Emails are comma-separated so n8n emailSend
    delivers to all recipients in one send.

    Falls back to the original BlockBookingConfig (block_booking_sites.json) if
    no concierges are found in the store.
    """
    try:
        from app.services.concierge_store import find_all_concierges_for_room

        # Try to extract building code from room_code (e.g. FA1-Room-101 -> FA1)
        building_code = site_id
        if room_code and "-" in room_code:
            building_code = room_code.split("-")[0]

        concierges = find_all_concierges_for_room(site_id, building_code)
        if concierges:
            emails = [c.email.strip() for c in concierges if c.email and c.email.strip()]
            if emails:
                config.concierge_email = ",".join(emails)
            # Use the first concierge's WhatsApp for the single-recipient WhatsApp alert
            for c in concierges:
                if c.mobile and c.mobile.strip():
                    config.concierge_whatsapp = f"whatsapp:{c.mobile.strip()}"
                    break
            logger.debug(
                "Using %d concierge(s) for room %s (site=%s): %s",
                len(concierges),
                room_code,
                site_id,
                config.concierge_email,
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

    site_ids = get_connected_site_ids()
    if not site_ids:
        return {
            "status": "skipped",
            "reason": "no_connected_site",
            "created": 0,
            "notified": 0,
            "reminders": 0,
            "scanned": 0,
        }

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

            # --- NEW HOURLY WINDOW (e.g. booking 09:00-11:00 triggers again at 10:05) ---
            if current.status in {"open", "pending_inspection"} and _should_send_new_hourly_alert(
                booking, current, now
            ):
                result = await send_ghost_booking_alert(current, config, site_name=site_name)
                if result.get("success"):
                    notified += 1
                    logger.info(
                        "Ghost booking re-notified for new hourly window: site=%s room=%s booking=%s",
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
