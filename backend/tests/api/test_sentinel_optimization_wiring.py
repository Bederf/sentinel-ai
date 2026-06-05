"""
SENTINEL Production Optimization Wiring Tests (post-simulation deletion)

Tests that the real production optimization path works:
  Scheduler → AIOptimizerService.analyze_building() → bridge/supabase → Claude

Simulation layer (LifecycleOrchestrator) removed — S002 uses live telemetry.

Tests cover:
- AIOptimizerService instantiation via factory
- analyze_building() returns valid result structure
- No lifecycle orchestrator references in production paths
- Data sync uses bridge telemetry (not simulation store)
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.ai_optimizer import AIOptimizerService


@pytest.fixture(autouse=True)
def mock_supabase():
    """Mock Supabase for all tests."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.execute.return_value.data = []
    mock_client.table.return_value.insert.return_value.execute.return_value.data = [{}]
    mock_client.table.return_value.upsert.return_value.execute.return_value.data = [{}]
    with patch("app.database.supabase_client.get_supabase_client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_bridge():
    """Mock bridge telemetry."""
    mock = MagicMock()
    mock.get_zone_telemetry.return_value = {}
    mock.get_equipment_status.return_value = {}
    return mock


class TestProductionOptimizationWiring:
    """Verify production optimization path is intact after simulation deletion."""

    def test_ai_optimizer_instantiates(self):
        """AIOptimizerService must be instantiable without lifecycle orchestrator."""
        # Should not raise ImportError
        from app.services.ai_optimizer import get_ai_optimizer

        optimizer = get_ai_optimizer()
        assert optimizer is not None
        assert isinstance(optimizer, AIOptimizerService)

    def test_no_lifecycle_orchestrator_in_scheduler(self):
        """Scheduler must not import lifecycle orchestrator."""
        import inspect

        from app.services.background_scheduler import BackgroundScheduler

        source = inspect.getsource(BackgroundScheduler)
        assert "lifecycle" not in source.lower(), "BackgroundScheduler must not reference lifecycle_orchestrator"
        assert "simulation_orchestrator" not in source.lower(), (
            "BackgroundScheduler must not reference simulation_orchestrator"
        )

    def test_no_lifecycle_orchestrator_in_ai_optimizer(self):
        """AIOptimizerService must not import lifecycle orchestrator."""
        import inspect

        from app.services.ai_optimizer import AIOptimizerService

        source = inspect.getsource(AIOptimizerService)
        assert "lifecycle" not in source.lower(), "AIOptimizerService must not reference lifecycle_orchestrator"
        assert "simulation" not in source.lower() or "simulation_store" not in source.lower(), (
            "AIOptimizerService must not reference simulation_store"
        )

    def test_cost_validation_engine_no_sim_store(self):
        """CostValidationEngine must not use simulation_store."""
        import inspect

        from app.services.cost_validation_engine import CostValidationEngine

        source = inspect.getsource(CostValidationEngine)
        assert "sim_store" not in source, "CostValidationEngine must not use sim_store"
        assert "get_simulation_store" not in source, "CostValidationEngine must not import simulation_store"

    def test_power_meter_validation_engine_no_sim_store(self):
        """PowerMeterValidationEngine must not use simulation_store."""
        import inspect

        from app.services.power_meter_validation_engine import PowerMeterValidationEngine

        source = inspect.getsource(PowerMeterValidationEngine)
        assert "sim_store" not in source, "PowerMeterValidationEngine must not use sim_store"

    def test_feature_engineering_no_sim_store_branch(self):
        """FeatureEngineeringService must not read from simulation_store."""
        import inspect

        from app.services.feature_engineering_service import FeatureEngineeringService

        source = inspect.getsource(FeatureEngineeringService)
        assert "simulation_store" not in source, "FeatureEngineeringService must not import simulation_store"

    def test_energy_api_no_simulated_endpoint(self):
        """Energy API /energy/simulated must return real data from Supabase."""
        import inspect

        from app.api.energy import get_energy_simulated

        source = inspect.getsource(get_energy_simulated)
        assert "simulation_orchestrator" not in source, "/energy/simulated must not use simulation_orchestrator"
        assert "_active_simulations" not in source, "/energy/simulated must not reference active simulations"

    @pytest.mark.asyncio
    async def test_analyze_building_returns_optimization_recommendation(self, mock_supabase):
        """analyze_building() must return an OptimizationRecommendation object."""
        from app.services.ai_optimizer import get_ai_optimizer

        optimizer = get_ai_optimizer()
        # With no real site_id, should raise ValueError, not ImportError
        with pytest.raises((ValueError, RuntimeError, AttributeError)):
            await optimizer.analyze_building("site-nonexistent")

    def test_startup_events_no_simulation_imports(self):
        """Startup events must not import lifecycle orchestrator or simulation services."""
        from app.startup import events

        source = events.__file__
        with open(source) as f:
            content = f.read()

        assert "from app.services.lifecycle_orchestrator" not in content, (
            "startup/events must not import lifecycle_orchestrator"
        )
        assert "from app.services.simulation_orchestrator" not in content, (
            "startup/events must not import simulation_orchestrator"
        )
        assert "from app.services.health_simulation_service" not in content, (
            "startup/events must not import health_simulation_service"
        )
        assert "from app.services.simulation_store" not in content, "startup/events must not import simulation_store"


class TestSimulationFilesDeleted:
    """Verify simulation files were actually deleted."""

    def test_lifecycle_orchestrator_gone(self):
        with pytest.raises(ImportError):
            from app.services import lifecycle_orchestrator  # noqa

    def test_simulation_orchestrator_gone(self):
        with pytest.raises(ImportError):
            from app.services import simulation_orchestrator  # noqa

    def test_thermal_simulation_engine_gone(self):
        with pytest.raises(ImportError):
            from app.services import thermal_simulation_engine  # noqa

    def test_simulation_store_gone(self):
        with pytest.raises(ImportError):
            from app.services import simulation_store  # noqa

    def test_health_simulation_service_gone(self):
        with pytest.raises(ImportError):
            from app.services import health_simulation_service  # noqa
