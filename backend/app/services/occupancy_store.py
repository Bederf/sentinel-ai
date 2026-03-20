"""Persistence layer for occupancy events and space findings."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from app.models.space_occupancy import (
    FocusRoomSession,
    GhostBookingFinding,
    OccupancyEvent,
    RightSizingFinding,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _use_supabase() -> bool:
    try:
        return bool(settings.supabase_url and settings.supabase_service_role_key)
    except Exception:
        return False


def _client():
    return get_supabase_client()


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str | datetime) -> datetime:
    if isinstance(s, datetime):
        dt = s
    else:
        normalized = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _make_naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _effective_time(event: OccupancyEvent) -> datetime:
    ts = _make_naive(event.timestamp)
    if ts.year < 2020 and event.received_at:
        return _make_naive(event.received_at)
    return ts


def _event_to_dict(e: OccupancyEvent) -> dict:
    d = {
        "id": e.id,
        "site_id": e.site_id,
        "room_code": e.room_code,
        "sensor_id": e.sensor_id,
        "occupied": e.occupied,
        "timestamp": _dt_to_str(e.timestamp),
        "source": e.source,
        "received_at": _dt_to_str(e.received_at),
    }
    if e.moving is not None:
        d["moving"] = e.moving
    if e.stationary is not None:
        d["stationary"] = e.stationary
    if e.distance_m is not None:
        d["distance_m"] = e.distance_m
    if e.moving_gate is not None:
        d["moving_gate"] = e.moving_gate
    if e.static_gate is not None:
        d["static_gate"] = e.static_gate
    return d


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
        moving=d.get("moving"),
        stationary=d.get("stationary"),
        distance_m=d.get("distance_m"),
        moving_gate=d.get("moving_gate"),
        static_gate=d.get("static_gate"),
    )


def save_event(event: OccupancyEvent) -> OccupancyEvent:
    with _lock:
        try:
            _client().table("space_occupancy_events").insert(_event_to_dict(event)).execute()
        except Exception as exc:
            logger.error("Canonical save_event failed: %s", exc)
        return event


def get_events_for_room(
    room_code: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> list[OccupancyEvent]:
    try:
        query = _client().table("space_occupancy_events").select("*").eq("room_code", room_code)
        if from_dt:
            query = query.gte("timestamp", _dt_to_str(from_dt))
        if to_dt:
            query = query.lte("timestamp", _dt_to_str(to_dt))
        response = query.order("timestamp").execute()
        return [_dict_to_event(r) for r in (response.data or [])]
    except Exception as exc:
        logger.error("Canonical get_events_for_room failed: %s", exc)
        return []


def room_has_sensor_data(room_code: str) -> bool:
    return len(get_events_for_room(room_code)) > 0


def _get_sensor_silence_threshold() -> int:
    try:
        from app.api.space_settings import get_space_setting

        val = get_space_setting("sensor_silence_threshold_minutes")
        if val is not None:
            return int(val)
    except Exception:
        pass
    try:
        return settings.sensor_silence_threshold_minutes or 30
    except Exception:
        return 30


def room_sensor_is_alive(room_code: str, max_silence_minutes: int = 0) -> bool:
    if max_silence_minutes <= 0:
        max_silence_minutes = _get_sensor_silence_threshold()
    events = get_events_for_room(room_code)
    if not events:
        return True
    last = events[-1]
    last_seen = _make_naive(last.received_at) if last.received_at else _make_naive(last.timestamp)
    age_minutes = (datetime.utcnow() - last_seen).total_seconds() / 60
    return age_minutes <= max_silence_minutes


def get_last_event(room_code: str) -> OccupancyEvent | None:
    events = get_events_for_room(room_code)
    return events[-1] if events else None


def get_occupied_minutes(room_code: str, from_dt: datetime, to_dt: datetime) -> int:
    events = get_events_for_room(room_code, from_dt, to_dt)
    if not events:
        return 0
    total_seconds = 0.0
    segment_start: datetime | None = None
    for event in events:
        et = _effective_time(event)
        if event.occupied and segment_start is None:
            segment_start = et
        elif not event.occupied and segment_start is not None:
            total_seconds += (et - segment_start).total_seconds()
            segment_start = None
    if segment_start is not None:
        total_seconds += (to_dt - segment_start).total_seconds()
    return int(total_seconds / 60)


def get_current_vacancy_start(room_code: str) -> datetime | None:
    last = get_last_event(room_code)
    if last is None or last.occupied:
        return None
    return _effective_time(last)


def _ghost_to_dict(f: GhostBookingFinding) -> dict:
    return {
        "id": f.id,
        "site_id": f.site_id,
        "room_code": f.room_code,
        "room_name": f.room_name,
        "booking_id": f.booking_id,
        "organiser_email": f.organiser_email,
        "organiser_name": f.organiser_name,
        "source_booking_flagged": f.source_booking_flagged,
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
        source_booking_flagged=d.get("source_booking_flagged", False),
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
        try:
            _client().table("ghost_findings").upsert(_ghost_to_dict(finding), on_conflict="id").execute()
        except Exception as exc:
            logger.error("Canonical save_ghost_finding failed: %s", exc)
        return finding


def get_open_ghost_finding(booking_id: str) -> GhostBookingFinding | None:
    try:
        response = _client().table("ghost_findings").select("*").eq("booking_id", booking_id).limit(1).execute()
        rows = response.data or []
        return _dict_to_ghost(rows[0]) if rows else None
    except Exception as exc:
        logger.error("Canonical get_open_ghost_finding failed: %s", exc)
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
        try:
            response = _client().table("ghost_findings").select("*").eq("id", finding_id).limit(1).execute()
            rows = response.data or []
            if not rows:
                return None
            r = rows[0]
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
            _client().table("ghost_findings").update(r).eq("id", finding_id).execute()
            return _dict_to_ghost(r)
        except Exception as exc:
            logger.error("Canonical update_ghost_finding_status failed: %s", exc)
            return None


def get_ghost_finding_by_id(finding_id: str) -> GhostBookingFinding | None:
    try:
        response = _client().table("ghost_findings").select("*").eq("id", finding_id).limit(1).execute()
        rows = response.data or []
        return _dict_to_ghost(rows[0]) if rows else None
    except Exception as exc:
        logger.error("Canonical get_ghost_finding_by_id failed: %s", exc)
        return None


def get_open_or_pending_ghost_finding(booking_id: str) -> GhostBookingFinding | None:
    try:
        response = (
            _client()
            .table("ghost_findings")
            .select("*")
            .eq("booking_id", booking_id)
            .in_("status", ["open", "pending_inspection"])
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return _dict_to_ghost(rows[0]) if rows else None
    except Exception as exc:
        logger.error("Canonical get_open_or_pending_ghost_finding failed: %s", exc)
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
        try:
            response = _client().table("ghost_findings").select("*").eq("id", finding_id).limit(1).execute()
            rows = response.data or []
            if not rows:
                return None
            r = rows[0]
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
            _client().table("ghost_findings").update(r).eq("id", finding_id).execute()
            return _dict_to_ghost(r)
        except Exception as exc:
            logger.error("Canonical mark_ghost_finding_notified failed: %s", exc)
            return None


def mark_ghost_finding_reminder_sent(
    finding_id: str,
    *,
    whatsapp_message_id: str | None = None,
) -> GhostBookingFinding | None:
    with _lock:
        try:
            response = _client().table("ghost_findings").select("*").eq("id", finding_id).limit(1).execute()
            rows = response.data or []
            if not rows:
                return None
            r = rows[0]
            now_str = _dt_to_str(datetime.utcnow())
            r["reminder_sent"] = True
            r["reminder_sent_at"] = now_str
            if whatsapp_message_id:
                r["whatsapp_message_id"] = whatsapp_message_id
            _client().table("ghost_findings").update(r).eq("id", finding_id).execute()
            return _dict_to_ghost(r)
        except Exception as exc:
            logger.error("Canonical mark_ghost_finding_reminder_sent failed: %s", exc)
            return None


def find_pending_ghost_for_whatsapp(
    concierge_whatsapp: str,
    *,
    reply_to_message_id: str | None = None,
) -> GhostBookingFinding | None:
    target = _normalise_whatsapp_number(concierge_whatsapp)
    if not target or not reply_to_message_id:
        return None
    try:
        response = (
            _client()
            .table("ghost_findings")
            .select("*")
            .in_("status", ["open", "pending_inspection"])
            .eq("concierge_whatsapp", target)
            .execute()
        )
        rows = response.data or []
    except Exception as exc:
        logger.error("Canonical find_pending_ghost_for_whatsapp failed: %s", exc)
        rows = []
    for row in rows:
        if row.get("whatsapp_message_id") == reply_to_message_id:
            return _dict_to_ghost(row)
    return None


def get_pending_ghost_findings_for_whatsapp(concierge_whatsapp: str) -> list[GhostBookingFinding]:
    target = _normalise_whatsapp_number(concierge_whatsapp)
    if not target:
        return []
    try:
        response = (
            _client()
            .table("ghost_findings")
            .select("*")
            .in_("status", ["open", "pending_inspection"])
            .eq("concierge_whatsapp", target)
            .execute()
        )
        rows = response.data or []
    except Exception as exc:
        logger.error("Canonical get_pending_ghost_findings_for_whatsapp failed: %s", exc)
        rows = []
    return [
        _dict_to_ghost(r)
        for r in rows
        if r.get("status") in ("open", "pending_inspection")
        and _normalise_whatsapp_number(r.get("concierge_whatsapp")) == target
    ]


def get_ghost_findings(site_id: str, status: str | None = None) -> list[GhostBookingFinding]:
    try:
        query = _client().table("ghost_findings").select("*").eq("site_id", site_id)
        if status:
            query = query.eq("status", status)
        response = query.execute()
        return [_dict_to_ghost(r) for r in (response.data or [])]
    except Exception as exc:
        logger.error("Canonical get_ghost_findings failed: %s", exc)
        return []


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
        try:
            _client().table("space_rightsizing_findings").upsert(_rs_to_dict(finding), on_conflict="id").execute()
        except Exception as exc:
            logger.error("Canonical save_rightsizing_finding failed: %s", exc)
        return finding


def get_open_rightsizing_finding(booking_id: str) -> RightSizingFinding | None:
    try:
        response = (
            _client()
            .table("space_rightsizing_findings")
            .select("*")
            .eq("booking_id", booking_id)
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return _dict_to_rs(rows[0]) if rows else None
    except Exception as exc:
        logger.error("Canonical get_open_rightsizing_finding failed: %s", exc)
        return None


def update_rightsizing_finding_status(finding_id: str, status: str) -> RightSizingFinding | None:
    with _lock:
        try:
            response = _client().table("space_rightsizing_findings").select("*").eq("id", finding_id).limit(1).execute()
            rows = response.data or []
            if not rows:
                return None
            rows[0]["status"] = status
            _client().table("space_rightsizing_findings").update(rows[0]).eq("id", finding_id).execute()
            return _dict_to_rs(rows[0])
        except Exception as exc:
            logger.error("Canonical update_rightsizing_finding_status failed: %s", exc)
            return None


def get_rightsizing_findings(site_id: str, status: str | None = None) -> list[RightSizingFinding]:
    try:
        query = _client().table("space_rightsizing_findings").select("*").eq("site_id", site_id)
        if status:
            query = query.eq("status", status)
        response = query.execute()
        return [_dict_to_rs(r) for r in (response.data or [])]
    except Exception as exc:
        logger.error("Canonical get_rightsizing_findings failed: %s", exc)
        return []


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
    with _lock:
        try:
            _client().table("space_focus_room_sessions").upsert(
                _session_to_dict(session), on_conflict="session_id"
            ).execute()
        except Exception as exc:
            logger.error("Canonical save_session failed: %s", exc)
        return session


def get_active_session(room_code: str) -> FocusRoomSession | None:
    try:
        response = (
            _client()
            .table("space_focus_room_sessions")
            .select("*")
            .eq("room_code", room_code)
            .is_("end_time", "null")
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return _dict_to_session(rows[0]) if rows else None
    except Exception as exc:
        logger.error("Canonical get_active_session failed: %s", exc)
        return None


def close_session(
    session_id: str,
    end_time: datetime,
    extended_threshold: int = 7200,
) -> FocusRoomSession | None:
    with _lock:
        try:
            response = (
                _client().table("space_focus_room_sessions").select("*").eq("session_id", session_id).limit(1).execute()
            )
            rows = response.data or []
            if not rows:
                return None
            r = rows[0]
            start = _str_to_dt(r["start_time"])
            duration = int((end_time - start).total_seconds())
            r["end_time"] = _dt_to_str(end_time)
            r["duration_seconds"] = duration
            r["extended_use"] = duration > extended_threshold
            _client().table("space_focus_room_sessions").update(r).eq("session_id", session_id).execute()
            return _dict_to_session(r)
        except Exception as exc:
            logger.error("Canonical close_session failed: %s", exc)
            return None


def discard_session(session_id: str) -> bool:
    with _lock:
        try:
            response = _client().table("space_focus_room_sessions").delete().eq("session_id", session_id).execute()
            return bool(response.data is not None)
        except Exception as exc:
            logger.error("Canonical discard_session failed: %s", exc)
            return False


def get_sessions_for_room(
    room_code: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> list[FocusRoomSession]:
    try:
        query = _client().table("space_focus_room_sessions").select("*").eq("room_code", room_code)
        if from_dt:
            query = query.gte("start_time", _dt_to_str(from_dt))
        if to_dt:
            query = query.lte("start_time", _dt_to_str(to_dt))
        response = query.order("start_time").execute()
        return [_dict_to_session(r) for r in (response.data or [])]
    except Exception as exc:
        logger.error("Canonical get_sessions_for_room failed: %s", exc)
        return []


def get_sessions_for_site(
    site_id: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    extended_only: bool = False,
) -> list[FocusRoomSession]:
    try:
        query = _client().table("space_focus_room_sessions").select("*").eq("site_id", site_id)
        if from_dt:
            query = query.gte("start_time", _dt_to_str(from_dt))
        if to_dt:
            query = query.lte("start_time", _dt_to_str(to_dt))
        if extended_only:
            query = query.eq("extended_use", True)
        response = query.order("start_time").execute()
        return [_dict_to_session(r) for r in (response.data or [])]
    except Exception as exc:
        logger.error("Canonical get_sessions_for_site failed: %s", exc)
        return []
