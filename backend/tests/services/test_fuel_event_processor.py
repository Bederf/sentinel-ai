"""Tests for FuelEventProcessor — 7 detection rules, derived calculations,
generator consumption tracking, and event bus integration (Phase 149-01).

Covers:
- FuelEventType enum (2 tests)
- Derived calculations (4 tests)
- Low fuel detection (3 tests)
- Theft detection (3 tests)
- Refill detection (2 tests)
- Leak detection (2 tests)
- Temp alert (3 tests)
- Sensor fault (2 tests)
- Runtime complete + generator consumption (3 tests)
- Event bus emission (1 test)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.fuel import FuelEventType, FuelTankConfig, FuelTelemetry
from app.services.fuel_event_processor import FuelEventProcessor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_processor():
    """Reset processor singleton between tests."""
    import app.services.fuel_event_processor as mod

    mod._instance = None
    yield
    mod._instance = None


def _make_telemetry(**overrides) -> FuelTelemetry:
    """Create a FuelTelemetry with sensible defaults."""
    defaults = {
        "node_id": "fuel-node-001",
        "site_id": "site-002",
        "tank_id": "S002-TANK-EXT-001",
        "generator_id": "S002-GEN-B1-001",
        "fuel_level_pct": 60.0,
        "fuel_level_litres": 3000.0,
        "fuel_level_mm": 1200,
        "fuel_temp_c": 22.0,
        "consumption_rate_lph": 40.0,
        "generator_running": False,
        "sensor_fault": False,
        "sensor_ma": 12.0,
        "ts": 1709683200,
    }
    defaults.update(overrides)
    return FuelTelemetry(**defaults)


def _make_config(**overrides) -> FuelTankConfig:
    """Create a FuelTankConfig with sensible defaults."""
    defaults = {
        "tank_id": "S002-TANK-EXT-001",
        "site_id": "site-002",
        "generator_id": "S002-GEN-B1-001",
        "capacity_litres": 5000,
        "tank_height_mm": 2000,
        "low_alert_pct_1": 30.0,
        "low_alert_pct_2": 15.0,
        "theft_rate_threshold_lpm": 2.0,
        "consumption_spec_lph": 45.0,
    }
    defaults.update(overrides)
    return FuelTankConfig(**defaults)


# ===========================================================================
# TestFuelEventType
# ===========================================================================


class TestFuelEventType:
    """FuelEventType enum tests."""

    def test_enum_has_7_values(self):
        assert len(list(FuelEventType)) == 7

    def test_string_conversion(self):
        assert FuelEventType.THEFT_ALERT.value == "theft_alert"
        assert FuelEventType.LOW_FUEL.value == "low_fuel"
        assert FuelEventType.REFILL_DETECTED == "refill_detected"


# ===========================================================================
# TestDerivedCalculations
# ===========================================================================


class TestDerivedCalculations:
    """Derived field computation tests."""

    @pytest.mark.asyncio
    async def test_days_to_empty_normal(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_level_litres=2400.0, consumption_rate_lph=40.0)
        config = _make_config()
        await processor.process_telemetry(t, config)
        # 2400 / 40 / 24 = 2.5 days
        assert t.days_to_empty == pytest.approx(2.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_days_to_empty_zero_rate(self):
        """Zero consumption rate should not cause ZeroDivisionError."""
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_level_litres=2400.0, consumption_rate_lph=0)
        config = _make_config()
        await processor.process_telemetry(t, config)
        # Uses safe_rate=0.01 -> 2400/0.01/24 = 10000 days
        assert t.days_to_empty == pytest.approx(10000.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_runtime_remaining_hrs(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_level_litres=200.0, consumption_rate_lph=50.0)
        config = _make_config()
        await processor.process_telemetry(t, config)
        # 200 / 50 = 4.0 hours
        assert t.runtime_remaining_hrs == pytest.approx(4.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_consumption_anomaly_detected(self):
        processor = FuelEventProcessor()
        # spec=45 lph, actual=60 lph -> deviation=33% > 20% threshold
        t = _make_telemetry(consumption_rate_lph=60.0)
        config = _make_config(consumption_spec_lph=45.0)
        await processor.process_telemetry(t, config)
        assert t.consumption_anomaly is True

    @pytest.mark.asyncio
    async def test_consumption_anomaly_within_threshold(self):
        processor = FuelEventProcessor()
        # spec=45 lph, actual=48 lph -> deviation=6.7% < 20% threshold
        t = _make_telemetry(consumption_rate_lph=48.0)
        config = _make_config(consumption_spec_lph=45.0)
        await processor.process_telemetry(t, config)
        assert t.consumption_anomaly is False


# ===========================================================================
# TestLowFuelDetection
# ===========================================================================


class TestLowFuelDetection:
    """Low fuel event detection."""

    @pytest.mark.asyncio
    async def test_below_pct_2_critical(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_level_pct=10.0)
        config = _make_config(low_alert_pct_1=30.0, low_alert_pct_2=15.0)
        events = await processor.process_telemetry(t, config)
        low = [e for e in events if e.event_type == FuelEventType.LOW_FUEL]
        assert len(low) == 1
        assert low[0].payload["severity"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_below_pct_1_high(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_level_pct=25.0)
        config = _make_config(low_alert_pct_1=30.0, low_alert_pct_2=15.0)
        events = await processor.process_telemetry(t, config)
        low = [e for e in events if e.event_type == FuelEventType.LOW_FUEL]
        assert len(low) == 1
        assert low[0].payload["severity"] == "HIGH"

    @pytest.mark.asyncio
    async def test_above_pct_1_no_event(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_level_pct=50.0)
        config = _make_config(low_alert_pct_1=30.0, low_alert_pct_2=15.0)
        events = await processor.process_telemetry(t, config)
        low = [e for e in events if e.event_type == FuelEventType.LOW_FUEL]
        assert len(low) == 0


# ===========================================================================
# TestTheftDetection
# ===========================================================================


class TestTheftDetection:
    """Theft detection rule tests."""

    @pytest.mark.asyncio
    async def test_rapid_loss_gen_off_theft(self):
        """Rapid fuel loss with generator off -> theft_alert."""
        processor = FuelEventProcessor()
        config = _make_config(theft_rate_threshold_lpm=2.0)
        # Previous reading: 3000L at ts=0
        prev = _make_telemetry(fuel_level_litres=3000.0, ts=1000, generator_running=False)
        await processor.process_telemetry(prev, config)
        # Current: 2700L at ts=1060 (60s later) -> loss=300L/min=5.0 lpm > 2.0
        curr = _make_telemetry(fuel_level_litres=2700.0, ts=1060, generator_running=False)
        events = await processor.process_telemetry(curr, config)
        theft = [e for e in events if e.event_type == FuelEventType.THEFT_ALERT]
        assert len(theft) == 1
        assert theft[0].payload["loss_rate_lpm"] > 2.0

    @pytest.mark.asyncio
    async def test_rapid_loss_gen_on_no_theft(self):
        """Rapid fuel loss with generator ON -> consumption, not theft."""
        processor = FuelEventProcessor()
        config = _make_config(theft_rate_threshold_lpm=2.0)
        prev = _make_telemetry(fuel_level_litres=3000.0, ts=1000, generator_running=True)
        await processor.process_telemetry(prev, config)
        curr = _make_telemetry(fuel_level_litres=2700.0, ts=1060, generator_running=True)
        events = await processor.process_telemetry(curr, config)
        theft = [e for e in events if e.event_type == FuelEventType.THEFT_ALERT]
        assert len(theft) == 0

    @pytest.mark.asyncio
    async def test_slow_loss_no_theft(self):
        """Slow fuel loss below threshold -> no theft event."""
        processor = FuelEventProcessor()
        config = _make_config(theft_rate_threshold_lpm=2.0)
        prev = _make_telemetry(fuel_level_litres=3000.0, ts=1000, generator_running=False)
        await processor.process_telemetry(prev, config)
        # 5L lost over 600s = 0.5 lpm (below 2.0 lpm threshold)
        curr = _make_telemetry(fuel_level_litres=2995.0, ts=1600, generator_running=False)
        events = await processor.process_telemetry(curr, config)
        theft = [e for e in events if e.event_type == FuelEventType.THEFT_ALERT]
        assert len(theft) == 0


# ===========================================================================
# TestRefillDetection
# ===========================================================================


class TestRefillDetection:
    """Refill detection rule tests."""

    @pytest.mark.asyncio
    async def test_level_jump_refill(self):
        """Large level jump -> refill_detected."""
        processor = FuelEventProcessor()
        config = _make_config()
        prev = _make_telemetry(fuel_level_pct=40.0, ts=1000)
        await processor.process_telemetry(prev, config)
        curr = _make_telemetry(fuel_level_pct=85.0, ts=1060)
        events = await processor.process_telemetry(curr, config)
        refill = [e for e in events if e.event_type == FuelEventType.REFILL_DETECTED]
        assert len(refill) == 1
        assert refill[0].payload["jump_pct"] == pytest.approx(45.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_small_fluctuation_no_refill(self):
        """Small fluctuation -> no refill event."""
        processor = FuelEventProcessor()
        config = _make_config()
        prev = _make_telemetry(fuel_level_pct=50.0, ts=1000)
        await processor.process_telemetry(prev, config)
        curr = _make_telemetry(fuel_level_pct=52.0, ts=1060)
        events = await processor.process_telemetry(curr, config)
        refill = [e for e in events if e.event_type == FuelEventType.REFILL_DETECTED]
        assert len(refill) == 0


# ===========================================================================
# TestLeakDetection
# ===========================================================================


class TestLeakDetection:
    """Leak detection rule tests."""

    @pytest.mark.asyncio
    async def test_sustained_loss_leak(self):
        """Sustained slow loss for >30 minutes without generator -> leak_detected."""
        processor = FuelEventProcessor()
        config = _make_config()
        base_ts = 10000
        # First reading
        t1 = _make_telemetry(fuel_level_litres=3000.0, ts=base_ts, generator_running=False)
        await processor.process_telemetry(t1, config)
        # Second reading 5 min later, slight loss
        t2 = _make_telemetry(fuel_level_litres=2998.0, ts=base_ts + 300, generator_running=False)
        await processor.process_telemetry(t2, config)
        # Third reading at 31 minutes, continued loss -> leak
        t3 = _make_telemetry(fuel_level_litres=2995.0, ts=base_ts + 1860, generator_running=False)
        events = await processor.process_telemetry(t3, config)
        leak = [e for e in events if e.event_type == FuelEventType.LEAK_DETECTED]
        assert len(leak) == 1

    @pytest.mark.asyncio
    async def test_no_loss_no_leak(self):
        """No fuel loss -> no leak event."""
        processor = FuelEventProcessor()
        config = _make_config()
        prev = _make_telemetry(fuel_level_litres=3000.0, ts=1000, generator_running=False)
        await processor.process_telemetry(prev, config)
        # Level stays same
        curr = _make_telemetry(fuel_level_litres=3000.0, ts=3000, generator_running=False)
        events = await processor.process_telemetry(curr, config)
        leak = [e for e in events if e.event_type == FuelEventType.LEAK_DETECTED]
        assert len(leak) == 0


# ===========================================================================
# TestTempAlert
# ===========================================================================


class TestTempAlert:
    """Temperature alert tests."""

    @pytest.mark.asyncio
    async def test_below_min_temp(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_temp_c=3.0)
        config = _make_config()
        events = await processor.process_telemetry(t, config)
        temp = [e for e in events if e.event_type == FuelEventType.TEMP_ALERT]
        assert len(temp) == 1
        assert temp[0].payload["severity"] == "HIGH"

    @pytest.mark.asyncio
    async def test_above_max_temp(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_temp_c=45.0)
        config = _make_config()
        events = await processor.process_telemetry(t, config)
        temp = [e for e in events if e.event_type == FuelEventType.TEMP_ALERT]
        assert len(temp) == 1

    @pytest.mark.asyncio
    async def test_temp_in_range_no_event(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(fuel_temp_c=22.0)
        config = _make_config()
        events = await processor.process_telemetry(t, config)
        temp = [e for e in events if e.event_type == FuelEventType.TEMP_ALERT]
        assert len(temp) == 0


# ===========================================================================
# TestSensorFault
# ===========================================================================


class TestSensorFault:
    """Sensor fault detection tests."""

    @pytest.mark.asyncio
    async def test_sensor_fault_true(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(sensor_fault=True, sensor_ma=2.5)
        config = _make_config()
        events = await processor.process_telemetry(t, config)
        fault = [e for e in events if e.event_type == FuelEventType.SENSOR_FAULT]
        assert len(fault) == 1
        assert fault[0].payload["sensor_ma"] == 2.5

    @pytest.mark.asyncio
    async def test_sensor_fault_false(self):
        processor = FuelEventProcessor()
        t = _make_telemetry(sensor_fault=False, sensor_ma=12.0)
        config = _make_config()
        events = await processor.process_telemetry(t, config)
        fault = [e for e in events if e.event_type == FuelEventType.SENSOR_FAULT]
        assert len(fault) == 0


# ===========================================================================
# TestRuntimeComplete
# ===========================================================================


class TestRuntimeComplete:
    """Generator runtime complete and consumption tracking."""

    @pytest.mark.asyncio
    async def test_gen_true_to_false_runtime_complete(self):
        """Generator running True->False -> runtime_complete event."""
        processor = FuelEventProcessor()
        config = _make_config(consumption_spec_lph=45.0)
        # Generator running with 3000L
        prev = _make_telemetry(generator_running=True, fuel_level_litres=3000.0, ts=10000)
        await processor.process_telemetry(prev, config)
        # Generator stops 1 hour later with 2955L
        curr = _make_telemetry(generator_running=False, fuel_level_litres=2955.0, ts=13600)
        events = await processor.process_telemetry(curr, config)
        rt = [e for e in events if e.event_type == FuelEventType.RUNTIME_COMPLETE]
        assert len(rt) == 1
        assert rt[0].payload["fuel_burned_litres"] == pytest.approx(45.0, abs=0.1)
        assert rt[0].payload["runtime_hours"] == pytest.approx(1.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_gen_already_off_no_event(self):
        """Generator was already off -> no runtime_complete event."""
        processor = FuelEventProcessor()
        config = _make_config()
        prev = _make_telemetry(generator_running=False, ts=10000)
        await processor.process_telemetry(prev, config)
        curr = _make_telemetry(generator_running=False, ts=13600)
        events = await processor.process_telemetry(curr, config)
        rt = [e for e in events if e.event_type == FuelEventType.RUNTIME_COMPLETE]
        assert len(rt) == 0


# ===========================================================================
# TestGeneratorConsumption
# ===========================================================================


class TestGeneratorConsumption:
    """Generator consumption anomaly detection during runtime."""

    @pytest.mark.asyncio
    async def test_consumption_matches_spec_no_anomaly(self):
        """Consumption matching spec -> no anomaly in runtime_complete."""
        processor = FuelEventProcessor()
        config = _make_config(consumption_spec_lph=45.0)
        # 1 hour run: burned 45L (matches 45 lph spec exactly)
        prev = _make_telemetry(generator_running=True, fuel_level_litres=3000.0, ts=10000)
        await processor.process_telemetry(prev, config)
        curr = _make_telemetry(generator_running=False, fuel_level_litres=2955.0, ts=13600)
        events = await processor.process_telemetry(curr, config)
        rt = [e for e in events if e.event_type == FuelEventType.RUNTIME_COMPLETE]
        assert len(rt) == 1
        assert rt[0].payload["consumption_anomaly"] is False

    @pytest.mark.asyncio
    async def test_consumption_exceeds_spec_anomaly(self):
        """Consumption > 20% above spec -> anomaly flagged."""
        processor = FuelEventProcessor()
        config = _make_config(consumption_spec_lph=45.0)
        # 1 hour run: burned 60L (33% above 45 lph spec)
        prev = _make_telemetry(generator_running=True, fuel_level_litres=3000.0, ts=10000)
        await processor.process_telemetry(prev, config)
        curr = _make_telemetry(generator_running=False, fuel_level_litres=2940.0, ts=13600)
        events = await processor.process_telemetry(curr, config)
        rt = [e for e in events if e.event_type == FuelEventType.RUNTIME_COMPLETE]
        assert len(rt) == 1
        assert rt[0].payload["consumption_anomaly"] is True


# ===========================================================================
# TestEventBusIntegration
# ===========================================================================


class TestEventBusIntegration:
    """Verify events are emitted to the event bus."""

    @pytest.mark.asyncio
    async def test_events_emitted_to_bus(self):
        """Detected events should be emitted via event bus."""
        processor = FuelEventProcessor()
        config = _make_config()
        t = _make_telemetry(fuel_level_pct=10.0)  # Should trigger low_fuel
        with patch("app.services.event_bus.get_event_bus") as mock_get_bus:
            mock_bus = AsyncMock()
            mock_get_bus.return_value = mock_bus
            events = await processor.process_telemetry(t, config)

            assert len(events) >= 1
            # event bus emit should have been called for each detected event
            assert mock_bus.emit.call_count == len(events)
            # Check the first emitted SentinelEvent has correct source
            call_args = mock_bus.emit.call_args_list[0]
            sentinel_event = call_args[0][0]
            assert sentinel_event.source == "fuel_event_processor"
            assert sentinel_event.event_type.startswith("fuel.")
