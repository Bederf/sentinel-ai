"""
Ghost Booking Signal Emitter — Phase 161-02
=============================================
Emits correlation signals when ghost bookings are confirmed. Sits
alongside ``ghost_booking_detector.py`` without modifying its logic.

Called from ``space_event_service.py`` after a GhostBookingFinding
is created, bridging the detection result into the signal pipeline.
"""

from __future__ import annotations

import logging

from app.database.supabase_client import get_supabase_client
from app.models.space_occupancy import GhostBookingFinding
from app.services.room_signal_mapper import link_signal_to_room
from app.services.signal_emitter_base import (
    build_signal_row,
    check_dedup,
    room_code_to_location_ref,
    write_signal,
)

logger = logging.getLogger(__name__)

SOURCE_MODULE = "booking_system"

# Dedup window: same room + booking within 60 min
_GHOST_DEDUP_WINDOW = 60 * 60


def _linked_block_booking_metadata(room_id: str, finding: GhostBookingFinding) -> dict:
    """Return linkage metadata to the earlier planning-stage block-booking signal."""
    if not finding.source_booking_flagged:
        return {
            "previously_flagged": False,
            "linked_signal_type": None,
            "linked_signal_ids": [],
        }

    linked_ids: list[str] = []
    client = get_supabase_client()
    if client:
        try:
            result = (
                client.table("signal")
                .select("id")
                .eq("signal_type", "booking_conflict")
                .eq("resolution_state", "active")
                .filter("metadata->>room_code", "eq", room_id)
                .execute()
            )
            linked_ids = [row["id"] for row in (result.data or []) if row.get("id")]
        except Exception as exc:
            logger.warning("Failed to resolve linked block-booking signal for %s: %s", room_id, exc)

    return {
        "previously_flagged": True,
        "linked_signal_type": "booking_conflict",
        "linked_signal_ids": linked_ids,
    }


async def emit_ghost_booking_signal(
    room_id: str,
    finding: GhostBookingFinding,
) -> dict | None:
    """Emit a no_show_pattern signal for a confirmed ghost booking.

    Args:
        room_id: Room code (e.g. 'FA2-1Q1-MR-01').
        finding: The GhostBookingFinding from the detector.

    Returns:
        Created signal dict, or None if deduplicated.
    """
    location_ref = room_code_to_location_ref(room_id)

    # Dedup key includes room_id + booking_id to avoid duplicate emissions
    dedup_key = f"{location_ref}:{finding.booking_id}"
    if check_dedup(
        SOURCE_MODULE,
        "no_show_pattern",
        dedup_key,
        window_seconds=_GHOST_DEDUP_WINDOW,
    ):
        logger.info("Ghost booking signal deduplicated for %s booking=%s", room_id, finding.booking_id)
        return None

    grace_min = finding.grace_period_minutes
    linkage = _linked_block_booking_metadata(room_id, finding)

    signal_row = build_signal_row(
        source_module=SOURCE_MODULE,
        signal_type="no_show_pattern",
        severity="critical",
        confidence=0.85,
        location_ref=location_ref,
        raw_content=(
            f"Ghost booking detected: {room_id} booked but no presence "
            f"after {grace_min} minutes. Organiser: {finding.organiser_email}"
        ),
        metadata={
            "signal_type": "no_show_pattern",
            "room_id": room_id,
            "organiser": finding.organiser_email,
            "booking_id": finding.booking_id,
            "booking_start": finding.booking_start.isoformat(),
            "booking_end": finding.booking_end.isoformat(),
            "grace_period_minutes": grace_min,
            "signal_stage": "runtime",
            "signal_lifecycle": "confirm",
            **linkage,
        },
        site_id=finding.site_id or None,
    )

    try:
        row = await write_signal(signal_row)
        await link_signal_to_room(signal_row["id"], room_id)
        logger.info(
            "Ghost booking signal emitted: room=%s booking=%s",
            room_id,
            finding.booking_id,
        )
        return row
    except Exception as exc:
        logger.error(
            "Failed to emit ghost booking signal for %s: %s",
            room_id,
            exc,
        )
        return None
