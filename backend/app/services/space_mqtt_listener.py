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
    room_code = raw_data.get("room_code") or raw_data.get("zone") or raw_data.get("room") or node_id
    occupied = bool(raw_data.get("presence", raw_data.get("occupied", False)))
    timestamp_raw = raw_data.get("ts") or raw_data.get("timestamp")
    parsed_timestamp: datetime | None = None
    if isinstance(timestamp_raw, (int, float)):
        parsed_timestamp = datetime.utcfromtimestamp(timestamp_raw)
    elif isinstance(timestamp_raw, str):
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            parsed_timestamp = None

    return MqttPresenceEvent(
        site_id=raw_data.get("site_id") or settings.space_default_site_id,
        room_code=room_code,
        sensor_id=raw_data.get("sensor_id") or node_id or room_code,
        occupied=occupied,
        room_type=raw_data.get("room_type", "meeting"),
        timestamp=parsed_timestamp,
    )


async def process_mqtt_presence_message(topic: str, payload: bytes | str | dict[str, Any]) -> dict[str, Any]:
    event = parse_mqtt_presence_message(topic, payload)
    return await process_occupancy_event(
        site_id=event.site_id,
        room_code=event.room_code,
        sensor_id=event.sensor_id,
        occupied=event.occupied,
        source=event.source,
        room_type=event.room_type,
        timestamp=event.timestamp,
    )


class SpaceMqttListener:
    """Optional MQTT subscriber for ESP32 room-presence topics."""

    def __init__(self) -> None:
        self._client = None
        self._enabled = bool(settings.space_mqtt_enabled and settings.space_mqtt_broker)
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        if not self._enabled:
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
            if reason_code == 0:
                client.subscribe(settings.space_mqtt_topic)
                logger.info("Space MQTT listener subscribed to %s", settings.space_mqtt_topic)
            else:
                logger.warning("Space MQTT listener connect failed: %s", reason_code)

        def _on_message(_client, _userdata, message):
            try:
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        process_mqtt_presence_message(message.topic, message.payload),
                        self._loop,
                    )
                else:
                    logger.warning("Space MQTT message dropped: listener loop unavailable")
            except Exception:
                logger.warning("Space MQTT message dropped: no running loop")

        client.on_connect = _on_connect
        client.on_message = _on_message
        client.connect_async(settings.space_mqtt_broker, settings.space_mqtt_port, keepalive=30)
        client.loop_start()
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
