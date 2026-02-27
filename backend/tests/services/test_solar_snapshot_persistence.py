"""Tests for solar snapshot persistence and meter differentiation.

Verifies that:
1. persist_solar_snapshot writes correct row to JSON simulation store
2. persist_solar_daily writes correct row to JSON simulation store
3. Meter readings differentiate grid, solar, and water meters
4. Building consumption vs council consumption are tracked correctly
5. Solar capacity unified to 297 kWp (4x 74.25 kWp inverters)
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def persistence(tmp_path):
    """Create SimulationPersistence with a temp-dir JSON store."""
    from app.services.simulation_persistence import SimulationPersistence

    p = SimulationPersistence("site-002")
    # Point the store at a temp directory so tests don't pollute real data
    p.store._dir = tmp_path
    return p


class TestPersistSolarSnapshot:
    """Test solar hourly snapshot persistence."""

    @pytest.mark.asyncio
    async def test_snapshot_extracts_inverter_power(self, persistence, tmp_path):
        """Solar gen should sum ac_power_kw from all inverter equipment."""
        equipment_states = {
            "S002-INV-R-001": {
                "type": "inverter",
                "sensor_readings": {"ac_power_kw": 80.0, "dc_power_kw": 85.0},
            },
            "S002-INV-R-002": {
                "type": "inverter",
                "sensor_readings": {"ac_power_kw": 75.0, "dc_power_kw": 80.0},
            },
            "S002-BESS-B1-001": {
                "type": "bess",
                "sensor_readings": {
                    "state_of_charge_pct": 65.0,
                    "charge_power_kw": 0.0,
                    "discharge_power_kw": 30.0,
                    "grid_import_kw": 10.0,
                },
            },
        }

        result = await persistence.persist_solar_snapshot(
            simulated_time=datetime(2026, 6, 15, 12, 0, 0),
            equipment_states=equipment_states,
            building_load_kw=20.0,
            tariff_band="standard",
            tariff_rate=200.0,
            hour_index=4380,
        )

        assert result is True
        rows = _read_jsonl(tmp_path / "solar_hourly_snapshots.jsonl")
        assert len(rows) == 1
        row = rows[0]
        assert row["solar_gen_kw"] == 155.0  # 80 + 75
        assert row["bess_soc_pct"] == 65.0
        assert row["bess_discharge_kw"] == 30.0
        assert row["grid_import_kw"] == 10.0
        assert row["tariff_band"] == "standard"
        assert row["hour_of_day"] == 12
        assert row["month"] == 6

    @pytest.mark.asyncio
    async def test_snapshot_no_solar_equipment(self, persistence, tmp_path):
        """When no inverters exist, solar_gen_kw should be 0."""
        equipment_states = {
            "S002-AHU-B1-001": {
                "type": "ahu",
                "sensor_readings": {"supply_air_temp": 14.0},
            },
        }

        result = await persistence.persist_solar_snapshot(
            simulated_time=datetime(2026, 1, 1, 3, 0, 0),
            equipment_states=equipment_states,
            building_load_kw=5.0,
            tariff_band="off_peak",
            tariff_rate=80.0,
            hour_index=3,
        )

        assert result is True
        rows = _read_jsonl(tmp_path / "solar_hourly_snapshots.jsonl")
        row = rows[0]
        assert row["solar_gen_kw"] == 0.0
        assert row["bess_soc_pct"] == 50.0  # default
        assert row["hour_of_day"] == 3

    @pytest.mark.asyncio
    async def test_grid_export_calculation(self, persistence, tmp_path):
        """Grid export = solar - load - charge + discharge (clamped to >= 0)."""
        equipment_states = {
            "S002-INV-R-001": {
                "type": "inverter",
                "sensor_readings": {"ac_power_kw": 200.0},
            },
            "S002-BESS-B1-001": {
                "type": "bess",
                "sensor_readings": {
                    "state_of_charge_pct": 80.0,
                    "charge_power_kw": 20.0,
                    "discharge_power_kw": 0.0,
                    "grid_import_kw": 0.0,
                },
            },
        }

        await persistence.persist_solar_snapshot(
            simulated_time=datetime(2026, 6, 15, 12, 0, 0),
            equipment_states=equipment_states,
            building_load_kw=50.0,
            tariff_band="standard",
            tariff_rate=200.0,
            hour_index=100,
        )

        rows = _read_jsonl(tmp_path / "solar_hourly_snapshots.jsonl")
        row = rows[0]
        # 200 - 50 - 20 + 0 = 130 kW export
        assert row["grid_export_kw"] == 130.0


class TestPersistSolarDaily:
    """Test solar daily aggregation persistence."""

    @pytest.mark.asyncio
    async def test_daily_aggregate_written(self, persistence, tmp_path):
        """Daily aggregate should write all required fields."""
        result = await persistence.persist_solar_daily(
            simulated_date=datetime(2026, 3, 15).date(),
            solar_gen_kwh=450.0,
            building_load_kwh=600.0,
            bess_charge_kwh=80.0,
            bess_discharge_kwh=60.0,
            grid_import_kwh=200.0,
            grid_export_kwh=30.0,
            peak_generation_kw=250.0,
            avg_bess_soc_pct=65.0,
        )

        assert result is True
        rows = _read_jsonl(tmp_path / "solar_daily_aggregates.jsonl")
        assert len(rows) == 1
        row = rows[0]
        assert row["solar_gen_kwh"] == 450.0
        assert row["peak_generation_kw"] == 250.0
        assert row["avg_bess_soc_pct"] == 65.0
        assert row["month"] == 3
        assert row["day_of_year"] == 74


# ------------------------------------------------------------------
# Meter Differentiation Tests
# ------------------------------------------------------------------


class TestMeterDifferentiation:
    """Verify grid, solar, and water meters produce different readings."""

    @pytest.fixture
    def orchestrator(self):
        """Create a minimal object with attributes needed by _generate_sensor_readings."""
        import random
        from app.services.lifecycle_orchestrator import LifecycleOrchestrator

        # Create raw instance without __init__ (avoids Supabase/ML imports)
        orc = object.__new__(LifecycleOrchestrator)
        orc._scenario_rng = random.Random(42)
        orc.current_building_load_kw = 120.0
        orc.current_solar_gen_kw = 200.0
        orc.current_grid_import_kw = 0.0
        orc.current_grid_export_kw = 80.0
        orc.current_hour_power_kw = 0.0
        orc._daily_solar_gen_kwh = 500.0
        orc.current_solar_efficiency = 90.0
        orc.current_ambient_temp = 25.0
        orc.bess_soc = 60.0
        orc.chw_model = MagicMock()
        orc.chw_model.supply_temp = 7.0
        orc.chw_model.return_temp = 12.0
        return orc

    @pytest.fixture
    def schedule_state(self):
        ss = MagicMock()
        ss.hvac_mode.value = "cooling"
        ss.chiller_staging.value = "stage_1"
        ss.lighting_mode.value = "full"
        return ss

    def test_grid_meter_shows_net_consumption(self, orchestrator, schedule_state):
        """S002-MTR-B1-MAIN shows council meter (net after solar)."""
        readings = orchestrator._generate_sensor_readings("S002-MTR-B1-MAIN", "meter", 95.0, 12, schedule_state)
        assert readings["power_kw"] == 0.0  # solar > building load
        assert readings["grid_export_kw"] == 80.0
        assert readings["building_load_kw"] == 120.0
        assert readings["solar_offset_kw"] == 200.0
        assert "power_factor" in readings

    def test_solar_meter_shows_generation(self, orchestrator, schedule_state):
        """S002-MTR-R-SOLAR shows PV generation."""
        readings = orchestrator._generate_sensor_readings("S002-MTR-R-SOLAR", "meter", 98.0, 12, schedule_state)
        assert readings["power_kw"] == 200.0  # solar gen
        assert readings["daily_energy_kwh"] == 500.0
        assert "power_factor" in readings

    def test_water_meter_no_electrical(self, orchestrator, schedule_state):
        """S002-MTR-B1-WATER has flow_rate, not power_kw."""
        readings = orchestrator._generate_sensor_readings("S002-MTR-B1-WATER", "meter", 100.0, 12, schedule_state)
        assert "flow_rate_lpm" in readings
        assert "power_kw" not in readings

    def test_grid_meter_shows_import_at_night(self, orchestrator, schedule_state):
        """At night with no solar, grid meter shows full building load + BESS charge."""
        orchestrator.current_solar_gen_kw = 0.0
        orchestrator.current_building_load_kw = 25.0
        orchestrator.current_grid_import_kw = 65.0  # 25 + 40 BESS charge
        orchestrator.current_grid_export_kw = 0.0
        readings = orchestrator._generate_sensor_readings("S002-MTR-B1-MAIN", "meter", 96.0, 3, schedule_state)
        assert readings["power_kw"] == 65.0  # Council sees building + BESS charge
        assert readings["building_load_kw"] == 25.0


# ------------------------------------------------------------------
# Solar Capacity Unification Tests
# ------------------------------------------------------------------


class TestSolarCapacityUnification:
    """Verify 297 kWp total plant capacity is used consistently."""

    @pytest.fixture
    def orchestrator(self):
        """Create raw orchestrator for capacity testing."""
        import random
        from app.services.lifecycle_orchestrator import LifecycleOrchestrator

        orc = object.__new__(LifecycleOrchestrator)
        orc._scenario_rng = random.Random(42)
        orc.current_solar_efficiency = 100.0
        orc.current_ambient_temp = 25.0
        orc.bess_soc = 50.0
        orc.current_hour_power_kw = 50.0
        orc.current_grid_import_kw = 0.0
        orc.chw_model = MagicMock()
        return orc

    @pytest.fixture
    def schedule_state(self):
        ss = MagicMock()
        ss.hvac_mode.value = "cooling"
        ss.chiller_staging.value = "off"
        ss.lighting_mode.value = "off"
        return ss

    def test_inverter_capacity_74kw(self, orchestrator, schedule_state):
        """Each inverter should have 74.25 kWp panel capacity (297/4)."""
        readings = orchestrator._generate_sensor_readings("S002-INV-R-001", "inverter", 100.0, 12, schedule_state)
        # At noon, 100% efficiency, 100% health: dc = 74.25 * 1.0 * 1.0 * 1.0
        assert abs(readings["dc_power_kw"] - 74.25) < 0.1
        # AC = DC * 0.96
        assert abs(readings["ac_power_kw"] - 71.3) < 0.2

    def test_four_inverters_total_297kw(self, orchestrator, schedule_state):
        """4 inverters at noon clear sky = ~297 kWp DC."""
        total_dc = 0.0
        for inv_code in ["S002-INV-R-001", "S002-INV-R-002", "S002-INV-R-003", "S002-INV-R-004"]:
            readings = orchestrator._generate_sensor_readings(inv_code, "inverter", 100.0, 12, schedule_state)
            total_dc += readings["dc_power_kw"]
        assert abs(total_dc - 297.0) < 1.0  # Tolerance for per-inverter rounding


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------


def _read_jsonl(path):
    """Read a JSONL file and return list of dicts."""
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
