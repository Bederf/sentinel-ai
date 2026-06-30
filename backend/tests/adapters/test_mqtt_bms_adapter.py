"""Tests for MqttBmsAdapter — SIMBIOT BmsAdapter wrapper for MQTT."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.simbiot import BmsConnectionConfig, BmsWriteRequest
from app.services.simbiot.mqtt_bms_adapter import MqttBmsAdapter


def _make_config(
    site_id="site-005",
    host="144.91.122.235",
    port=1883,
    username="mqtt-site-005",
    password="test-secret-32-bytes-long!",
    topic_prefix="sentinel/site-005",
    client_id="sentinel-mqtt-site-005",
):
    return BmsConnectionConfig(
        site_id=site_id,
        source_type="mqtt",
        host=host,
        port=port,
        username=username,
        password=password,
        timeout_seconds=5.0,
        metadata={
            "topic_prefix": topic_prefix,
            "client_id": client_id,
        },
    )


def _sample_point_configs():
    return [
        {
            "point_id": "temperature_zone_a",
            "name": "Zone A Temperature",
            "read_topic": "sentinel/site-005/temperature/zone_a",
            "write_topic": "sentinel/site-005/temperature/zone_a/set",
            "type": "analog",
            "unit": "°C",
        },
        {
            "point_id": "light_level_b",
            "name": "Light Level B",
            "read_topic": "sentinel/site-005/light/b",
            "write_topic": "sentinel/site-005/light/b/set",
            "type": "analog",
            "unit": "%",
        },
        {
            "point_id": "switch_readonly",
            "name": "Read-only Switch",
            "read_topic": "sentinel/site-005/switch/ro",
            "type": "binary",
            "unit": "",
        },
    ]


# -------------------------------------------------------------------------
# Capabilities
# -------------------------------------------------------------------------
class TestCapabilities:
    def test_adapter_id(self):
        adapter = MqttBmsAdapter()
        assert adapter.adapter_id == "mqtt"

    def test_capabilities(self):
        adapter = MqttBmsAdapter()
        caps = adapter.capabilities
        assert caps.supports_reads is True
        assert caps.supports_writes is True
        assert caps.supports_subscriptions is True
        assert caps.supports_history is False
        assert caps.supports_device_discovery is True
        assert caps.supports_point_discovery is True


# -------------------------------------------------------------------------
# Connect / Disconnect
# -------------------------------------------------------------------------
class TestConnect:
    @pytest.mark.asyncio
    @patch("app.services.simbiot.mqtt_bms_adapter.mqtt")
    async def test_connect_success(self, mock_mqtt):
        mock_client = MagicMock()
        mock_mqtt.Client.return_value = mock_client

        adapter = MqttBmsAdapter()
        config = _make_config()
        status = await adapter.connect(config)

        assert status.connected is True
        assert status.site_id == "site-005"
        assert status.source_type == "mqtt"
        mock_mqtt.Client.assert_called_once_with(client_id="sentinel-mqtt-site-005")
        mock_client.username_pw_set.assert_called_once_with("mqtt-site-005", "test-secret-32-bytes-long!")
        mock_client.connect.assert_called_once_with("144.91.122.235", 1883, keepalive=60)
        mock_client.loop_start.assert_called_once()
        mock_client.subscribe.assert_called_once_with("sentinel/site-005/#", qos=1)

    @pytest.mark.asyncio
    @patch("app.services.simbiot.mqtt_bms_adapter.mqtt")
    async def test_connect_sets_on_connect_and_on_message(self, mock_mqtt):
        mock_client = MagicMock()
        mock_mqtt.Client.return_value = mock_client

        adapter = MqttBmsAdapter()
        await adapter.connect(_make_config())

        assert mock_client.on_connect is not None
        assert mock_client.on_message is not None

    @pytest.mark.asyncio
    @patch("app.services.simbiot.mqtt_bms_adapter.mqtt")
    async def test_connect_without_auth(self, mock_mqtt):
        mock_client = MagicMock()
        mock_mqtt.Client.return_value = mock_client

        adapter = MqttBmsAdapter()
        config = _make_config(username="", password="")
        await adapter.connect(config)

        mock_client.username_pw_set.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.simbiot.mqtt_bms_adapter.mqtt", None)
    async def test_connect_no_paho(self):
        adapter = MqttBmsAdapter()
        config = _make_config()
        status = await adapter.connect(config)

        assert status.connected is False
        assert "paho-mqtt" in status.message

    @pytest.mark.asyncio
    async def test_disconnect(self):
        adapter = MqttBmsAdapter()
        client = MagicMock()
        adapter._mqtt_client = client
        adapter._connected = True

        await adapter.disconnect()

        assert adapter._mqtt_client is None
        assert adapter._connected is False
        client.loop_stop.assert_called_once()
        client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        adapter = MqttBmsAdapter()
        await adapter.disconnect()


# -------------------------------------------------------------------------
# Discovery
# -------------------------------------------------------------------------
class TestDiscovery:
    @pytest.mark.asyncio
    async def test_discover_devices(self):
        adapter = MqttBmsAdapter()
        adapter._site_id = "site-005"
        adapter._broker = "144.91.122.235"
        adapter._port = 1883
        adapter._topic_prefix = "sentinel/site-005"

        devices = await adapter.discover_devices()
        assert len(devices) == 1
        assert devices[0].device_id == "mqtt-site-005"
        assert devices[0].protocol == "mqtt"
        assert devices[0].address == "144.91.122.235:1883"

    @pytest.mark.asyncio
    async def test_discover_points(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())

        points = await adapter.discover_points("mqtt-site-005")
        assert len(points) == 3

        temp = next(p for p in points if p.point_id == "temperature_zone_a")
        assert temp.writable is True
        assert temp.unit == "°C"

        ro = next(p for p in points if p.point_id == "switch_readonly")
        assert ro.writable is False


# -------------------------------------------------------------------------
# Read — cached state with age reporting
# -------------------------------------------------------------------------
class TestRead:
    @pytest.mark.asyncio
    async def test_read_point_returns_cached_value(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())
        adapter._state["temperature_zone_a"] = 22.5
        adapter._last_message_time = 1000.0

        with patch("app.services.simbiot.mqtt_bms_adapter.time") as mock_time:
            mock_time.time.return_value = 1005.0
            result = await adapter.read_point("mqtt-site-005", "temperature_zone_a")

        assert result.device_id == "mqtt-site-005"
        assert result.point_id == "temperature_zone_a"
        assert result.value == 22.5
        assert result.quality == "good"
        assert result.unit == "°C"
        assert result.metadata["age_seconds"] == 5.0

    @pytest.mark.asyncio
    async def test_read_point_unknown_point_returns_bad_quality(self):
        adapter = MqttBmsAdapter()
        result = await adapter.read_point("mqtt-site-005", "nonexistent")
        assert result.value is None
        assert result.quality == "bad"

    @pytest.mark.asyncio
    async def test_read_point_stale(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())
        adapter._state["temperature_zone_a"] = 22.5
        adapter._last_message_time = 0.0

        result = await adapter.read_point("mqtt-site-005", "temperature_zone_a")
        assert result.value == 22.5
        assert result.metadata["age_seconds"] == -1.0

    @pytest.mark.asyncio
    async def test_read_points_batch(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())
        adapter._state["temperature_zone_a"] = 22.5
        adapter._state["light_level_b"] = 80
        adapter._last_message_time = 1000.0

        with patch("app.services.simbiot.mqtt_bms_adapter.time") as mock_time:
            mock_time.time.return_value = 1002.0
            results = await adapter.read_points("mqtt-site-005", ["temperature_zone_a", "light_level_b"])

        assert len(results) == 2
        assert results[0].value == 22.5
        assert results[1].value == 80


# -------------------------------------------------------------------------
# Write
# -------------------------------------------------------------------------
class TestWrite:
    @pytest.mark.asyncio
    async def test_write_point_success(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())
        adapter._connected = True
        client = MagicMock()
        client.publish.return_value.rc = 0
        adapter._mqtt_client = client

        with patch("app.services.simbiot.mqtt_bms_adapter.mqtt") as mock_mqtt:
            mock_mqtt.MQTT_ERR_SUCCESS = 0
            request = BmsWriteRequest(device_id="mqtt-site-005", point_id="temperature_zone_a", value=23.0)
            result = await adapter.write_point(request)

        assert result is True
        client.publish.assert_called_once_with(
            "sentinel/site-005/temperature/zone_a/set",
            "23.0",
            qos=1,
            retain=False,
        )

    @pytest.mark.asyncio
    @patch("app.services.simbiot.mqtt_bms_adapter.mqtt", MagicMock())
    async def test_write_point_unwritable(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())
        adapter._connected = True
        adapter._mqtt_client = MagicMock()

        request = BmsWriteRequest(device_id="mqtt-site-005", point_id="switch_readonly", value=True)
        result = await adapter.write_point(request)

        assert result is False
        adapter._mqtt_client.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_point_not_connected(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())
        adapter._connected = False

        request = BmsWriteRequest(device_id="mqtt-site-005", point_id="temperature_zone_a", value=23.0)
        result = await adapter.write_point(request)
        assert result is False


# -------------------------------------------------------------------------
# MQTT Callbacks
# -------------------------------------------------------------------------
class TestCallbacks:
    def test_on_message_updates_state(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())

        msg = MagicMock()
        msg.topic = "sentinel/site-005/temperature/zone_a"
        msg.payload = b"22.5"
        adapter._on_message(None, None, msg)

        assert adapter._state["temperature_zone_a"] == 22.5
        assert adapter._last_message_time > 0

    def test_on_message_unavailable(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())

        msg = MagicMock()
        msg.topic = "sentinel/site-005/temperature/zone_a"
        msg.payload = b"unavailable"
        adapter._on_message(None, None, msg)

        assert adapter._state["temperature_zone_a"] is None

    def test_on_message_unmapped_topic(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())

        msg = MagicMock()
        msg.topic = "some/other/topic"
        msg.payload = b"42"
        adapter._on_message(None, None, msg)

        assert "temperature_zone_a" not in adapter._state

    def test_on_connect_rc_0_sets_connected(self):
        adapter = MqttBmsAdapter()
        adapter._on_connect(None, None, None, 0)
        assert adapter._connected is True

    def test_on_connect_rc_nonzero(self):
        adapter = MqttBmsAdapter()
        adapter._on_connect(None, None, None, 5)
        assert adapter._connected is False


# -------------------------------------------------------------------------
# Config loading
# -------------------------------------------------------------------------
class TestConfigLoading:
    def test_load_point_config(self):
        adapter = MqttBmsAdapter()
        configs = _sample_point_configs()
        adapter.load_point_config(configs)

        assert len(adapter._point_defs) == 3
        assert "temperature_zone_a" in adapter._point_defs
        assert adapter._point_defs["temperature_zone_a"]["read_topic"] == "sentinel/site-005/temperature/zone_a"

    def test_load_point_config_empty(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config([])
        assert adapter._point_defs == {}

    def test_load_point_config_clears_previous(self):
        adapter = MqttBmsAdapter()
        adapter.load_point_config(_sample_point_configs())
        adapter.load_point_config([])
        assert adapter._point_defs == {}


# -------------------------------------------------------------------------
# Status
# -------------------------------------------------------------------------
class TestStatus:
    @pytest.mark.asyncio
    async def test_get_status_connected(self):
        adapter = MqttBmsAdapter()
        adapter._site_id = "site-005"
        adapter._connected = True
        adapter._broker = "144.91.122.235"
        adapter._port = 1883
        adapter._topic_prefix = "sentinel/site-005"
        adapter._last_message_time = 1000.0

        with patch("app.services.simbiot.mqtt_bms_adapter.time") as mock_time:
            mock_time.time.return_value = 1005.0
            status = await adapter.get_status()

        assert status.connected is True
        assert status.status == "connected"
        assert status.metadata["last_message_age_seconds"] == 5.0
        assert status.metadata["topic_prefix"] == "sentinel/site-005"

    @pytest.mark.asyncio
    async def test_get_status_disconnected(self):
        adapter = MqttBmsAdapter()
        adapter._site_id = "site-005"
        adapter._connected = False

        status = await adapter.get_status()
        assert status.connected is False
        assert status.status == "disconnected"


# -------------------------------------------------------------------------
# Subscribe (MQTT-native push)
# -------------------------------------------------------------------------
class TestSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_points(self):
        adapter = MqttBmsAdapter()
        adapter._site_id = "site-005"
        adapter.load_point_config(_sample_point_configs())
        adapter._connected = True
        adapter._mqtt_client = MagicMock()

        sub = await adapter.subscribe_points("mqtt-site-005", ["temperature_zone_a", "light_level_b"])

        assert sub.subscription_id == "mqtt-sub-site-005"
        assert sub.point_ids == ["temperature_zone_a", "light_level_b"]
        assert adapter._mqtt_client.subscribe.call_count == 2

    @pytest.mark.asyncio
    async def test_subscribe_not_connected(self):
        adapter = MqttBmsAdapter()
        adapter._connected = False

        with pytest.raises(RuntimeError, match="not connected"):
            await adapter.subscribe_points("mqtt-site-005", ["temperature_zone_a"])
