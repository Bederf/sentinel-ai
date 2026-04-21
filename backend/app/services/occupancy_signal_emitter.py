"""
Occupancy Signal Emitter — Phase 159-03
========================================
Converts occupancy anomalies (sensor vs booking mismatches, underutilisation,
sensor faults) into correlation signals.  Feeds the correlation engine so
occupancy issues can cluster with email complaints and booking anomalies.

Three emission functions:
    emit_occupancy_mismatch_signal   — ghost/shadow usage detection
    emit_underutilisation_signal     — low room utilisation over a period
    emit_sensor_fault_signal         — no_data / stuck_value / impossible_count

Source module: ``occupancy_sensor`` for all signals.
"""

import logging
import uuid

from app.services.signal_emitter_base import (
    build_signal_row,
    check_dedup,
    room_code_to_location_ref,
    write_entities,
    write_signal,
)

logger = logging.getLogger(__name__)

SOURCE_MODULE = "occupancy_sensor"

# ---------------------------------------------------------------------------
# Dedup windows (seconds)
# ---------------------------------------------------------------------------
_MISMATCH_DEDUP_WINDOW = 30 * 60  # 30 minutes — rapid sensor updates
_UNDERUTIL_DEDUP_WINDOW = 24 * 60 * 60  # 24 hours — daily metric
_SENSOR_FAULT_DEDUP_WINDOW = 4 * 60 * 60  # 4 hours


# ---------------------------------------------------------------------------
# 1. Occupancy mismatch (ghost bookings / shadow usage)
# ---------------------------------------------------------------------------


async def emit_occupancy_mismatch_signal(data: dict) -> dict | None:
    """Emit a signal when sensor occupancy contradicts booking state.

    Detects:
    - **Ghost booking**: room booked but physically empty.
    - **Shadow usage**: room occupied but not booked.

    Args:
        data: dict with keys ``room_code``, ``booking_active`` (bool),
              ``sensor_occupancy`` (int), ``expected_occupancy`` (int),
              ``timestamp``, ``site_id``.

    Returns:
        Created signal dict, or ``None`` if deduplicated / no anomaly.
    """
    room_code: str = data.get("room_code", "")
    booking_active: bool = data.get("booking_active", False)
    sensor_occ: int = data.get("sensor_occupancy", 0)
    expected_occ: int = data.get("expected_occupancy", 0)
    site_id: str = data.get("site_id", "")

    # Determine mismatch type
    if booking_active and sensor_occ == 0:
        mismatch_type = "ghost_booking"
    elif not booking_active and sensor_occ > 0:
        mismatch_type = "shadow_usage"
    elif expected_occ > 0 and sensor_occ > 0:
        # Both present — check deviation magnitude
        deviation_pct = abs(sensor_occ - expected_occ) / max(expected_occ, 1)
        if deviation_pct < 0.1:
            # Within 10% — not an anomaly
            return None
        mismatch_type = "occupancy_deviation"
    else:
        # No anomaly
        return None

    location_ref = room_code_to_location_ref(room_code)

    # Dedup: same room + occupancy_mismatch within 30 min
    if check_dedup(
        SOURCE_MODULE,
        "occupancy_mismatch",
        location_ref,
        window_seconds=_MISMATCH_DEDUP_WINDOW,
    ):
        logger.info("Occupancy mismatch deduplicated for %s", room_code)
        return None

    # Severity based on deviation
    if expected_occ > 0 and sensor_occ > 0:
        deviation_pct = abs(sensor_occ - expected_occ) / max(expected_occ, 1)
        severity = "low" if deviation_pct < 0.3 else "medium"
    else:
        # Ghost or shadow — always at least medium
        severity = "medium"

    raw_content = (
        f"Occupancy mismatch ({mismatch_type}) in {room_code}: "
        f"booking_active={booking_active}, sensor={sensor_occ}, "
        f"expected={expected_occ}"
    )

    signal_row = build_signal_row(
        source_module=SOURCE_MODULE,
        signal_type="occupancy_mismatch",
        severity=severity,
        confidence=0.80,
        location_ref=location_ref,
        raw_content=raw_content,
        metadata={
            "room_code": room_code,
            "mismatch_type": mismatch_type,
            "booking_active": booking_active,
            "sensor_occupancy": sensor_occ,
            "expected_occupancy": expected_occ,
            "timestamp": data.get("timestamp", ""),
        },
        site_id=site_id or None,
    )

    # Write signal
    row = await write_signal(signal_row)

    # Write room entity
    entity_rows = [
        {
            "id": str(uuid.uuid4()),
            "signal_id": signal_row["id"],
            "entity_type": "room",
            "name": room_code,
            "metadata": {"mismatch_type": mismatch_type},
        }
    ]
    try:
        await write_entities(entity_rows)
    except Exception as exc:
        logger.warning("Failed to write entities for signal %s: %s", signal_row["id"], exc)

    return {
        "signal_id": row["id"],
        "source_module": SOURCE_MODULE,
        "signal_type": "occupancy_mismatch",
        "severity": severity,
        "location_ref": location_ref,
        "mismatch_type": mismatch_type,
        "status": "created",
    }


