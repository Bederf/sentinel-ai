"""SIMBIOT Gateway schemas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SIMBIOTPoint:
    """A single data point exposed by a SIMBIOT gateway.

    Maps to an MQTT topic: sentinel/{site_id}/{sentinel_field}
    """

    point_id: str
    display_name: str
    unit: str  # "W" | "°C" | "%" | "V" | "binary"
    category: str  # "energy" | "hvac" | "safety" | "occupancy"
    sentinel_field: str  # MQTT topic suffix
    gateway_type: str  # "bacnet" | "modbus" | "home_assistant"
    writable: bool
    site_id: str
    last_value: float | None = None
    last_updated: datetime | None = None


@dataclass
class GatewayStatus:
    """Current health and connectivity status of a SIMBIOT gateway."""

    site_id: str
    gateway_type: str
    connected: bool
    last_heartbeat: datetime | None
    point_count: int
    error: str | None = None
