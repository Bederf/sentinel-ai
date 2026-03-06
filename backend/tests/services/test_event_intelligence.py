"""Tests for EventIntelligenceService — Operational Event Intelligence layer.

Verifies detection rules, duration tracking, trend analysis, deduplication,
event bus emission, and query methods.

Phase 145: Operational Event Intelligence.
"""

import asyncio
from datetime import datetime, timezone, timedelta

import pytest

from app.models.operational_event import (
    EventSeverity,
    OperationalEvent,
    OperationalEventType,
    _generate_event_id,
)
from app.services.event_bus import Importance, SentinelEvent, reset_event_bus
from app.services.event_intelligence_service import (
    EventIntelligenceService,
    reset_event_intelligence_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons before each test."""
    reset_event_intelligence_service()
    reset_event_bus()
    yield
    reset_event_intelligence_service()
    reset_event_bus()


@pytest.fixture
def service():
    """Create a fresh EventIntelligenceService."""
    return EventIntelligenceService()


@pytest.fixture
def hvac_telemetry_normal():
    """Normal HVAC telemetry — should not trigger any events."""
    return {
        "current_temp": 22.0,
        "setpoint": 22.0,
        "zone_temp": 22.0,
        "power_kw": 5.0,
        "status": "running",
    }


@pytest.fixture
def hvac_telemetry_hot():
    """HVAC telemetry with temperature 5C above setpoint."""
    return {
        "current_temp": 27.0,
        "setpoint": 22.0,
        "zone_temp": 27.0,
        "power_kw": 5.0,
        "status": "running",
    }


# ---------------------------------------------------------------------------
# Test: Temperature deviation detection
# ---------------------------------------------------------------------------


class TestTemperatureDeviation:
    @pytest.mark.asyncio
    async def test_temperature_deviation_detected(self, service):
        """Equipment with temp 5C above setpoint triggers event."""
        telemetry = {"current_temp": 27.0, "setpoint": 22.0}
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        assert len(events) >= 1
        temp_events = [e for e in events if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        assert len(temp_events) == 1

        evt = temp_events[0]
        assert evt.severity in (EventSeverity.WARNING, EventSeverity.HIGH)
        assert evt.actual_value == 27.0
        assert "27.0" in evt.description
        assert "22.0" in evt.description
        assert evt.equipment_id == "S002-FCU-101"
        assert evt.site_id == "site-002"

    @pytest.mark.asyncio
    async def test_high_severity_for_large_deviation(self, service):
        """Deviation > 2x threshold gets HIGH severity."""
        telemetry = {"current_temp": 30.0, "setpoint": 22.0}  # 8C deviation > 4C (2x default 2)
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        temp_events = [e for e in events if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        assert len(temp_events) == 1
        assert temp_events[0].severity == EventSeverity.HIGH

    @pytest.mark.asyncio
    async def test_no_event_for_within_threshold(self, service):
        """Temperature within threshold produces no deviation event."""
        telemetry = {"current_temp": 23.0, "setpoint": 22.0}  # 1C < 2C threshold
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        temp_events = [e for e in events if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        assert len(temp_events) == 0


# ---------------------------------------------------------------------------
# Test: No event when normal
# ---------------------------------------------------------------------------


class TestNoEventWhenNormal:
    @pytest.mark.asyncio
    async def test_no_event_when_normal(self, service, hvac_telemetry_normal):
        """Normal telemetry produces no events."""
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", hvac_telemetry_normal)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_no_event_non_hvac_for_hvac_rules(self, service):
        """Non-HVAC equipment does not trigger HVAC-specific rules."""
        telemetry = {"current_temp": 27.0, "setpoint": 22.0}
        events = await service.evaluate_equipment("S002-GEN-B1-001", "site-002", telemetry)

        # GEN type should not match FCU/AHU/VAV rules for temp deviation
        temp_events = [e for e in events if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        assert len(temp_events) == 0


# ---------------------------------------------------------------------------
# Test: Energy spike detection
# ---------------------------------------------------------------------------


class TestEnergySpike:
    @pytest.mark.asyncio
    async def test_energy_spike_detection(self, service):
        """Power reading 2x average triggers event."""
        # Build up history first (need >= 3 readings)
        for power in [5.0, 5.0, 5.0, 5.0]:
            await service.evaluate_equipment("S002-AHU-101", "site-002", {"power_kw": power})

        # Now spike to 15kW (3x average of ~5)
        events = await service.evaluate_equipment("S002-AHU-101", "site-002", {"power_kw": 15.0})

        spike_events = [e for e in events if e.event_type == OperationalEventType.ENERGY_SPIKE]
        assert len(spike_events) == 1
        assert spike_events[0].actual_value == 15.0
        assert "rolling average" in spike_events[0].description

    @pytest.mark.asyncio
    async def test_no_spike_insufficient_history(self, service):
        """No spike event if insufficient history (< 3 readings)."""
        events = await service.evaluate_equipment("S002-AHU-101", "site-002", {"power_kw": 100.0})
        spike_events = [e for e in events if e.event_type == OperationalEventType.ENERGY_SPIKE]
        assert len(spike_events) == 0


# ---------------------------------------------------------------------------
# Test: Sensor failure detection
# ---------------------------------------------------------------------------


class TestSensorFailure:
    @pytest.mark.asyncio
    async def test_sensor_failure_none_value(self, service):
        """None values in telemetry trigger sensor failure event."""
        telemetry = {"supply_temp": None, "return_temp": 18.0}
        events = await service.evaluate_equipment("S002-AHU-101", "site-002", telemetry)

        sensor_events = [e for e in events if e.event_type == OperationalEventType.SENSOR_FAILURE]
        assert len(sensor_events) == 1
        assert "supply_temp" in sensor_events[0].description

    @pytest.mark.asyncio
    async def test_sensor_failure_nan_value(self, service):
        """NaN values trigger sensor failure event."""
        telemetry = {"supply_temp": float("nan"), "return_temp": 18.0}
        events = await service.evaluate_equipment("S002-AHU-101", "site-002", telemetry)

        sensor_events = [e for e in events if e.event_type == OperationalEventType.SENSOR_FAILURE]
        assert len(sensor_events) == 1

    @pytest.mark.asyncio
    async def test_sensor_failure_stale_reading(self, service):
        """Stale timestamp (> 15 min old) triggers sensor failure."""
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        telemetry = {"supply_temp": 20.0, "last_reading_timestamp": old_time}
        events = await service.evaluate_equipment("S002-AHU-101", "site-002", telemetry)

        sensor_events = [e for e in events if e.event_type == OperationalEventType.SENSOR_FAILURE]
        assert len(sensor_events) == 1
        assert "stale" in sensor_events[0].signals[0].get("reason", "")

    @pytest.mark.asyncio
    async def test_no_sensor_failure_when_healthy(self, service):
        """Valid telemetry values produce no sensor failure."""
        telemetry = {"supply_temp": 20.0, "return_temp": 18.0}
        events = await service.evaluate_equipment("S002-AHU-101", "site-002", telemetry)

        sensor_events = [e for e in events if e.event_type == OperationalEventType.SENSOR_FAILURE]
        assert len(sensor_events) == 0


# ---------------------------------------------------------------------------
# Test: Comfort violation detection
# ---------------------------------------------------------------------------


class TestComfortViolation:
    @pytest.mark.asyncio
    async def test_comfort_violation_too_hot(self, service):
        """Zone temp above comfort band triggers event."""
        telemetry = {"zone_temp": 28.0}
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        comfort_events = [e for e in events if e.event_type == OperationalEventType.COMFORT_VIOLATION]
        assert len(comfort_events) == 1
        assert "above" in comfort_events[0].description
        assert comfort_events[0].actual_value == 28.0

    @pytest.mark.asyncio
    async def test_comfort_violation_too_cold(self, service):
        """Zone temp below comfort band triggers event."""
        telemetry = {"zone_temp": 16.0}
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        comfort_events = [e for e in events if e.event_type == OperationalEventType.COMFORT_VIOLATION]
        assert len(comfort_events) == 1
        assert "below" in comfort_events[0].description

    @pytest.mark.asyncio
    async def test_no_comfort_violation_in_band(self, service):
        """Zone temp within comfort band produces no event."""
        telemetry = {"zone_temp": 22.0}
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        comfort_events = [e for e in events if e.event_type == OperationalEventType.COMFORT_VIOLATION]
        assert len(comfort_events) == 0


# ---------------------------------------------------------------------------
# Test: ML anomaly integration
# ---------------------------------------------------------------------------


class TestMLAnomaly:
    @pytest.mark.asyncio
    async def test_ml_anomaly_high_score(self, service):
        """High anomaly score triggers pattern_anomaly event."""
        telemetry = {"anomaly_score": 0.85, "supply_temp": 20.0}
        events = await service.evaluate_equipment("S002-CHILLER-B1-001", "site-002", telemetry)

        anomaly_events = [e for e in events if e.event_type == OperationalEventType.PATTERN_ANOMALY]
        assert len(anomaly_events) == 1
        assert anomaly_events[0].severity == EventSeverity.CRITICAL
        assert anomaly_events[0].actual_value == 0.85

    @pytest.mark.asyncio
    async def test_ml_anomaly_moderate_score(self, service):
        """Moderate anomaly score (0.5 < score <= 0.8) triggers HIGH event."""
        telemetry = {"anomaly_score": 0.65}
        events = await service.evaluate_equipment("S002-CHILLER-B1-001", "site-002", telemetry)

        anomaly_events = [e for e in events if e.event_type == OperationalEventType.PATTERN_ANOMALY]
        assert len(anomaly_events) == 1
        assert anomaly_events[0].severity == EventSeverity.HIGH

    @pytest.mark.asyncio
    async def test_ml_anomaly_below_threshold(self, service):
        """Anomaly score below threshold produces no event."""
        telemetry = {"anomaly_score": 0.3}
        events = await service.evaluate_equipment("S002-CHILLER-B1-001", "site-002", telemetry)

        anomaly_events = [e for e in events if e.event_type == OperationalEventType.PATTERN_ANOMALY]
        assert len(anomaly_events) == 0


# ---------------------------------------------------------------------------
# Test: Event duration tracking
# ---------------------------------------------------------------------------


class TestDurationTracking:
    @pytest.mark.asyncio
    async def test_event_duration_tracking(self, service):
        """Repeated detection updates duration_minutes."""
        telemetry = {"current_temp": 28.0, "setpoint": 22.0}

        # First detection — no duration
        events1 = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)
        temp_events1 = [e for e in events1 if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        assert len(temp_events1) == 1
        assert temp_events1[0].duration_minutes is None

        # Second detection — should have duration >= 0
        events2 = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)
        temp_events2 = [e for e in events2 if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        assert len(temp_events2) == 1
        assert temp_events2[0].duration_minutes is not None
        assert temp_events2[0].duration_minutes >= 0.0

    @pytest.mark.asyncio
    async def test_correlation_id_set_on_repeat(self, service):
        """Repeated detection sets correlation_id to first event."""
        telemetry = {"current_temp": 28.0, "setpoint": 22.0}

        events1 = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)
        first_id = events1[0].event_id

        events2 = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)
        assert events2[0].correlation_id == first_id


# ---------------------------------------------------------------------------
# Test: Trend detection
# ---------------------------------------------------------------------------


class TestTrendDetection:
    @pytest.mark.asyncio
    async def test_rising_trend(self, service):
        """Rising temperature values produce 'rising' trend."""
        for temp in [24.0, 25.0, 26.0, 27.0, 28.0]:
            events = await service.evaluate_equipment(
                "S002-FCU-101",
                "site-002",
                {"current_temp": temp, "setpoint": 22.0},
            )

        # The last evaluation should have rising trend
        temp_events = [e for e in events if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        if temp_events:
            assert temp_events[0].trend == "rising"

    @pytest.mark.asyncio
    async def test_stable_trend(self, service):
        """Fluctuating values produce 'stable' trend."""
        for temp in [27.0, 28.0, 27.0, 28.0, 27.0]:
            events = await service.evaluate_equipment(
                "S002-FCU-101",
                "site-002",
                {"current_temp": temp, "setpoint": 22.0},
            )

        temp_events = [e for e in events if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        if temp_events:
            assert temp_events[0].trend == "stable"


# ---------------------------------------------------------------------------
# Test: OperationalEvent -> SentinelEvent conversion
# ---------------------------------------------------------------------------


class TestSentinelEventConversion:
    def test_event_to_sentinel_event_conversion(self):
        """OperationalEvent converts to SentinelEvent correctly."""
        op_event = OperationalEvent(
            event_id="EVT-20260305-abcd1234",
            event_type=OperationalEventType.TEMPERATURE_DEVIATION,
            equipment_id="S002-FCU-101",
            site_id="site-002",
            severity=EventSeverity.HIGH,
            timestamp=datetime.now(timezone.utc),
            signals=[{"point": "current_temp", "value": 28.0}],
            description="S002-FCU-101: temperature deviation",
            actual_value=28.0,
            threshold_value=2.0,
        )

        sentinel = op_event.to_sentinel_event()

        assert isinstance(sentinel, SentinelEvent)
        assert sentinel.event_type == "operational.temperature_deviation"
        assert sentinel.source == "event_intelligence_service"
        assert sentinel.importance == Importance.HIGH
        assert sentinel.site_id == "site-002"
        assert sentinel.equipment_id == "S002-FCU-101"
        assert sentinel.payload["operational_event_id"] == "EVT-20260305-abcd1234"
        assert sentinel.payload["actual_value"] == 28.0

    def test_severity_mapping(self):
        """All severity levels map to correct Importance."""
        mapping = {
            EventSeverity.INFO: Importance.INFO,
            EventSeverity.WARNING: Importance.MEDIUM,
            EventSeverity.HIGH: Importance.HIGH,
            EventSeverity.CRITICAL: Importance.CRITICAL,
        }

        for severity, expected_importance in mapping.items():
            op_event = OperationalEvent(
                event_id=_generate_event_id(),
                event_type=OperationalEventType.TEMPERATURE_DEVIATION,
                equipment_id="S002-FCU-101",
                site_id="site-002",
                severity=severity,
                timestamp=datetime.now(timezone.utc),
                signals=[],
                description="test",
            )
            sentinel = op_event.to_sentinel_event()
            assert sentinel.importance == expected_importance, (
                f"EventSeverity.{severity.name} should map to Importance.{expected_importance.name}"
            )


# ---------------------------------------------------------------------------
# Test: Active conditions cleared on resolution
# ---------------------------------------------------------------------------


class TestConditionResolution:
    @pytest.mark.asyncio
    async def test_active_conditions_cleared_on_resolution(self, service):
        """When condition resolves, event is cleared from active conditions."""
        # Trigger condition
        telemetry_hot = {"current_temp": 28.0, "setpoint": 22.0}
        await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry_hot)

        active1 = await service.get_active_events(equipment_id="S002-FCU-101")
        assert len(active1) > 0

        # Resolve condition (temperature back to normal)
        telemetry_normal = {"current_temp": 22.0, "setpoint": 22.0}
        await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry_normal)

        active2 = await service.get_active_events(equipment_id="S002-FCU-101")
        temp_active = [e for e in active2 if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        assert len(temp_active) == 0


# ---------------------------------------------------------------------------
# Test: process_site emits to event bus
# ---------------------------------------------------------------------------


class TestProcessSite:
    @pytest.mark.asyncio
    async def test_process_site_emits_to_bus(self, service):
        """Verify events are emitted to EventBus when processing a site."""
        from app.services.event_bus import get_event_bus

        bus = get_event_bus()
        captured_events = []

        async def handler(event: SentinelEvent):
            captured_events.append(event)

        bus.subscribe("operational.*", handler)

        equipment_telemetry = {
            "S002-FCU-101": {"current_temp": 28.0, "setpoint": 22.0, "zone_temp": 28.0},
        }

        events = await service.process_site("site-002", equipment_telemetry=equipment_telemetry)
        assert len(events) > 0

        # Give the event loop time to process
        await asyncio.sleep(0.05)

        # At least one event should have been emitted to the bus
        # (dedup middleware may suppress some, but the first should go through)
        assert len(captured_events) >= 1
        assert captured_events[0].event_type.startswith("operational.")


# ---------------------------------------------------------------------------
# Test: Event summary
# ---------------------------------------------------------------------------


class TestEventSummary:
    @pytest.mark.asyncio
    async def test_event_summary(self, service):
        """Summary returns correct counts by type and severity."""
        equipment_telemetry = {
            "S002-FCU-101": {"current_temp": 28.0, "setpoint": 22.0, "zone_temp": 28.0},
            "S002-FCU-102": {"current_temp": 30.0, "setpoint": 22.0, "zone_temp": 30.0},
        }

        await service.process_site("site-002", equipment_telemetry=equipment_telemetry)

        summary = await service.get_event_summary("site-002")
        assert summary["site_id"] == "site-002"
        assert summary["active_count"] >= 2
        assert "temperature_deviation" in summary["by_type"] or "comfort_violation" in summary["by_type"]


# ---------------------------------------------------------------------------
# Test: Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_same_condition_no_duplicate_active(self, service):
        """Same condition does not create duplicate active events."""
        telemetry = {"current_temp": 28.0, "setpoint": 22.0}

        await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)
        await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)
        await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        active = await service.get_active_events(equipment_id="S002-FCU-101")
        temp_active = [e for e in active if e.event_type == OperationalEventType.TEMPERATURE_DEVIATION]
        # Only one active condition, even after 3 evaluations
        assert len(temp_active) == 1


# ---------------------------------------------------------------------------
# Test: Setpoint drift
# ---------------------------------------------------------------------------


class TestSetpointDrift:
    @pytest.mark.asyncio
    async def test_setpoint_drift_detected(self, service):
        """Setpoint drift from baseline triggers event."""
        telemetry = {"setpoint": 25.0, "baseline_setpoint": 22.0}
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        drift_events = [e for e in events if e.event_type == OperationalEventType.SETPOINT_DRIFT]
        assert len(drift_events) == 1
        assert "drifted" in drift_events[0].description

    @pytest.mark.asyncio
    async def test_no_drift_within_threshold(self, service):
        """Small setpoint change within threshold produces no event."""
        telemetry = {"setpoint": 22.5, "baseline_setpoint": 22.0}
        events = await service.evaluate_equipment("S002-FCU-101", "site-002", telemetry)

        drift_events = [e for e in events if e.event_type == OperationalEventType.SETPOINT_DRIFT]
        assert len(drift_events) == 0


# ---------------------------------------------------------------------------
# Test: Threshold breach
# ---------------------------------------------------------------------------


class TestThresholdBreach:
    @pytest.mark.asyncio
    async def test_threshold_breach_above_max(self, service):
        """Value above configured max triggers threshold breach."""
        telemetry = {
            "supply_temp": 18.0,
            "thresholds": {"supply_temp": {"min": 5.0, "max": 15.0}},
        }
        events = await service.evaluate_equipment("S002-CHILLER-B1-001", "site-002", telemetry)

        breach_events = [e for e in events if e.event_type == OperationalEventType.THRESHOLD_BREACH]
        assert len(breach_events) == 1
        assert breach_events[0].signals[0]["breach"] == "above_max"

    @pytest.mark.asyncio
    async def test_threshold_breach_below_min(self, service):
        """Value below configured min triggers threshold breach."""
        telemetry = {
            "supply_temp": 3.0,
            "thresholds": {"supply_temp": {"min": 5.0, "max": 15.0}},
        }
        events = await service.evaluate_equipment("S002-CHILLER-B1-001", "site-002", telemetry)

        breach_events = [e for e in events if e.event_type == OperationalEventType.THRESHOLD_BREACH]
        assert len(breach_events) == 1
        assert breach_events[0].signals[0]["breach"] == "below_min"


# ---------------------------------------------------------------------------
# Test: to_dict serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict(self):
        """OperationalEvent.to_dict() produces valid JSON-serializable dict."""
        now = datetime.now(timezone.utc)
        event = OperationalEvent(
            event_id="EVT-20260305-test1234",
            event_type=OperationalEventType.ENERGY_SPIKE,
            equipment_id="S002-AHU-101",
            site_id="site-002",
            severity=EventSeverity.WARNING,
            timestamp=now,
            signals=[{"point": "power_kw", "value": 15.0}],
            description="test energy spike",
            trend="rising",
            duration_minutes=5.2,
            threshold_value=10.0,
            actual_value=15.0,
        )

        d = event.to_dict()
        assert d["event_id"] == "EVT-20260305-test1234"
        assert d["event_type"] == "energy_spike"
        assert d["severity"] == "warning"
        assert d["timestamp"] == now.isoformat()
        assert d["trend"] == "rising"
        assert d["duration_minutes"] == 5.2
        assert d["actual_value"] == 15.0


# ---------------------------------------------------------------------------
# Test: Event history query
# ---------------------------------------------------------------------------


class TestEventHistory:
    @pytest.mark.asyncio
    async def test_event_history_filters(self, service):
        """Event history respects filters."""
        equipment_telemetry = {
            "S002-FCU-101": {"current_temp": 28.0, "setpoint": 22.0, "zone_temp": 28.0},
            "S002-FCU-102": {"current_temp": 22.0, "setpoint": 22.0, "zone_temp": 22.0},
        }

        await service.process_site("site-002", equipment_telemetry=equipment_telemetry)

        # Filter by equipment
        history = await service.get_event_history(equipment_id="S002-FCU-101")
        assert all(e["equipment_id"] == "S002-FCU-101" for e in history)

        # Filter by site
        history_site = await service.get_event_history(site_id="site-002")
        assert all(e["site_id"] == "site-002" for e in history_site)

    @pytest.mark.asyncio
    async def test_get_event_by_id(self, service):
        """Can look up a specific event by ID."""
        telemetry = {"current_temp": 28.0, "setpoint": 22.0}

        # Use process_site to both detect and store events
        events = await service.process_site(
            "site-002",
            equipment_telemetry={"S002-FCU-101": telemetry},
        )
        assert len(events) > 0

        # Look up by ID from the returned events
        found = await service.get_event_by_id(events[0].event_id)
        assert found is not None
        assert found["equipment_id"] == "S002-FCU-101"

    @pytest.mark.asyncio
    async def test_get_event_by_id_not_found(self, service):
        """Looking up non-existent event returns None."""
        result = await service.get_event_by_id("EVT-nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Test: Equipment type extraction
# ---------------------------------------------------------------------------


class TestEquipmentTypeExtraction:
    def test_zone_format(self):
        assert EventIntelligenceService._extract_equipment_type("S002-FCU-101") == "FCU"

    def test_plant_format(self):
        assert EventIntelligenceService._extract_equipment_type("S002-CHILLER-B1-001") == "CHILLER"

    def test_dali_format(self):
        assert EventIntelligenceService._extract_equipment_type("S002-DALI-201") == "DALI"

    def test_unknown_format(self):
        assert EventIntelligenceService._extract_equipment_type("UNKNOWN") == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test: Event ID generation
# ---------------------------------------------------------------------------


class TestEventIdGeneration:
    def test_generate_event_id_format(self):
        """Generated event IDs match expected format."""
        eid = _generate_event_id()
        assert eid.startswith("EVT-")
        parts = eid.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 14  # YYYYMMDDHHmmss
        assert len(parts[2]) == 8  # short uuid

    def test_generate_event_id_unique(self):
        """Event IDs are unique."""
        ids = {_generate_event_id() for _ in range(100)}
        assert len(ids) == 100
