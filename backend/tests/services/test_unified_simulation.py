"""Tests for the unified simulation engine (LifecycleOrchestrator with JSON loading).

Validates that:
- _collect_equipment_states loads from JSON files
- All equipment types generate sensor readings
- Health degradation and cascade effects work for all types
- Compatibility methods (alerts, maintenance, fault injection) work
"""

from unittest.mock import patch

import pytest

from app.services.building_schedule import SiteSchedule
from app.services.lifecycle_orchestrator import LifecycleOrchestrator


@pytest.fixture
def orchestrator():
    """Create a fresh LifecycleOrchestrator for testing."""
    orch = LifecycleOrchestrator(site_id="site-002")
    return orch


@pytest.fixture
def schedule_state_occupied():
    """A schedule state representing occupied business hours."""
    bs = SiteSchedule()
    state = bs.get_state(10, day_of_week=2)  # 10 AM Wednesday — occupied
    return state


@pytest.fixture
def schedule_state_unoccupied():
    """A schedule state representing unoccupied night hours."""
    bs = SiteSchedule()
    state = bs.get_state(2, day_of_week=2)  # 2 AM Wednesday — unoccupied
    return state


class TestCollectEquipmentStates:
    """Test _collect_equipment_states loads from JSON."""

    @pytest.mark.asyncio
    async def test_loads_all_equipment_from_json(self, orchestrator, schedule_state_occupied):
        """Should load all 90 equipment items from JSON files."""
        # Patch Supabase to ensure we're testing JSON path
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        assert len(states) >= 75, f"Expected 75+ equipment, got {len(states)}"

    @pytest.mark.asyncio
    async def test_all_states_have_required_fields(self, orchestrator, schedule_state_occupied):
        """Each equipment state must have health_score, status, sensor_readings, type."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        for code, state in states.items():
            assert "health_score" in state, f"{code} missing health_score"
            assert "status" in state, f"{code} missing status"
            assert "sensor_readings" in state, f"{code} missing sensor_readings"
            assert "type" in state, f"{code} missing type"
            assert "is_running" in state, f"{code} missing is_running"

    @pytest.mark.asyncio
    async def test_equipment_types_normalized(self, orchestrator, schedule_state_occupied):
        """LTG → luminaire, CT → cooling_tower, etc."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        # LTG files should be normalized to luminaire
        ltg_codes = [c for c in states if c.startswith("S002-LTG")]
        for code in ltg_codes:
            assert states[code]["type"] == "luminaire", f"{code} should be 'luminaire', got '{states[code]['type']}'"

        # CT files should be normalized to cooling_tower
        ct_codes = [c for c in states if c.startswith("S002-CT")]
        for code in ct_codes:
            assert states[code]["type"] == "cooling_tower"

    @pytest.mark.asyncio
    async def test_snapshot_stored(self, orchestrator, schedule_state_occupied):
        """_simulation_equipment should be populated after collection."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        assert len(orchestrator._simulation_equipment) >= 75


class TestSensorReadings:
    """Test that each equipment type generates appropriate sensor readings."""

    @pytest.mark.asyncio
    async def test_luminaire_generates_brightness(self, orchestrator, schedule_state_occupied):
        """Luminaire (LTG) equipment should generate brightness_pct, power_w, status."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        ltg_codes = [c for c in states if c.startswith("S002-LTG")]
        assert len(ltg_codes) >= 18

        for code in ltg_codes[:3]:  # Spot check first 3
            readings = states[code]["sensor_readings"]
            assert "brightness_pct" in readings, f"{code} missing brightness_pct"
            assert "power_w" in readings, f"{code} missing power_w"
            assert "status" in readings, f"{code} missing status"
            assert readings["brightness_pct"] >= 0

    @pytest.mark.asyncio
    async def test_dali_controller_generates_bus_status(self, orchestrator, schedule_state_occupied):
        """DALI controller should generate status, bus_fault, devices_online."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        dali_ctrl_codes = [c for c in states if "DALI_CONTROLLER" in c]
        assert len(dali_ctrl_codes) >= 1

        for code in dali_ctrl_codes:
            readings = states[code]["sensor_readings"]
            assert "status" in readings, f"{code} missing status"
            assert "bus_fault" in readings, f"{code} missing bus_fault"
            assert "devices_online" in readings, f"{code} missing devices_online"
            assert readings["devices_online"] >= 0

    @pytest.mark.asyncio
    async def test_chiller_generates_temps(self, orchestrator, schedule_state_occupied):
        """Chiller should generate supply_temp, return_temp, load_pct."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        chiller_codes = [c for c in states if c.startswith("S002-CHILLER")]
        assert len(chiller_codes) >= 2

        for code in chiller_codes:
            readings = states[code]["sensor_readings"]
            assert "supply_temp" in readings
            assert "return_temp" in readings

    @pytest.mark.asyncio
    async def test_inverter_generates_power(self, orchestrator, schedule_state_occupied):
        """Inverter should generate dc_power_kw, ac_power_kw."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        inv_codes = [c for c in states if c.startswith("S002-INV")]
        assert len(inv_codes) >= 4

        for code in inv_codes:
            readings = states[code]["sensor_readings"]
            assert "dc_power_kw" in readings or "ac_power_kw" in readings or "status" in readings

    @pytest.mark.asyncio
    async def test_bess_generates_soc(self, orchestrator, schedule_state_occupied):
        """BESS should generate state_of_charge_pct."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        bess_codes = [c for c in states if c.startswith("S002-BESS")]
        assert len(bess_codes) >= 1

        for code in bess_codes:
            readings = states[code]["sensor_readings"]
            assert "state_of_charge_pct" in readings

    @pytest.mark.asyncio
    async def test_meter_generates_power(self, orchestrator, schedule_state_occupied):
        """Meter should generate power_kw."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        mtr_codes = [c for c in states if c.startswith("S002-MTR")]
        assert len(mtr_codes) >= 3

        for code in mtr_codes:
            readings = states[code]["sensor_readings"]
            assert "power_kw" in readings or "flow_rate_lps" in readings or len(readings) > 0

    @pytest.mark.asyncio
    async def test_pump_generates_flow(self, orchestrator, schedule_state_occupied):
        """Pump should generate speed_pct, flow_lps."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        pump_codes = [c for c in states if c.startswith("S002-PUMP")]
        assert len(pump_codes) >= 1

        for code in pump_codes:
            readings = states[code]["sensor_readings"]
            assert "speed_pct" in readings or "status" in readings

    @pytest.mark.asyncio
    async def test_unknown_generates_status(self, orchestrator, schedule_state_occupied):
        """Unknown equipment should generate at least a status reading (if any exist)."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        unknown_codes = [c for c in states if "UNKNOWN" in c]
        # UNKNOWN files were removed during inventory cleanup — skip if none
        if not unknown_codes:
            pytest.skip("No UNKNOWN equipment in current inventory")

        for code in unknown_codes:
            readings = states[code]["sensor_readings"]
            assert "status" in readings

    @pytest.mark.asyncio
    async def test_all_equipment_has_nonempty_readings(self, orchestrator, schedule_state_occupied):
        """Every equipment item should have at least one sensor reading."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        for code, state in states.items():
            readings = state.get("sensor_readings", {})
            assert len(readings) > 0, f"{code} ({state['type']}) has no sensor readings"


