"""Tests for HomeAssistantGateway."""

from __future__ import annotations

from app.gateways.home_assistant import (
    HomeAssistantGateway,
    _parse_ha_state,
    _validate_entity_id,
)


class TestValidateEntityId:
    def test_valid_entity_ids(self):
        assert _validate_entity_id("sensor.deye_pv_power") is True
        assert _validate_entity_id("sensor.battery_soc") is True
        assert _validate_entity_id("switch.geyser") is True
        assert _validate_entity_id("sensor.pv_power_total") is True

    def test_rejects_wildcards(self):
        assert _validate_entity_id("sensor.#") is False
        assert _validate_entity_id("sensor/+state") is False

    def test_rejects_long(self):
        assert _validate_entity_id("a" * 101) is False

    def test_rejects_empty(self):
        assert _validate_entity_id("") is False


class TestParseHAState:
    def test_numeric_strings(self):
        assert _parse_ha_state("1234.5", "pv_power_w") == 1234.5
        assert _parse_ha_state("0", "grid_power_w") == 0.0
        assert _parse_ha_state("-100", "battery_power_w") == -100.0

    def test_unavailable_returns_none(self):
        assert _parse_ha_state("unavailable", "pv_power_w") is None
        assert _parse_ha_state("unknown", "battery_soc_pct") is None
        assert _parse_ha_state("", "grid_power_w") is None

    def test_on_off_binary_power_fields(self):
        assert _parse_ha_state("on", "geyser_state") == "on"
        assert _parse_ha_state("off", "geyser_state") == "off"

    def test_on_off_numeric_fields(self):
        assert _parse_ha_state("on", "load_power_w") == 1.0
        assert _parse_ha_state("off", "load_power_w") == 0.0


class TestHomeAssistantGateway:
    def test_init_sets_site_id(self):
        gw = HomeAssistantGateway(
            site_id="res-123",
            config={"entity_map": {"pv_power_w": "sensor.pv"}},
        )
        assert gw.site_id == "res-123"
        assert gw.entity_map == {"pv_power_w": "sensor.pv"}

    def test_default_entity_map_empty(self):
        gw = HomeAssistantGateway(site_id="res-456", config={})
        assert gw.entity_map == {}

    def test_build_subscription_topics(self):
        gw = HomeAssistantGateway(
            site_id="res-789",
            config={
                "entity_map": {
                    "pv_power_w": "sensor.pv",
                    "battery_soc_pct": "sensor.soc",
                    "geyser_state": "switch.geyser",
                }
            },
        )
        topics = gw._build_subscription_topics()
        topic_strs = [t[0] for t in topics]
        assert "homeassistant/sensor/sensor.pv/state" in topic_strs
        assert "homeassistant/sensor/sensor.soc/state" in topic_strs
        assert "homeassistant/switch/switch.geyser/state" in topic_strs

    def test_subscription_topics_respects_entity_map(self):
        """Only mapped fields produce subscription topics."""
        gw = HomeAssistantGateway(
            site_id="res-test",
            config={"entity_map": {"pv_power_w": "sensor.pv"}},
        )
        topics = dict(gw._build_subscription_topics())
        # geyser not mapped — no topic
        geyser_topic = "homeassistant/switch/switch.geyser/state"
        assert geyser_topic not in topics

    def test_entity_to_sentinel_field(self):
        gw = HomeAssistantGateway(
            site_id="res-map",
            config={"entity_map": {"pv_power_w": "sensor.deye_pv"}},
        )
        result = gw._entity_to_sentinel_field("homeassistant/sensor/sensor.deye_pv/state")
        assert result == "pv_power_w"

    def test_unknown_topic_returns_none(self):
        gw = HomeAssistantGateway(site_id="res-unknown", config={})
        result = gw._entity_to_sentinel_field("homeassistant/sensor/completely/unknown/state")
        assert result is None

    def test_state_accumulates(self):
        gw = HomeAssistantGateway(
            site_id="res-state",
            config={"entity_map": {"pv_power_w": "sensor.pv", "battery_soc_pct": "sensor.soc"}},
        )
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.topic = "homeassistant/sensor/sensor.pv/state"
        msg.payload = b"1500.5"
        gw.on_mqtt_message(None, None, msg)
        assert gw._state["pv_power_w"] == 1500.5
        msg.topic = "homeassistant/sensor/sensor.soc/state"
        msg.payload = b"75"
        gw.on_mqtt_message(None, None, msg)
        assert gw._state["battery_soc_pct"] == 75.0
