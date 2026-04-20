"""Rules engine for space-occupancy anomaly detection.

Evaluates room state against 5 rules:
  1. ghost_booking   — booked but unoccupied past grace period
  2. overstay        — occupied with no active booking past grace period
  3. early_vacate    — booked but vacated well before booking end
  4. sensor_offline  — no heartbeat within threshold
  5. sensor_recovery — was offline, now receiving events again
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from app.space.models import RoomStateFinding, SensorEventPayload

logger = logging.getLogger("sentinel.space.engine")

GHOST_BOOKING_GRACE_MINUTES = int(os.getenv("GHOST_BOOKING_GRACE_MINUTES", "20"))
OVERSTAY_GRACE_MINUTES = int(os.getenv("OVERSTAY_GRACE_MINUTES", "15"))
EARLY_VACATE_THRESHOLD_MINUTES = int(os.getenv("EARLY_VACATE_THRESHOLD_MINUTES", "90"))
SENSOR_OFFLINE_THRESHOLD_SECONDS = int(os.getenv("SENSOR_OFFLINE_THRESHOLD_SECONDS", "180"))


async def evaluate_room_state(
    room_code: str,
    current_state: dict | None,
    new_event: SensorEventPayload,
    booking_data: dict | None = None,
) -> list[RoomStateFinding]:
    """Evaluate all rules against the incoming event and room state.

    Args:
        room_code: The room being evaluated.
        current_state: The existing materialised state (may be None for first event).
        new_event: The freshly received sensor event.
        booking_data: Optional calendar/booking data with keys:
            - active_booking (bool): whether a booking is currently in progress
            - booking_start (datetime | str): when the current booking started
            - booking_end (datetime | str): when the current booking ends
            - last_booking_end (datetime | str): when the most recent booking ended

    Returns:
        A list of findings (may be empty when everything is normal).
    """
    now = datetime.now(UTC)
    site_id = current_state.get("site_id", "FLN02") if current_state else "FLN02"
    findings: list[RoomStateFinding] = []

    # ── Rule 5: sensor_recovery ─────────────────────────────────────────
    was_offline = False
    if current_state and not current_state.get("sensor_online", True):
        was_offline = True
        findings.append(
            RoomStateFinding(
                room_code=room_code,
                site_id=site_id,
                finding_type="sensor_recovery",
                detail="Sensor back online after being offline",
                detected_at=now,
                resolved=False,
            )
        )

    # ── Rule 4: sensor_offline ──────────────────────────────────────────
    if current_state and not was_offline:
        last_hb_raw = current_state.get("last_heartbeat_at")
        last_sc_raw = current_state.get("last_state_change_at")
        last_contact_raw = last_hb_raw or last_sc_raw
        if last_contact_raw:
            if isinstance(last_contact_raw, str):
                try:
                    last_contact = datetime.fromisoformat(last_contact_raw.replace("Z", "+00:00"))
                except ValueError:
                    last_contact = None
            else:
                last_contact = last_contact_raw
            if last_contact:
                if last_contact.tzinfo is None:
                    last_contact = last_contact.replace(tzinfo=UTC)
                elapsed = (now - last_contact).total_seconds()
                if elapsed > SENSOR_OFFLINE_THRESHOLD_SECONDS:
                    findings.append(
                        RoomStateFinding(
                            room_code=room_code,
                            site_id=site_id,
                            finding_type="sensor_offline",
                            detail=f"No heartbeat for {int(elapsed)}s (threshold {SENSOR_OFFLINE_THRESHOLD_SECONDS}s)",
                            detected_at=now,
                            resolved=False,
                        )
                    )

    # ── Booking-dependent rules (skip if no booking data) ───────────────
    if booking_data is not None:
        active_booking = booking_data.get("active_booking", False)

        # Rule 1: ghost_booking
        if active_booking and not new_event.occupied:
            booking_start_raw = booking_data.get("booking_start")
            if booking_start_raw:
                booking_start = _parse_dt(booking_start_raw)
                if booking_start:
                    minutes_since = (now - booking_start).total_seconds() / 60
                    if minutes_since > GHOST_BOOKING_GRACE_MINUTES:
                        findings.append(
                            RoomStateFinding(
                                room_code=room_code,
                                site_id=site_id,
                                finding_type="ghost_booking",
                                detail=(
                                    f"Room unoccupied {int(minutes_since)} min after booking start "
                                    f"(grace {GHOST_BOOKING_GRACE_MINUTES} min)"
                                ),
                                detected_at=now,
                                resolved=False,
                            )
                        )

        # Rule 2: overstay
        if not active_booking and new_event.occupied:
            last_booking_end_raw = booking_data.get("last_booking_end")
            if last_booking_end_raw:
                last_booking_end = _parse_dt(last_booking_end_raw)
                if last_booking_end:
                    minutes_since = (now - last_booking_end).total_seconds() / 60
                    if minutes_since > OVERSTAY_GRACE_MINUTES:
                        findings.append(
                            RoomStateFinding(
                                room_code=room_code,
                                site_id=site_id,
                                finding_type="overstay",
                                detail=(
                                    f"Room occupied {int(minutes_since)} min after last booking ended "
                                    f"(grace {OVERSTAY_GRACE_MINUTES} min)"
                                ),
                                detected_at=now,
                                resolved=False,
                            )
                        )

        # Rule 3: early_vacate
        if active_booking and not new_event.occupied:
            booking_end_raw = booking_data.get("booking_end")
            if booking_end_raw:
                booking_end = _parse_dt(booking_end_raw)
                if booking_end:
                    minutes_remaining = (booking_end - now).total_seconds() / 60
                    if minutes_remaining > EARLY_VACATE_THRESHOLD_MINUTES:
                        findings.append(
                            RoomStateFinding(
                                room_code=room_code,
                                site_id=site_id,
                                finding_type="early_vacate",
                                detail=(
                                    f"Room vacated with {int(minutes_remaining)} min remaining "
                                    f"(threshold {EARLY_VACATE_THRESHOLD_MINUTES} min)"
                                ),
                                detected_at=now,
                                resolved=False,
                            )
                        )

    return findings


def _parse_dt(value: str | datetime) -> datetime | None:
    """Safely parse a datetime value."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except (ValueError, TypeError):
            return None
    return None