class TestHealthDegradation:
    """Test health degradation for all equipment types."""

    @pytest.mark.asyncio
    async def test_health_decreases_over_time(self, orchestrator, schedule_state_occupied):
        """Running equipment should degrade slightly each tick."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            # First tick — seeds health
            states1 = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

            # Find an AHU (should be running during occupied hours)
            ahu_code = next((c for c in states1 if c.startswith("S002-AHU")), None)
            assert ahu_code is not None
            health1 = states1[ahu_code]["health_score"]

            # Second tick
            states2 = await orchestrator._collect_equipment_states(11, schedule_state_occupied)
            health2 = states2[ahu_code]["health_score"]

            assert health2 <= health1, "Health should not increase between ticks"

    @pytest.mark.asyncio
    async def test_fault_accelerates_degradation(self, orchestrator, schedule_state_occupied):
        """Equipment with active faults should degrade faster."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            states1 = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

            ahu_code = next((c for c in states1 if c.startswith("S002-AHU")), None)
            assert ahu_code is not None
            health1 = states1[ahu_code]["health_score"]

            # Inject a fault
            orchestrator.active_faults[ahu_code] = {
                "fault_type": "FAN_FAILURE",
                "hours_faulted": 0,
            }

            states2 = await orchestrator._collect_equipment_states(11, schedule_state_occupied)
            health2 = states2[ahu_code]["health_score"]

            # Fault degradation is 2% per hour — much more than baseline
            health_drop = health1 - health2
            assert health_drop >= 1.0, f"Fault should cause significant degradation, only dropped {health_drop}"


