"""Repository for space-occupancy POC CRUD operations.

Implements the standard 3-tier fallback: Supabase -> JSON fallback.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config.settings import settings

logger = logging.getLogger("sentinel.space.repository")

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "space"


def _load_json(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if path.exists():
        return json.loads(path.read_text())
    return []


def _save_json(filename: str, data: list[dict]) -> None:
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def _use_supabase() -> bool:
    """Return True when Supabase is available and we are NOT in demo mode."""
    try:
        if settings.demo_mode:
            return False
        return bool(settings.supabase_url and settings.supabase_service_role_key)
    except Exception:
        return False


def _get_client():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


# ---------------------------------------------------------------------------
# Device helpers
# ---------------------------------------------------------------------------


async def get_device_by_token(token: str) -> Optional[dict]:
    """Look up a sensor device by its bearer token."""
    if _use_supabase():
        try:
            client = _get_client()
            resp = client.table("space_sensor_devices").select("*").eq("device_token", token).execute()
            if resp.data:
                return resp.data[0]
        except Exception as exc:
            logger.warning("Supabase lookup failed, falling back to JSON: %s", exc)
    # JSON fallback
    for device in _load_json("sensor_devices.json"):
        if device.get("device_token") == token:
            return device
    return None


async def get_all_devices(site_id: str = "FLN02") -> list[dict]:
    """Return all registered sensor devices for a site."""
    if _use_supabase():
        try:
            client = _get_client()
            resp = client.table("space_sensor_devices").select("*").eq("site_id", site_id).execute()
            return resp.data or []
        except Exception as exc:
            logger.warning("Supabase get_all_devices failed: %s", exc)
    return [d for d in _load_json("sensor_devices.json") if d.get("site_id") == site_id]


async def update_device_last_seen(
    sensor_id: str,
    rssi: Optional[int] = None,
    uptime: Optional[int] = None,
    firmware: Optional[str] = None,
) -> None:
    """Update last-seen metadata on a sensor device."""
    now = datetime.now(timezone.utc).isoformat()
    if _use_supabase():
        try:
            client = _get_client()
            payload: dict[str, Any] = {"last_seen_at": now}
            if rssi is not None:
                payload["last_rssi"] = rssi
            if uptime is not None:
                payload["uptime_seconds"] = uptime
            if firmware:
                payload["firmware_version"] = firmware
            client.table("space_sensor_devices").update(payload).eq("sensor_id", sensor_id).execute()
            return
        except Exception as exc:
            logger.warning("Supabase update_device_last_seen failed: %s", exc)
    # JSON fallback
    devices = _load_json("sensor_devices.json")
    for d in devices:
        if d.get("sensor_id") == sensor_id:
            d["last_seen_at"] = now
            if rssi is not None:
                d["last_rssi"] = rssi
            if uptime is not None:
                d["uptime_seconds"] = uptime
            if firmware:
                d["firmware_version"] = firmware
    _save_json("sensor_devices.json", devices)


# ---------------------------------------------------------------------------
# Room events
# ---------------------------------------------------------------------------


async def insert_room_event(event: dict) -> None:
    """Persist a raw sensor event."""
    if _use_supabase():
        try:
            client = _get_client()
            client.table("space_room_events").insert(event).execute()
            return
        except Exception as exc:
            logger.warning("Supabase insert_room_event failed: %s", exc)
    events = _load_json("room_events.json")
    events.append(event)
    _save_json("room_events.json", events)


# ---------------------------------------------------------------------------
# Room current state
# ---------------------------------------------------------------------------


async def upsert_room_current_state(state: dict) -> None:
    """Create or update the materialised room state."""
    if _use_supabase():
        try:
            client = _get_client()
            client.table("space_room_current_state").upsert(state, on_conflict="room_code").execute()
            return
        except Exception as exc:
            logger.warning("Supabase upsert_room_current_state failed: %s", exc)
    states = _load_json("room_current_state.json")
    updated = False
    for i, s in enumerate(states):
        if s.get("room_code") == state.get("room_code"):
            states[i] = state
            updated = True
            break
    if not updated:
        states.append(state)
    _save_json("room_current_state.json", states)


async def get_room_current_state(room_code: str) -> Optional[dict]:
    """Fetch the current state for a single room."""
    if _use_supabase():
        try:
            client = _get_client()
            resp = client.table("space_room_current_state").select("*").eq("room_code", room_code).execute()
            if resp.data:
                return resp.data[0]
        except Exception as exc:
            logger.warning("Supabase get_room_current_state failed: %s", exc)
    for s in _load_json("room_current_state.json"):
        if s.get("room_code") == room_code:
            return s
    return None


async def get_all_room_states(site_id: str = "FLN02") -> list[dict]:
    """Return all current room states for a site."""
    if _use_supabase():
        try:
            client = _get_client()
            resp = client.table("space_room_current_state").select("*").eq("site_id", site_id).execute()
            return resp.data or []
        except Exception as exc:
            logger.warning("Supabase get_all_room_states failed: %s", exc)
    return [s for s in _load_json("room_current_state.json") if s.get("site_id") == site_id]


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


async def insert_finding(finding: dict) -> None:
    """Persist a rules-engine finding."""
    if _use_supabase():
        try:
            client = _get_client()
            client.table("space_room_state_findings").insert(finding).execute()
            return
        except Exception as exc:
            logger.warning("Supabase insert_finding failed: %s", exc)
    findings = _load_json("room_state_findings.json")
    findings.append(finding)
    _save_json("room_state_findings.json", findings)


async def resolve_finding(room_code: str, finding_type: str) -> None:
    """Mark all active findings of a given type as resolved for a room."""
    now = datetime.now(timezone.utc).isoformat()
    if _use_supabase():
        try:
            client = _get_client()
            client.table("space_room_state_findings").update({"resolved": True, "resolved_at": now}).eq(
                "room_code", room_code
            ).eq("finding_type", finding_type).eq("resolved", False).execute()
            return
        except Exception as exc:
            logger.warning("Supabase resolve_finding failed: %s", exc)
    findings = _load_json("room_state_findings.json")
    for f in findings:
        if f.get("room_code") == room_code and f.get("finding_type") == finding_type and not f.get("resolved"):
            f["resolved"] = True
            f["resolved_at"] = now
    _save_json("room_state_findings.json", findings)


async def get_active_findings(room_code: Optional[str] = None) -> list[dict]:
    """Return unresolved findings, optionally filtered by room."""
    if _use_supabase():
        try:
            client = _get_client()
            query = client.table("space_room_state_findings").select("*").eq("resolved", False)
            if room_code:
                query = query.eq("room_code", room_code)
            resp = query.execute()
            return resp.data or []
        except Exception as exc:
            logger.warning("Supabase get_active_findings failed: %s", exc)
    findings = _load_json("room_state_findings.json")
    return [f for f in findings if not f.get("resolved") and (room_code is None or f.get("room_code") == room_code)]
