"""FastAPI router for sensor event ingestion and room-state queries.

Endpoints:
    POST /api/space/events         — ingest a sensor event
    GET  /api/space/rooms          — all room states
    GET  /api/space/rooms/{code}   — single room + recent events
    GET  /api/space/devices        — registered devices
    GET  /api/space/findings       — active findings
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.space.models import (
    RoomStateResponse,
    SensorDeviceInfo,
    SensorEventPayload,
    SensorEventResponse,
)
from app.space import space_repository as repo
from app.space.room_state_engine import evaluate_room_state

logger = logging.getLogger("sentinel.space.ingest")

router = APIRouter(prefix="/api/space", tags=["space-occupancy"])


# ---------------------------------------------------------------------------
# POST /api/space/events
# ---------------------------------------------------------------------------


@router.post("/events", response_model=SensorEventResponse)
async def ingest_sensor_event(
    payload: SensorEventPayload,
    authorization: Optional[str] = Header(None),
):
    """Ingest a sensor state-change or heartbeat event."""

    # --- Auth: extract bearer token ---
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    device = await repo.get_device_by_token(token)
    if device is None:
        raise HTTPException(status_code=401, detail="Invalid device token")

    # --- Device checks ---
    if not device.get("enabled", True):
        raise HTTPException(status_code=403, detail="Device is disabled")

    if device.get("room_code") != payload.room_code:
        raise HTTPException(
            status_code=403,
            detail=f"Room code mismatch: token registered to {device.get('room_code')}",
        )

    now = datetime.now(timezone.utc)
    site_id = device.get("site_id", "FLN02")

    # --- Persist raw event ---
    event_dict = {
        "id": str(uuid.uuid4()),
        "room_code": payload.room_code,
        "sensor_id": payload.sensor_id,
        "occupied": payload.occupied,
        "event_type": payload.event_type,
        "rssi": payload.rssi,
        "uptime_seconds": payload.uptime_seconds,
        "firmware_version": payload.firmware_version,
        "timestamp": payload.timestamp.isoformat(),
        "received_at": now.isoformat(),
        "site_id": site_id,
    }
    await repo.insert_room_event(event_dict)

    # --- Update device last-seen ---
    await repo.update_device_last_seen(
        sensor_id=payload.sensor_id,
        rssi=payload.rssi,
        uptime=payload.uptime_seconds,
        firmware=payload.firmware_version,
    )

    # --- Fetch + update current state ---
    current_state = await repo.get_room_current_state(payload.room_code)

    new_state: dict = {
        "room_code": payload.room_code,
        "site_id": site_id,
        "occupied": payload.occupied,
        "last_event_type": payload.event_type,
        "sensor_online": True,
        "updated_at": now.isoformat(),
    }

    if payload.event_type == "state_change":
        new_state["last_state_change_at"] = now.isoformat()
        if payload.occupied:
            new_state["occupied_since"] = now.isoformat()
            new_state["empty_since"] = None
        else:
            new_state["empty_since"] = now.isoformat()
            new_state["occupied_since"] = None
        # Carry over heartbeat timestamp from previous state
        if current_state:
            new_state.setdefault("last_heartbeat_at", current_state.get("last_heartbeat_at"))
    elif payload.event_type == "heartbeat":
        new_state["last_heartbeat_at"] = now.isoformat()
        # Carry over state-change fields from previous state
        if current_state:
            new_state.setdefault("last_state_change_at", current_state.get("last_state_change_at"))
            new_state.setdefault("occupied_since", current_state.get("occupied_since"))
            new_state.setdefault("empty_since", current_state.get("empty_since"))

    await repo.upsert_room_current_state(new_state)

    # --- Run rules engine ---
    findings = await evaluate_room_state(
        room_code=payload.room_code,
        current_state=current_state,
        new_event=payload,
        booking_data=None,  # No booking integration yet
    )

    alarm_id: Optional[str] = None
    for finding in findings:
        finding_dict = finding.model_dump()
        finding_dict["id"] = str(uuid.uuid4())
        finding_dict["detected_at"] = finding.detected_at.isoformat()
        if finding.occupied_at:
            finding_dict["occupied_at"] = finding.occupied_at.isoformat()
        await repo.insert_finding(finding_dict)

        # If this is a sensor_recovery, also resolve the offline finding
        if finding.finding_type == "sensor_recovery":
            await repo.resolve_finding(payload.room_code, "sensor_offline")

        if alarm_id is None and finding.finding_type not in ("sensor_recovery",):
            alarm_id = finding_dict["id"]

    return SensorEventResponse(
        received=True,
        alarm_id=alarm_id,
        server_time=now,
    )


# ---------------------------------------------------------------------------
# GET /api/space/rooms
# ---------------------------------------------------------------------------


@router.get("/rooms", response_model=list[RoomStateResponse])
async def get_all_rooms(site_id: str = Query("FLN02")):
    """Return current state for all rooms at a site."""
    states = await repo.get_all_room_states(site_id=site_id)
    return [
        RoomStateResponse(
            room_code=s["room_code"],
            site_id=s.get("site_id", site_id),
            occupied=s.get("occupied", False),
            last_state_change_at=s.get("last_state_change_at"),
            last_heartbeat_at=s.get("last_heartbeat_at"),
            occupied_since=s.get("occupied_since"),
            empty_since=s.get("empty_since"),
            sensor_online=s.get("sensor_online", False),
        )
        for s in states
    ]


# ---------------------------------------------------------------------------
# GET /api/space/rooms/{room_code}
# ---------------------------------------------------------------------------


@router.get("/rooms/{room_code}", response_model=RoomStateResponse)
async def get_room_detail(room_code: str):
    """Return the current state for a single room."""
    state = await repo.get_room_current_state(room_code)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Room {room_code} not found")
    return RoomStateResponse(
        room_code=state["room_code"],
        site_id=state.get("site_id", "FLN02"),
        occupied=state.get("occupied", False),
        last_state_change_at=state.get("last_state_change_at"),
        last_heartbeat_at=state.get("last_heartbeat_at"),
        occupied_since=state.get("occupied_since"),
        empty_since=state.get("empty_since"),
        sensor_online=state.get("sensor_online", False),
    )


# ---------------------------------------------------------------------------
# GET /api/space/devices
# ---------------------------------------------------------------------------


@router.get("/devices", response_model=list[SensorDeviceInfo])
async def get_devices(site_id: str = Query("FLN02")):
    """Return all registered sensor devices (tokens masked)."""
    devices = await repo.get_all_devices(site_id=site_id)
    result = []
    for d in devices:
        token_raw = d.get("device_token", "")
        masked = token_raw[:6] + "***" if len(token_raw) > 6 else "***"
        result.append(
            SensorDeviceInfo(
                device_token=masked,
                room_code=d.get("room_code", ""),
                sensor_id=d.get("sensor_id", ""),
                firmware_version=d.get("firmware_version"),
                site_id=d.get("site_id", site_id),
                enabled=d.get("enabled", True),
                last_seen_at=d.get("last_seen_at"),
                last_rssi=d.get("last_rssi"),
                sensor_online=d.get("sensor_online", False),
            )
        )
    return result


# ---------------------------------------------------------------------------
# GET /api/space/findings
# ---------------------------------------------------------------------------


@router.get("/findings")
async def get_findings(room_code: Optional[str] = Query(None)):
    """Return active (unresolved) findings, optionally filtered by room."""
    findings = await repo.get_active_findings(room_code=room_code)
    return findings
