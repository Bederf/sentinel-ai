from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.lifecycle_orchestrator import LifecycleOrchestrator
from app.services.occupancy_profile_service import calculate_building_occupancy_percent, calculate_zone_occupancy


class StubRng:
    def __init__(self, value: float):
        self.value = value

    def uniform(self, _a: float, _b: float) -> float:
        return self.value


class SequenceRng:
    def __init__(self, values: list[float]):
        self.values = list(values)

    def uniform(self, _a: float, _b: float) -> float:
        if self.values:
            return self.values.pop(0)
        raise AssertionError("SequenceRng exhausted")


@pytest.fixture
def orchestrator():
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

    orch.simulated_time = datetime(2026, 1, 14, 10, 0)
    orch.current_scenario = MagicMock(demo_mode=False)
    orch.events = []

    equipment_repo = equipment_repo_cls.return_value
    equipment_repo.get_all.return_value = []
    control_service_fn.return_value.is_controllable.return_value = True
    return orch


def test_calculate_zone_occupancy_uses_weekend_profile():
    assert calculate_zone_occupancy(hour=11, day_of_week=6, is_weekend=True, zone_type="office") == pytest.approx(5.0)
    assert calculate_zone_occupancy(hour=11, day_of_week=6, is_weekend=True, zone_type="utility") == pytest.approx(2.0)


def test_calculate_zone_occupancy_uses_holiday_profile():
    assert calculate_zone_occupancy(
        hour=11, day_of_week=2, is_weekend=False, is_holiday=True, zone_type="office"
    ) == pytest.approx(5.0)


def test_calculate_zone_occupancy_supports_injected_rng():
    occupancy = calculate_zone_occupancy(
        hour=10,
        day_of_week=0,
        is_weekend=False,
        zone_type="office",
        rng=StubRng(2.5),
    )

    assert occupancy == pytest.approx(87.5)


def test_calculate_building_occupancy_percent_uses_holiday_profile():
    occupancy = calculate_building_occupancy_percent(hour=10, day_of_week=2, is_weekend=False, is_holiday=True)
    assert occupancy == pytest.approx(5.0)


def test_lifecycle_occupancy_generation_uses_simulator_rng(orchestrator):
    orchestrator.simulated_time = datetime(2026, 1, 14, 10, 0)
    orchestrator._scenario_rng = SequenceRng([1.05, 5.0, 1.05, 5.0, 1.05, 5.0, 1.05, 5.0, 1.05])
    orchestrator.seasonal_modeler = None

    occupancy_data = orchestrator._generate_occupancy_for_hour(10)

    assert occupancy_data["Zone-B1-001"] == pytest.approx(10.5)
    assert occupancy_data["Zone-L1-A"] == pytest.approx(94.5)


def test_lifecycle_building_occupancy_uses_site_holiday_calendar(orchestrator):
    orchestrator.simulated_time = datetime(2026, 12, 25, 10, 0)
    orchestrator.seasonal_modeler = None

    assert orchestrator._calculate_occupancy(10) == 5


def test_lifecycle_zone_occupancy_includes_meeting_rooms(orchestrator):
    orchestrator.simulated_time = datetime(2026, 1, 14, 11, 0)
    orchestrator.seasonal_modeler = None

    occupancy_data = orchestrator._generate_occupancy_for_hour(11)

    assert "Zone-L1-MR1" in occupancy_data
    assert "Zone-L2-MR1" in occupancy_data
    assert "Zone-L3-MR1" in occupancy_data


def test_lifecycle_zone_occupancy_includes_five_office_zones_per_office_floor(orchestrator):
    orchestrator.simulated_time = datetime(2026, 1, 14, 11, 0)
    orchestrator.seasonal_modeler = None

    occupancy_data = orchestrator._generate_occupancy_for_hour(11)

    for zone_id in [
        "Zone-L1-A",
        "Zone-L1-B",
        "Zone-L1-C",
        "Zone-L1-D",
        "Zone-L1-E",
        "Zone-L2-A",
        "Zone-L2-B",
        "Zone-L2-C",
        "Zone-L2-D",
        "Zone-L2-E",
        "Zone-L3-A",
        "Zone-L3-B",
        "Zone-L3-C",
        "Zone-L3-D",
        "Zone-L3-E",
    ]:
        assert zone_id in occupancy_data
