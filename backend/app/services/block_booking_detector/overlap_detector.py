"""Detect overlapping room bookings by the same organiser.

Core detection logic:
1. Group bookings by organiser
2. For each organiser, group by date
3. Check for time overlaps where the same person holds N+ rooms
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


def _times_overlap(a: BookingRecord, b: BookingRecord) -> bool:
    """Return True if two bookings have overlapping time windows."""
    return a.start_time < b.end_time and b.start_time < a.end_time


def _find_overlap_clusters(
    bookings: list[BookingRecord],
) -> list[list[BookingRecord]]:
    """Find clusters of mutually overlapping bookings.

    Uses a simple greedy approach: for each booking, find all others that
    overlap with it. If the resulting group has 2+ bookings, it's a cluster.
    """
    if len(bookings) < 2:
        return []

    # Sort by start time
    sorted_bookings = sorted(bookings, key=lambda b: b.start_time)
    clusters: list[list[BookingRecord]] = []
    used: set[str] = set()

    for i, booking in enumerate(sorted_bookings):
        if booking.id in used:
            continue
        cluster = [booking]
        for j in range(i + 1, len(sorted_bookings)):
            other = sorted_bookings[j]
            if other.id in used:
                continue
            # Check if this booking overlaps with ANY booking in the cluster
            if any(_times_overlap(c, other) for c in cluster):
                cluster.append(other)

        if len(cluster) >= 2:
            for b in cluster:
                used.add(b.id)
            clusters.append(cluster)

    return clusters


def detect_overlaps(
    site_id: str,
    bookings: list[BookingRecord],
    config: BlockBookingConfig,
    store: Optional[BookingStore] = None,
) -> list[BlockBookingAlert]:
    """Scan bookings for overlapping reservations by the same organiser.

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

            # Find overlap clusters
            clusters = _find_overlap_clusters(day_bookings)

            for cluster in clusters:
                if len(cluster) < config.min_rooms_for_alert:
                    continue

                # De-duplicate: skip if open alert already exists
                booking_date = cluster[0].booking_date
                if store and store.has_open_alert_for(site_id, organiser_email, booking_date):
                    logger.debug(
                        "Skipping duplicate alert for %s on %s",
                        organiser_email,
                        date_str,
                    )
                    continue

                # Build alert
                overlap_start = min(b.start_time for b in cluster)
                overlap_end = max(b.end_time for b in cluster)
                rooms = list({b.room_name for b in cluster})
                organiser_name = cluster[0].organiser_name

                alert = BlockBookingAlert(
                    site_id=site_id,
                    organiser_email=organiser_email,
                    organiser_name=organiser_name,
                    overlap_window_start=overlap_start,
                    overlap_window_end=overlap_end,
                    rooms=rooms,
                    room_count=len(rooms),
                    booking_ids=[b.id for b in cluster],
                    detected_at=datetime.utcnow(),
                )

                new_alerts.append(alert)
                logger.info(
                    "Block booking detected: %s holds %d rooms on %s",
                    organiser_email,
                    len(rooms),
                    date_str,
                )

    return new_alerts
