"""Unit tests for sceneCOM telemetry generation in LightingSimulationEngine.

Tests cover:
    - Luminaire topology creation from zone metadata (2 tests)
    - Per-luminaire energy telemetry (3 tests)
    - Driver diagnostics (temperature, health) (3 tests)
    - Emergency gear simulation (2 tests)
    - Sensor telemetry (2 tests)
    - Controller telemetry (1 test)
    - Fault injection (1 test)
    - Telemetry accessor (1 test)

Total: 15 tests

All tests mock Supabase and test pure simulation logic only.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.lighting_simulation_engine import LightingSimulationEngine


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def engine():
    """Create engine with mocked Supabase and pre-populated zone cache."""
    with patch("app.services.lighting_simulation_engine.get_supabase_client") as mock_sb:
        mock_sb.return_value = MagicMock()
        eng = LightingSimulationEngine("site-002")

        eng._zone_cache = {
            "Zone-001": {"zone_name": "L0 Zone A", "floor": "L0", "typical_occupancy": 10, "area_sqm": 80},
            "Zone-002": {"zone_name": "L0 Zone B", "floor": "L0", "typical_occupancy": 10, "area_sqm": 40},
            "Zone-101": {"zone_name": "L1 Zone A", "floor": "L1", "typical_occupancy": 10, "area_sqm": 80},
        }
        return eng


@pytest.fixture
def engine_with_telemetry(engine):
    """Engine that has already generated one round of telemetry."""
    zone_power = {"Zone-001": 1.2, "Zone-002": 0.8, "Zone-101": 1.0}
    occupancy_data = {"Zone-001": 80.0, "Zone-002": 50.0, "Zone-101": 60.0}
    engine._generate_scenecom_telemetry(
        zone_power=zone_power,
        occupancy_data=occupancy_data,
        daylight_lux=400.0,
        simulated_hour=10,
    )
    return engine


# ------------------------------------------------------------------
# 1. Luminaire Topology
# ------------------------------------------------------------------


class TestLuminaireTopology:
    """Verify luminaire-per-zone mapping from area_sqm."""

    def test_topology_luminaire_count_from_area(self, engine):
        """80 sqm zone → 10 luminaires (80 / 8 sqm per fixture)."""
        engine._ensure_luminaire_topology()
        assert len(engine._zone_luminaires["Zone-001"]) == 10

    def test_topology_small_zone_minimum_2(self, engine):
        """40 sqm zone → 5 luminaires (40 / 8), never below 2."""
        engine._ensure_luminaire_topology()
        assert len(engine._zone_luminaires["Zone-002"]) == 5


# ------------------------------------------------------------------
# 2. Per-Luminaire Energy Telemetry
# ------------------------------------------------------------------


class TestEnergyTelemetry:
    """Verify per-luminaire power distribution and energy accumulation."""

    def test_luminaire_records_generated(self, engine_with_telemetry):
        """Telemetry contains luminaire records for all zones."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        assert len(telemetry["luminaires"]) > 0

    def test_active_power_distributed_across_luminaires(self, engine_with_telemetry):
        """Zone power is distributed roughly evenly across luminaires."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        zone_001_lums = [r for r in telemetry["luminaires"] if r["zone_id"] == "Zone-001"]
        # 1.2 kW requested but rated power caps at 80W (80sqm * 10 W/sqm / 10 lums)
        # With ±5% noise: 76–84W per luminaire
        for lum in zone_001_lums:
            assert 70 < lum["active_power_w"] < 90, f"Power {lum['active_power_w']}W outside range"

    def test_accumulated_energy_increases(self, engine):
        """Energy accumulates across multiple simulation steps."""
        engine._ensure_luminaire_topology()
        lum_id = engine._zone_luminaires["Zone-001"][0]
        initial_energy = engine._luminaire_state[lum_id]["accumulated_energy_kwh"]

        zone_power = {"Zone-001": 1.5, "Zone-002": 0.5, "Zone-101": 0.5}
        occupancy = {"Zone-001": 100.0, "Zone-002": 50.0, "Zone-101": 50.0}
        engine._generate_scenecom_telemetry(zone_power, occupancy, 500.0, 10)
        engine._generate_scenecom_telemetry(zone_power, occupancy, 500.0, 11)

        final_energy = engine._luminaire_state[lum_id]["accumulated_energy_kwh"]
        assert final_energy > initial_energy


# ------------------------------------------------------------------
# 3. Driver Diagnostics
# ------------------------------------------------------------------


class TestDriverDiagnostics:
    """Verify driver temperature and health calculations."""

    def test_driver_temp_correlates_with_power(self, engine):
        """Higher power → higher driver temperature."""
        engine._ensure_luminaire_topology()

        # Low power run
        engine._generate_scenecom_telemetry(
            zone_power={"Zone-001": 0.2, "Zone-002": 0.1, "Zone-101": 0.1},
            occupancy_data={"Zone-001": 30.0, "Zone-002": 30.0, "Zone-101": 30.0},
            daylight_lux=800.0,
            simulated_hour=10,
        )
        low_temps = [
            r["driver_temp_c"] for r in engine.get_latest_telemetry()["luminaires"] if r["zone_id"] == "Zone-001"
        ]

        # High power run
        engine._generate_scenecom_telemetry(
            zone_power={"Zone-001": 1.8, "Zone-002": 1.8, "Zone-101": 1.8},
            occupancy_data={"Zone-001": 100.0, "Zone-002": 100.0, "Zone-101": 100.0},
            daylight_lux=0.0,
            simulated_hour=11,
        )
        high_temps = [
            r["driver_temp_c"] for r in engine.get_latest_telemetry()["luminaires"] if r["zone_id"] == "Zone-001"
        ]

        avg_low = sum(low_temps) / len(low_temps)
        avg_high = sum(high_temps) / len(high_temps)
        assert avg_high > avg_low, f"High power temp {avg_high} should exceed low {avg_low}"

    def test_driver_health_ok_at_normal_temps(self, engine_with_telemetry):
        """Normal power → driver health = 'ok'."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        # At ~120W per luminaire, temp should be well below 85°C
        ok_count = sum(1 for r in telemetry["luminaires"] if r["driver_health"] == "ok")
        assert ok_count > 0

    def test_light_output_degrades_with_lamp_hours(self, engine):
        """Light output decreases as lamp hours accumulate."""
        engine._ensure_luminaire_topology()
        lum_id = engine._zone_luminaires["Zone-001"][0]

        # Set high lamp hours
        engine._luminaire_state[lum_id]["lamp_hours"] = 40000

        engine._generate_scenecom_telemetry(
            zone_power={"Zone-001": 1.0, "Zone-002": 0.5, "Zone-101": 0.5},
            occupancy_data={"Zone-001": 80.0, "Zone-002": 50.0, "Zone-101": 50.0},
            daylight_lux=300.0,
            simulated_hour=12,
        )

        lum_record = next(r for r in engine.get_latest_telemetry()["luminaires"] if r["luminaire_id"] == lum_id)
        assert lum_record["light_output_pct"] < 100.0
        assert lum_record["colour_shift_sdcm"] > 0


