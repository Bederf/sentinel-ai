"""Persistence layer for occupancy events and space findings.

Stores OccupancyEvent, GhostBookingFinding, and RightSizingFinding.
Uses 3-tier fallback: Supabase -> JSON file.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from app.models.space_occupancy import (
    FocusRoomSession,
    GhostBookingFinding,
    OccupancyEvent,
    RightSizingFinding,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "space"
_EVENTS_FILE = _DATA_DIR / "occupancy_events.json"
_GHOST_FILE = _DATA_DIR / "ghost_findings.json"
_RIGHTSIZING_FILE = _DATA_DIR / "rightsizing_findings.json"
_SESSIONS_FILE = _DATA_DIR / "focus_room_sessions.json"

_lock = threading.Lock()


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_json(path: Path, data: list[dict]) -> None:
    _ensure_data_dir()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# OccupancyEvent persistence
# ---------------------------------------------------------------------------


def _event_to_dict(e: OccupancyEvent) -> dict:
    return {
        "id": e.id,
        "site_id": e.site_id,
        "room_code": e.room_code,
        "sensor_id": e.sensor_id,
        "occupied": e.occupied,
        "timestamp": _dt_to_str(e.timestamp),
        "source": e.source,
        "received_at": _dt_to_str(e.received_at),
    }


def _dict_to_event(d: dict) -> OccupancyEvent:
    return OccupancyEvent(
        id=d["id"],
        site_id=d.get("site_id", ""),
        room_code=d.get("room_code", ""),
        sensor_id=d.get("sensor_id", ""),
        occupied=d.get("occupied", False),
        timestamp=_str_to_dt(d["timestamp"]),
        source=d.get("source", ""),
        received_at=_str_to_dt(d.get("received_at", d["timestamp"])),
    )


def save_event(event: OccupancyEvent) -> OccupancyEvent:
    """Persist a single occupancy event."""
    with _lock:
        rows = _load_json(_EVENTS_FILE)
        rows.append(_event_to_dict(event))
        # Keep last 10000 events to prevent unbounded growth
        if len(rows) > 10000:
            rows = rows[-10000:]
        _save_json(_EVENTS_FILE, rows)
    return event


def get_events_for_room(
    room_code: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> list[OccupancyEvent]:
    """Return events for a room, optionally filtered by time range."""
    rows = _load_json(_EVENTS_FILE)
    events = [_dict_to_event(r) for r in rows if r.get("room_code") == room_code]
    if from_dt:
        events = [e for e in events if e.timestamp >= from_dt]
    if to_dt:
        events = [e for e in events if e.timestamp <= to_dt]
    events.sort(key=lambda e: e.timestamp)
    return events


def room_has_sensor_data(room_code: str) -> bool:
    """Return True if we have ever received any occupancy event for this room.

    Used to distinguish 'no presence detected' (ghost) from 'no sensor deployed'.
    """
    events = get_events_for_room(room_code)
    return len(events) > 0


def _get_sensor_silence_threshold() -> int:
    """Read sensor silence threshold from space settings, fall back to config."""
    try:
        from app.api.space_settings import get_space_setting

        val = get_space_setting("sensor_silence_threshold_minutes")
        if val is not None:
            return int(val)
    except Exception:
        pass
    try:
        from app.config.settings import settings

        return settings.sensor_silence_threshold_minutes or 30
    except Exception:
        return 30


def room_sensor_is_alive(room_code: str, max_silence_minutes: int = 0) -> bool:
    """Return True if the sensor has reported within the last N minutes.

    If the sensor has gone silent (no events for max_silence_minutes), this
    indicates a connectivity or hardware fault — not a ghost booking.
    Returns True if no events exist at all (defer to room_has_sensor_data).
    """
    if max_silence_minutes <= 0:
        max_silence_minutes = _get_sensor_silence_threshold()
    events = get_events_for_room(room_code)
    if not events:
        return True  # No data at all — handled by room_has_sensor_data
    last = events[-1]
    age_minutes = (datetime.utcnow() - _make_naive(last.timestamp)).total_seconds() / 60
    return age_minutes <= max_silence_minutes


def _make_naive(dt: datetime) -> datetime:
    """Strip timezone info for safe comparison with naive datetimes."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def get_last_event(room_code: str) -> OccupancyEvent | None:
    """Return the most recent event for a room regardless of state."""
    events = get_events_for_room(room_code)
    return events[-1] if events else None


