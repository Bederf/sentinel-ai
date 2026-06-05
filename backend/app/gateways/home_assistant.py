"""Home Assistant SIMBIOT Gateway.

Home Assistant acts as a residential SIMBIOT gateway.
HA publishes entity states via MQTT over a WireGuard tunnel to VPS Mosquitto.
SENTINEL subscribes to those topics and normalises the data.

Authentication:
- WireGuard tunnel provides network-level auth (peer must be active in wg0.conf)
- Mosquitto ACL credentials are provisioned by existing mqtt_provisioner
- No vendor API credentials required — HA is entirely local

This gateway is an MQTT subscriber, NOT a poller.
HomeAssistantGateway.subscribe() manages all MQTT subscriptions.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # type: ignore[assignment]

from app.gateways.base import SIMBIOTGateway
from app.gateways.schemas import GatewayStatus, SIMBIOTPoint
from app.services.residential.wireguard_peer_manager import WireGuardPeerManager

logger = logging.getLogger(__name__)

# Default HA MQTT integration topic patterns
# entity_id is substituted at subscription time from site_config.entity_map
_ENTITY_TOPIC_PATTERNS = {
    "pv_power_w": "homeassistant/sensor/{entity_id}/state",
    "battery_soc_pct": "homeassistant/sensor/{entity_id}/state",
    "battery_power_w": "homeassistant/sensor/{entity_id}/state",
    "grid_power_w": "homeassistant/sensor/{entity_id}/state",
    "grid_voltage_v": "homeassistant/sensor/{entity_id}/state",
    "load_power_w": "homeassistant/sensor/{entity_id}/state",
    "geyser_state": "homeassistant/switch/{entity_id}/state",
    "geyser_power_w": "homeassistant/sensor/{entity_id}/state",
    "ev_charger_power_w": "homeassistant/sensor/{entity_id}/state",
}

# Fields that are binary (on/off) rather than numeric
_BINARY_FIELDS = {"geyser_state"}

# Fields that are writable (controllable switches)
# Derived from entity_map field names — entities mapped to these fields
# are switches that can be turned on/off via MQTT command topic
_WRITABLE_FIELDS = {"geyser_state"}

# HA MQTT command topic patterns for controllable entities
_COMMAND_TOPIC_PATTERNS = {
    "geyser_state": "homeassistant/switch/{entity_id}/set",
}

# HA state values that represent unavailable/missing data
_UNAVAILABLE_STATES = {"unavailable", "unknown", "none", ""}

_ENTITY_ID_RE = re.compile(r"^[a-z0-9_\.]+$")


def _validate_entity_id(entity_id: str) -> bool:
    """Validate entity ID format — alphanumeric, dots, underscores only. No wildcards."""
    if not entity_id or len(entity_id) > 100:
        return False
    return bool(_ENTITY_ID_RE.match(entity_id))


def _parse_ha_state(value: str, field: str) -> float | str | None:
    """Parse HA state payload into numeric or string value.

    Handles:
    - Numeric strings: "1234.5" → 1234.5
    - "on"/"off": binary switches → 1.0/0.0 for power fields, "on"/"off" for state fields
    - "unavailable"/"unknown"/"": → None (stale/unavailable)
    """
    v = value.strip()
    if v.lower() in _UNAVAILABLE_STATES:
        return None
    if v in ("on", "off"):
        if field in _BINARY_FIELDS:
            return v  # geyser_state stays as string
        return 1.0 if v == "on" else 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


class HomeAssistantGateway(SIMBIOTGateway):
    """
    Home Assistant as a residential SIMBIOT gateway.

    HA publishes entity states via MQTT over WireGuard.
    SENTINEL subscribes and normalises to EnergySnapshot.

    gateway_type = "home_assistant"
    source_system = "home_assistant"

    No polling — this is an MQTT subscriber.
    """

    def __init__(self, site_id: str, config: dict):
        """
        Args:
            site_id: SENTINEL site ID (e.g. "res-{chat_id}")
            config: Must contain:
                - entity_map: dict[str, str]  field → HA entity_id
                - mqtt_broker: str
                - mqtt_port: int
                - mqtt_username: str
                - mqtt_password: str
        """
        super().__init__(site_id, config)
        self.entity_map: dict[str, str] = config.get("entity_map", {})
        self._state: dict[str, float | str | None] = {}
        self._last_updated: datetime | None = None
        self._mqtt_client: mqtt.Client | None = None
        self._peer_manager = WireGuardPeerManager()
        self._connected = False

    def _build_subscription_topics(self) -> list[tuple[str, int]]:
        """Build (topic, qos) pairs for all mapped entity topics."""
        topics = []
        for field, entity_id in self.entity_map.items():
            if entity_id and field in _ENTITY_TOPIC_PATTERNS:
                pattern = _ENTITY_TOPIC_PATTERNS[field]
                topic = pattern.format(entity_id=entity_id)
                topics.append((topic, 1))
        return topics

    def _entity_to_sentinel_field(self, topic: str) -> str | None:
        """Map incoming HA MQTT topic to sentinel field name."""
        # topic format: homeassistant/sensor/{entity_id}/state
        for field, pattern in _ENTITY_TOPIC_PATTERNS.items():
            # Build the regex version of the pattern for matching
            regex_pattern = pattern.replace("{entity_id}", r"([a-z0-9_\.]+)").replace("/", r"\/")
            m = re.match(f"^{regex_pattern}$", topic)
            if m:
                entity_id = m.group(1)
                # Find which field maps to this entity_id
                for f, eid in self.entity_map.items():
                    if eid == entity_id and f in _ENTITY_TOPIC_PATTERNS:
                        return f
        return None

    def on_mqtt_message(self, client, userdata, msg) -> None:
        """Called by paho-mqtt on every HA entity state change."""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            return

        sentinel_field = self._entity_to_sentinel_field(topic)
        if sentinel_field is None:
            return

        value = _parse_ha_state(payload, sentinel_field)
        self._state[sentinel_field] = value
        self._last_updated = datetime.now(UTC)

        # Publish normalised value to sentinel/{site_id}/energy/{field}
        self._publish_sentinel_field(sentinel_field, value)

        logger.debug(
            "HA gateway %s: %s = %s (from %s)",
            self.site_id,
            sentinel_field,
            value,
            topic,
        )

    def _publish_sentinel_field(self, field: str, value: float | str | None) -> None:
        """Publish a normalised field value to the sentinel MQTT namespace."""
        if self._mqtt_client is None or not self._connected:
            return
        topic = self.mqtt_topic(f"energy/{field}")
        if value is None:
            payload = ""
        elif isinstance(value, str):
            payload = value
        else:
            payload = str(value)
        self._mqtt_client.publish(topic, payload, qos=1, retain=True)

    async def connect(self) -> bool:
        """Verify WireGuard peer is active, then connect to Mosquitto."""
        peer = self._peer_manager.get_peer(self.site_id)
        if peer is None or peer.status != "active":
            logger.warning(
                "HA gateway %s: WireGuard peer not active (status=%s)",
                self.site_id,
                peer.status if peer else "not found",
            )
            return False

        if mqtt is None:
            logger.error("paho-mqtt not installed — HA gateway requires paho-mqtt")
            return False

        broker = self.config.get("mqtt_broker", "localhost")
        port = self.config.get("mqtt_port", 1883)
        username = self.config.get("mqtt_username", "")
        password = self.config.get("mqtt_password", "")

        client_id = f"sentinel-ha-gateway-{self.site_id}"
        self._mqtt_client = mqtt.Client(client_id=client_id)
        if username:
            self._mqtt_client.username_pw_set(username, password)
        self._mqtt_client.on_message = self.on_mqtt_message

        try:
            self._mqtt_client.connect(broker, port, keepalive=60)
            self._mqtt_client.loop_start()
            self._connected = True
            logger.info("HA gateway %s connected to Mosquitto at %s:%s", self.site_id, broker, port)
            return True
        except Exception as e:
            logger.error("HA gateway %s failed to connect to Mosquitto: %s", self.site_id, e)
            return False

    async def send_command(self, field: str, value: str) -> bool:
        """Send a control command to a writable HA entity via MQTT.

        Args:
            field: sentinel field name (e.g. "geyser_state")
            value: "on" or "off"

        Returns:
            True if command was published successfully
        """
        if field not in _WRITABLE_FIELDS:
            logger.warning("HA gateway %s: field %s is not writable", self.site_id, field)
            return False

        entity_id = self.entity_map.get(field)
        if not entity_id:
            logger.warning("HA gateway %s: no entity mapped for field %s", self.site_id, field)
            return False

        pattern = _COMMAND_TOPIC_PATTERNS.get(field)
        if not pattern:
            logger.warning("HA gateway %s: no command topic for field %s", self.site_id, field)
            return False

        topic = pattern.format(entity_id=entity_id)
        payload = "ON" if value.lower() == "on" else "OFF"

        if self._mqtt_client is None or not self._connected:
            logger.warning("HA gateway %s: cannot send command — not connected", self.site_id)
            return False

        try:
            result = self._mqtt_client.publish(topic, payload, qos=1, retain=False)
            logger.info(
                "HA gateway %s: command %s -> %s on %s (rc=%s)",
                self.site_id,
                field,
                payload,
                topic,
                result.rc,
            )
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error("HA gateway %s: command failed for %s: %s", self.site_id, field, e)
            return False

    async def get_writable_entities(self) -> list[dict]:
        """Return list of controllable entities with their current state."""
        entities = []
        for field in _WRITABLE_FIELDS:
            entity_id = self.entity_map.get(field)
            if entity_id:
                friendly = field.replace("_state", "").replace("_", " ").title()
                entities.append(
                    {
                        "field": field,
                        "entity_id": entity_id,
                        "friendly_name": friendly,
                        "current_state": self._state.get(field),
                    }
                )
        return entities

    async def get_point_list(self) -> list[SIMBIOTPoint]:
        """Build SIMBIOTPoint list from entity_map configuration."""
        points = []
        for field, entity_id in self.entity_map.items():
            if not entity_id:
                continue
            unit = (
                "W"
                if "power" in field
                or field
                in (
                    "pv_power_w",
                    "battery_power_w",
                    "grid_power_w",
                    "load_power_w",
                    "geyser_power_w",
                    "ev_charger_power_w",
                )
                else "%"
                if field == "battery_soc_pct"
                else "V"
                if field == "grid_voltage_v"
                else "binary"
                if field == "geyser_state"
                else ""
            )
            category = (
                "energy"
                if field
                in (
                    "pv_power_w",
                    "battery_soc_pct",
                    "battery_power_w",
                    "grid_power_w",
                    "load_power_w",
                    "geyser_power_w",
                    "ev_charger_power_w",
                )
                else "hvac"
            )
            points.append(
                SIMBIOTPoint(
                    point_id=entity_id,
                    display_name=f"{field} ({entity_id})",
                    unit=unit,
                    category=category,
                    sentinel_field=f"energy/{field}",
                    gateway_type="home_assistant",
                    writable=False,
                    site_id=self.site_id,
                    last_value=self._state.get(field),
                    last_updated=self._last_updated,
                )
            )
        return points

    async def subscribe(self) -> None:
        """Subscribe to all mapped HA entity topics and publish null to all sentinel topics."""
        if self._mqtt_client is None or not self._connected:
            logger.warning("HA gateway %s: cannot subscribe — not connected", self.site_id)
            return

        topics = self._build_subscription_topics()
        for topic, qos in topics:
            result = self._mqtt_client.subscribe(topic, qos)
            logger.info("HA gateway %s subscribed to %s (rc=%s)", self.site_id, topic, result)

        # Publish null to all sentinel topics (will be overwritten on first real message)
        # This clears any stale data from a previous session
        for field in _ENTITY_TOPIC_PATTERNS:
            self._publish_sentinel_field(field, None)

        # Publish heartbeat
        heartbeat_topic = self.mqtt_topic("energy/last_updated")
        self._mqtt_client.publish(
            heartbeat_topic,
            datetime.now(UTC).isoformat(),
            qos=1,
            retain=True,
        )

    async def get_status(self) -> GatewayStatus:
        """Return current gateway health and connectivity status."""
        peer = self._peer_manager.get_peer(self.site_id)
        peer_active = peer is not None and peer.status == "active"

        # Check data freshness
        error: str | None = None
        if self._last_updated is None:
            error = "No data received yet"
        else:
            age = (datetime.now(UTC) - self._last_updated).total_seconds()
            if age > 600:  # 10 minutes without data
                error = f"Data stale ({age / 60:.0f} minutes since last update)"

        point_count = len([e for e in self.entity_map.values() if e])

        return GatewayStatus(
            site_id=self.site_id,
            gateway_type="home_assistant",
            connected=self._connected and peer_active,
            last_heartbeat=self._last_updated,
            point_count=point_count,
            error=error,
        )

    async def disconnect(self) -> None:
        """Unsubscribe from all topics and publish null to retained sentinel topics."""
        if self._mqtt_client is not None:
            # Publish null to all retained sentinel topics to clear state
            for field in _ENTITY_TOPIC_PATTERNS:
                self._publish_sentinel_field(field, None)
            heartbeat_topic = self.mqtt_topic("energy/last_updated")
            self._mqtt_client.publish(heartbeat_topic, "", qos=1, retain=True)

            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception as e:
                logger.warning("HA gateway %s error on disconnect: %s", self.site_id, e)
            self._mqtt_client = None
        self._connected = False
        self._state.clear()
        self._last_updated = None
