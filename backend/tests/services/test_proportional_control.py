"""Tests for proportional closed-loop control in LifecycleOrchestrator.

Validates that:
- Ramp rate limiting constrains actuator step changes
- FCU valve position is proportional to zone temperature error
- AHU supply air temp resets based on zone demand
- Pump dP follows affinity laws (dP ~ N^2)
- Multi-hour startup ramps gradually instead of snapping
"""

import pytest

from app.services.building_schedule import BuildingSchedule
from app.services.lifecycle_orchestrator import LifecycleOrchestrator, RAMP_RATES


@pytest.fixture
def orchestrator():
    """Create a fresh LifecycleOrchestrator for testing."""
    return LifecycleOrchestrator(site_id="site-002")


@pytest.fixture
def schedule_occupied():
    """10 AM Wednesday — occupied business hours."""
    bs = BuildingSchedule()
    return bs.get_state(10, day_of_week=2)


@pytest.fixture
def schedule_off():
    """2 AM Wednesday — HVAC off."""
    bs = BuildingSchedule()
    return bs.get_state(2, day_of_week=2)


class TestRampLimit:
    """Ramp rate limiting constrains actuator step changes."""

    def test_large_increase_capped(self, orchestrator):
        """A 0→100 jump should be capped by the ramp rate."""
        # Seed a previous value
        orchestrator._actuator_state["TEST-001"] = {"valve_position": 0.0}
        result = orchestrator._ramp_limit("TEST-001", "valve_position", 100.0, 10)
        assert result <= RAMP_RATES["valve_position"]
        assert result > 0

    def test_large_decrease_capped(self, orchestrator):
        """A 100→0 drop should be capped by the ramp rate."""
        orchestrator._actuator_state["TEST-001"] = {"valve_position": 100.0}
        result = orchestrator._ramp_limit("TEST-001", "valve_position", 0.0, 10)
        assert result >= 100.0 - RAMP_RATES["valve_position"]
        assert result < 100.0

    def test_small_change_passes_through(self, orchestrator):
        """Changes within rate limit should pass unchanged."""
        orchestrator._actuator_state["TEST-001"] = {"valve_position": 50.0}
        result = orchestrator._ramp_limit("TEST-001", "valve_position", 55.0, 10)
        assert result == 55.0

    def test_first_tick_50pct_approach(self, orchestrator):
        """First tick with no history should do 50% approach."""
        result = orchestrator._ramp_limit("NEW-001", "valve_position", 80.0, 6)
        assert result == 40.0  # 50% of 80

    def test_unknown_reading_passes_through(self, orchestrator):
        """Readings not in RAMP_RATES should pass through unchanged."""
        result = orchestrator._ramp_limit("TEST-001", "room_temp", 25.0, 10)
        assert result == 25.0


class TestFCUProportionalControl:
    """FCU valve position responds proportionally to zone temp error."""

    def test_warm_room_opens_valve(self, orchestrator, schedule_occupied):
        """Room above setpoint should open valve proportionally."""
        setpoint = orchestrator.building_schedule.COMFORT_SETPOINT
        # Warm room: 3°C above setpoint
        zone_id = "Zone-201"
        orchestrator.zone_temperatures[zone_id] = setpoint + 3.0
        # Prime actuator state so we don't get 50% startup
        orchestrator._actuator_state["S002-FCU-201"] = {"valve_position": 50.0, "fan_speed": 2.0}

        readings = orchestrator._generate_sensor_readings("S002-FCU-201", "fcu", 100.0, 10, schedule_occupied)
        assert readings["valve_position"] > 50.0, "Warm room should open valve"

    def test_cool_room_closes_valve(self, orchestrator, schedule_occupied):
        """Room below setpoint should close valve to minimum."""
        setpoint = orchestrator.building_schedule.COMFORT_SETPOINT
        zone_id = "Zone-201"
        orchestrator.zone_temperatures[zone_id] = setpoint - 2.0
        orchestrator._actuator_state["S002-FCU-201"] = {"valve_position": 10.0, "fan_speed": 1.0}

        readings = orchestrator._generate_sensor_readings("S002-FCU-201", "fcu", 100.0, 10, schedule_occupied)
        assert readings["valve_position"] <= 10.0, "Cool room should have low valve"

    def test_fan_follows_valve(self, orchestrator, schedule_occupied):
        """Fan speed should increase with valve demand."""
        setpoint = orchestrator.building_schedule.COMFORT_SETPOINT
        zone_id = "Zone-201"
        # Very warm room — high valve demand
        orchestrator.zone_temperatures[zone_id] = setpoint + 4.0
        orchestrator._actuator_state["S002-FCU-201"] = {"valve_position": 85.0, "fan_speed": 2.0}

        readings = orchestrator._generate_sensor_readings("S002-FCU-201", "fcu", 100.0, 10, schedule_occupied)
        # High valve → fan should be medium or high (2 or 3)
        assert readings["fan_speed"] >= 2.0

    def test_hvac_off_ramps_down(self, orchestrator, schedule_off):
        """HVAC off should ramp valve toward zero, not snap."""
        orchestrator._actuator_state["S002-FCU-201"] = {"valve_position": 60.0, "fan_speed": 2.0}
        readings = orchestrator._generate_sensor_readings("S002-FCU-201", "fcu", 100.0, 2, schedule_off)
        # Should ramp down, not snap to zero
        assert readings["valve_position"] < 60.0
        assert readings["valve_position"] >= 60.0 - RAMP_RATES["valve_position"]


