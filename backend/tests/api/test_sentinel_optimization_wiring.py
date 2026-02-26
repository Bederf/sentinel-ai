"""
SENTINEL AI Optimization Wiring Tests (v28.0)

Tests that the lifecycle simulation calls real SENTINEL services through the BMS
data layer — NOT by feeding simulation internals directly to the LLM.

Architecture under test:
  Simulation → persist_hourly_state() → Supabase (fake BMS)
  SENTINEL  → AIOptimizerService.analyze_building() → reads Supabase → Claude → QualityGate

Tests cover:
- State fingerprint quantization and caching
- analyze_building() invocation (production code path)
- Budget exhaustion fallback to hardcoded
- LLM unavailability fallback to hardcoded
- local_ai_only skip
- DALI exclusion (Tridonic-first)
- Mode dispatch (sentinel/hardcoded/hybrid)
- Hardcoded fallback still works
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.lifecycle_orchestrator import LifecycleOrchestrator


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
def orchestrator():
    """Create a LifecycleOrchestrator instance with mocked dependencies."""
    with patch("app.database.repositories.equipment_repository.EquipmentRepository"):
        with patch("app.database.repositories.prediction_repository.PredictionRepository"):
            with patch("app.database.repositories.recommendation_repository.get_recommendation_repository"):
                with patch("app.database.repositories.work_order_repository.get_work_order_repository"):
                    with patch("app.services.feedback_collection_service.get_feedback_collection_service"):
                        with patch("app.services.device_control_service.get_device_control_service"):
                            with patch("app.services.simulation_persistence.get_simulation_persistence"):
                                orch = LifecycleOrchestrator(task_id="test-task", site_id="site-002")
                                orch.simulated_time = datetime(2026, 1, 15, 10, 0)
                                orch._equipment_health = {
                                    "S002-FCU-L1-A": 85.0,
                                    "S002-AHU-B1-001": 90.0,
                                    "S002-CHILLER-B1-001": 78.0,
                                }
                                return orch


# ============================================================================
# State Fingerprint Tests
# ============================================================================


class TestStateFingerprint:
    """Test _compute_state_fingerprint quantization."""

    def test_occupancy_10pct_buckets(self, orchestrator):
        """Occupancy values within same 10% bucket produce same fingerprint."""
        fp1 = orchestrator._compute_state_fingerprint(51, 10, 50)
        fp2 = orchestrator._compute_state_fingerprint(59, 10, 50)
        assert fp1 == fp2, "51% and 59% should be in same 50% bucket"

    def test_occupancy_different_buckets(self, orchestrator):
        """Occupancy values in different 10% buckets produce different fingerprints."""
        fp1 = orchestrator._compute_state_fingerprint(49, 10, 50)
        fp2 = orchestrator._compute_state_fingerprint(51, 10, 50)
        assert fp1 != fp2, "49% (40 bucket) and 51% (50 bucket) should differ"

    def test_hour_3hr_periods(self, orchestrator):
        """Hours within same 3-hour period produce same fingerprint."""
        fp1 = orchestrator._compute_state_fingerprint(50, 10, 50)
        fp2 = orchestrator._compute_state_fingerprint(50, 11, 50)
        assert fp1 == fp2, "Hour 10 and 11 should be in same 9-11 bucket"

    def test_hour_different_periods(self, orchestrator):
        """Hours in different 3-hour periods produce different fingerprints."""
        fp1 = orchestrator._compute_state_fingerprint(50, 8, 50)
        fp2 = orchestrator._compute_state_fingerprint(50, 12, 50)
        assert fp1 != fp2, "Hour 8 (6-8 bucket) and 12 (12-14 bucket) should differ"

    def test_daylight_25pct_buckets(self, orchestrator):
        """Daylight values within same 25% bucket produce same fingerprint."""
        fp1 = orchestrator._compute_state_fingerprint(50, 10, 30)
        fp2 = orchestrator._compute_state_fingerprint(50, 10, 49)
        assert fp1 == fp2, "30% and 49% should be in same 25% bucket"

    def test_fingerprint_string_format(self, orchestrator):
        """Fingerprint has expected string format."""
        fp = orchestrator._compute_state_fingerprint(75, 14, 80)
        assert fp.startswith("occ70_hr12_dl75_hvac")


# ============================================================================
# SENTINEL Optimization (via analyze_building) Tests
# ============================================================================


class TestSentinelOptimization:
    """Test _sentinel_optimization calls AIOptimizerService.analyze_building()."""

    @pytest.mark.asyncio
    async def test_cache_hit_reuses_recs(self, orchestrator):
        """Same fingerprint should reuse cached recommendations."""
        orchestrator._last_state_fingerprint = orchestrator._compute_state_fingerprint(50, 10, 50)
        orchestrator._cached_sentinel_recs = [{"equipment": "S002-FCU-L1-A", "cached": True}]

        equipment = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
        recs = await orchestrator._sentinel_optimization(equipment, "hour_10", 50, 50, 10)

        assert len(recs) == 1
        assert recs[0].get("cached") is True

    @pytest.mark.asyncio
    async def test_calls_analyze_building(self, orchestrator):
        """sentinel mode should call AIOptimizerService.analyze_building()."""
        mock_result = MagicMock()
        mock_result.recommendations = [
            {
                "equipment_id": "S002-FCU-L1-A",
                "equipment_name": "FCU L1 A",
                "point_name": "zone_cooling_setpoint",
                "recommended_value": 23.0,
                "reason": "Low occupancy — raise setpoint",
                "savings_kwh": 8,
            }
        ]
        mock_result.confidence = 0.85
        mock_result.quality_gate_status = "pass"
        mock_result.quality_gate_enforcement = "normal"

        mock_optimizer = AsyncMock()
        mock_optimizer.analyze_building.return_value = mock_result

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.local_ai_only = False
            mock_settings.simulation_llm_budget_max_calls = 5000

            with patch("app.services.ai_optimizer.get_ai_optimizer", return_value=mock_optimizer):
                equipment = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
                recs = await orchestrator._sentinel_optimization(equipment, "hour_10", 50, 50, 10)

        assert len(recs) == 1
        assert recs[0]["equipment"] == "S002-FCU-L1-A"
        assert recs[0]["source"] == "sentinel_analyze_building"
        assert recs[0]["quality_gate_status"] == "pass"
        mock_optimizer.analyze_building.assert_called_once_with("site-002")
        assert orchestrator._llm_call_count == 1

    @pytest.mark.asyncio
    async def test_budget_exhaustion_fallback(self, orchestrator):
        """When LLM budget is exhausted, fall back to hardcoded."""
        orchestrator.current_scenario = MagicMock(demo_mode=True)
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.simulation_llm_budget_max_calls = 10
            mock_settings.local_ai_only = False
            orchestrator._llm_call_count = 10  # Budget exhausted

            equipment = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
            # occupancy 15% is below demo threshold of 30
            recs = await orchestrator._sentinel_optimization(equipment, "hour_10", 15, 50, 10)

            assert any(r.get("control_point") == "cooling_setpoint" for r in recs)

    @pytest.mark.asyncio
    async def test_analyze_building_failure_fallback(self, orchestrator):
        """When analyze_building() fails, fall back to hardcoded optimization."""
        orchestrator.current_scenario = MagicMock(demo_mode=True)

        mock_optimizer = AsyncMock()
        mock_optimizer.analyze_building.side_effect = RuntimeError("Claude unavailable")

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.local_ai_only = False
            mock_settings.simulation_llm_budget_max_calls = 5000

            with patch("app.services.ai_optimizer.get_ai_optimizer", return_value=mock_optimizer):
                equipment = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
                recs = await orchestrator._sentinel_optimization(equipment, "hour_10", 15, 50, 10)

        # Should get hardcoded FCU recommendation
        assert any(r.get("control_point") == "cooling_setpoint" for r in recs)

    @pytest.mark.asyncio
    async def test_local_ai_only_skips_sentinel(self, orchestrator):
        """local_ai_only=true should skip SENTINEL and use hardcoded."""
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.local_ai_only = True

            equipment = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
            recs = await orchestrator._sentinel_optimization(equipment, "hour_10", 25, 50, 10)

            assert isinstance(recs, list)

    @pytest.mark.asyncio
    async def test_llm_call_increments_counter(self, orchestrator):
        """Each analyze_building() call should increment the counter."""
        mock_result = MagicMock()
        mock_result.recommendations = []
        mock_result.quality_gate_status = "pass"
        mock_result.quality_gate_enforcement = "normal"

        mock_optimizer = AsyncMock()
        mock_optimizer.analyze_building.return_value = mock_result

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.local_ai_only = False
            mock_settings.simulation_llm_budget_max_calls = 5000

            with patch("app.services.ai_optimizer.get_ai_optimizer", return_value=mock_optimizer):
                equipment = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
                await orchestrator._sentinel_optimization(equipment, "hour_10", 50, 50, 10)

        assert orchestrator._llm_call_count == 1

    @pytest.mark.asyncio
    async def test_uses_site_id_not_prefix(self, orchestrator):
        """analyze_building() should be called with site_id ('site-002'), not prefix ('S002')."""
        mock_result = MagicMock()
        mock_result.recommendations = []

        mock_optimizer = AsyncMock()
        mock_optimizer.analyze_building.return_value = mock_result

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.local_ai_only = False
            mock_settings.simulation_llm_budget_max_calls = 5000

            with patch("app.services.ai_optimizer.get_ai_optimizer", return_value=mock_optimizer):
                equipment = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
                await orchestrator._sentinel_optimization(equipment, "hour_10", 50, 50, 10)

        # Must pass the full site_id, not the S002 prefix
        mock_optimizer.analyze_building.assert_called_once_with("site-002")


# ============================================================================
# Hardcoded Fallback Tests
# ============================================================================


class TestHardcodedFallback:
    """Test _hardcoded_optimization_batch."""

    def test_fcu_low_occupancy(self, orchestrator):
        """FCU generates cooling_setpoint rec at low occupancy."""
        orchestrator.current_scenario = MagicMock(demo_mode=True)
        equipment = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
        recs = orchestrator._hardcoded_optimization_batch(equipment, "hour_10", 20, 50, 10)
        assert len(recs) >= 1
        assert recs[0]["control_point"] == "cooling_setpoint"
        assert recs[0]["target_value"] == 24.0

    def test_ahu_low_occupancy(self, orchestrator):
        """AHU generates supply_temp_setpoint rec at low occupancy."""
        orchestrator.current_scenario = MagicMock(demo_mode=True)
        equipment = [{"code": "S002-AHU-B1-001", "type": "AHU"}]
        recs = orchestrator._hardcoded_optimization_batch(equipment, "hour_10", 20, 50, 10)
        assert len(recs) >= 1
        assert recs[0]["control_point"] == "supply_temp_setpoint"

    def test_chiller_recommendation(self, orchestrator):
        """Chiller generates chw_setpoint rec at low occupancy."""
        orchestrator.current_scenario = MagicMock(demo_mode=True)
        equipment = [{"code": "S002-CHILLER-B1-001", "type": "CHILLER"}]
        recs = orchestrator._hardcoded_optimization_batch(equipment, "hour_10", 20, 50, 10)
        assert len(recs) >= 1
        assert recs[0]["control_point"] == "chw_setpoint"

    def test_dali_excluded_from_hardcoded(self, orchestrator):
        """DALI equipment should not generate hardcoded recommendations."""
        orchestrator.current_scenario = MagicMock(demo_mode=True)
        equipment = [{"code": "S002-DALI-L1-A", "type": "DALI"}]
        recs = orchestrator._hardcoded_optimization_batch(equipment, "hour_10", 50, 50, 10)
        assert len(recs) == 0

    def test_mixed_equipment_batch(self, orchestrator):
        """Multiple equipment types in one batch."""
        orchestrator.current_scenario = MagicMock(demo_mode=True)
        equipment = [
            {"code": "S002-FCU-L1-A", "type": "FCU"},
            {"code": "S002-AHU-B1-001", "type": "AHU"},
            {"code": "S002-VAV-L1-A", "type": "VAV"},
        ]
        recs = orchestrator._hardcoded_optimization_batch(equipment, "hour_10", 20, 50, 10)
        eq_codes = [r["equipment"] for r in recs]
        assert "S002-FCU-L1-A" in eq_codes
        assert "S002-AHU-B1-001" in eq_codes
        assert "S002-VAV-L1-A" in eq_codes


# ============================================================================
# Mode Dispatch Tests
# ============================================================================


class TestModeDispatch:
    """Test _ai_optimization mode switching."""

    @pytest.mark.asyncio
    async def test_sentinel_mode_calls_sentinel(self, orchestrator):
        """sentinel mode should call _sentinel_optimization."""
        orchestrator._optimization_mode = "sentinel"

        mock_sentinel = AsyncMock(return_value=[])
        orchestrator._sentinel_optimization = mock_sentinel

        orchestrator.equipment_repo = MagicMock()
        orchestrator.equipment_repo.get_all.return_value = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
        orchestrator.device_control_service = MagicMock()
        orchestrator.device_control_service.is_controllable.return_value = True

        await orchestrator._ai_optimization("hour_10")
        mock_sentinel.assert_called_once()

    @pytest.mark.asyncio
    async def test_hardcoded_mode_skips_sentinel(self, orchestrator):
        """hardcoded mode should not call _sentinel_optimization."""
        orchestrator._optimization_mode = "hardcoded"
        orchestrator.current_scenario = MagicMock(demo_mode=False)

        mock_sentinel = AsyncMock(return_value=[])
        orchestrator._sentinel_optimization = mock_sentinel

        orchestrator.equipment_repo = MagicMock()
        orchestrator.equipment_repo.get_all.return_value = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
        orchestrator.device_control_service = MagicMock()
        orchestrator.device_control_service.is_controllable.return_value = True

        await orchestrator._ai_optimization("hour_10")
        mock_sentinel.assert_not_called()

    @pytest.mark.asyncio
    async def test_hybrid_mode_calls_both(self, orchestrator):
        """hybrid mode should call both sentinel and hardcoded."""
        orchestrator._optimization_mode = "hybrid"
        orchestrator.current_scenario = MagicMock(demo_mode=False)
        orchestrator.recommendation_repo = AsyncMock()
        orchestrator.recommendation_repo.create = AsyncMock()

        mock_sentinel = AsyncMock(
            return_value=[{"equipment": "S002-FCU-L1-A", "control_point": "cooling_setpoint", "target_value": 23.0}]
        )
        orchestrator._sentinel_optimization = mock_sentinel

        mock_hardcoded = MagicMock(
            return_value=[
                {
                    "equipment": "S002-FCU-L1-A",
                    "control_point": "cooling_setpoint",
                    "target_value": 24.0,
                    "reason": "test",
                    "description": "test",
                    "savings": 5,
                }
            ]
        )
        orchestrator._hardcoded_optimization_batch = mock_hardcoded

        orchestrator.equipment_repo = MagicMock()
        orchestrator.equipment_repo.get_all.return_value = [{"code": "S002-FCU-L1-A", "type": "FCU"}]
        orchestrator.device_control_service = MagicMock()
        orchestrator.device_control_service.is_controllable.return_value = True

        await orchestrator._ai_optimization("hour_10")
        mock_sentinel.assert_called_once()
        mock_hardcoded.assert_called_once()


# ============================================================================
# Notification Wiring Tests
# ============================================================================


class TestWorkOrderNotifications:
    """Test that _auto_create_work_order sends Telegram/email notifications."""

    @pytest.mark.asyncio
    async def test_wo_triggers_sentry_notification(self, orchestrator):
        """Work order creation should call _notify_sentry when sentry_notifications enabled."""
        orchestrator.current_scenario = MagicMock(sentry_notifications=True)
        orchestrator.work_order_repo = MagicMock()
        orchestrator.work_order_repo.create = MagicMock()
        orchestrator._events = []

        mock_notify = AsyncMock()
        orchestrator._notify_sentry = mock_notify

        with patch("app.database.repositories.technician_repository.TechnicianRepository") as mock_tech_cls:
            mock_tech = MagicMock()
            mock_tech.get_technician_for_equipment_code = AsyncMock(return_value={"name": "John Smith"})
            mock_tech_cls.return_value = mock_tech

            await orchestrator._auto_create_work_order("S002-CHILLER-B1-001", "chiller", 35.0, 100)

        mock_notify.assert_called_once()
        call_args = mock_notify.call_args
        equipment_dict = call_args[0][0]
        fault_info = call_args[0][1]
        wo_code = call_args[0][2]

        assert equipment_dict["type"] == "chiller"
        assert fault_info["equipment_code"] == "S002-CHILLER-B1-001"
        assert "35.0%" in fault_info["fault_type"]
        assert fault_info["severity"] == 90  # health < 40 → severity 90
        assert wo_code.startswith("WO-SIM-")

    @pytest.mark.asyncio
    async def test_wo_skips_notification_when_disabled(self, orchestrator):
        """Work order creation should NOT call _notify_sentry when notifications disabled."""
        orchestrator.current_scenario = MagicMock(sentry_notifications=False)
        orchestrator.work_order_repo = MagicMock()
        orchestrator.work_order_repo.create = MagicMock()
        orchestrator._events = []

        mock_notify = AsyncMock()
        orchestrator._notify_sentry = mock_notify

        with patch("app.database.repositories.technician_repository.TechnicianRepository") as mock_tech_cls:
            mock_tech = MagicMock()
            mock_tech.get_technician_for_equipment_code = AsyncMock(return_value=None)
            mock_tech_cls.return_value = mock_tech

            await orchestrator._auto_create_work_order("S002-FCU-L1-A", "fcu", 45.0, 200)

        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_wo_skips_notification_when_no_scenario(self, orchestrator):
        """Work order creation should NOT call _notify_sentry when no scenario set."""
        orchestrator.current_scenario = None
        orchestrator.work_order_repo = MagicMock()
        orchestrator.work_order_repo.create = MagicMock()
        orchestrator._events = []

        mock_notify = AsyncMock()
        orchestrator._notify_sentry = mock_notify

        with patch("app.database.repositories.technician_repository.TechnicianRepository") as mock_tech_cls:
            mock_tech = MagicMock()
            mock_tech.get_technician_for_equipment_code = AsyncMock(return_value=None)
            mock_tech_cls.return_value = mock_tech

            await orchestrator._auto_create_work_order("S002-AHU-B1-001", "ahu", 42.0, 300)

        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_wo_medium_severity_for_health_above_40(self, orchestrator):
        """Health >= 40 should produce severity 60 (MEDIUM), not 90 (HIGH)."""
        orchestrator.current_scenario = MagicMock(sentry_notifications=True)
        orchestrator.work_order_repo = MagicMock()
        orchestrator.work_order_repo.create = MagicMock()
        orchestrator._events = []

        mock_notify = AsyncMock()
        orchestrator._notify_sentry = mock_notify

        with patch("app.database.repositories.technician_repository.TechnicianRepository") as mock_tech_cls:
            mock_tech = MagicMock()
            mock_tech.get_technician_for_equipment_code = AsyncMock(return_value=None)
            mock_tech_cls.return_value = mock_tech

            await orchestrator._auto_create_work_order("S002-FCU-L1-A", "fcu", 45.0, 150)

        fault_info = mock_notify.call_args[0][1]
        assert fault_info["severity"] == 60  # health >= 40 → MEDIUM
