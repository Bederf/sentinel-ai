"""Ghost Booking & Right-Sizing Detection (Rev 1.2).

Ghost booking: room booked but never occupied after grace period.
Right-sizing: room occupied but underused (presence-based patterns, no headcount).

The HLK-LD2410C mmWave sensor reports presence zones only.
All logic uses ``occupied: bool`` — never a count.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.config.settings import settings
from app.models.booking_record import BookingRecord
from app.models.space_occupancy import (
    GhostBookingFinding,
    RightSizingFinding,
    RightSizingPattern,
)
from app.services import occupancy_store

logger = logging.getLogger(__name__)


def _make_naive(dt: datetime) -> datetime:
    """Strip timezone info for safe comparison with naive datetimes."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


# ---------------------------------------------------------------------------
# Config — sourced from settings / env vars
# ---------------------------------------------------------------------------

GHOST_GRACE_MINUTES = 15  # Wait N minutes after booking start before flagging

EARLY_VACATE_THRESHOLD_MINUTES = 90  # Room empty with >90 min of booking remaining
SPORADIC_USE_THRESHOLD_PCT = 25  # Occupied < 25% of total booking duration
BRIEF_OCCUPATION_THRESHOLD_MIN = 30  # Occupied < 30 min total in the whole booking
RIGHT_SIZING_GRACE_MINUTES = 20  # Do not flag until meeting has been running this long


def _get_config_int(attr: str, default: int) -> int:
    return getattr(settings, attr, default) or default


def _grace_minutes() -> int:
    return _get_config_int("ghost_booking_grace_minutes", GHOST_GRACE_MINUTES)


def _early_vacate_threshold() -> int:
    return _get_config_int("early_vacate_threshold_minutes", EARLY_VACATE_THRESHOLD_MINUTES)


def _sporadic_pct() -> int:
    return _get_config_int("sporadic_use_threshold_pct", SPORADIC_USE_THRESHOLD_PCT)


def _brief_threshold() -> int:
    return _get_config_int("brief_occupation_threshold_min", BRIEF_OCCUPATION_THRESHOLD_MIN)


def _rs_grace() -> int:
    return _get_config_int("right_sizing_grace_minutes", RIGHT_SIZING_GRACE_MINUTES)


# ---------------------------------------------------------------------------
# Ghost Booking Detection
# ---------------------------------------------------------------------------


def detect_ghost_booking(
    booking: BookingRecord,
    now: datetime | None = None,
    room_code: str | None = None,
) -> GhostBookingFinding | None:
    """Check if a booking is a ghost (no occupancy after grace period).

    Returns a GhostBookingFinding if ghost detected, else None.
    Does not create a finding if one already exists for this booking.
    """
    now = now or datetime.utcnow()
    room = room_code or booking.room_id
    grace = _grace_minutes()

    # Normalize to naive UTC for safe comparison
    now_n = _make_naive(now)
    start_n = _make_naive(booking.start_time)
    end_n = _make_naive(booking.end_time)

    # Not yet past grace period
    elapsed = (now_n - start_n).total_seconds() / 60
    if elapsed < grace:
        return None

    # Booking already ended
    if now_n > end_n:
        return None

    # Already have an open finding for this booking
    existing = occupancy_store.get_open_ghost_finding(booking.id)
    if existing:
        return None

    # Skip rooms with no sensor deployed — no data ≠ empty room
    if not occupancy_store.room_has_sensor_data(room):
        logger.debug("Skipping ghost check for %s — no sensor data", room)
        return None

    # Skip rooms where sensor has gone silent — likely hardware/connectivity fault
    if not occupancy_store.room_sensor_is_alive(room):
        logger.warning("Skipping ghost check for %s — sensor silent (possible fault)", room)
        return None

    # Check if room was ever occupied since booking start
    occupied_mins = occupancy_store.get_occupied_minutes(room, start_n, now_n)
    if occupied_mins > 0:
        return None  # Room was used — not a ghost booking

    finding = GhostBookingFinding(
        site_id=booking.site_id,
        room_code=room,
        room_name=booking.room_name,
        booking_id=booking.id,
        organiser_email=booking.organiser_email,
        organiser_name=booking.organiser_name,
        booking_start=booking.start_time,
        booking_end=booking.end_time,
        grace_period_minutes=grace,
        detected_at=now,
    )
    occupancy_store.save_ghost_finding(finding)
    logger.info(
        "Ghost booking detected: room=%s booking=%s organiser=%s",
        room,
        booking.id,
        booking.organiser_email,
    )
    return finding


