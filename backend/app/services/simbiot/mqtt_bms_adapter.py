"""MQTT BMS adapter — config-driven, push-based, with cached reads."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from collections.abc import Sequence

from app.services.simbiot.bms_adapter import (
    BmsAdapter,
    BmsAdapterCapabilities,
    BmsConnectionConfig,
    BmsConnectionStatus,
    BmsDeviceDescriptor,
    BmsPointDescriptor,
    BmsPointValue,
    BmsSubscription,
    BmsWriteRequest,
)

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


class MqttBmsAdapter(BmsAdapter):
    """Config-driven MQTT adapter for commercial BMS integrations.

    Connects to a shared Mosquitto broker with per-site credentials and
    topic scoping (``sentinel/{site_id}/#``). Point definitions come from
    a per-site CSV or JSON config map, not hardcoded fields.

    Read returns cached state populated by the push subscriber callback.
    Staleness (``age_seconds``) is reported so the freshness/grounding
    layer can detect stale MQTT data.
    """

    def __init__(
        self,
        broker: str = "144.91.122.235",
        port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "",
        client_id: str = "",
        use_tls: bool = False,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._broker = broker
        self._port = port
        self._username = username
        self._password = password
        self._topic_prefix = topic_prefix
        self._client_id = client_id or f"sentinel-mqtt-{topic_prefix or 'unknown'}"
        self._use_tls = use_tls
        self._timeout = timeout_seconds

        self._site_id: str = ""
        self._connected = False
        self._mqtt_client: Any = None

        # ── point config (populated by discover_points) ──
        self._point_defs: dict[str, dict[str, Any]] = {}

        # ── cached state populated by on_message ──
        self._state: dict[str, Any] = {}
        self._last_message_time: float = 0.0

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def adapter_id(self) -> str:
        return "mqtt"

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return BmsAdapterCapabilities(
            supports_device_discovery=True,
            supports_point_discovery=True,
            supports_hierarchy_discovery=False,
            supports_reads=True,
            supports_writes=True,
            supports_subscriptions=True,
            supports_history=False,
        )

    # ── Connection lifecycle ────────────────────────────────────────────────

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        self._site_id = config.site_id

        if mqtt is None:
            logger.error("paho-mqtt not installed — MQTT adapter unavailable")
            return BmsConnectionStatus(
                connected=False,
                site_id=self._site_id,
                source_type="mqtt",
                status="error",
                message="paho-mqtt package not available",
            )

        broker = config.host or self._broker
        port = config.port or self._port
        username = config.username or self._username
        password = config.password or self._password
        topic_prefix = config.metadata.get("topic_prefix", "") or self._topic_prefix
        self._topic_prefix = topic_prefix
        client_id = config.metadata.get("client_id", "") or f"sentinel-mqtt-{self._site_id}"

        self._mqtt_client = mqtt.Client(client_id=client_id)
        if username:
            self._mqtt_client.username_pw_set(username, password)

        if config.use_tls or config.metadata.get("use_tls", False):
            self._mqtt_client.tls_set()

        self._mqtt_client.on_message = self._on_message
        self._mqtt_client.on_connect = self._on_connect

        try:
            self._mqtt_client.connect(broker, port, keepalive=60)
            self._mqtt_client.loop_start()
            self._connected = True

            subscribe_topic = f"{topic_prefix}/#" if topic_prefix else "#"
            self._mqtt_client.subscribe(subscribe_topic, qos=1)
            logger.info(
                "MQTT adapter %s connected to %s:%s, subscribed to %s",
                self._site_id,
                broker,
                port,
                subscribe_topic,
            )

            return BmsConnectionStatus(
                connected=True,
                site_id=self._site_id,
                source_type="mqtt",
                status="connected",
                message=f"Connected to MQTT broker at {broker}:{port}",
            )
        except Exception as exc:
            logger.error("MQTT adapter %s connection failed: %s", self._site_id, exc)
            return BmsConnectionStatus(
                connected=False,
                site_id=self._site_id,
                source_type="mqtt",
                status="error",
                message=str(exc),
            )

    async def disconnect(self) -> None:
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception as exc:
                logger.debug("MQTT disconnect: %s", exc)
        self._mqtt_client = None
        self._connected = False

    async def get_status(self) -> BmsConnectionStatus:
        now = time.time()
        age = now - self._last_message_time if self._last_message_time > 0 else -1.0
        return BmsConnectionStatus(
            connected=self._connected,
            site_id=self._site_id,
            source_type="mqtt",
            status="connected" if self._connected else "disconnected",
            message=f"Last message received {age:.1f}s ago" if self._connected else "Disconnected",
            metadata={
                "broker": self._broker,
                "port": self._port,
                "topic_prefix": self._topic_prefix,
                "last_message_age_seconds": age,
            },
        )

    # ── Discovery ───────────────────────────────────────────────────────────

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        return [
            BmsDeviceDescriptor(
                device_id=f"mqtt-{self._site_id}",
                display_name=f"MQTT Broker ({self._site_id})",
                protocol="mqtt",
                address=f"{self._broker}:{self._port}",
                metadata={"topic_prefix": self._topic_prefix},
            ),
        ]

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        return [
            BmsPointDescriptor(
                point_id=pid,
                point_name=cfg.get("name", pid),
                point_type=cfg.get("type", "analog"),
                unit=cfg.get("unit"),
                writable=bool(cfg.get("write_topic")),
                metadata=cfg,
            )
            for pid, cfg in self._point_defs.items()
        ]

    # ── Read ────────────────────────────────────────────────────────────────

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        now = time.time()
        age = now - self._last_message_time if self._last_message_time > 0 else -1.0
        value = self._state.get(point_id)
        cfg = self._point_defs.get(point_id, {})

        quality = "good" if value is not None else "bad"
        timestamp = (
            datetime.fromtimestamp(self._last_message_time, tz=UTC).isoformat() if self._last_message_time > 0 else None
        )

        return BmsPointValue(
            device_id=device_id,
            point_id=point_id,
            value=value,
            quality=quality,
            timestamp=timestamp,
            unit=cfg.get("unit"),
            metadata={
                "age_seconds": age,
                "topic": cfg.get("read_topic", ""),
            },
        )

    async def read_points(self, device_id: str, point_ids: Sequence[str]) -> list[BmsPointValue]:
        return [await self.read_point(device_id, pid) for pid in point_ids]

    # ── Write ───────────────────────────────────────────────────────────────

    async def write_point(self, request: BmsWriteRequest) -> bool:
        if self._mqtt_client is None or not self._connected:
            logger.warning("MQTT adapter %s: cannot write — not connected", self._site_id)
            return False

        cfg = self._point_defs.get(request.point_id)
        if not cfg:
            logger.warning("MQTT adapter %s: unknown point %s", self._site_id, request.point_id)
            return False

        write_topic = cfg.get("write_topic")
        if not write_topic:
            logger.warning("MQTT adapter %s: point %s has no write_topic", self._site_id, request.point_id)
            return False

        payload = str(request.value)
        try:
            result = self._mqtt_client.publish(write_topic, payload, qos=1, retain=False)
            ok = result.rc == mqtt.MQTT_ERR_SUCCESS if mqtt is not None else False
            logger.info(
                "MQTT adapter %s: wrote %s=%s to %s (rc=%s)",
                self._site_id,
                request.point_id,
                payload,
                write_topic,
                result.rc,
            )
            return ok
        except Exception as exc:
            logger.error("MQTT adapter %s: write failed for %s: %s", self._site_id, request.point_id, exc)
            return False

    # ── Subscriptions (MQTT-native push) ────────────────────────────────────

    async def subscribe_points(self, device_id: str, point_ids: Sequence[str]) -> BmsSubscription:
        if self._mqtt_client is None or not self._connected:
            raise RuntimeError("MQTT adapter not connected")

        for pid in point_ids:
            cfg = self._point_defs.get(pid)
            topic = (cfg or {}).get("read_topic", "")
            if topic:
                self._mqtt_client.subscribe(topic, qos=1)

        return BmsSubscription(
            subscription_id=f"mqtt-sub-{self._site_id}",
            device_id=device_id,
            point_ids=list(point_ids),
        )

    # ── Config loader ───────────────────────────────────────────────────────

    def load_point_config(self, points: list[dict[str, Any]]) -> None:
        """Load point definitions from a list of config dicts.

        Each entry supports::

            {
                "point_id": "temperature_zone_a",
                "name": "Zone A Temperature",
                "read_topic": "sentinel/site-005/temperature/zone_a",
                "write_topic": "sentinel/site-005/temperature/zone_a/set",  # optional
                "type": "analog",       # analog | binary | multistate
                "unit": "°C",
            }

        This is the config-driven alternative to hardcoded entity fields.
        """
        self._point_defs = {p["point_id"]: p for p in points}

    # ── MQTT callbacks ──────────────────────────────────────────────────────

    def _on_connect(self, client: Any, userdata: Any, flags: dict, rc: int) -> None:
        self._connected = rc == 0
        logger.info("MQTT adapter %s on_connect rc=%d", self._site_id, rc)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            return

        self._last_message_time = time.time()

        point_id = self._resolve_point_id(topic)
        if point_id is None:
            return

        parsed = self._parse_payload(payload)
        self._state[point_id] = parsed

    def _resolve_point_id(self, topic: str) -> str | None:
        """Reverse-map a topic to a point_id using the point definition."""
        for pid, cfg in self._point_defs.items():
            if cfg.get("read_topic") == topic:
                return pid
        return None

    @staticmethod
    def _parse_payload(payload: str) -> Any:
        """Parse incoming MQTT payload to a typed value."""
        v = payload.strip()
        if v.lower() in {"unavailable", "unknown", "none", ""}:
            return None
        if v.lower() in ("on", "true", "1"):
            return True
        if v.lower() in ("off", "false", "0"):
            return False
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            return float(v)
        except (ValueError, TypeError):
            return v
