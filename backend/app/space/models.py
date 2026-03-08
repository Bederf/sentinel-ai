"""Pydantic models for the Space Occupancy POC sensor pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class SensorEventPayload(BaseModel):
    """Payload sent by an occupancy sensor (LD2410C mmWave)."""

    device_token: str
    room_code: str
    sensor_id: str
    occupied: bool
    event_type: Literal["state_change", "heartbeat"]
    rssi: Optional[int] = None
    uptime_seconds: Optional[int] = None
    firmware_version: Optional[str] = None
    timestamp: datetime


class SensorEventResponse(BaseModel):
    """Response returned after ingesting a sensor event."""

    received: bool
    alarm_id: Optional[str] = None
    server_time: datetime


class RoomCurrentState(BaseModel):
    """Materialised current state of a single room."""

    room_code: str
    site_id: str
    occupied: bool
    last_event_type: Optional[str] = None
    last_state_change_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    occupied_since: Optional[datetime] = None
    empty_since: Optional[datetime] = None
    sensor_online: bool
    updated_at: datetime


class RoomStateFinding(BaseModel):
    """An anomaly or operational finding detected by the rules engine."""

    room_code: str
    site_id: str
    finding_type: str
    detail: Optional[str] = None
    occupied_at: Optional[datetime] = None
    detected_at: datetime
    resolved: bool = False


class SensorDeviceInfo(BaseModel):
    """Registered sensor device record."""

    device_token: str  # masked in responses
    room_code: str
    sensor_id: str
    firmware_version: Optional[str] = None
    site_id: str
    enabled: bool
    last_seen_at: Optional[datetime] = None
    last_rssi: Optional[int] = None
    sensor_online: bool = False


class RoomStateResponse(BaseModel):
    """Public room-state response (no internal fields)."""

    room_code: str
    site_id: str
    occupied: bool
    last_state_change_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    occupied_since: Optional[datetime] = None
    empty_since: Optional[datetime] = None
    sensor_online: bool
