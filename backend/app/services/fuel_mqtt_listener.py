"""MQTT ingest for fuel tank monitoring nodes (Phase 148).

Subscribes to fuel-level, event, and status MQTT topics. Parses telemetry,
validates sensor readings, persists via FuelStore, and emits events to the
SENTINEL event bus. Follows the same pattern as SpaceMqttListener.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event importance mapping for fuel event types
# ---------------------------------------------------------------------------

_EVENT_IMPORTANCE: dict[str, str] = {
    "theft_alert": "CRITICAL",
    "leak_detected": "CRITICAL",
    "low_fuel": "HIGH",
    "overfill": "HIGH",
    "temp_alert": "HIGH",
    "refill_detected": "INFO",
    "runtime_complete": "INFO",
    "sensor_fault": "MEDIUM",
}


def get_event_importance(event_type: str) -> Any:
    """Map a fuel event_type string to an Importance enum value."""
    from app.services.event_bus import Importance

    level_name = _EVENT_IMPORTANCE.get(event_type, "INFO")
    return getattr(Importance, level_name, Importance.INFO)


# ---------------------------------------------------------------------------
# FuelMqttListener
# ---------------------------------------------------------------------------


class FuelMqttListener:
    """Optional MQTT subscriber for fuel tank monitoring topics."""

    def __init__(self) -> None:
        self._client: Any = None
        self._enabled = bool(settings.fuel_mqtt_enabled and settings.fuel_mqtt_broker)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        """Connect to the MQTT broker and subscribe to fuel topics."""
        if not self._enabled:
            logger.info(
                "Fuel MQTT listener disabled (fuel_mqtt_enabled=%s, broker=%s)",
                settings.fuel_mqtt_enabled,
                settings.fuel_mqtt_broker or "<empty>",
            )
            return

        self._loop = asyncio.get_running_loop()

        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("Fuel MQTT listener not started: paho-mqtt not installed")
            return

        import socket

        client_id = (settings.fuel_mqtt_client_id or "sentinel-fuel-backend") + "-" + socket.gethostname()
        client = mqtt.Client(client_id=client_id)

        if settings.fuel_mqtt_username:
            client.username_pw_set(settings.fuel_mqtt_username, settings.fuel_mqtt_password)

        def _on_connect(client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None) -> None:
            if reason_code == 0:
                topics = [
                    settings.fuel_mqtt_topic_level,
                    settings.fuel_mqtt_topic_events,
                    settings.fuel_mqtt_topic_status,
                ]
                for topic in topics:
                    client.subscribe(topic)
                    logger.info("Fuel MQTT listener subscribed to %s", topic)
            else:
                logger.warning("Fuel MQTT listener connect failed: %s", reason_code)

        def _on_message(_client: Any, _userdata: Any, message: Any) -> None:
            try:
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.process_fuel_message(message.topic, message.payload),
                        self._loop,
                    )
                else:
                    logger.warning("Fuel MQTT message dropped: listener loop unavailable")
            except Exception:
                logger.warning("Fuel MQTT message dropped: no running loop")

        client.on_connect = _on_connect
        client.on_message = _on_message
        client.connect_async(settings.fuel_mqtt_broker, settings.fuel_mqtt_port, keepalive=30)
        client.loop_start()
        self._client = client
        logger.info("Fuel MQTT listener started (broker=%s:%d)", settings.fuel_mqtt_broker, settings.fuel_mqtt_port)

    async def stop(self) -> None:
        """Disconnect from the MQTT broker and stop the network loop."""
        if self._client is None:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._client = None
        logger.info("Fuel MQTT listener stopped")

    # -----------------------------------------------------------------------
    # Message processing
    # -----------------------------------------------------------------------

    async def process_fuel_message(self, topic: str, payload: bytes) -> None:
        """Route an incoming MQTT message to the correct handler by topic suffix."""
        try:
            if topic.endswith("/level"):
                await self._handle_level(topic, payload)
            elif topic.endswith("/events"):
                await self._handle_event(topic, payload)
            elif topic.endswith("/status"):
                await self._handle_status(topic, payload)
            else:
                logger.debug("Fuel MQTT: ignoring unknown topic %s", topic)
        except Exception as exc:
            logger.error("Error processing fuel MQTT message on %s: %s", topic, exc)

    async def _handle_level(self, topic: str, payload: bytes) -> None:
        """Parse telemetry, validate sensor reading, persist, emit event."""
        from app.models.fuel import parse_fuel_telemetry, validate_sensor_reading
        from app.services.fuel_store import get_fuel_store

        telemetry = parse_fuel_telemetry(topic, payload)
        if telemetry is None:
            return

        telemetry = validate_sensor_reading(telemetry)
        await get_fuel_store().store_telemetry(telemetry)

        # Emit telemetry event to event bus
        try:
            from app.services.event_bus import Importance, SentinelEvent, get_event_bus

            await get_event_bus().emit(
                SentinelEvent(
                    event_type="fuel.telemetry",
                    source="fuel_mqtt_listener",
                    payload={
                        "tank_id": telemetry.tank_id,
                        "fuel_level_pct": telemetry.fuel_level_pct,
                        "fuel_level_litres": telemetry.fuel_level_litres,
                        "sensor_fault": telemetry.sensor_fault,
                        "generator_running": telemetry.generator_running,
                    },
                    importance=Importance.INFO,
                    site_id=telemetry.site_id,
                    equipment_id=telemetry.tank_id,
                )
            )
        except Exception as exc:
            logger.debug("Event bus emit failed (non-fatal): %s", exc)

    async def _handle_event(self, topic: str, payload: bytes) -> None:
        """Parse a fuel event and emit to the event bus with appropriate importance."""
        from app.models.fuel import FuelEvent

        try:
            if isinstance(payload, bytes):
                raw: dict[str, Any] = json.loads(payload.decode("utf-8"))
            elif isinstance(payload, str):
                raw = json.loads(payload)
            else:
                raw = payload

            event = FuelEvent(
                node_id=raw.get("node_id", ""),
                site_id=raw.get("site_id", ""),
                tank_id=raw.get("tank_id", ""),
                event_type=raw.get("event_type", "unknown"),
                payload=raw.get("payload", {}),
                ts=int(raw.get("ts", 0)),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse fuel event: %s", exc)
            return

        # Emit to event bus
        try:
            from app.services.event_bus import SentinelEvent, get_event_bus

            importance = get_event_importance(event.event_type)
            await get_event_bus().emit(
                SentinelEvent(
                    event_type=f"fuel.{event.event_type}",
                    source="fuel_mqtt_listener",
                    payload={
                        "tank_id": event.tank_id,
                        "node_id": event.node_id,
                        "event_payload": event.payload,
                    },
                    importance=importance,
                    site_id=event.site_id,
                    equipment_id=event.tank_id,
                )
            )
        except Exception as exc:
            logger.debug("Event bus emit failed (non-fatal): %s", exc)

    async def _handle_status(self, topic: str, payload: bytes) -> None:
        """Handle node online/offline status messages."""
        try:
            if isinstance(payload, bytes):
                raw: dict[str, Any] = json.loads(payload.decode("utf-8"))
            elif isinstance(payload, str):
                raw = json.loads(payload)
            else:
                raw = payload

            node_id = raw.get("node_id", "")
            status = raw.get("status", "unknown")
            site_id = raw.get("site_id", "")
            is_online = status.lower() in ("online", "connected", "up")

            event_type = "fuel.node_online" if is_online else "fuel.node_offline"
            logger.info("Fuel node %s is %s (site=%s)", node_id, status, site_id)

            # Emit to event bus
            try:
                from app.services.event_bus import Importance, SentinelEvent, get_event_bus

                await get_event_bus().emit(
                    SentinelEvent(
                        event_type=event_type,
                        source="fuel_mqtt_listener",
                        payload={"node_id": node_id, "status": status},
                        importance=Importance.INFO,
                        site_id=site_id,
                    )
                )
            except Exception as exc:
                logger.debug("Event bus emit failed (non-fatal): %s", exc)

        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse fuel status message: %s", exc)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[FuelMqttListener] = None


def get_fuel_mqtt_listener() -> FuelMqttListener:
    """Return the singleton FuelMqttListener instance."""
    global _instance
    if _instance is None:
        _instance = FuelMqttListener()
    return _instance
