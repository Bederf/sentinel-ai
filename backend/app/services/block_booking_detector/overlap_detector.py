"""Detect same-slot room bookings by the same organiser.

Core detection logic:
1. Group bookings by organiser
2. For each organiser, group by date
3. Check for identical time windows where the same person holds N+ rooms
4. Generate BlockBookingAlert for each overlap cluster

De-duplicates against existing open alerts.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

from app.models.booking_record import (
    BlockBookingAlert,
    BlockBookingConfig,
    BookingRecord,
)
from app.services.block_booking_detector.booking_store import BookingStore

logger = logging.getLogger(__name__)


def _time_slot_key(booking: BookingRecord) -> tuple[str, str]:
    """Return a stable key for an exact booking time window."""
    return (booking.start_time.isoformat(), booking.end_time.isoformat())


def detect_overlaps(
    site_id: str,
    bookings: list[BookingRecord],
    config: BlockBookingConfig,
    store: Optional[BookingStore] = None,
) -> list[BlockBookingAlert]:
    """Scan bookings for same-slot reservations by the same organiser.

    Args:
        site_id: The site to scan
        bookings: List of booking records to check
        config: Detection thresholds
        store: BookingStore instance for dedup checking (optional)

    Returns:
        List of new BlockBookingAlert objects (not yet persisted).
    """
    if not config.enabled:
        return []

    # Group by organiser
    by_organiser: dict[str, list[BookingRecord]] = defaultdict(list)
    for b in bookings:
        by_organiser[b.organiser_email].append(b)

    new_alerts: list[BlockBookingAlert] = []

    for organiser_email, org_bookings in by_organiser.items():
        # Group by date
        by_date: dict[str, list[BookingRecord]] = defaultdict(list)
        for b in org_bookings:
            by_date[b.booking_date.isoformat()].append(b)

        for date_str, day_bookings in by_date.items():
            if len(day_bookings) < config.min_rooms_for_alert:
                continue

            by_slot: dict[tuple[str, str], list[BookingRecord]] = defaultdict(list)
            for booking in day_bookings:
                by_slot[_time_slot_key(booking)].append(booking)

            for slot_bookings in by_slot.values():
                rooms = sorted({b.room_name for b in slot_bookings})
                if len(rooms) < config.min_rooms_for_alert:
                    continue

                slot_start = slot_bookings[0].start_time
                slot_end = slot_bookings[0].end_time
                booking_date = slot_bookings[0].booking_date

                # De-duplicate: skip if open alert already exists
                if store and store.has_open_alert_for(
                    site_id,
                    organiser_email,
                    booking_date,
                    slot_start,
                    slot_end,
                ):
                    logger.debug(
                        "Skipping duplicate alert for %s on %s %s-%s",
                        organiser_email,
                        date_str,
                        slot_start.strftime("%H:%M"),
                        slot_end.strftime("%H:%M"),
                    )
                    continue

                # Build alert
                organiser_name = slot_bookings[0].organiser_name

                alert = BlockBookingAlert(
                    site_id=site_id,
                    organiser_email=organiser_email,
                    organiser_name=organiser_name,
                    overlap_window_start=slot_start,
                    overlap_window_end=slot_end,
                    rooms=rooms,
                    room_count=len(rooms),
                    booking_ids=[b.id for b in slot_bookings],
                    detected_at=datetime.utcnow(),
                )

                new_alerts.append(alert)
                logger.info(
                    "Block booking detected: %s holds %d rooms on %s for %s-%s",
                    organiser_email,
                    len(rooms),
                    date_str,
                    slot_start.strftime("%H:%M"),
                    slot_end.strftime("%H:%M"),
                )

    return new_alerts