def get_occupied_minutes(room_code: str, from_dt: datetime, to_dt: datetime) -> int:
    """Calculate total minutes where occupied=True between from_dt and to_dt.

    Uses event timestamps to compute duration of each occupied segment.
    """
    events = get_events_for_room(room_code, from_dt, to_dt)
    if not events:
        return 0

    total_seconds = 0.0
    segment_start: datetime | None = None

    for event in events:
        if event.occupied and segment_start is None:
            segment_start = event.timestamp
        elif not event.occupied and segment_start is not None:
            total_seconds += (event.timestamp - segment_start).total_seconds()
            segment_start = None

    # If still occupied at to_dt, count up to to_dt
    if segment_start is not None:
        total_seconds += (to_dt - segment_start).total_seconds()

    return int(total_seconds / 60)


def get_current_vacancy_start(room_code: str) -> datetime | None:
    """Return the timestamp of the most recent transition to occupied=False.

    Returns None if the room is currently occupied or has no events.
    """
    last = get_last_event(room_code)
    if last is None or last.occupied:
        return None
    return last.timestamp


# ---------------------------------------------------------------------------
# GhostBookingFinding persistence
# ---------------------------------------------------------------------------


def _ghost_to_dict(f: GhostBookingFinding) -> dict:
    return {
        "id": f.id,
        "site_id": f.site_id,
        "room_code": f.room_code,
        "room_name": f.room_name,
        "booking_id": f.booking_id,
        "organiser_email": f.organiser_email,
        "organiser_name": f.organiser_name,
        "booking_start": _dt_to_str(f.booking_start),
        "booking_end": _dt_to_str(f.booking_end),
        "grace_period_minutes": f.grace_period_minutes,
        "detected_at": _dt_to_str(f.detected_at),
        "notification_sent": f.notification_sent,
        "notification_sent_at": _dt_to_str(f.notification_sent_at) if f.notification_sent_at else None,
        "status": f.status,
        "resolved_at": _dt_to_str(f.resolved_at) if f.resolved_at else None,
        "inspected_by": f.inspected_by,
        "inspected_at": _dt_to_str(f.inspected_at) if f.inspected_at else None,
        "concierge_email": f.concierge_email,
        "concierge_whatsapp": f.concierge_whatsapp,
        "email_notified_at": _dt_to_str(f.email_notified_at) if f.email_notified_at else None,
        "whatsapp_notified_at": _dt_to_str(f.whatsapp_notified_at) if f.whatsapp_notified_at else None,
        "whatsapp_message_id": f.whatsapp_message_id,
        "response_message_id": f.response_message_id,
        "response_text": f.response_text,
        "reminder_sent": f.reminder_sent,
        "reminder_sent_at": _dt_to_str(f.reminder_sent_at) if f.reminder_sent_at else None,
        "cost_centre": f.cost_centre,
        "charge_amount": f.charge_amount,
        "charge_reason": f.charge_reason,
    }


