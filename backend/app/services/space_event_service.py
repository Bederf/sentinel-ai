"""Shared occupancy-event processing for space optimization."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.api.block_bookings import get_block_booking_config
from app.models.space_occupancy import OccupancyEvent
from app.services import occupancy_store
from app.services.focus_room_session_service import process_focus_room_event
from app.services.ghost_booking_detector import (
    auto_dismiss_rightsizing_on_reoccupation,
    auto_resolve_ghost_on_occupation,
    detect_ghost_booking,
    detect_right_sizing_patterns,
)
from app.services.ghost_room_notifier import send_ghost_booking_alert


def get_active_bookings_for_room(site_id: str, room_code: str, now: datetime) -> list:
    """Get active bookings for a room at the given time."""
    try:
        from app.services.block_booking_detector.booking_store import get_booking_store

        store = get_booking_store()
        day_bookings = store.get_bookings_for_site(site_id, now.date())
        return [
            b
            for b in day_bookings
            if (b.room_id == room_code or b.room_name == room_code) and b.start_time <= now <= b.end_time
        ]
    except Exception:
        return []


async def process_occupancy_event(
    *,
    site_id: str,
    room_code: str,
    sensor_id: str,
    occupied: bool,
    source: str = "mmwave_ld2410c",
    room_type: str = "meeting",
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Persist an occupancy event and apply space-optimization rules."""
    now = timestamp or datetime.utcnow()
    event = OccupancyEvent(
        site_id=site_id,
        room_code=room_code,
        sensor_id=sensor_id,
        occupied=occupied,
        timestamp=now,
        source=source,
        received_at=datetime.utcnow(),
    )
    occupancy_store.save_event(event)

    result: dict[str, Any] = {
        "success": True,
        "event_id": event.id,
        "room_code": room_code,
        "occupied": occupied,
    }

    if room_type == "focus":
        result["focus_session"] = process_focus_room_event(
            site_id=site_id,
            room_code=room_code,
            sensor_id=sensor_id,
            occupied=occupied,
            timestamp=now,
            source=source,
            room_type="focus",
        )
        return result

    active_bookings = get_active_bookings_for_room(site_id, room_code, now)
    if not active_bookings:
        return result

    if occupied:
        resolved_count = 0
        dismissed_count = 0
        for booking in active_bookings:
            if auto_resolve_ghost_on_occupation(booking.id):
                resolved_count += 1
            if auto_dismiss_rightsizing_on_reoccupation(booking.id):
                dismissed_count += 1
        result["ghost_findings_resolved"] = resolved_count
        result["rightsizing_findings_dismissed"] = dismissed_count
        return result

    ghost_findings_created = 0
    ghost_notifications_sent = 0
    config = get_block_booking_config(site_id)

    for booking in active_bookings:
        ghost = detect_ghost_booking(booking, now=now, room_code=room_code)
        if ghost:
            ghost_findings_created += 1
            notification = await send_ghost_booking_alert(ghost, config, site_name=site_id)
            if notification.get("success"):
                ghost_notifications_sent += 1

    rs_findings = detect_right_sizing_patterns(
        site_id=site_id,
        bookings=active_bookings,
        now=now,
    )

    result["ghost_findings_created"] = ghost_findings_created
    result["ghost_notifications_sent"] = ghost_notifications_sent
    result["rightsizing_findings_created"] = len(rs_findings)
    return result