# ---------------------------------------------------------------------------
# 2. Underutilisation
# ---------------------------------------------------------------------------


async def emit_underutilisation_signal(data: dict) -> dict | None:
    """Emit a signal when a room is significantly underutilised.

    Args:
        data: dict with keys ``room_code``, ``capacity``, ``avg_occupancy``,
              ``utilisation_pct`` (0-100), ``period`` (e.g. '7d'), ``site_id``.

    Returns:
        Created signal dict, or ``None`` if deduplicated.
    """
    room_code: str = data.get("room_code", "")
    utilisation_pct: float = data.get("utilisation_pct", 0)
    capacity: int = data.get("capacity", 0)
    avg_occupancy: float = data.get("avg_occupancy", 0)
    period: str = data.get("period", "7d")
    site_id: str = data.get("site_id", "")

    location_ref = room_code_to_location_ref(room_code)

    # Dedup: same room + underutilisation within 24h
    if check_dedup(
        SOURCE_MODULE,
        "underutilisation",
        location_ref,
        window_seconds=_UNDERUTIL_DEDUP_WINDOW,
    ):
        logger.info("Underutilisation deduplicated for %s", room_code)
        return None

    # Severity: low if 20-40%, medium if <20%
    severity = "medium" if utilisation_pct < 20 else "low"

    raw_content = (
        f"Underutilisation in {room_code}: {utilisation_pct:.0f}% over {period} "
        f"(capacity={capacity}, avg_occupancy={avg_occupancy:.1f})"
    )

    signal_row = build_signal_row(
        source_module=SOURCE_MODULE,
        signal_type="underutilisation",
        severity=severity,
        confidence=0.85,
        location_ref=location_ref,
        raw_content=raw_content,
        metadata={
            "room_code": room_code,
            "capacity": capacity,
            "avg_occupancy": avg_occupancy,
            "utilisation_pct": utilisation_pct,
            "period": period,
        },
        site_id=site_id or None,
    )

    row = await write_signal(signal_row)

    entity_rows = [
        {
            "id": str(uuid.uuid4()),
            "signal_id": signal_row["id"],
            "entity_type": "room",
            "name": room_code,
            "metadata": {"utilisation_pct": utilisation_pct},
        }
    ]
    try:
        await write_entities(entity_rows)
    except Exception as exc:
        logger.warning("Failed to write entities for signal %s: %s", signal_row["id"], exc)

    return {
        "signal_id": row["id"],
        "source_module": SOURCE_MODULE,
        "signal_type": "underutilisation",
        "severity": severity,
        "location_ref": location_ref,
        "status": "created",
    }


# ---------------------------------------------------------------------------
# 3. Sensor fault
# ---------------------------------------------------------------------------


async def emit_sensor_fault_signal(data: dict) -> dict | None:
    """Emit a signal when an occupancy sensor is faulty.

    Args:
        data: dict with keys ``sensor_id``, ``room_code``,
              ``fault_type`` ('no_data'|'stuck_value'|'impossible_count'),
              ``last_reading_at``, ``site_id``.

    Returns:
        Created signal dict, or ``None`` if deduplicated.
    """
    sensor_id: str = data.get("sensor_id", "")
    room_code: str = data.get("room_code", "")
    fault_type: str = data.get("fault_type", "unknown")
    last_reading_at: str = data.get("last_reading_at", "")
    site_id: str = data.get("site_id", "")

    location_ref = room_code_to_location_ref(room_code)

    # Dedup key uses sensor_id for fault signals (per-sensor, not per-room)
    dedup_location = f"{location_ref}:{sensor_id}"
    if check_dedup(
        SOURCE_MODULE,
        "sensor_fault",
        dedup_location,
        window_seconds=_SENSOR_FAULT_DEDUP_WINDOW,
    ):
        logger.info("Sensor fault deduplicated for %s/%s", room_code, sensor_id)
        return None

    raw_content = (
        f"Sensor fault ({fault_type}) for {sensor_id} in {room_code}. Last reading: {last_reading_at or 'N/A'}"
    )

    signal_row = build_signal_row(
        source_module=SOURCE_MODULE,
        signal_type="sensor_fault",
        severity="medium",
        confidence=0.90,
        location_ref=location_ref,
        raw_content=raw_content,
        metadata={
            "sensor_id": sensor_id,
            "room_code": room_code,
            "fault_type": fault_type,
            "last_reading_at": last_reading_at,
        },
        site_id=site_id or None,
    )

    row = await write_signal(signal_row)

    entity_rows = [
        {
            "id": str(uuid.uuid4()),
            "signal_id": signal_row["id"],
            "entity_type": "room",
            "name": room_code,
            "metadata": {"sensor_id": sensor_id, "fault_type": fault_type},
        }
    ]
    try:
        await write_entities(entity_rows)
    except Exception as exc:
        logger.warning("Failed to write entities for signal %s: %s", signal_row["id"], exc)

    return {
        "signal_id": row["id"],
        "source_module": SOURCE_MODULE,
        "signal_type": "sensor_fault",
        "severity": "medium",
        "location_ref": location_ref,
        "status": "created",
    }