def _dict_to_ghost(d: dict) -> GhostBookingFinding:
    status = d.get("status", "open")
    if status == "released":
        status = "confirmed_empty"

    return GhostBookingFinding(
        id=d["id"],
        site_id=d.get("site_id", ""),
        room_code=d.get("room_code", ""),
        room_name=d.get("room_name", ""),
        booking_id=d.get("booking_id", ""),
        organiser_email=d.get("organiser_email", ""),
        organiser_name=d.get("organiser_name", ""),
        booking_start=_str_to_dt(d["booking_start"]),
        booking_end=_str_to_dt(d["booking_end"]),
        grace_period_minutes=d.get("grace_period_minutes", 0),
        detected_at=_str_to_dt(d["detected_at"]),
        notification_sent=d.get("notification_sent", False),
        notification_sent_at=_str_to_dt(d["notification_sent_at"]) if d.get("notification_sent_at") else None,
        status=status,
        resolved_at=_str_to_dt(d["resolved_at"]) if d.get("resolved_at") else None,
        inspected_by=d.get("inspected_by"),
        inspected_at=_str_to_dt(d["inspected_at"]) if d.get("inspected_at") else None,
        concierge_email=d.get("concierge_email"),
        concierge_whatsapp=d.get("concierge_whatsapp"),
        email_notified_at=_str_to_dt(d["email_notified_at"]) if d.get("email_notified_at") else None,
        whatsapp_notified_at=_str_to_dt(d["whatsapp_notified_at"]) if d.get("whatsapp_notified_at") else None,
        whatsapp_message_id=d.get("whatsapp_message_id"),
        response_message_id=d.get("response_message_id"),
        response_text=d.get("response_text"),
        reminder_sent=d.get("reminder_sent", False),
        reminder_sent_at=_str_to_dt(d["reminder_sent_at"]) if d.get("reminder_sent_at") else None,
        cost_centre=d.get("cost_centre"),
        charge_amount=d.get("charge_amount"),
        charge_reason=d.get("charge_reason"),
    )


def save_ghost_finding(finding: GhostBookingFinding) -> GhostBookingFinding:
    with _lock:
        rows = _load_json(_GHOST_FILE)
        rows.append(_ghost_to_dict(finding))
        _save_json(_GHOST_FILE, rows)
    return finding


def get_open_ghost_finding(booking_id: str) -> GhostBookingFinding | None:
    """Return any existing ghost finding for a booking (prevents duplicates).

    Once a finding exists for a booking — regardless of status — we never
    create another one.  The scanner and event handler both call this before
    inserting a new finding.
    """
    rows = _load_json(_GHOST_FILE)
    for r in rows:
        if r.get("booking_id") == booking_id:
            return _dict_to_ghost(r)
    return None


def update_ghost_finding_status(
    finding_id: str,
    status: str,
    *,
    inspected_by: str | None = None,
    cost_centre: str | None = None,
    charge_amount: float | None = None,
    charge_reason: str | None = None,
    response_message_id: str | None = None,
    response_text: str | None = None,
) -> GhostBookingFinding | None:
    with _lock:
        rows = _load_json(_GHOST_FILE)
        for r in rows:
            if r["id"] == finding_id:
                if status == "released":
                    status = "confirmed_empty"
                r["status"] = status
                if status in ("verified_occupied", "confirmed_empty", "dismissed"):
                    r["resolved_at"] = _dt_to_str(datetime.utcnow())
                if inspected_by:
                    r["inspected_by"] = inspected_by
                    r["inspected_at"] = _dt_to_str(datetime.utcnow())
                if response_message_id:
                    r["response_message_id"] = response_message_id
                if response_text:
                    r["response_text"] = response_text
                if cost_centre:
                    r["cost_centre"] = cost_centre
                if charge_amount is not None:
                    r["charge_amount"] = charge_amount
                if charge_reason:
                    r["charge_reason"] = charge_reason
                _save_json(_GHOST_FILE, rows)
                return _dict_to_ghost(r)
    return None


def get_ghost_finding_by_id(finding_id: str) -> GhostBookingFinding | None:
    """Return a ghost finding by ID."""
    rows = _load_json(_GHOST_FILE)
    for r in rows:
        if r["id"] == finding_id:
            return _dict_to_ghost(r)
    return None


def get_open_or_pending_ghost_finding(booking_id: str) -> GhostBookingFinding | None:
    """Return open or pending_inspection ghost finding for a booking."""
    rows = _load_json(_GHOST_FILE)
    for r in rows:
        if r.get("booking_id") == booking_id and r.get("status") in ("open", "pending_inspection"):
            return _dict_to_ghost(r)
    return None


