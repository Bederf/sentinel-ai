"""Tests for fuel MQTT listener, models, store, and event mapping (Phase 148-02).

Covers:
- Telemetry parsing (5 tests)
- Sensor validation (5 tests)
- Fuel store (5 tests)
- Event importance mapping (4 tests)
- Listener lifecycle (2 tests)
- Message routing (3 tests)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.models.fuel import (
    FuelTankConfig,
    FuelTelemetry,
    parse_fuel_telemetry,
    validate_sensor_reading,
)
from app.services.event_bus import Importance, reset_event_bus
from app.services.fuel_mqtt_listener import FuelMqttListener, get_event_importance

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TELEMETRY = {
    "node_id": "fuel-node-001",
    "site_id": "site-002",
    "tank_id": "S002-TANK-EXT-001",
    "generator_id": "S002-GEN-B1-001",
    "fuel_level_pct": 72.5,
    "fuel_level_litres": 3625.0,
    "fuel_level_mm": 1450,
    "fuel_temp_c": 22.3,
    "consumption_rate_lph": 38.5,
    "consumption_anomaly": False,
    "runtime_remaining_hrs": 94.2,
    "days_to_empty": 3.9,
    "generator_running": True,
    "leak_detected": False,
    "overfill_alert": False,
    "theft_suspected": False,
    "sensor_fault": False,
    "sensor_ma": 12.0,
    "rssi": -45,
    "uptime_s": 86400,
    "ts": 1709683200,
}

SAMPLE_TELEMETRY_MINIMAL = {
    "node_id": "fuel-node-002",
    "site_id": "site-003",
    "tank_id": "S003-TANK-EXT-001",
    "fuel_level_pct": 50.0,
}


@pytest.fixture(autouse=True)
def _reset_event_bus():
    """Reset the event bus singleton before each test."""
    reset_event_bus()
    yield
    reset_event_bus()


# ===========================================================================
# 1. Telemetry parsing tests
# ===========================================================================


class TestParseFuelTelemetry:
    """Tests for parse_fuel_telemetry()."""

    def test_parse_valid_fuel_telemetry(self):
        """Valid JSON dict payload produces FuelTelemetry with all fields."""
        result = parse_fuel_telemetry("sentinel/fuel/node-001/level", SAMPLE_TELEMETRY)
        assert result is not None
        assert isinstance(result, FuelTelemetry)
        assert result.node_id == "fuel-node-001"
        assert result.site_id == "site-002"
        assert result.tank_id == "S002-TANK-EXT-001"
        assert result.fuel_level_pct == 72.5
        assert result.fuel_level_litres == 3625.0
        assert result.generator_running is True
        assert result.sensor_ma == 12.0

    def test_parse_fuel_telemetry_bytes(self):
        """Bytes payload is correctly decoded and parsed."""
        payload_bytes = json.dumps(SAMPLE_TELEMETRY).encode("utf-8")
        result = parse_fuel_telemetry("sentinel/fuel/node-001/level", payload_bytes)
        assert result is not None
        assert result.tank_id == "S002-TANK-EXT-001"
        assert result.fuel_level_pct == 72.5

    def test_parse_fuel_telemetry_missing_required(self):
        """Missing required fields returns None."""
        incomplete = {"node_id": "n1", "site_id": "s1"}  # no tank_id, no fuel_level_pct
        result = parse_fuel_telemetry("sentinel/fuel/n1/level", incomplete)
        assert result is None

    def test_parse_fuel_telemetry_invalid_json(self):
        """Malformed JSON bytes returns None."""
        result = parse_fuel_telemetry("sentinel/fuel/n1/level", b"not valid json{{{")
        assert result is None

    def test_parse_fuel_telemetry_minimal(self):
        """Only required fields produces FuelTelemetry with defaults."""
        result = parse_fuel_telemetry("sentinel/fuel/n2/level", SAMPLE_TELEMETRY_MINIMAL)
        assert result is not None
        assert result.fuel_level_pct == 50.0
        assert result.fuel_level_litres == 0.0  # default
        assert result.generator_running is False  # default
        assert result.sensor_fault is False  # default
        assert result.consumption_rate_lph is None  # default


# ===========================================================================
# 2. Sensor validation tests
# ===========================================================================


class TestValidateSensorReading:
    """Tests for validate_sensor_reading()."""

    def test_validate_sensor_normal(self):
        """Normal mA reading (12.0) keeps sensor_fault False."""
        t = FuelTelemetry(node_id="n1", site_id="s1", tank_id="t1", sensor_ma=12.0)
        result = validate_sensor_reading(t)
        assert result.sensor_fault is False

    def test_validate_sensor_low_fault(self):
        """Below 3.5 mA sets sensor_fault True."""
        t = FuelTelemetry(node_id="n1", site_id="s1", tank_id="t1", sensor_ma=3.0)
        result = validate_sensor_reading(t)
        assert result.sensor_fault is True

    def test_validate_sensor_high_fault(self):
        """Above 21.0 mA sets sensor_fault True."""
        t = FuelTelemetry(node_id="n1", site_id="s1", tank_id="t1", sensor_ma=22.0)
        result = validate_sensor_reading(t)
        assert result.sensor_fault is True

    def test_validate_sensor_boundary_low(self):
        """At 3.5 mA (boundary), sensor_fault remains False."""
        t = FuelTelemetry(node_id="n1", site_id="s1", tank_id="t1", sensor_ma=3.5)
        result = validate_sensor_reading(t)
        assert result.sensor_fault is False

    def test_validate_sensor_boundary_high(self):
        """At 21.0 mA (boundary), sensor_fault remains False."""
        t = FuelTelemetry(node_id="n1", site_id="s1", tank_id="t1", sensor_ma=21.0)
        result = validate_sensor_reading(t)
        assert result.sensor_fault is False


# ===========================================================================
# 3. Fuel store tests
# ===========================================================================


class TestFuelStore:
    """Tests for FuelStore configuration and persistence."""

    def test_fuel_store_loads_tanks(self):
        """get_fuel_store() loads tank configs from seed JSON."""
        from app.services.fuel_store import FuelStore

        store = FuelStore()
        tanks = store.get_all_tanks()
        assert len(tanks) >= 1  # At least the seed tank

    def test_fuel_store_get_tank_config(self):
        """get_tank_config returns correct config for known tank."""
        from app.services.fuel_store import FuelStore

        store = FuelStore()
        config = store.get_tank_config("S002-TANK-EXT-001")
        assert config is not None
        assert isinstance(config, FuelTankConfig)
        assert config.site_id == "site-002"

    def test_fuel_store_get_tank_config_missing(self):
        """get_tank_config returns None for unknown tank."""
        from app.services.fuel_store import FuelStore

        store = FuelStore()
        config = store.get_tank_config("NONEXISTENT-TANK")
        assert config is None

    def test_fuel_store_get_all_tanks_filtered(self):
        """get_all_tanks(site_id=) filters by site."""
        from app.services.fuel_store import FuelStore

        store = FuelStore()
        tanks = store.get_all_tanks(site_id="site-002")
        assert all(t.site_id == "site-002" for t in tanks)

    @pytest.mark.asyncio
    async def test_fuel_store_telemetry_json_fallback(self, tmp_path):
        """store_telemetry writes to JSON when Supabase/Redis unavailable."""
        from app.services import fuel_store as fs_module

        # Point data dir to tmp
        orig_data_dir = fs_module._DATA_DIR
        orig_telemetry_file = fs_module._TELEMETRY_FILE
        fs_module._DATA_DIR = tmp_path
        fs_module._TELEMETRY_FILE = tmp_path / "telemetry.json"

        try:
            store = fs_module.FuelStore.__new__(fs_module.FuelStore)
            store._tanks = {}

            telemetry = FuelTelemetry(
                node_id="n1",
                site_id="s1",
                tank_id="t1",
                fuel_level_pct=55.0,
                sensor_ma=12.0,
            )
            await store.store_telemetry(telemetry)

            # Check JSON file was written
            assert fs_module._TELEMETRY_FILE.exists()
            content = fs_module._TELEMETRY_FILE.read_text().strip()
            record = json.loads(content)
            assert record["tank_id"] == "t1"
            assert record["fuel_level_pct"] == 55.0
        finally:
            fs_module._DATA_DIR = orig_data_dir
            fs_module._TELEMETRY_FILE = orig_telemetry_file


# ===========================================================================
# 4. Event importance mapping tests
# ===========================================================================


class TestEventImportanceMapping:
    """Tests for get_event_importance()."""

    def test_theft_alert_critical_importance(self):
        assert get_event_importance("theft_alert") == Importance.CRITICAL

    def test_low_fuel_high_importance(self):
        assert get_event_importance("low_fuel") == Importance.HIGH

    def test_refill_info_importance(self):
        assert get_event_importance("refill_detected") == Importance.INFO

    def test_sensor_fault_medium_importance(self):
        assert get_event_importance("sensor_fault") == Importance.MEDIUM


# ===========================================================================
# 5. Listener lifecycle tests
# ===========================================================================


class TestListenerLifecycle:
    """Tests for FuelMqttListener enable/disable and start behavior."""

    def test_listener_disabled_by_default(self):
        """Listener is disabled when settings have fuel_mqtt_enabled=False."""
        listener = FuelMqttListener()
        assert listener._enabled is False

    @pytest.mark.asyncio
    async def test_listener_start_when_disabled(self):
        """start() returns immediately without creating MQTT client when disabled."""
        listener = FuelMqttListener()
        assert listener._enabled is False
        await listener.start()
        assert listener._client is None


# ===========================================================================
# 6. Message routing tests
# ===========================================================================


class TestMessageRouting:
    """Tests for process_fuel_message topic routing."""

    @pytest.mark.asyncio
    async def test_level_topic_routes_to_handle_level(self):
        """A /level topic routes to _handle_level."""
        listener = FuelMqttListener()
        listener._handle_level = AsyncMock()
        payload = json.dumps(SAMPLE_TELEMETRY).encode()
        await listener.process_fuel_message("sentinel/fuel/node-001/level", payload)
        listener._handle_level.assert_called_once()

    @pytest.mark.asyncio
    async def test_events_topic_routes_to_handle_event(self):
        """A /events topic routes to _handle_event."""
        listener = FuelMqttListener()
        listener._handle_event = AsyncMock()
        payload = json.dumps({"event_type": "theft_alert", "node_id": "n1", "site_id": "s1", "tank_id": "t1"}).encode()
        await listener.process_fuel_message("sentinel/fuel/node-001/events", payload)
        listener._handle_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_topic_routes_to_handle_status(self):
        """A /status topic routes to _handle_status."""
        listener = FuelMqttListener()
        listener._handle_status = AsyncMock()
        payload = json.dumps({"node_id": "n1", "status": "online", "site_id": "s1"}).encode()
        await listener.process_fuel_message("sentinel/fuel/node-001/status", payload)
        listener._handle_status.assert_called_once()
