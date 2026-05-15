"""MQTT ingest for ESP32 room-presence nodes."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config.settings import settings
from app.services.space_event_service import process_occupancy_event

logger = logging.getLogger(__name__)


@dataclass
class MqttPresenceEvent:
    site_id: str
    room_code: str
    sensor_id: str
    occupied: bool
    source: str = "mqtt_mmwave_ld2410c"
    room_type: str = "meeting"
    timestamp: datetime | None = None
    # Radar telemetry (from LD2410C extended payload)
    moving: bool | None = None
    stationary: bool | None = None
    distance_m: float | None = None
    moving_gate: int | None = None
    static_gate: int | None = None
    # Door state (magnetic reed switch on GPIO — ground truth for "did they leave?")
    door_closed: bool | None = None


def _load_node_room_mapping() -> dict[str, dict[str, Any]]:
    """Load server-side node_id → room_code overrides from Supabase (primary) or JSON (fallback)."""
    # 1. Try Supabase
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        response = client.table("node_room_mappings").select("*").eq("active", True).execute()
        if response.data:
            return {row["node_id"]: row for row in response.data}
    except Exception:
        pass

    # 2. Fallback: JSON file
    from pathlib import Path

    path = Path(__file__).parent.parent / "data" / "space" / "node_room_mapping.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        return {}


# Cached at module level; restart to pick up changes
_node_room_mapping: dict[str, dict[str, Any]] | None = None


def get_node_room_mapping() -> dict[str, dict[str, Any]]:
    global _node_room_mapping
    if _node_room_mapping is None:
        _node_room_mapping = _load_node_room_mapping()
    return _node_room_mapping


def parse_mqtt_presence_message(topic: str, payload: bytes | str | dict[str, Any]) -> MqttPresenceEvent:
    """Parse a MQTT presence message from the ESP32 node topic/payload."""
    if isinstance(payload, bytes):
        raw_data: Any = json.loads(payload.decode("utf-8"))
    elif isinstance(payload, str):
        raw_data = json.loads(payload)
    else:
        raw_data = payload

    topic_parts = topic.split("/")
    node_id = topic_parts[2] if len(topic_parts) >= 3 else raw_data.get("node_id", "")

    # Server-side override: node_room_mapping.json takes precedence over firmware zone
    mapping = get_node_room_mapping()
    node_override = mapping.get(node_id, {})
    room_code = (
        node_override.get("room_code")
        or raw_data.get("room_code")
        or raw_data.get("zone")
        or raw_data.get("room")
        or node_id
    )
    site_id_override = node_override.get("site_id")

    occupied = bool(raw_data.get("presence", raw_data.get("occupied", False)))
    timestamp_raw = raw_data.get("ts") or raw_data.get("timestamp")
    parsed_timestamp: datetime | None = None
    if isinstance(timestamp_raw, (int, float)):
        # Guard against firmware sending uptime_seconds as ts instead of epoch.
        # Any ts before 2020-01-01 (epoch 1577836800) is clearly uptime, not a real timestamp.
        if timestamp_raw > 1577836800:
            parsed_timestamp = datetime.utcfromtimestamp(timestamp_raw)
        else:
            # Uptime value — use server receive time instead
            parsed_timestamp = datetime.utcnow()
    elif isinstance(timestamp_raw, str):
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            parsed_timestamp = None

    # Extract radar telemetry fields (optional — LD2410C extended payload)
    moving = raw_data.get("moving")
    stationary = raw_data.get("stationary")
    distance_m = raw_data.get("distance_m") or raw_data.get("distance")
    moving_gate = raw_data.get("moving_gate")
    static_gate = raw_data.get("static_gate")

    # Extract door state (magnetic reed switch on GPIO — ground truth for "did they leave?")
    # Firmware sends reed_closed: True = door closed (magnet contact closed), False = door open
    # None = no door sensor installed or field not present
    door_closed_raw = raw_data.get("reed_closed")
    door_closed: bool | None = None if door_closed_raw is None else bool(door_closed_raw)

    # Derive presence from radar fields if not explicitly set
    # LD2410C: presence = moving OR stationary
    if "presence" not in raw_data and "occupied" not in raw_data and (moving is not None or stationary is not None):
        occupied = bool(moving) or bool(stationary)

    from app.core.site_resolver import get_primary_site_code

    resolved_site_id = (
        site_id_override or raw_data.get("site_id") or settings.space_default_site_id or get_primary_site_code()
    )
    if not resolved_site_id:
        raise ValueError("No site_id provided in MQTT payload and no registered primary site is available")

    return MqttPresenceEvent(
        site_id=resolved_site_id,
        room_code=room_code,
        sensor_id=raw_data.get("sensor_id") or node_id or room_code,
        occupied=occupied,
        room_type=node_override.get("room_type") or raw_data.get("room_type", "meeting"),
        timestamp=parsed_timestamp,
        moving=bool(moving) if moving is not None else None,
        stationary=bool(stationary) if stationary is not None else None,
        distance_m=float(distance_m) if distance_m is not None else None,
        moving_gate=int(moving_gate) if moving_gate is not None else None,
        static_gate=int(static_gate) if static_gate is not None else None,
        door_closed=door_closed,
    )


def _distance_in_valid_range(event: MqttPresenceEvent) -> bool:
    """Server-side distance filtering per LD2410C radar config.

    Valid range: 0.2 m – configured max (default 3.0 m).
    Readings outside this range are hallway bleed or noise — ignore them.
    Only filters when the payload includes distance data AND event claims occupied.
    """
    if event.distance_m is None or not event.occupied:
        return True  # No distance data → trust the occupied flag as-is

    min_m = settings.radar_distance_min_m
    max_m = settings.radar_distance_max_m
    if event.distance_m < min_m or event.distance_m > max_m:
        logger.debug(
            "Distance filter: %.2f m outside [%.1f, %.1f] for %s — treating as empty",
            event.distance_m,
            min_m,
            max_m,
            event.room_code,
        )
        return False
    return True


async def process_mqtt_presence_message(topic: str, payload: bytes | str | dict[str, Any]) -> dict[str, Any]:
    event = parse_mqtt_presence_message(topic, payload)

    # Server-side distance filtering: reject occupied readings outside valid range
    if settings.radar_distance_filter_enabled and not _distance_in_valid_range(event):
        event.occupied = False  # Treat as no presence

    return await process_occupancy_event(
        site_id=event.site_id,
        room_code=event.room_code,
        sensor_id=event.sensor_id,
        occupied=event.occupied,
        source=event.source,
        room_type=event.room_type,
        timestamp=event.timestamp,
        moving=event.moving,
        stationary=event.stationary,
        distance_m=event.distance_m,
        moving_gate=event.moving_gate,
        static_gate=event.static_gate,
        door_closed=event.door_closed,
    )


class SpaceMqttListener:
    """Optional MQTT subscriber for ESP32 room-presence topics."""

    def __init__(self) -> None:
        self._client = None
        self._enabled = bool(settings.space_mqtt_enabled and settings.space_mqtt_broker)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if not self._enabled:
            return
        async with self._lock:
            if self._client is not None:
                return
            self._loop = asyncio.get_running_loop()
            try:
                import paho.mqtt.client as mqtt
            except ImportError:
                logger.warning("MQTT listener not started: paho-mqtt not installed")
                return

            client = mqtt.Client(client_id=settings.space_mqtt_client_id or "sentinel-space-backend")
            if settings.space_mqtt_username:
                client.username_pw_set(settings.space_mqtt_username, settings.space_mqtt_password)

            def _on_connect(client, _userdata, _flags, reason_code, _properties=None):
                # reason_code is an int (MQTTConnellError) in paho-mqtt 1.x and 2.x
                logger.warning("Space MQTT _on_connect fired: rc=%s", reason_code)
                if reason_code == 0:
                    radar_topic = settings.space_mqtt_radar_topic
                    if radar_topic:
                        client.subscribe(radar_topic)
                        logger.info(
                            "Space MQTT listener connected — subscribed to %s",
                            radar_topic,
                        )
                    else:
                        client.subscribe(settings.space_mqtt_topic)
                        logger.info(
                            "Space MQTT listener connected — subscribed to %s (legacy)",
                            settings.space_mqtt_topic,
                        )
                else:
                    logger.warning("Space MQTT listener connect failed: reason_code=%s (%s)", reason_code, type(reason_code))

            def _on_message(_client, _userdata, message):
                logger.warning("Space MQTT _on_message fired: topic=%s", message.topic)
                try:
                    if self._loop and self._loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(
                            process_mqtt_presence_message(message.topic, message.payload),
                            self._loop,
                        )
                        future.add_done_callback(
                            lambda completed: (
                                logger.warning("Space MQTT message rejected: %s", completed.exception())
                                if completed.exception()
                                else None
                            )
                        )
                    else:
                        logger.warning("Space MQTT message dropped: listener loop unavailable")
                except Exception as exc:
                    logger.warning("Space MQTT message dropped: %s", exc)

            client.on_connect = _on_connect
            client.on_message = _on_message
            client.connect_async(settings.space_mqtt_broker, settings.space_mqtt_port, keepalive=30)
            client.loop_start()
            logger.info("Space MQTT client started — connecting to %s:%d", settings.space_mqtt_broker, settings.space_mqtt_port)
            self._client = client

    async def stop(self) -> None:
        if self._client is None:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._client = None


_space_mqtt_listener: SpaceMqttListener | None = None


def get_space_mqtt_listener() -> SpaceMqttListener:
    global _space_mqtt_listener
    if _space_mqtt_listener is None:
        _space_mqtt_listener = SpaceMqttListener()
    return _space_mqtt_listener
