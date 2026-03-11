"""Fuel tank monitoring data models (Phase 148).

Pydantic-free dataclasses for MQTT telemetry ingestion, event tracking,
and per-tank configuration. Follows the same pattern as space_mqtt_listener
for payload parsing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class FuelTelemetry:
    """Single fuel-level reading from an ESP32 node or Modbus-MQTT bridge."""

    node_id: str
    site_id: str
    tank_id: str
    generator_id: str = ""
    fuel_level_pct: float = 0.0
    fuel_level_litres: float = 0.0
    fuel_level_mm: float = 0.0
    fuel_temp_c: float = 0.0
    consumption_rate_lph: Optional[float] = None
    consumption_anomaly: bool = False
    runtime_remaining_hrs: Optional[float] = None
    days_to_empty: Optional[float] = None
    generator_running: bool = False
    leak_detected: bool = False
    overfill_alert: bool = False
    theft_suspected: bool = False
    sensor_fault: bool = False
    sensor_ma: float = 0.0
    rssi: int = 0
    uptime_s: int = 0
    ts: int = 0
    received_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class FuelEvent:
    """Discrete event from a fuel node (refill, theft_alert, leak, etc.)."""

    node_id: str
    site_id: str
    tank_id: str
    event_type: str
    payload: dict = field(default_factory=dict)
    ts: int = 0
    received_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class FuelTankConfig:
    """Per-tank static configuration (capacity, thresholds, generator link)."""

    tank_id: str
    site_id: str
    generator_id: str = ""
    capacity_litres: int = 0
    tank_height_mm: int = 0
    low_alert_pct_1: float = 30.0
    low_alert_pct_2: float = 15.0
    theft_rate_threshold_lpm: float = 2.0
    consumption_spec_lph: float = 45.0


def parse_fuel_telemetry(topic: str, payload: bytes | str | dict[str, Any]) -> Optional[FuelTelemetry]:
    """Parse an MQTT fuel telemetry message into a FuelTelemetry dataclass.

    Returns None on invalid or incomplete payload (logs warning).
    """
    try:
        if isinstance(payload, bytes):
            raw: dict[str, Any] = json.loads(payload.decode("utf-8"))
        elif isinstance(payload, str):
            raw = json.loads(payload)
        else:
            raw = payload

        # Extract node_id from topic fallback
        topic_parts = topic.split("/")
        topic_node_id = topic_parts[2] if len(topic_parts) >= 3 else ""

        node_id = raw.get("node_id") or topic_node_id
        site_id = raw.get("site_id", "")
        tank_id = raw.get("tank_id", "")
        fuel_level_pct = raw.get("fuel_level_pct")

        # Required fields
        if not node_id or not site_id or not tank_id or fuel_level_pct is None:
            logger.warning(
                "Fuel telemetry missing required fields (node_id=%s, site_id=%s, tank_id=%s, fuel_level_pct=%s)",
                node_id,
                site_id,
                tank_id,
                fuel_level_pct,
            )
            return None

        return FuelTelemetry(
            node_id=node_id,
            site_id=site_id,
            tank_id=tank_id,
            generator_id=raw.get("generator_id", ""),
            fuel_level_pct=float(fuel_level_pct),
            fuel_level_litres=float(raw.get("fuel_level_litres", 0)),
            fuel_level_mm=float(raw.get("fuel_level_mm", 0)),
            fuel_temp_c=float(raw.get("fuel_temp_c", 0)),
            consumption_rate_lph=raw.get("consumption_rate_lph"),
            consumption_anomaly=bool(raw.get("consumption_anomaly", False)),
            runtime_remaining_hrs=raw.get("runtime_remaining_hrs"),
            days_to_empty=raw.get("days_to_empty"),
            generator_running=bool(raw.get("generator_running", False)),
            leak_detected=bool(raw.get("leak_detected", False)),
            overfill_alert=bool(raw.get("overfill_alert", False)),
            theft_suspected=bool(raw.get("theft_suspected", False)),
            sensor_fault=bool(raw.get("sensor_fault", False)),
            sensor_ma=float(raw.get("sensor_ma", 0)),
            rssi=int(raw.get("rssi", 0)),
            uptime_s=int(raw.get("uptime_s", 0)),
            ts=int(raw.get("ts", 0)),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Failed to parse fuel telemetry: %s", exc)
        return None


def validate_sensor_reading(telemetry: FuelTelemetry) -> FuelTelemetry:
    """Flag sensor_fault if mA reading is outside the 4-20 mA valid range.

    The 3.5 mA lower bound (instead of 4.0) allows for minor calibration
    drift without false-faulting. Readings above 21.0 mA indicate a wiring
    fault or sensor failure.
    """
    if telemetry.sensor_ma < 3.5 or telemetry.sensor_ma > 21.0:
        telemetry.sensor_fault = True
    return telemetry