# ---------------------------------------------------------------------------
# Right-Sizing Pattern Detection
# ---------------------------------------------------------------------------


def detect_right_sizing_patterns(
    site_id: str,
    bookings: list[BookingRecord],
    now: datetime | None = None,
    room_codes: dict[str, str] | None = None,
    room_capacities: dict[str, int] | None = None,
) -> list[RightSizingFinding]:
    """Detect underuse patterns for active bookings.

    For each active booking where booking_start + RIGHT_SIZING_GRACE_MINUTES has elapsed:
    1. Calculate occupied_minutes, consecutive_vacancy_minutes, vacancy_started_at
    2. Check patterns: EARLY_VACATE, BRIEF_OCCUPATION, SPORADIC_USE
    3. Ghost booking takes precedence: skip if occupied_minutes == 0

    Args:
        site_id: Site identifier.
        bookings: Active bookings to check.
        now: Current time (for testing).
        room_codes: Optional mapping of booking.room_id -> room_code for sensor lookup.
        room_capacities: Optional mapping of room_code -> capacity.

    Returns:
        List of newly created RightSizingFindings.
    """
    now = now or datetime.utcnow()
    rs_grace = _rs_grace()
    early_thresh = _early_vacate_threshold()
    sporadic_pct = _sporadic_pct()
    brief_thresh = _brief_threshold()
    room_codes = room_codes or {}
    room_capacities = room_capacities or {}

    findings: list[RightSizingFinding] = []

    for booking in bookings:
        # Only check active bookings past grace period
        start_n = _make_naive(booking.start_time)
        end_n = _make_naive(booking.end_time)
        now_n = _make_naive(now)
        if now_n < start_n or now_n > end_n:
            continue

        elapsed_minutes = (now_n - start_n).total_seconds() / 60
        if elapsed_minutes < rs_grace:
            continue

        room = room_codes.get(booking.room_id, booking.room_id)

        # Already have an open finding for this booking
        existing = occupancy_store.get_open_rightsizing_finding(booking.id)
        if existing:
            continue

        # Calculate occupancy metrics
        occupied_mins = occupancy_store.get_occupied_minutes(room, start_n, now_n)

        # Ghost booking takes strict precedence — do NOT create right-sizing finding
        if occupied_mins == 0:
            continue

        vacancy_start = occupancy_store.get_current_vacancy_start(room)
        last_event = occupancy_store.get_last_event(room)

        consecutive_vacancy = 0
        if vacancy_start is not None:
            consecutive_vacancy = int((now - vacancy_start).total_seconds() / 60)

        booking_duration = int((end_n - start_n).total_seconds() / 60)
        time_remaining = int((end_n - now_n).total_seconds() / 60)
        currently_empty = last_event is not None and not last_event.occupied

        # Check patterns in order
        pattern: RightSizingPattern | None = None

        # EARLY_VACATE: room was occupied, now empty, >90 min of booking remaining
        if (
            currently_empty
            and occupied_mins > 0
            and time_remaining > early_thresh
            and consecutive_vacancy >= early_thresh
        ):
            pattern = RightSizingPattern.EARLY_VACATE

        # BRIEF_OCCUPATION: occupied < 30 min, booking running > 60 min, currently empty
        elif currently_empty and occupied_mins < brief_thresh and elapsed_minutes > 60:
            pattern = RightSizingPattern.BRIEF_OCCUPATION

        # SPORADIC_USE: occupied < 25% of booking, booking > 50% elapsed
        elif (
            booking_duration > 0
            and occupied_mins < (booking_duration * sporadic_pct / 100)
            and elapsed_minutes > (booking_duration * 0.5)
        ):
            pattern = RightSizingPattern.SPORADIC_USE

        if pattern is None:
            continue

        finding = RightSizingFinding(
            site_id=site_id,
            room_code=room,
            room_name=booking.room_name,
            room_capacity=room_capacities.get(room, 0),
            booking_id=booking.id,
            organiser_email=booking.organiser_email,
            organiser_name=booking.organiser_name,
            booking_start=booking.start_time,
            booking_end=booking.end_time,
            booking_duration_minutes=booking_duration,
            occupied_minutes=occupied_mins,
            vacancy_started_at=vacancy_start or now,
            consecutive_vacancy_minutes=consecutive_vacancy,
            pattern_type=pattern.value,
            detected_at=now,
        )
        occupancy_store.save_rightsizing_finding(finding)
        logger.info(
            "Right-sizing pattern detected: room=%s pattern=%s booking=%s occupied=%d/%d min",
            room,
            pattern.value,
            booking.id,
            occupied_mins,
            booking_duration,
        )
        findings.append(finding)

    return findings


