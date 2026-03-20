"""Boundary tests for LifecycleOrchestrator's building-owned behavior.

These tests pin the parts of the orchestrator that should survive the
SIMBIOT/SENTINEL extraction:
- internal building control policy still runs without LLM wiring
- control recommendations are scoped to the current simulated site
- serialized state remains building-focused and can be restored
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.lifecycle_orchestrator import LifecycleOrchestrator


@pytest.fixture
def orchestrator():
    """Create a LifecycleOrchestrator with external services stubbed out."""
    with patch("app.services.lifecycle_orchestrator.EquipmentRepository") as equipment_repo_cls:
        with patch("app.services.lifecycle_orchestrator.PredictionRepository"):
            with patch("app.services.lifecycle_orchestrator.get_work_order_repository"):
                with patch("app.services.lifecycle_orchestrator.get_feedback_collection_service"):
                    with patch("app.services.lifecycle_orchestrator.get_device_control_service") as control_service_fn:
                        with patch("app.services.lifecycle_orchestrator.get_simulation_persistence"):
                            with patch("app.services.lifecycle_orchestrator.get_sentinel_data_sync"):
                                with patch("app.services.lifecycle_orchestrator.SustainabilityMetricsCollector"):
                                    with patch("app.services.lifecycle_orchestrator.SentinelAlertEngine"):
                                        orch = LifecycleOrchestrator(task_id="test-task", site_id="site-002")

    orch.simulated_time = datetime(2026, 1, 14, 10, 0)  # Wednesday 10:00
    orch._optimization_mode = "hardcoded"
    orch.current_scenario = MagicMock(demo_mode=False)
    orch._callbacks = []
    orch.events = []

    equipment_repo = equipment_repo_cls.return_value
    equipment_repo.get_all.return_value = [
        {"code": "S002-FCU-201", "type": "FCU"},
        {"code": "S002-AHU-B1-001", "type": "AHU"},
        {"code": "S999-FCU-001", "type": "FCU"},
    ]

    orch.device_control_service.is_controllable.side_effect = lambda code: code != "S002-AHU-B1-001"
    return orch


class TestBuildingControlPolicy:
    """Tests for simulator-owned control behavior."""

    def test_building_control_plan_uses_hardcoded_policy_without_llm_service(self, orchestrator):
        """Simulator-owned control planning should not touch the LLM path."""
        with patch("app.services.ai_optimizer.get_ai_optimizer") as get_ai_optimizer:
            plan = orchestrator._build_hardcoded_control_plan(
                context="hour_10",
                occupancy_percent=90,
                daylight_factor=50,
                current_hour=10,
                zones_active=11,
            )

        get_ai_optimizer.assert_not_called()
        assert plan["context"] == "hour_10"
        assert isinstance(plan["recommendations"], list)
        assert plan["total_recommendations"] >= 1
        assert all(rec.get("source") != "sentinel_analyze_building" for rec in plan["recommendations"]), (
            "Hardcoded plan should not emit SENTINEL-sourced recommendations"
        )

    def test_building_control_plan_scopes_output_to_current_site(self, orchestrator):
        """Foreign-site and non-controllable equipment should be excluded from control output."""
        plan = orchestrator._build_hardcoded_control_plan(
            context="hour_10",
            occupancy_percent=90,
            daylight_factor=50,
            current_hour=10,
            zones_active=11,
        )
        recommended_equipment = {rec.get("equipment") for rec in plan["recommendations"]}

        assert "S999-FCU-001" not in recommended_equipment
        assert recommended_equipment == {"S002-FCU-201"}


class TestBuildingStateSerialization:
    """Tests for building-state persistence and recovery."""

    def test_serialize_and_deserialize_round_trip_building_state(self, orchestrator):
        """Crash-recovery snapshot should preserve building state without external services."""
        orchestrator.days_simulated = 17
        orchestrator.active_faults = {"S002-FCU-201": {"fault_type": "bearing_wear"}}
        orchestrator.pending_repairs = {"S002-FCU-201": {"scheduled_repair_hour": 14}}
        orchestrator._occupancy_seed = 1234
        orchestrator.total_energy_kwh = 1550.4
        orchestrator.current_hour_power_kw = 187.25
        orchestrator._cumulative_baseline_kwh = 210.75
        orchestrator._cumulative_sentinel_kwh = 198.25
        orchestrator._cumulative_solar_gen_kwh = 55.0
        orchestrator._cumulative_bess_discharge_kwh = 12.5
        orchestrator._solar_hour_index = 41
        orchestrator._actuator_state = {"S002-FCU-201": {"valve_position": 62.5}}

        state = orchestrator.serialize_state()

        with patch("app.services.lifecycle_orchestrator.EquipmentRepository"):
            with patch("app.services.lifecycle_orchestrator.PredictionRepository"):
                with patch("app.services.lifecycle_orchestrator.get_work_order_repository"):
                    with patch("app.services.lifecycle_orchestrator.get_feedback_collection_service"):
                        with patch("app.services.lifecycle_orchestrator.get_device_control_service"):
                            with patch("app.services.lifecycle_orchestrator.get_simulation_persistence"):
                                with patch("app.services.lifecycle_orchestrator.get_sentinel_data_sync"):
                                    with patch("app.services.lifecycle_orchestrator.SustainabilityMetricsCollector"):
                                        with patch("app.services.lifecycle_orchestrator.SentinelAlertEngine"):
                                            restored = LifecycleOrchestrator.deserialize_state(state)

        assert restored.simulated_time == orchestrator.simulated_time
        assert restored.days_simulated == 17
        assert restored.active_faults == orchestrator.active_faults
        assert restored.pending_repairs == orchestrator.pending_repairs
        assert restored._occupancy_seed == 1234
        assert restored.total_energy_kwh == pytest.approx(1550.4)
        assert restored.current_hour_power_kw == pytest.approx(187.25)
        assert restored._cumulative_baseline_kwh == pytest.approx(210.75)
        assert restored._cumulative_sentinel_kwh == pytest.approx(198.25)
        assert restored._cumulative_solar_gen_kwh == pytest.approx(55.0)
        assert restored._cumulative_bess_discharge_kwh == pytest.approx(12.5)
        assert restored._solar_hour_index == 41
        assert restored._actuator_state == {"S002-FCU-201": {"valve_position": 62.5}}