class TestAHUSupplyAirReset:
    """AHU supply air temp resets based on zone demand."""

    def test_high_demand_lowers_sat(self, orchestrator, schedule_occupied):
        """Warm zones should drive SAT lower (toward 12°C)."""
        setpoint = orchestrator.building_schedule.COMFORT_SETPOINT
        # Many zones warm
        for i in range(1, 10):
            orchestrator.zone_temperatures[f"Zone-{100 + i}"] = setpoint + 3.0
        orchestrator._actuator_state["S002-AHU-B1-001"] = {"supply_air_temp": 14.0, "fan_speed_pct": 60.0}

        readings = orchestrator._generate_sensor_readings("S002-AHU-B1-001", "ahu", 100.0, 10, schedule_occupied)
        assert readings["supply_air_temp"] < 14.0, "High demand should lower SAT"

    def test_satisfied_zones_raise_sat(self, orchestrator, schedule_occupied):
        """Satisfied zones should allow SAT to rise (toward 16°C)."""
        setpoint = orchestrator.building_schedule.COMFORT_SETPOINT
        # All zones at setpoint
        for i in range(1, 10):
            orchestrator.zone_temperatures[f"Zone-{100 + i}"] = setpoint
        orchestrator._actuator_state["S002-AHU-B1-001"] = {"supply_air_temp": 13.0, "fan_speed_pct": 50.0}

        readings = orchestrator._generate_sensor_readings("S002-AHU-B1-001", "ahu", 100.0, 10, schedule_occupied)
        assert readings["supply_air_temp"] > 13.0, "Satisfied zones should raise SAT"


class TestPumpAffinityLaws:
    """Pump dP follows affinity laws: dP ~ N^2."""

    def test_dp_follows_speed_squared(self, orchestrator, schedule_occupied):
        """Differential pressure should scale with speed squared."""
        setpoint = orchestrator.building_schedule.COMFORT_SETPOINT
        # Set some zones warm so pump speeds up
        for i in range(1, 5):
            orchestrator.zone_temperatures[f"Zone-{100 + i}"] = setpoint + 2.0
        orchestrator._actuator_state["S002-PUMP-B1-001"] = {"speed_pct": 60.0}

        readings = orchestrator._generate_sensor_readings("S002-PUMP-B1-001", "pump", 100.0, 10, schedule_occupied)
        speed = readings["speed_pct"]
        dp = readings["differential_pressure_kpa"]
        # dP = (speed/100)^2 * 150
        expected_dp = (speed / 100.0) ** 2 * 150.0
        assert abs(dp - expected_dp) < 1.0, f"dP should follow N^2: got {dp}, expected {expected_dp}"


class TestMultiHourRamping:
    """Trends over multiple hours should ramp gradually."""

    def test_morning_startup_ramp(self, orchestrator):
        """Morning startup should ramp valve up over multiple hours."""
        bs = BuildingSchedule()
        setpoint = orchestrator.building_schedule.COMFORT_SETPOINT
        zone_id = "Zone-201"
        # Zone is warm in the morning (building was off overnight)
        orchestrator.zone_temperatures[zone_id] = setpoint + 2.5

        valve_values = []
        for hour in range(5, 12):
            state = bs.get_state(hour, day_of_week=2)
            readings = orchestrator._generate_sensor_readings("S002-FCU-201", "fcu", 100.0, hour, state)
            valve_values.append(readings["valve_position"])

        # Should have gradual increase, not a single jump
        # Check no consecutive pair has a jump > ramp rate
        for i in range(1, len(valve_values)):
            delta = abs(valve_values[i] - valve_values[i - 1])
            assert delta <= RAMP_RATES["valve_position"] + 0.1, (
                f"Hour {5 + i}: jump {delta:.1f}% exceeds ramp rate {RAMP_RATES['valve_position']}%/hr"
            )

    def test_evening_shutdown_gradual(self, orchestrator):
        """Evening shutdown should not snap to zero."""
        bs = BuildingSchedule()
        setpoint = orchestrator.building_schedule.COMFORT_SETPOINT
        zone_id = "Zone-201"
        orchestrator.zone_temperatures[zone_id] = setpoint + 1.0
        # Prime with a midday valve position
        orchestrator._actuator_state["S002-FCU-201"] = {"valve_position": 55.0, "fan_speed": 2.0}

        valve_values = []
        for hour in range(16, 22):
            state = bs.get_state(hour, day_of_week=2)
            readings = orchestrator._generate_sensor_readings("S002-FCU-201", "fcu", 100.0, hour, state)
            valve_values.append(readings["valve_position"])

        # Should ramp down, not snap
        for i in range(1, len(valve_values)):
            delta = abs(valve_values[i] - valve_values[i - 1])
            assert delta <= RAMP_RATES["valve_position"] + 0.1, f"Hour {16 + i}: jump {delta:.1f}% exceeds ramp rate"