# ---------------------------------------------------------------------------
# Auto-resolution helpers
# ---------------------------------------------------------------------------


def auto_resolve_ghost_on_occupation(booking_id: str) -> GhostBookingFinding | None:
    """If room becomes occupied and there's an open/pending ghost finding, resolve it."""
    finding = occupancy_store.get_open_or_pending_ghost_finding(booking_id)
    if finding:
        updated = occupancy_store.update_ghost_finding_status(finding.id, "verified_occupied")
        if updated:
            logger.info("Ghost finding auto-resolved: booking=%s -> verified_occupied", booking_id)
        return updated
    return None


def concierge_confirm_empty(
    finding_id: str,
    confirmed_by: str,
    cost_centre: str = "",
    charge_amount: float = 0.0,
) -> GhostBookingFinding | None:
    """Concierge confirms room is empty after physical inspection."""
    finding = occupancy_store.get_ghost_finding_by_id(finding_id)
    if not finding:
        return None

    if finding.status not in ("open", "pending_inspection"):
        logger.warning(
            "Cannot confirm finding %s: status=%s (expected open or pending_inspection)",
            finding_id,
            finding.status,
        )
        return None

    inspection_note = (
        f"Ghost booking inspection: {finding.room_name} ({finding.room_code}) confirmed empty by {confirmed_by}."
    )

    updated = occupancy_store.update_ghost_finding_status(
        finding_id,
        "confirmed_empty",
        inspected_by=confirmed_by,
        cost_centre=cost_centre,
        charge_amount=charge_amount,
        charge_reason=inspection_note,
    )
    if updated:
        logger.info(
            "Ghost booking confirmed empty: room=%s booking=%s confirmed_by=%s",
            finding.room_code,
            finding.booking_id,
            confirmed_by,
        )
    return updated


def concierge_confirm_occupied(
    finding_id: str,
    confirmed_by: str,
    *,
    response_message_id: str | None = None,
    response_text: str | None = None,
) -> GhostBookingFinding | None:
    """Concierge confirms the room is occupied after inspection."""
    finding = occupancy_store.get_ghost_finding_by_id(finding_id)
    if not finding:
        return None

    if finding.status not in ("open", "pending_inspection"):
        logger.warning(
            "Cannot confirm occupied for finding %s: status=%s",
            finding_id,
            finding.status,
        )
        return None

    updated = occupancy_store.update_ghost_finding_status(
        finding_id,
        "verified_occupied",
        inspected_by=confirmed_by,
        response_message_id=response_message_id,
        response_text=response_text,
    )
    if updated:
        logger.info(
            "Ghost booking confirmed occupied: room=%s booking=%s confirmed_by=%s",
            finding.room_code,
            finding.booking_id,
            confirmed_by,
        )
    return updated


def mark_pending_inspection(finding_id: str) -> GhostBookingFinding | None:
    """Mark a ghost finding as pending concierge inspection (notification sent)."""
    return occupancy_store.update_ghost_finding_status(finding_id, "pending_inspection")


