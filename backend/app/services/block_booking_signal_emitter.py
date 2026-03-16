"""
Block Booking Signal Emitter — Phase 161-02
=============================================
Detects block booking patterns and booking saturation from the booking
store and emits typed signals into the correlation engine pipeline.

Two signal types:
    booking_conflict     — single organiser holding >= BLOCK_BOOKER_MIN_ROOMS rooms
    booking_saturation   — room at >= SATURATION_THRESHOLD_PCT capacity over 7 days

Uses shared utilities from ``signal_emitter_base`` and links signals
to rooms via ``room_signal_mapper``.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from app.services.signal_emitter_base import (
    build_signal_row,
    check_dedup,
    room_code_to_location_ref,
    write_signal,
)
from app.services.room_signal_mapper import link_signal_to_room

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------

BLOCK_BOOKER_MIN_ROOMS = 2
SATURATION_THRESHOLD_PCT = 70
SATURATION_HIGH_PCT = 90
SATURATION_LOOKAHEAD_DAYS = 7

SOURCE_MODULE = "space_optimisation"

# Dedup windows
_BLOCK_BOOKING_DEDUP_WINDOW = 24 * 60 * 60  # 24 hours
_SATURATION_DEDUP_WINDOW = 4 * 60 * 60  # 4 hours


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def emit_block_booking_signals(site_id: str) -> list[dict]:
    """Detect block booking patterns and saturation, emit signals.

    Fetches booking data from the BookingStore, detects:
    1. Block bookers — single organiser holding >= BLOCK_BOOKER_MIN_ROOMS
       rooms on the same day/time
    2. Booking saturation — rooms at >= SATURATION_THRESHOLD_PCT capacity
       over the next SATURATION_LOOKAHEAD_DAYS

    Args:
        site_id: Site identifier (e.g. 'S001').

    Returns:
        List of emitted signal dicts.
    """
    from app.services.block_booking_detector.booking_store import get_booking_store

    store = get_booking_store()
    emitted: list[dict] = []
    today = date.today()

    # Collect bookings for the lookahead window
    all_bookings = []
    for day_offset in range(SATURATION_LOOKAHEAD_DAYS):
        target_date = today + timedelta(days=day_offset)
        day_bookings = store.get_bookings_for_site(site_id, target_date)
        all_bookings.extend(day_bookings)

    if not all_bookings:
        logger.info("No bookings found for site %s — skipping signal emission", site_id)
        return emitted

    # --- 1. Detect block bookers ---
    block_signals = await _detect_block_bookers(site_id, all_bookings)
    emitted.extend(block_signals)

    # --- 2. Detect booking saturation ---
    saturation_signals = await _detect_saturation(site_id, all_bookings)
    emitted.extend(saturation_signals)

    return emitted


# ---------------------------------------------------------------------------
# Block booker detection
# ---------------------------------------------------------------------------


async def _detect_block_bookers(site_id: str, bookings: list) -> list[dict]:
    """Detect organisers holding multiple rooms simultaneously."""
    emitted: list[dict] = []

    # Group bookings by (date, organiser_email)
    by_date_organiser: dict[tuple[date, str], list] = defaultdict(list)
    for b in bookings:
        key = (b.booking_date, b.organiser_email)
        by_date_organiser[key].append(b)

    for (booking_date, organiser_email), org_bookings in by_date_organiser.items():
        # Count distinct rooms
        rooms = list({b.room_id or b.room_name for b in org_bookings})
        if len(rooms) < BLOCK_BOOKER_MIN_ROOMS:
            continue

        organiser_name = org_bookings[0].organiser_name or organiser_email
        room_id = rooms[0]  # Primary room for location_ref
        location_ref = room_code_to_location_ref(room_id)

        # Dedup: same organiser + booking_conflict within 24h
        dedup_key = f"{location_ref}:{organiser_email}"
        if check_dedup(SOURCE_MODULE, "booking_conflict", dedup_key, window_seconds=_BLOCK_BOOKING_DEDUP_WINDOW):
            logger.info("Block booking signal deduplicated for %s by %s", room_id, organiser_email)
            continue

        signal_row = build_signal_row(
            source_module=SOURCE_MODULE,
            signal_type="booking_conflict",
            severity="high",
            confidence=0.90,
            location_ref=location_ref,
            raw_content=(
                f"{organiser_name} has block booked {len(rooms)} rooms "
                f"on {booking_date.isoformat()}: {', '.join(rooms)}"
            ),
            metadata={
                "signal_type": "booking_conflict",
                "organiser_email": organiser_email,
                "organiser_name": organiser_name,
                "rooms": rooms,
                "room_count": len(rooms),
                "booking_date": booking_date.isoformat(),
                "booking_ids": [b.id for b in org_bookings],
            },
            site_id=site_id,
        )

        try:
            row = await write_signal(signal_row)
            # Link to primary room
            await link_signal_to_room(signal_row["id"], room_id)
            emitted.append(row)
            logger.info(
                "Block booking signal emitted: organiser=%s rooms=%d site=%s",
                organiser_email,
                len(rooms),
                site_id,
            )
        except Exception as exc:
            logger.error("Failed to emit block booking signal: %s", exc)

    return emitted


# ---------------------------------------------------------------------------
# Saturation detection
# ---------------------------------------------------------------------------


async def _detect_saturation(site_id: str, bookings: list) -> list[dict]:
    """Detect rooms at high booking saturation over the lookahead window."""
    emitted: list[dict] = []

    # Count booked hours per room
    room_hours: dict[str, float] = defaultdict(float)
    for b in bookings:
        room_key = b.room_id or b.room_name
        duration_hours = (b.end_time - b.start_time).total_seconds() / 3600
        room_hours[room_key] += duration_hours

    # Available hours: 10 hours/day * lookahead days (business hours)
    available_hours = 10.0 * SATURATION_LOOKAHEAD_DAYS

    for room_id, booked_hours in room_hours.items():
        if available_hours <= 0:
            continue
        utilisation_pct = (booked_hours / available_hours) * 100

        if utilisation_pct < SATURATION_THRESHOLD_PCT:
            continue

        location_ref = room_code_to_location_ref(room_id)

        # Dedup: same room + booking_saturation within 4h
        if check_dedup(SOURCE_MODULE, "booking_saturation", location_ref, window_seconds=_SATURATION_DEDUP_WINDOW):
            logger.info("Saturation signal deduplicated for %s", room_id)
            continue

        severity = "high" if utilisation_pct >= SATURATION_HIGH_PCT else "medium"

        signal_row = build_signal_row(
            source_module=SOURCE_MODULE,
            signal_type="booking_saturation",
            severity=severity,
            confidence=0.85,
            location_ref=location_ref,
            raw_content=(
                f"Room {room_id} is at {utilisation_pct:.0f}% booking saturation "
                f"over the next {SATURATION_LOOKAHEAD_DAYS} days "
                f"({booked_hours:.1f}/{available_hours:.0f} available hours)"
            ),
            metadata={
                "signal_type": "booking_saturation",
                "room_id": room_id,
                "utilisation_pct": round(utilisation_pct, 1),
                "booked_hours": round(booked_hours, 1),
                "available_hours": available_hours,
                "lookahead_days": SATURATION_LOOKAHEAD_DAYS,
            },
            site_id=site_id,
        )

        try:
            row = await write_signal(signal_row)
            await link_signal_to_room(signal_row["id"], room_id)
            emitted.append(row)
            logger.info(
                "Saturation signal emitted: room=%s utilisation=%.0f%% site=%s",
                room_id,
                utilisation_pct,
                site_id,
            )
        except Exception as exc:
            logger.error("Failed to emit saturation signal for %s: %s", room_id, exc)

    return emitted
