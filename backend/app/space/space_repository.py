"""Repository for space-occupancy CRUD operations backed by the canonical DB store."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("sentinel.space.repository")


def _get_client():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


async def get_device_by_token(token: str) -> Optional[dict]:
    """Look up a sensor device by its bearer token."""
    try:
        client = _get_client()
        resp = client.table("space_sensor_devices").select("*").eq("device_token", token).execute()
        if resp.data:
            return resp.data[0]
    except Exception as exc:
        logger.error("Canonical get_device_by_token failed: %s", exc)
    return None


async def get_all_devices(site_id: str = "FLN02") -> list[dict]:
    """Return all registered sensor devices for a site."""
    try:
        client = _get_client()
        resp = client.table("space_sensor_devices").select("*").eq("site_id", site_id).execute()
        return resp.data or []
    except Exception as exc:
        logger.error("Canonical get_all_devices failed: %s", exc)
        return []


async def update_device_last_seen(
    sensor_id: str,
    rssi: Optional[int] = None,
    uptime: Optional[int] = None,
    firmware: Optional[str] = None,
) -> None:
    """Update last-seen metadata on a sensor device."""
    now = datetime.now(timezone.utc).isoformat()
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
    except Exception as exc:
        logger.error("Canonical update_device_last_seen failed: %s", exc)


async def insert_room_event(event: dict) -> None:
    """Persist a raw sensor event."""
    try:
        client = _get_client()
        client.table("space_room_events").insert(event).execute()
    except Exception as exc:
        logger.error("Canonical insert_room_event failed: %s", exc)


async def upsert_room_current_state(state: dict) -> None:
    """Create or update the materialised room state."""
    try:
        client = _get_client()
        client.table("space_room_current_state").upsert(state, on_conflict="room_code").execute()
    except Exception as exc:
        logger.error("Canonical upsert_room_current_state failed: %s", exc)


async def get_room_current_state(room_code: str) -> Optional[dict]:
    """Fetch the current state for a single room."""
    try:
        client = _get_client()
        resp = client.table("space_room_current_state").select("*").eq("room_code", room_code).execute()
        if resp.data:
            return resp.data[0]
    except Exception as exc:
        logger.error("Canonical get_room_current_state failed: %s", exc)
    return None


async def get_all_room_states(site_id: str = "FLN02") -> list[dict]:
    """Return all current room states for a site."""
    try:
        client = _get_client()
        resp = client.table("space_room_current_state").select("*").eq("site_id", site_id).execute()
        return resp.data or []
    except Exception as exc:
        logger.error("Canonical get_all_room_states failed: %s", exc)
        return []


async def insert_finding(finding: dict) -> None:
    """Persist a rules-engine finding."""
    try:
        client = _get_client()
        client.table("space_room_state_findings").insert(finding).execute()
    except Exception as exc:
        logger.error("Canonical insert_finding failed: %s", exc)


async def resolve_finding(room_code: str, finding_type: str) -> None:
    """Mark all active findings of a given type as resolved for a room."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        client = _get_client()
        client.table("space_room_state_findings").update({"resolved": True, "resolved_at": now}).eq(
            "room_code", room_code
        ).eq("finding_type", finding_type).eq("resolved", False).execute()
    except Exception as exc:
        logger.error("Canonical resolve_finding failed: %s", exc)


async def get_active_findings(room_code: Optional[str] = None) -> list[dict]:
    """Return unresolved findings, optionally filtered by room."""
    try:
        client = _get_client()
        query = client.table("space_room_state_findings").select("*").eq("resolved", False)
        if room_code:
            query = query.eq("room_code", room_code)
        resp = query.execute()
        return resp.data or []
    except Exception as exc:
        logger.error("Canonical get_active_findings failed: %s", exc)
        return []
