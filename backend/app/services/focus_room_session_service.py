"""Focus Room Session Service (Phase 2).

Converts raw occupancy events into continuous sessions for focus rooms
that have no booking system. Sessions are:
  - Created when occupied=True arrives with no active session
  - Held open through short vacancy gaps (gap tolerance)
  - Closed when occupied=False arrives and gap exceeds threshold
  - Discarded if duration < min_session_seconds (noise filtering)
  - Flagged as extended_use if duration > extended_use_threshold_seconds

No hardware or firmware changes — uses the same LD2410C OUT pin events.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.models.space_occupancy import FocusRoomSession

logger = logging.getLogger(__name__)

# Default thresholds (overridden by settings)
DEFAULT_MIN_SESSION_SECONDS = 180  # 3 minutes — discard shorter visits
DEFAULT_EXTENDED_USE_SECONDS = 7200  # 2 hours — flag as extended
DEFAULT_RED_LIGHT_COOLDOWN_SECONDS = 300  # 5 minutes — keep red light on after overstay ends
DEFAULT_GAP_TOLERANCE_SECONDS = 30  # 30 seconds — door-open buffer before closing session


def describe_focus_session_state(
    session: FocusRoomSession,
    now: datetime | None = None,
    extended_use_seconds: int | None = None,
    red_light_cooldown_seconds: int | None = None,
) -> dict[str, int | float | bool]:
    """Compute live session state for API/UI use.

    Active sessions should expose current elapsed duration and whether the
    overstay red-light indicator should be on right now.
    """
    current_time = now or datetime.utcnow()
    extended_threshold = extended_use_seconds or _get_extended_use_seconds()
    cooldown_threshold = red_light_cooldown_seconds or _get_red_light_cooldown_seconds()

    if session.is_active:
        duration_seconds = max(int((current_time - session.start_time).total_seconds()), 0)
        red_light_on = duration_seconds > extended_threshold
    else:
        duration_seconds = session.duration_seconds
        red_light_on = bool(
            session.extended_use
            and session.end_time
            and (current_time - session.end_time).total_seconds() <= cooldown_threshold
        )
    cooldown_remaining_seconds = 0
    if red_light_on and not session.is_active and session.end_time:
        cooldown_elapsed = max(int((current_time - session.end_time).total_seconds()), 0)
        cooldown_remaining_seconds = max(cooldown_threshold - cooldown_elapsed, 0)

    return {
        "duration_seconds": duration_seconds,
        "duration_minutes": round(duration_seconds / 60, 1),
        "extended_use": session.extended_use or red_light_on,
        "red_light_on": red_light_on,
        "max_allowed_minutes": round(extended_threshold / 60),
        "red_light_cooldown_seconds": cooldown_threshold,
        "red_light_cooldown_remaining_seconds": cooldown_remaining_seconds,
    }


def process_focus_room_event(
    site_id: str,
    room_code: str,
    sensor_id: str,
    occupied: bool,
    timestamp: datetime,
    source: str = "mmwave_ld2410c",
    room_type: str = "focus",
    min_session_seconds: int | None = None,
    extended_use_seconds: int | None = None,
    gap_tolerance_seconds: int | None = None,
) -> dict:
    """Process a single occupancy event for a focus room.

    Returns a dict describing what happened:
      - session_started: new session created
      - session_closed: session ended (with duration, extended_use flag)
      - session_discarded: session was too short (noise)
      - session_held: vacancy received but gap tolerance still open
      - no_action: event didn't change state (duplicate or within gap tolerance)
    """
    from app.services import occupancy_store

    min_secs = min_session_seconds or _get_min_session_seconds()
    ext_secs = extended_use_seconds or _get_extended_use_seconds()
    gap_secs = gap_tolerance_seconds or _get_gap_tolerance_seconds()

    active = occupancy_store.get_active_session(room_code)

    if occupied and active is None:
        # Start a new session
        session = FocusRoomSession(
            site_id=site_id,
            room_code=room_code,
            room_type=room_type,
            sensor_id=sensor_id,
            source=source,
            start_time=timestamp,
            created_at=datetime.utcnow(),
        )
        occupancy_store.save_session(session)
        logger.info("Focus session started: room=%s session=%s", room_code, session.session_id)
        return {
            "action": "session_started",
            "session_id": session.session_id,
            "room_code": room_code,
            "start_time": timestamp.isoformat(),
        }

    elif occupied and active is not None:
        # Occupied event — clear any vacant_since, session stays open
        if active.vacant_since is not None:
            occupancy_store.clear_vacant_since(active.session_id)
            logger.debug("Focus session held open: room=%s (occupied resumed)", room_code)
        return {"action": "no_action", "room_code": room_code}

    elif not occupied and active is not None:
        # Vacancy event — start gap timer if not already running
        if active.vacant_since is None:
            occupancy_store.set_vacant_since(active.session_id, timestamp)
            logger.debug(
                "Focus session gap started: room=%s at %s (tolerance=%ds)",
                room_code,
                timestamp.isoformat(),
                gap_secs,
            )
            return {"action": "session_held", "room_code": room_code}

        # Gap timer already running — check if tolerance exceeded
        gap_duration = int((timestamp - active.vacant_since).total_seconds())
        if gap_duration < gap_secs:
            logger.debug(
                "Focus session gap still open: room=%s gap=%ds < %ds tolerance",
                room_code,
                gap_duration,
                gap_secs,
            )
            return {"action": "no_action", "room_code": room_code}

        # Gap exceeded — close the session
        duration = int((timestamp - active.start_time).total_seconds())

        if duration < min_secs:
            occupancy_store.discard_session(active.session_id)
            logger.debug(
                "Focus session discarded (noise): room=%s duration=%ds < %ds",
                room_code,
                duration,
                min_secs,
            )
            return {
                "action": "session_discarded",
                "session_id": active.session_id,
                "room_code": room_code,
                "duration_seconds": duration,
                "reason": f"Duration {duration}s < minimum {min_secs}s",
            }

        closed = occupancy_store.close_session(active.session_id, timestamp, extended_threshold=ext_secs)
        if closed:
            logger.info(
                "Focus session closed: room=%s duration=%ds extended=%s",
                room_code,
                closed.duration_seconds,
                closed.extended_use,
            )
            return {
                "action": "session_closed",
                "session_id": closed.session_id,
                "room_code": room_code,
                "start_time": closed.start_time.isoformat(),
                "end_time": closed.end_time.isoformat() if closed.end_time else None,
                "duration_seconds": closed.duration_seconds,
                "extended_use": closed.extended_use,
            }

    # No state change (duplicate occupied or unmatched vacant)
    return {"action": "no_action", "room_code": room_code}


def get_focus_room_analytics(
    site_id: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> dict:
    """Generate analytics for focus room sessions.

    Returns:
      - total_sessions
      - average_duration_minutes
      - longest_session_minutes
      - extended_use_count
      - sessions_by_room: {room_code: count}
      - peak_hour: most common session start hour
    """
    from app.services import occupancy_store

    sessions = occupancy_store.get_sessions_for_site(site_id, from_dt, to_dt)
    active = [s for s in sessions if s.end_time is None]
    closed = [s for s in sessions if s.end_time is not None]

    if not sessions:
        return {
            "site_id": site_id,
            "total_sessions": 0,
            "active_sessions": 0,
            "completed_sessions": 0,
            "average_duration_minutes": 0,
            "longest_session_minutes": 0,
            "extended_use_count": 0,
            "extended_use_sessions": 0,
            "sessions_by_room": {},
            "peak_hour": None,
        }

    durations = [s.duration_seconds for s in closed]
    avg_min = round(sum(durations) / len(durations) / 60, 1) if durations else 0
    longest_min = round(max(durations) / 60, 1) if durations else 0
    active_extended = sum(1 for s in active if describe_focus_session_state(s)["red_light_on"])
    extended = sum(1 for s in closed if s.extended_use) + active_extended

    by_room: dict[str, int] = {}
    hour_counts: dict[int, int] = {}
    for s in sessions:
        by_room[s.room_code] = by_room.get(s.room_code, 0) + 1
        h = s.start_time.hour
        hour_counts[h] = hour_counts.get(h, 0) + 1

    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None

    return {
        "site_id": site_id,
        "total_sessions": len(closed),
        "active_sessions": len(active),
        "completed_sessions": len(closed),
        "average_duration_minutes": avg_min,
        "longest_session_minutes": longest_min,
        "extended_use_count": extended,
        "extended_use_sessions": extended,
        "sessions_by_room": by_room,
        "peak_hour": peak_hour,
    }


def _get_min_session_seconds() -> int:
    try:
        from app.config.settings import settings

        return settings.focus_min_session_seconds
    except Exception:
        return DEFAULT_MIN_SESSION_SECONDS


def _get_extended_use_seconds() -> int:
    try:
        from app.config.settings import settings

        return settings.focus_extended_use_seconds
    except Exception:
        return DEFAULT_EXTENDED_USE_SECONDS


def _get_red_light_cooldown_seconds() -> int:
    try:
        from app.config.settings import settings

        return settings.focus_red_light_cooldown_seconds
    except Exception:
        return DEFAULT_RED_LIGHT_COOLDOWN_SECONDS


def _get_gap_tolerance_seconds() -> int:
    try:
        from app.config.settings import settings

        return settings.focus_vacancy_grace_seconds
    except Exception:
        return DEFAULT_GAP_TOLERANCE_SECONDS