def _normalise_whatsapp_number(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("whatsapp:", "").replace(" ", "").strip()


def mark_ghost_finding_notified(
    finding_id: str,
    *,
    concierge_email: str | None = None,
    concierge_whatsapp: str | None = None,
    email_sent: bool = False,
    whatsapp_sent: bool = False,
    whatsapp_message_id: str | None = None,
) -> GhostBookingFinding | None:
    with _lock:
        rows = _load_json(_GHOST_FILE)
        for r in rows:
            if r["id"] != finding_id:
                continue

            now_str = _dt_to_str(datetime.utcnow())
            r["notification_sent"] = bool(r.get("notification_sent")) or email_sent or whatsapp_sent
            r["notification_sent_at"] = now_str
            if concierge_email:
                r["concierge_email"] = concierge_email
            if concierge_whatsapp:
                r["concierge_whatsapp"] = _normalise_whatsapp_number(concierge_whatsapp)
            if email_sent:
                r["email_notified_at"] = now_str
            if whatsapp_sent:
                r["whatsapp_notified_at"] = now_str
            if whatsapp_message_id:
                r["whatsapp_message_id"] = whatsapp_message_id
            if r.get("status") == "open":
                r["status"] = "pending_inspection"
            _save_json(_GHOST_FILE, rows)
            return _dict_to_ghost(r)
    return None


def mark_ghost_finding_reminder_sent(
    finding_id: str,
    *,
    whatsapp_message_id: str | None = None,
) -> GhostBookingFinding | None:
    """Mark that the 15-min reminder was sent for this finding."""
    with _lock:
        rows = _load_json(_GHOST_FILE)
        for r in rows:
            if r["id"] != finding_id:
                continue
            now_str = _dt_to_str(datetime.utcnow())
            r["reminder_sent"] = True
            r["reminder_sent_at"] = now_str
            if whatsapp_message_id:
                r["whatsapp_message_id"] = whatsapp_message_id
            _save_json(_GHOST_FILE, rows)
            return _dict_to_ghost(r)
    return None


def find_pending_ghost_for_whatsapp(
    concierge_whatsapp: str,
    *,
    reply_to_message_id: str | None = None,
) -> GhostBookingFinding | None:
    target = _normalise_whatsapp_number(concierge_whatsapp)
    if not target:
        return None

    rows = _load_json(_GHOST_FILE)
    candidates = [
        r
        for r in rows
        if r.get("status") in ("open", "pending_inspection")
        and _normalise_whatsapp_number(r.get("concierge_whatsapp")) == target
    ]
    if not candidates:
        return None

    # Always require swipe-reply — match quoted message exactly
    if not reply_to_message_id:
        return None

    for row in candidates:
        if row.get("whatsapp_message_id") == reply_to_message_id:
            return _dict_to_ghost(row)

    return None


def get_pending_ghost_findings_for_whatsapp(concierge_whatsapp: str) -> list[GhostBookingFinding]:
    """Return all pending ghost findings for a concierge WhatsApp number."""
    target = _normalise_whatsapp_number(concierge_whatsapp)
    if not target:
        return []
    rows = _load_json(_GHOST_FILE)
    return [
        _dict_to_ghost(r)
        for r in rows
        if r.get("status") in ("open", "pending_inspection")
        and _normalise_whatsapp_number(r.get("concierge_whatsapp")) == target
    ]


def get_ghost_findings(site_id: str, status: str | None = None) -> list[GhostBookingFinding]:
    rows = _load_json(_GHOST_FILE)
    findings = [_dict_to_ghost(r) for r in rows if r.get("site_id") == site_id]
    if status:
        findings = [f for f in findings if f.status == status]
    return findings


# ---------------------------------------------------------------------------
# RightSizingFinding persistence
# ---------------------------------------------------------------------------


def _rs_to_dict(f: RightSizingFinding) -> dict:
    return {
        "id": f.id,
        "site_id": f.site_id,
        "room_code": f.room_code,
        "room_name": f.room_name,
        "room_capacity": f.room_capacity,
        "booking_id": f.booking_id,
        "organiser_email": f.organiser_email,
        "organiser_name": f.organiser_name,
        "booking_start": _dt_to_str(f.booking_start),
        "booking_end": _dt_to_str(f.booking_end),
        "booking_duration_minutes": f.booking_duration_minutes,
        "occupied_minutes": f.occupied_minutes,
        "vacancy_started_at": _dt_to_str(f.vacancy_started_at),
        "consecutive_vacancy_minutes": f.consecutive_vacancy_minutes,
        "pattern_type": f.pattern_type,
        "detected_at": _dt_to_str(f.detected_at),
        "notification_sent": f.notification_sent,
        "notification_sent_at": _dt_to_str(f.notification_sent_at) if f.notification_sent_at else None,
        "status": f.status,
    }


def _dict_to_rs(d: dict) -> RightSizingFinding:
    return RightSizingFinding(
        id=d["id"],
        site_id=d.get("site_id", ""),
        room_code=d.get("room_code", ""),
        room_name=d.get("room_name", ""),
        room_capacity=d.get("room_capacity", 0),
        booking_id=d.get("booking_id", ""),
        organiser_email=d.get("organiser_email", ""),
        organiser_name=d.get("organiser_name", ""),
        booking_start=_str_to_dt(d["booking_start"]),
        booking_end=_str_to_dt(d["booking_end"]),
        booking_duration_minutes=d.get("booking_duration_minutes", 0),
        occupied_minutes=d.get("occupied_minutes", 0),
        vacancy_started_at=_str_to_dt(d["vacancy_started_at"]),
        consecutive_vacancy_minutes=d.get("consecutive_vacancy_minutes", 0),
        pattern_type=d.get("pattern_type", ""),
        detected_at=_str_to_dt(d["detected_at"]),
        notification_sent=d.get("notification_sent", False),
        notification_sent_at=_str_to_dt(d["notification_sent_at"]) if d.get("notification_sent_at") else None,
        status=d.get("status", "open"),
    )


def save_rightsizing_finding(finding: RightSizingFinding) -> RightSizingFinding:
    with _lock:
        rows = _load_json(_RIGHTSIZING_FILE)
        rows.append(_rs_to_dict(finding))
        _save_json(_RIGHTSIZING_FILE, rows)
    return finding


def get_open_rightsizing_finding(booking_id: str) -> RightSizingFinding | None:
    """Return open right-sizing finding for a booking, if any."""
    rows = _load_json(_RIGHTSIZING_FILE)
    for r in rows:
        if r.get("booking_id") == booking_id and r.get("status") == "open":
            return _dict_to_rs(r)
    return None


def update_rightsizing_finding_status(finding_id: str, status: str) -> RightSizingFinding | None:
    with _lock:
        rows = _load_json(_RIGHTSIZING_FILE)
        for r in rows:
            if r["id"] == finding_id:
                r["status"] = status
                _save_json(_RIGHTSIZING_FILE, rows)
                return _dict_to_rs(r)
    return None


def get_rightsizing_findings(site_id: str, status: str | None = None) -> list[RightSizingFinding]:
    rows = _load_json(_RIGHTSIZING_FILE)
    findings = [_dict_to_rs(r) for r in rows if r.get("site_id") == site_id]
    if status:
        findings = [f for f in findings if f.status == status]
    return findings


# ---------------------------------------------------------------------------
# FocusRoomSession persistence (Phase 2)
# ---------------------------------------------------------------------------


def _session_to_dict(s: FocusRoomSession) -> dict:
    return {
        "session_id": s.session_id,
        "site_id": s.site_id,
        "room_code": s.room_code,
        "room_type": s.room_type,
        "sensor_id": s.sensor_id,
        "source": s.source,
        "start_time": _dt_to_str(s.start_time),
        "end_time": _dt_to_str(s.end_time) if s.end_time else None,
        "duration_seconds": s.duration_seconds,
        "extended_use": s.extended_use,
        "created_at": _dt_to_str(s.created_at),
    }


def _dict_to_session(d: dict) -> FocusRoomSession:
    return FocusRoomSession(
        session_id=d["session_id"],
        site_id=d.get("site_id", ""),
        room_code=d.get("room_code", ""),
        room_type=d.get("room_type", "focus"),
        sensor_id=d.get("sensor_id", ""),
        source=d.get("source", "mmwave_ld2410c"),
        start_time=_str_to_dt(d["start_time"]),
        end_time=_str_to_dt(d["end_time"]) if d.get("end_time") else None,
        duration_seconds=d.get("duration_seconds", 0),
        extended_use=d.get("extended_use", False),
        created_at=_str_to_dt(d.get("created_at", d["start_time"])),
    )


def save_session(session: FocusRoomSession) -> FocusRoomSession:
    """Persist a new focus room session."""
    with _lock:
        rows = _load_json(_SESSIONS_FILE)
        rows.append(_session_to_dict(session))
        # Keep last 10000 sessions
        if len(rows) > 10000:
            rows = rows[-10000:]
        _save_json(_SESSIONS_FILE, rows)
    return session


def get_active_session(room_code: str) -> FocusRoomSession | None:
    """Return the currently open (no end_time) session for a room."""
    rows = _load_json(_SESSIONS_FILE)
    for r in reversed(rows):
        if r.get("room_code") == room_code and r.get("end_time") is None:
            return _dict_to_session(r)
    return None


def close_session(
    session_id: str,
    end_time: datetime,
    extended_threshold: int = 7200,
) -> FocusRoomSession | None:
    """Close a session: set end_time, compute duration, flag extended_use."""
    with _lock:
        rows = _load_json(_SESSIONS_FILE)
        for r in rows:
            if r["session_id"] == session_id:
                start = _str_to_dt(r["start_time"])
                duration = int((end_time - start).total_seconds())
                r["end_time"] = _dt_to_str(end_time)
                r["duration_seconds"] = duration
                r["extended_use"] = duration > extended_threshold
                _save_json(_SESSIONS_FILE, rows)
                return _dict_to_session(r)
    return None


def discard_session(session_id: str) -> bool:
    """Remove a session (noise filtering — too short)."""
    with _lock:
        rows = _load_json(_SESSIONS_FILE)
        before = len(rows)
        rows = [r for r in rows if r["session_id"] != session_id]
        if len(rows) < before:
            _save_json(_SESSIONS_FILE, rows)
            return True
    return False


def get_sessions_for_room(
    room_code: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> list[FocusRoomSession]:
    """Return closed sessions for a room, optionally filtered by time range."""
    rows = _load_json(_SESSIONS_FILE)
    sessions = [_dict_to_session(r) for r in rows if r.get("room_code") == room_code]
    if from_dt:
        sessions = [s for s in sessions if s.start_time >= from_dt]
    if to_dt:
        sessions = [s for s in sessions if s.start_time <= to_dt]
    sessions.sort(key=lambda s: s.start_time)
    return sessions


def get_sessions_for_site(
    site_id: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    extended_only: bool = False,
) -> list[FocusRoomSession]:
    """Return sessions for a site with optional filters."""
    rows = _load_json(_SESSIONS_FILE)
    sessions = [_dict_to_session(r) for r in rows if r.get("site_id") == site_id]
    if from_dt:
        sessions = [s for s in sessions if s.start_time >= from_dt]
    if to_dt:
        sessions = [s for s in sessions if s.start_time <= to_dt]
    if extended_only:
        sessions = [s for s in sessions if s.extended_use]
    sessions.sort(key=lambda s: s.start_time)
    return sessions
