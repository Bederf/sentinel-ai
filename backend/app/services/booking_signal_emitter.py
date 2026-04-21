"""
Booking Signal Emitter — Phase 159-02
======================================
Converts booking anomaly detections into correlation signals:
- Ghost bookings (no-show sensor-confirmed)
- Block booking overlaps (resource hoarding)
- Booking saturation (capacity alerts)

Uses shared utilities from ``signal_emitter_base``.
"""

import logging
import uuid

from app.services.signal_emitter_base import (
    build_signal_row,
    check_dedup,
    write_entities,
    write_signal,
)

logger = logging.getLogger(__name__)

# Site code to friendly name mapping
_SITE_NAME_MAP: dict[str, str] = {
    "S002": "Fairlands",
    "FA1": "Fairlands",
    "FA2": "Fairlands",
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _room_code_to_location_ref(room_code: str) -> str:
    """Convert room code to hierarchical location reference.

    Examples:
        FA1-1Q4-MR10 → Fairlands/FA1/1Q4/MR10
        S002-CONF-L2-A → S002/CONF/L2/A
        arbitrary → arbitrary (returned as-is)
    """
    if not room_code:
        return "unknown"

    # Pattern: FA1-1Q4-MR10 (building-floorQuadrant-typeNumber)
    parts = room_code.split("-")
    if len(parts) >= 3:
        building = parts[0].upper()
        site_name = _SITE_NAME_MAP.get(building, building)
        # Reconstruct: site/building/remaining parts joined by /
        remaining = "/".join(parts[1:])
        if site_name != building:
            return f"{site_name}/{building}/{remaining}"
        return f"{building}/{remaining}"

    return room_code


# ---------------------------------------------------------------------------
# Ghost booking signal
# ---------------------------------------------------------------------------


async def emit_ghost_booking_signal(finding: dict) -> dict | None:
    """Emit a signal for a sensor-confirmed ghost booking (no-show).

    Args:
        finding: Dict with keys: room_code, booking_title, booked_by,
                 start_time, end_time, occupancy_detected (bool), site_id

    Returns:
        Created signal dict, or None if deduplicated.
    """
    room_code = finding.get("room_code", "")
    location_ref = _room_code_to_location_ref(room_code)

    # Dedup: same room + ghost_booking within 60 min
    if check_dedup("booking_system", "ghost_booking", location_ref, window_seconds=3600):
        logger.info("Ghost booking signal deduplicated for %s", room_code)
        return None

    # Severity: low for single, medium if recurrence metadata present
    metadata = finding.get("metadata", {})
    recurrence_count = metadata.get("recurrence_count", 1) if isinstance(metadata, dict) else 1
    severity = "medium" if recurrence_count > 1 else "low"

    signal_row = build_signal_row(
        source_module="booking_system",
        signal_type="no_show_pattern",
        severity=severity,
        confidence=0.85,
        location_ref=location_ref,
        raw_content=(
            f"Ghost booking detected: {finding.get('booking_title', 'N/A')} "
            f"in {room_code} by {finding.get('booked_by', 'unknown')}. "
            f"No occupancy detected between {finding.get('start_time', '?')} "
            f"and {finding.get('end_time', '?')}."
        ),
        metadata={
            "room_code": room_code,
            "booking_title": finding.get("booking_title", ""),
            "booked_by": finding.get("booked_by", ""),
            "start_time": finding.get("start_time", ""),
            "end_time": finding.get("end_time", ""),
            "occupancy_detected": finding.get("occupancy_detected", False),
        },
        site_id=finding.get("site_id"),
    )

    row = await write_signal(signal_row)

    # Entities: person, room, booking_ref
    entities = []
    booked_by = finding.get("booked_by", "")
    if booked_by:
        entities.append(
            {
                "id": str(uuid.uuid4()),
                "signal_id": signal_row["id"],
                "entity_type": "person",
                "name": booked_by,
                "metadata": {},
            }
        )
    if room_code:
        entities.append(
            {
                "id": str(uuid.uuid4()),
                "signal_id": signal_row["id"],
                "entity_type": "room",
                "name": room_code,
                "metadata": {},
            }
        )
    booking_title = finding.get("booking_title", "")
    if booking_title:
        entities.append(
            {
                "id": str(uuid.uuid4()),
                "signal_id": signal_row["id"],
                "entity_type": "booking_ref",
                "name": booking_title,
                "metadata": {},
            }
        )

    if entities:
        try:
            await write_entities(entities)
        except Exception as exc:
            logger.warning("Failed to write entities for ghost booking signal %s: %s", signal_row["id"], exc)

    return row


# ---------------------------------------------------------------------------
# Block booking signal
# ---------------------------------------------------------------------------


async def emit_block_booking_signal(alert: dict) -> dict | None:
    """Emit a signal for a block booking overlap / resource hoarding pattern.

    Args:
        alert: Dict with keys: room_code, booked_by, pattern (daily/weekly),
               booking_count, date_range, site_id

    Returns:
        Created signal dict, or None if deduplicated.
    """
    room_code = alert.get("room_code", "")
    booked_by = alert.get("booked_by", "")
    location_ref = _room_code_to_location_ref(room_code)

    # Dedup: same room + block_booking + same person within 24h
    dedup_location = f"{location_ref}:{booked_by}"
    if check_dedup("booking_system", "block_booking", dedup_location, window_seconds=86400):
        logger.info("Block booking signal deduplicated for %s by %s", room_code, booked_by)
        return None

    signal_row = build_signal_row(
        source_module="booking_system",
        signal_type="booking_conflict",
        severity="medium",
        confidence=0.75,
        location_ref=location_ref,
        raw_content=(
            f"Block booking pattern detected: {booked_by} has "
            f"{alert.get('booking_count', '?')} {alert.get('pattern', 'recurring')} "
            f"bookings for {room_code} over {alert.get('date_range', 'N/A')}."
        ),
        metadata={
            "room_code": room_code,
            "booked_by": booked_by,
            "pattern": alert.get("pattern", ""),
            "booking_count": alert.get("booking_count", 0),
            "date_range": alert.get("date_range", ""),
            "alert_id": alert.get("alert_id"),
            "booking_ids": alert.get("booking_ids", []),
            "overlap_window_start": alert.get("overlap_window_start"),
            "overlap_window_end": alert.get("overlap_window_end"),
            "signal_stage": alert.get("signal_stage", "planning"),
            "signal_lifecycle": alert.get("signal_lifecycle", "warn"),
        },
        site_id=alert.get("site_id"),
    )

    row = await write_signal(signal_row)

    # Entities: person + room
    entities = []
    if booked_by:
        entities.append(
            {
                "id": str(uuid.uuid4()),
                "signal_id": signal_row["id"],
                "entity_type": "person",
                "name": booked_by,
                "metadata": {},
            }
        )
    if room_code:
        entities.append(
            {
                "id": str(uuid.uuid4()),
                "signal_id": signal_row["id"],
                "entity_type": "room",
                "name": room_code,
                "metadata": {},
            }
        )

    if entities:
        try:
            await write_entities(entities)
        except Exception as exc:
            logger.warning("Failed to write entities for block booking signal %s: %s", signal_row["id"], exc)

    return row


# ---------------------------------------------------------------------------
# Booking saturation signal
# ---------------------------------------------------------------------------


async def emit_booking_saturation_signal(data: dict) -> dict | None:
    """Emit a signal for booking saturation (high utilisation).

    Args:
        data: Dict with keys: building_code, floor, utilisation_pct,
              peak_hour, site_id

    Returns:
        Created signal dict, or None if deduplicated.
    """
    building_code = data.get("building_code", "")
    floor = data.get("floor", "")
    utilisation_pct = data.get("utilisation_pct", 0)

    location_ref = f"{building_code}/{floor}" if floor else building_code or "unknown"

    # Dedup: same building + floor + booking_saturation within 4h
    if check_dedup("booking_system", "booking_saturation", location_ref, window_seconds=14400):
        logger.info("Booking saturation signal deduplicated for %s/%s", building_code, floor)
        return None

    # Severity based on utilisation
    severity = "high" if utilisation_pct > 95 else "medium"

    signal_row = build_signal_row(
        source_module="booking_system",
        signal_type="booking_saturation",
        severity=severity,
        confidence=0.90,
        location_ref=location_ref,
        raw_content=(
            f"Booking saturation alert: {building_code} floor {floor} at "
            f"{utilisation_pct}% utilisation. Peak hour: {data.get('peak_hour', 'N/A')}."
        ),
        metadata={
            "building_code": building_code,
            "floor": floor,
            "utilisation_pct": utilisation_pct,
            "peak_hour": data.get("peak_hour", ""),
        },
        site_id=data.get("site_id"),
    )

    row = await write_signal(signal_row)

    # Entity: building
    if building_code:
        entities = [
            {
                "id": str(uuid.uuid4()),
                "signal_id": signal_row["id"],
                "entity_type": "building",
                "name": building_code,
                "metadata": {},
            }
        ]
        try:
            await write_entities(entities)
        except Exception as exc:
            logger.warning("Failed to write entities for saturation signal %s: %s", signal_row["id"], exc)

    return row