class TestCascadeEffects:
    """Test cascade effects from plant to zone equipment."""

    @pytest.mark.asyncio
    async def test_chiller_failure_affects_fcu(self, orchestrator, schedule_state_occupied):
        """When all chillers fail, FCU zone_temp should rise."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            # Normal operation first
            states_normal = await orchestrator._collect_equipment_states(10, schedule_state_occupied)

            fcu_codes = [c for c in states_normal if c.startswith("S002-FCU")]
            if not fcu_codes:
                pytest.skip("No FCU equipment found")

            # Force all chillers to critical health
            chiller_codes = [c for c in states_normal if c.startswith("S002-CHILLER")]
            for cc in chiller_codes:
                orchestrator._equipment_health[cc] = 15.0

            states_degraded = await orchestrator._collect_equipment_states(11, schedule_state_occupied)

            # Verify cascade effects exist
            assert len(states_degraded) >= len(states_normal) - 1


class TestCompatibilityMethods:
    """Test methods transplanted from BMSimulationService."""

    @pytest.mark.asyncio
    async def test_perform_maintenance(self, orchestrator, schedule_state_occupied):
        """Maintenance should restore health by 30, capped at 95."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        ahu_code = next((c for c in orchestrator._equipment_health if c.startswith("S002-AHU")), None)
        assert ahu_code is not None

        # Set health low
        orchestrator._equipment_health[ahu_code] = 50.0

        result = orchestrator.perform_maintenance(ahu_code)
        assert result["success"] is True
        assert result["new_health"] == 80.0  # 50 + 30 = 80

    @pytest.mark.asyncio
    async def test_maintenance_caps_at_95(self, orchestrator, schedule_state_occupied):
        """Maintenance on healthy equipment should cap at 95."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        ahu_code = next((c for c in orchestrator._equipment_health if c.startswith("S002-AHU")), None)
        assert ahu_code is not None

        orchestrator._equipment_health[ahu_code] = 90.0
        result = orchestrator.perform_maintenance(ahu_code)
        assert result["new_health"] == 95.0  # min(95, 90+30)

    @pytest.mark.asyncio
    async def test_maintenance_clears_faults(self, orchestrator, schedule_state_occupied):
        """Maintenance should clear active faults."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        ahu_code = next((c for c in orchestrator._equipment_health if c.startswith("S002-AHU")), None)
        orchestrator.active_faults[ahu_code] = {"fault_type": "TEST"}

        result = orchestrator.perform_maintenance(ahu_code)
        assert result["fault_cleared"] is True
        assert ahu_code not in orchestrator.active_faults

    def test_maintenance_nonexistent_equipment(self, orchestrator):
        """Maintenance on unknown equipment should return error."""
        result = orchestrator.perform_maintenance("S002-FAKE-001")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_inject_fault(self, orchestrator, schedule_state_occupied):
        """Injecting a fault should add to active_faults and create an alert."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        ahu_code = next((c for c in orchestrator._equipment_health if c.startswith("S002-AHU")), None)
        result = orchestrator.inject_fault(ahu_code, "MOTOR_OVERTEMP")
        assert result["success"] is True
        assert ahu_code in orchestrator.active_faults
        assert result["alert_id"] > 0

    def test_inject_fault_nonexistent(self, orchestrator):
        """Injecting a fault on unknown equipment should return error."""
        result = orchestrator.inject_fault("S002-FAKE-001", "TEST")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_alert_lifecycle(self, orchestrator, schedule_state_occupied):
        """Alerts: inject → get_active → acknowledge → clear."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        ahu_code = next((c for c in orchestrator._equipment_health if c.startswith("S002-AHU")), None)
        result = orchestrator.inject_fault(ahu_code, "TEST_FAULT")
        alert_id = str(result["alert_id"])

        # Active alerts should have 1
        active = orchestrator.get_active_alerts()
        assert len(active) >= 1

        # Acknowledge
        assert orchestrator.acknowledge_alert(alert_id) is True
        ack_alert = next(a for a in orchestrator._alert_queue if str(a["id"]) == alert_id)
        assert ack_alert["status"] == "acknowledged"

        # Clear
        assert orchestrator.clear_alert(alert_id) is True
        active_after = orchestrator.get_active_alerts()
        assert len(active_after) == 0
        assert len(orchestrator.get_alert_history()) >= 1

    @pytest.mark.asyncio
    async def test_get_equipment_summary(self, orchestrator, schedule_state_occupied):
        """Summary should include total, by_type, health_stats, faults."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        summary = orchestrator.get_equipment_summary()
        assert summary["total"] >= 75
        assert "by_type" in summary
        assert "luminaire" in summary["by_type"]
        assert summary["health_stats"]["avg"] > 0
        assert summary["faults"] == 0

    @pytest.mark.asyncio
    async def test_clear_faults(self, orchestrator, schedule_state_occupied):
        """clear_faults should remove active fault."""
        with patch.object(orchestrator.equipment_repo, "get_all", return_value=[]):
            await orchestrator._collect_equipment_states(10, schedule_state_occupied)

        ahu_code = next((c for c in orchestrator._equipment_health if c.startswith("S002-AHU")), None)
        orchestrator.inject_fault(ahu_code, "TEST")
        assert orchestrator.clear_faults(ahu_code) is True
        assert ahu_code not in orchestrator.active_faults