def auto_dismiss_rightsizing_on_reoccupation(booking_id: str) -> RightSizingFinding | None:
    """If room becomes occupied again and there's an open right-sizing finding, dismiss it."""
    finding = occupancy_store.get_open_rightsizing_finding(booking_id)
    if finding:
        updated = occupancy_store.update_rightsizing_finding_status(finding.id, "dismissed")
        if updated:
            logger.info("Right-sizing finding auto-dismissed: booking=%s -> room reoccupied", booking_id)
        return updated
    return None


# ---------------------------------------------------------------------------
# Notification formatting
# ---------------------------------------------------------------------------


def format_right_sizing_notification(
    finding: RightSizingFinding,
    site_name: str,
    available_rooms: list[dict] | None = None,
) -> str:
    """Format a right-sizing notification message.

    Args:
        finding: The detected finding.
        site_name: Human-readable site name.
        available_rooms: List of dicts with keys: room_code, capacity, available_until.
    """
    pattern_desc = _pattern_description(finding)

    lines = [
        f"Room Usage Alert -- {site_name}",
        "",
        f"{finding.room_name} ({finding.room_code}, {finding.room_capacity} seats) "
        f"has been booked since {finding.booking_start.strftime('%H:%M')}",
        "but appears underused.",
        "",
        f"Pattern: {pattern_desc}",
        "",
        f"Organiser: {finding.organiser_name}",
        f"Booked until: {finding.booking_end.strftime('%H:%M')}",
    ]

    if available_rooms:
        lines.append("")
        lines.append("Smaller rooms currently available:")
        for room in available_rooms:
            lines.append(
                f"  - {room['room_code']} ({room['capacity']} seats) -- available until {room['available_until']}"
            )

    lines.append("")
    lines.append("Please contact the organiser to discuss releasing this room.")
    lines.append("")
    lines.append(f"SENTINEL - {site_name}")

    return "\n".join(lines)


def _pattern_description(finding: RightSizingFinding) -> str:
    """Generate human-readable pattern description."""
    if finding.pattern_type == RightSizingPattern.EARLY_VACATE:
        _remaining = finding.booking_duration_minutes - finding.occupied_minutes
        return f"Room occupied then vacated with {finding.consecutive_vacancy_minutes} minutes of booking remaining."
    elif finding.pattern_type == RightSizingPattern.BRIEF_OCCUPATION:
        return (
            f"Room occupied for only {finding.occupied_minutes} minutes "
            f"of a {finding.booking_duration_minutes}-minute booking."
        )
    elif finding.pattern_type == RightSizingPattern.SPORADIC_USE:
        pct = (
            round(finding.occupied_minutes / finding.booking_duration_minutes * 100)
            if finding.booking_duration_minutes > 0
            else 0
        )
        return (
            f"Room has been occupied for only {finding.occupied_minutes} "
            f"of {finding.booking_duration_minutes} minutes booked ({pct}%)."
        )
    return "Unknown pattern."


def format_ghost_booking_notification(
    finding: GhostBookingFinding,
    site_name: str,
    confirm_url: str | None = None,
) -> str:
    """Format a ghost booking notification for the concierge."""
    lines = [
        f"Ghost Booking -- Inspection Required -- {site_name}",
        "",
        f"{finding.room_name} ({finding.room_code}) has been booked since "
        f"{finding.booking_start.strftime('%H:%M')} but no movement has been "
        f"detected for {finding.grace_period_minutes} minutes.",
        "",
        "ACTION REQUIRED:",
        f"  Please inspect {finding.room_name} ({finding.room_code}).",
        "  Confirm whether the room is occupied or empty.",
        "",
        f"Organiser: {finding.organiser_name} ({finding.organiser_email})",
        f"Booked until: {finding.booking_end.strftime('%H:%M')}",
        f"Finding ID: {finding.id}",
    ]

    if confirm_url:
        lines.append("")
        lines.append(f"Confirm empty: {confirm_url}")

    lines.extend(
        [
            "",
            f"SENTINEL - {site_name}",
        ]
    )

    return "\n".join(lines)