# ------------------------------------------------------------------
# 4. Emergency Gear
# ------------------------------------------------------------------


class TestEmergencyGear:
    """Verify emergency battery simulation."""

    def test_emergency_gear_generated_for_subset(self, engine_with_telemetry):
        """~10% of luminaires have emergency gear records."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        total_lums = len(telemetry["luminaires"])
        total_emergency = len(telemetry["emergency_gear"])
        # At least 1 per zone (3 zones), up to ~10% of total
        assert total_emergency >= 3
        assert total_emergency <= max(3, int(total_lums * 0.15) + 1)

    def test_emergency_battery_has_required_fields(self, engine_with_telemetry):
        """Emergency gear records contain all required fields."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        for rec in telemetry["emergency_gear"]:
            assert "luminaire_id" in rec
            assert "battery_pct" in rec
            assert "charge_status" in rec
            assert rec["charge_status"] in ("charged", "charging", "fault")
            assert 0 <= rec["battery_pct"] <= 100


# ------------------------------------------------------------------
# 5. Sensor Telemetry
# ------------------------------------------------------------------


class TestSensorTelemetry:
    """Verify per-zone sensor records."""

    def test_one_sensor_per_zone(self, engine_with_telemetry):
        """Each zone gets exactly one sensor record."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        assert len(telemetry["sensors"]) == 3  # 3 zones

    def test_sensor_occupancy_count_from_percent(self, engine_with_telemetry):
        """Occupancy count derived from pct × typical_occupancy."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        zone_001_sensor = next(s for s in telemetry["sensors"] if s["zone_id"] == "Zone-001")
        # 80% of 10 typical = 8 people
        assert zone_001_sensor["occupancy_count"] == 8
        assert zone_001_sensor["occupancy"] is True


# ------------------------------------------------------------------
# 6. Controller Telemetry
# ------------------------------------------------------------------


class TestControllerTelemetry:
    """Verify sceneCOM controller records."""

    def test_controllers_grouped_by_floor(self, engine_with_telemetry):
        """Controllers created per floor, with correct zone mappings."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        ctrl_ids = {c["controller_id"] for c in telemetry["controllers"]}
        # 2 floors: L0 (Zone-001, Zone-002) and L1 (Zone-101)
        assert len(ctrl_ids) == 2
        for ctrl in telemetry["controllers"]:
            assert ctrl["mqtt_connected"] is True
            assert ctrl["luminaire_count"] > 0


# ------------------------------------------------------------------
# 7. Fault Injection
# ------------------------------------------------------------------


class TestFaultInjection:
    """Verify fault injection mechanism."""

    def test_forced_fault_appears_in_telemetry(self, engine):
        """Manually faulted luminaire appears in faults list."""
        engine._ensure_luminaire_topology()
        lum_id = engine._zone_luminaires["Zone-001"][2]
        engine._luminaire_state[lum_id]["fault_status"] = True
        engine._luminaire_state[lum_id]["fault_code"] = "lamp_failure"

        engine._generate_scenecom_telemetry(
            zone_power={"Zone-001": 1.0, "Zone-002": 0.5, "Zone-101": 0.5},
            occupancy_data={"Zone-001": 80.0, "Zone-002": 50.0, "Zone-101": 50.0},
            daylight_lux=400.0,
            simulated_hour=14,
        )

        telemetry = engine.get_latest_telemetry()
        fault_ids = {f["luminaire_id"] for f in telemetry["faults"]}
        assert lum_id in fault_ids


# ------------------------------------------------------------------
# 8. Telemetry Accessor
# ------------------------------------------------------------------


class TestTelemetryAccessor:
    """Verify get_latest_telemetry returns correct structure."""

    def test_telemetry_has_all_top_level_keys(self, engine_with_telemetry):
        """Telemetry dict has all expected top-level keys."""
        telemetry = engine_with_telemetry.get_latest_telemetry()
        for key in (
            "timestamp",
            "site_id",
            "luminaires",
            "sensors",
            "controllers",
            "emergency_gear",
            "faults",
            "summary",
        ):
            assert key in telemetry, f"Missing key: {key}"

        assert telemetry["summary"]["total_luminaires"] > 0
        assert telemetry["summary"]["total_active_power_w"] > 0
