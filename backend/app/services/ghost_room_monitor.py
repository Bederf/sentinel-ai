"""Periodic ghost-room scanning for booked meeting rooms."""

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
from app.services.occupancy_store import get_ghost_finding_by_id, get_open_ghost_finding

logger = logging.getLogger(__name__)


def _booking_is_due(booking: BookingRecord, now: datetime) -> bool:
    grace = timedelta(minutes=settings.ghost_booking_grace_minutes or 15)
    return booking.start_time + grace <= now <= booking.end_time


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
    scanned = 0

    for site_id in site_ids:
        config = get_block_booking_config(site_id)
        site_name = site_id

        bookings: list[BookingRecord] = []
        for target_date in _dates_to_scan(now):
            bookings.extend(store.get_bookings_for_site(site_id, target_date))

        for booking in bookings:
            if not _booking_is_due(booking, now):
                continue

            scanned += 1
            room_code = _booking_room_code(booking)
            finding = detect_ghost_booking(booking, now=now, room_code=room_code)
            if finding is not None:
                created += 1

            current = finding or get_open_ghost_finding(booking.id)
            if current and not current.notification_sent:
                result = await send_ghost_booking_alert(current, config, site_name=site_name)
                if result.get("success"):
                    notified += 1
                    current = get_ghost_finding_by_id(current.id) or current
                    logger.info(
                        "Ghost booking notified: site=%s room=%s booking=%s",
                        site_id,
                        current.room_code,
                        current.booking_id,
                    )

    return {
        "timestamp": now.isoformat(),
        "bookings_scanned": scanned,
        "ghost_findings_created": created,
        "notifications_sent": notified,
    }
