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

from app.models.booking_record import (
    BlockBookingAlert,
    BlockBookingConfig,
    BookingRecord,
)
from app.services.block_booking_detector.booking_store import BookingStore

logger = logging.getLogger(__name__)


def _duration_hours(booking: BookingRecord) -> float:
    """Return booking duration in hours."""
    return (booking.end_time - booking.start_time).total_seconds() / 3600.0


def _merge_long_overlap_segments(
    bookings: list[BookingRecord],
    min_rooms_for_alert: int,
    threshold_hours: float,
) -> list[tuple[datetime, datetime, list[BookingRecord]]]:
    """Return merged long-overlap clusters for a day's bookings.

    We treat block booking as a long overlapping hold across multiple rooms on
    the same date, not merely identical time slots. A cluster only qualifies if:
    - each constituent booking is at least `threshold_hours` long
    - the shared overlap window itself is at least `threshold_hours` long
    - the active room count meets `min_rooms_for_alert`
    """
    long_bookings = [b for b in bookings if _duration_hours(b) >= threshold_hours]
    if len(long_bookings) < min_rooms_for_alert:
        return []

    boundaries = sorted({b.start_time for b in long_bookings} | {b.end_time for b in long_bookings})
    segments: list[tuple[datetime, datetime, list[BookingRecord]]] = []

    for index in range(len(boundaries) - 1):
        segment_start = boundaries[index]
        segment_end = boundaries[index + 1]
        if segment_start >= segment_end:
            continue

        active = [
            booking
            for booking in long_bookings
            if booking.start_time <= segment_start and booking.end_time >= segment_end
        ]
        if len({booking.room_name for booking in active}) < min_rooms_for_alert:
            continue

        segments.append((segment_start, segment_end, active))

    merged: list[tuple[datetime, datetime, list[BookingRecord]]] = []
    for segment_start, segment_end, active in segments:
        active_ids = sorted(booking.id for booking in active)
        if merged:
            prev_start, prev_end, prev_active = merged[-1]
            prev_ids = sorted(booking.id for booking in prev_active)
            if active_ids == prev_ids and prev_end == segment_start:
                merged[-1] = (prev_start, segment_end, prev_active)
                continue

        merged.append((segment_start, segment_end, active))

    qualifying: list[tuple[datetime, datetime, list[BookingRecord]]] = []
    for overlap_start, overlap_end, active in merged:
        overlap_hours = (overlap_end - overlap_start).total_seconds() / 3600.0
        if overlap_hours >= threshold_hours:
            qualifying.append((overlap_start, overlap_end, active))

    return qualifying


def detect_overlaps(
    site_id: str,
    bookings: list[BookingRecord],
    config: BlockBookingConfig,
    store: BookingStore | None = None,
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

            overlap_clusters = _merge_long_overlap_segments(
                day_bookings,
                min_rooms_for_alert=config.min_rooms_for_alert,
                threshold_hours=config.full_day_threshold_hours,
            )

            for overlap_start, overlap_end, slot_bookings in overlap_clusters:
                rooms = sorted({b.room_name for b in slot_bookings})
                booking_date = slot_bookings[0].booking_date

                # De-duplicate: skip if open alert already exists
                if store and store.has_open_alert_for(
                    site_id,
                    organiser_email,
                    booking_date,
                    overlap_start,
                    overlap_end,
                ):
                    logger.debug(
                        "Skipping duplicate alert for %s on %s %s-%s",
                        organiser_email,
                        date_str,
                        overlap_start.strftime("%H:%M"),
                        overlap_end.strftime("%H:%M"),
                    )
                    continue

                # Build alert
                organiser_name = slot_bookings[0].organiser_name

                alert = BlockBookingAlert(
                    site_id=site_id,
                    organiser_email=organiser_email,
                    organiser_name=organiser_name,
                    overlap_window_start=overlap_start,
                    overlap_window_end=overlap_end,
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
                    overlap_start.strftime("%H:%M"),
                    overlap_end.strftime("%H:%M"),
                )

    return new_alerts
