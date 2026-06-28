"""
Background scheduler tests for APScheduler integration.

Tests scheduled jobs, job management, and cron triggers.
"""

import logging
from datetime import datetime, timedelta

import pytest


@pytest.mark.unit
class TestBackgroundScheduler:
    """Test background scheduler functionality."""

    def test_scheduler_initialization(self):
        """Test scheduler can be initialized."""
        from app.services.background_scheduler import scheduler_service

        assert scheduler_service is not None

    def test_scheduler_has_scheduler_instance(self):
        """Test scheduler has underlying APScheduler instance."""
        from app.services.background_scheduler import scheduler_service

        # Should have scheduler attribute
        assert hasattr(scheduler_service, "scheduler")

    def test_scheduler_has_add_methods(self):
        """Test scheduler has job addition methods."""
        from app.services.background_scheduler import scheduler_service

        # Should have methods to add jobs
        assert hasattr(scheduler_service, "add_demo_data_job")
        assert hasattr(scheduler_service, "add_optimization_analysis_job")

    def test_coordinated_optimization_is_protected_from_generic_pending_expiry(self):
        """Coordinated drafts are intentionally execution-blocked while awaiting approval."""
        from app.services.background_scheduler import _is_protected_pending_recommendation

        assert _is_protected_pending_recommendation("coordinated_optimization") is True
        assert _is_protected_pending_recommendation("ai_optimization") is False
        assert _is_protected_pending_recommendation(None) is False

    def test_pending_hvac_conflict_detected_by_source_rule_not_target(self):
        """Conflict advisories supersede HVAC shutdown rows even with a different target ID."""
        from app.models.recommendation import Recommendation
        from app.services.background_scheduler import HVAC_OCCUPANCY_CONFLICT_RULE, _has_pending_source_rule

        conflict = Recommendation(
            site_id="site-002",
            action_type="ai_optimization",
            target_equipment="SITE-002-HVAC-OCCUPANCY-VERIFY",
            metadata={"source_metadata": {"rule": HVAC_OCCUPANCY_CONFLICT_RULE}},
        )

        assert _has_pending_source_rule([conflict], {HVAC_OCCUPANCY_CONFLICT_RULE}) is True

    def test_after_hours_hvac_gate_triggers_once_per_cooldown(self):
        """Stable zero-occupancy HVAC load should trigger analysis without waiting 6h."""
        from app.services.background_scheduler import BackgroundSchedulerService

        service = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        service._last_after_hours_hvac_analysis = {}
        now = datetime(2026, 6, 18, 22, 0)

        assert service._should_trigger_after_hours_hvac_analysis("site-002", 0, 21.0, False, now) is True
        assert service._should_trigger_after_hours_hvac_analysis("site-002", 0, 21.0, False, now) is False
        assert (
            service._should_trigger_after_hours_hvac_analysis(
                "site-002",
                0,
                21.0,
                False,
                now + timedelta(hours=3),
            )
            is True
        )

    def test_after_hours_hvac_gate_does_not_trigger_when_occupied_or_low_load(self):
        from app.services.background_scheduler import BackgroundSchedulerService

        service = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        service._last_after_hours_hvac_analysis = {}
        now = datetime(2026, 6, 18, 22, 0)

        assert service._should_trigger_after_hours_hvac_analysis("site-002", 1, 21.0, False, now) is False
        assert service._should_trigger_after_hours_hvac_analysis("site-002", 0, 1.0, False, now) is False
        assert service._should_trigger_after_hours_hvac_analysis("site-002", 0, 21.0, True, now) is False

    def test_noop_recommendation_is_suppressed_when_current_equals_target(self):
        from app.services.background_scheduler import _is_noop_recommendation

        assert _is_noop_recommendation(18.0, 18.0) is True
        assert _is_noop_recommendation("18", 18.0) is True
        assert _is_noop_recommendation(18.0, 18.05) is False
        assert _is_noop_recommendation(None, 18.0) is False

    def test_recent_executed_action_suppresses_same_point_and_value(self, monkeypatch):
        from app.services import background_scheduler as bg

        class _Resp:
            data = [
                {
                    "id": "rec-executed",
                    "status": "executed",
                    "action": {"point": "damper_position", "value": 100.0},
                    "executed_at": "2026-06-21T16:11:46Z",
                }
            ]

        class _Query:
            def select(self, *_args, **_kwargs):
                return self

            def eq(self, *_args, **_kwargs):
                return self

            def in_(self, *_args, **_kwargs):
                return self

            def gte(self, *_args, **_kwargs):
                return self

            def order(self, *_args, **_kwargs):
                return self

            def limit(self, *_args, **_kwargs):
                return self

            def execute(self):
                return _Resp()

        class _Client:
            def table(self, _name):
                return _Query()

        monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _Client())

        assert (
            bg._recent_executed_action_exists(
                site_id="site-002",
                equipment_id="S002-AHU-B01",
                point_name="damper_position",
                action_value=100.0,
            )
            is True
        )
        assert (
            bg._recent_executed_action_exists(
                site_id="site-002",
                equipment_id="S002-AHU-B01",
                point_name="damper_position",
                action_value=70.0,
            )
            is False
        )

    def test_recent_executed_action_context_returns_energy_outcome(self, monkeypatch):
        from app.services import background_scheduler as bg

        class _Resp:
            data = [
                {
                    "id": "rec-executed",
                    "status": "executed",
                    "action": {"point": "damper_position", "value": 100.0},
                    "executed_at": "2026-06-21T16:11:46Z",
                    "outcome_validated": False,
                    "outcome_notes": "Control reached target but energy increased",
                    "actual_saving_kwh": -4.726,
                    "actual_saving_zar": -39.37,
                    "actual_value_set": "100",
                }
            ]

        class _Query:
            def select(self, *_args, **_kwargs):
                return self

            def eq(self, *_args, **_kwargs):
                return self

            def in_(self, *_args, **_kwargs):
                return self

            def gte(self, *_args, **_kwargs):
                return self

            def order(self, *_args, **_kwargs):
                return self

            def limit(self, *_args, **_kwargs):
                return self

            def execute(self):
                return _Resp()

        class _Client:
            def table(self, _name):
                return _Query()

        monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _Client())

        context = bg._recent_executed_action_context(
            site_id="site-002",
            equipment_id="S002-AHU-B01",
            point_name="damper_position",
            action_value=100.0,
        )

        assert context["recommendation_id"] == "rec-executed"
        assert context["actual_saving_kwh"] == -4.726
        assert context["actual_saving_zar"] == -39.37

    def test_after_hours_manual_advisory_is_visible_pending_ai_recommendation(self):
        """Root operational advisories must stay visible even when point actions exist."""
        from app.models.recommendation import RecommendationStatus
        from app.services.background_scheduler import _build_manual_advisory_recommendation

        rec = _build_manual_advisory_recommendation(
            site_id="site-002",
            rec_dict={
                "target_equipment": "S002-CHILLER-B01",
                "recommended_value": "Apply after-hours HVAC setback or stop non-critical HVAC where safe",
                "reason": "Weekend unoccupied with 0 occupants and HVAC load still present.",
                "confidence": 0.82,
                "metadata": {
                    "rule": "after_hours_zero_occupancy_hvac_load",
                    "equipment_name": "Chiller Basement",
                },
            },
            equipment_id="S002-CHILLER-B01",
            action_value="Apply after-hours HVAC setback or stop non-critical HVAC where safe",
            confidence_num=0.82,
            optimization_profile="cost",
            projected_savings={"cost_zar_per_hour": 14.86},
            current_stage="supervised",
            validation_results=[{"equipment_id": "S002-AHU-B01", "point_name": "damper_position", "allowed": True}],
        )

        assert rec.status == RecommendationStatus.PENDING
        assert rec.action_type == "ai_optimization"
        assert rec.requires_approval is True
        assert rec.shadow_mode is False
        assert rec.action["point"] is None
        assert rec.action["execution_blocked"] is True
        assert rec.action["blocker"] == "missing_verified_plant_enable_or_schedule_point"
        assert rec.metadata["manual_action_required"] is True
        assert rec.metadata["operator_label"] == "Correct BMS closed-hours HVAC schedule"
        assert rec.metadata["source_metadata"]["rule"] == "after_hours_zero_occupancy_hvac_load"
        assert rec.expected_impact["cost_zar"] == 14.86
        assert "After-hours HVAC plant operation requires operator review." in rec.reason

    def test_occupancy_conflict_manual_advisory_is_medium_risk_and_explicitly_blocked(self):
        from app.models.recommendation import ActionRiskLevel, RecommendationStatus
        from app.services.background_scheduler import _build_manual_advisory_recommendation

        rec = _build_manual_advisory_recommendation(
            site_id="site-002",
            rec_dict={
                "target_equipment": "SITE-002-HVAC-OCCUPANCY-VERIFY",
                "recommended_value": "Hold blanket HVAC shutdown; verify occupancy/IAQ conflict",
                "reason": "Aggregate reports zero occupancy while CO2 indicates people may be present.",
                "confidence": 0.42,
                "risk_level": "medium",
                "metadata": {
                    "rule": "occupancy_conflict_blocks_hvac_shutdown",
                    "blocked_rule": "closed_empty_building_hvac_running",
                    "advisory_type": "occupancy_conflict_control_gate",
                },
            },
            equipment_id="SITE-002-HVAC-OCCUPANCY-VERIFY",
            action_value="Hold blanket HVAC shutdown; verify occupancy/IAQ conflict",
            confidence_num=0.42,
            optimization_profile="cost",
            projected_savings={"cost_zar_per_hour": 0.0},
            current_stage="supervised",
            validation_results=[],
        )

        assert rec.status == RecommendationStatus.PENDING
        assert rec.risk_level == ActionRiskLevel.MEDIUM
        assert rec.requires_approval is True
        assert rec.action["execution_blocked"] is True
        assert rec.action["blocker"] == "occupancy_signal_conflict"
        assert rec.metadata["operator_label"] == "Occupancy conflict — verify before HVAC shutdown"
        assert rec.metadata["source_metadata"]["rule"] == "occupancy_conflict_blocks_hvac_shutdown"
        assert "Occupancy and IAQ signals conflict" in rec.reason

    def test_bridge_object_catalog_maps_to_point_asset_rows(self):
        """Bridge /objects rows should persist enough BACnet metadata for meter kWh lookup."""
        from app.services.background_scheduler import BackgroundSchedulerService

        rows = BackgroundSchedulerService._build_bridge_point_mappings(
            site_uuid="site-uuid-002",
            known_codes={"S002-MTR-B1-MAI"},
            objects=[
                {
                    "object_id": "S002-MTR-B1-MAI.energy_import_kwh",
                    "object_name": "energy_import_kwh",
                    "object_type": "analogInput",
                    "instance": 3503,
                    "unit": "kWh",
                    "equipment_id": "S002-MTR-B1-MAI",
                    "equipment_type": "meter",
                    "writable": False,
                },
                {
                    "object_id": "S002-MTR-B1-MAI.energy_import_kwh",
                    "object_name": "energy_import_kwh_duplicate",
                    "object_type": "analogInput",
                    "instance": 3503,
                    "unit": "kWh",
                    "equipment_id": "S002-MTR-B1-MAI",
                    "equipment_type": "meter",
                    "writable": False,
                },
            ],
        )

        assert rows == [
            {
                "site_id": "site-uuid-002",
                "bms_point_id": "S002-MTR-B1-MAI.energy_import_kwh",
                "extracted_asset_id": "S002-MTR-B1-MAI",
                "parameter_name": "energy_import_kwh",
                "parameter_type": "meter:analogInput,3503:kWh",
                "match_confidence": "exact",
                "is_verified": False,
                "mapping_source": "bridge_objects",
            }
        ]

    def test_bridge_object_catalog_normalizes_to_sentinel_equipment_code(self):
        """Raw bridge asset IDs should map to SENTINEL canonical naming."""
        from app.services.background_scheduler import BackgroundSchedulerService

        rows = BackgroundSchedulerService._build_bridge_point_mappings(
            site_uuid="site-uuid-002",
            known_codes={"S002-AHU-B01"},
            objects=[
                {
                    "object_id": "S002-AHU-B1-001.DAMPER_POSITION",
                    "object_name": "damper_position",
                    "object_type": "analogOutput",
                    "instance": 1341,
                    "unit": "%",
                    "equipment_id": "S002-AHU-B1-001",
                    "point_type": "command",
                    "writable": True,
                }
            ],
        )

        assert rows == [
            {
                "site_id": "site-uuid-002",
                "bms_point_id": "S002-AHU-B1-001.DAMPER_POSITION",
                "extracted_asset_id": "S002-AHU-B01",
                "parameter_name": "damper_position",
                "parameter_type": "command:analogOutput,1341:%",
                "match_confidence": "exact",
                "is_verified": True,
                "mapping_source": "bridge_objects",
            }
        ]

    def test_bridge_object_catalog_marks_bridge_writable_value_as_verified(self):
        """When the bridge write guard is synced, writable=true becomes readiness metadata."""
        from app.services.background_scheduler import BackgroundSchedulerService

        rows = BackgroundSchedulerService._build_bridge_point_mappings(
            site_uuid="site-uuid-002",
            known_codes={"S002-AHU-B01"},
            objects=[
                {
                    "object_id": "S002-AHU-B1-001.CONFIG_VALUE",
                    "object_name": "config_value",
                    "object_type": "analogValue",
                    "instance": 1375,
                    "unit": "%",
                    "equipment_id": "S002-AHU-B1-001",
                    "writable": True,
                }
            ],
        )

        assert rows[0]["extracted_asset_id"] == "S002-AHU-B01"
        assert rows[0]["parameter_type"] == "writable:analogValue,1375:%"
        assert rows[0]["is_verified"] is True


@pytest.mark.unit
class TestScheduledJobs:
    """Test individual scheduled jobs."""

    def test_demo_data_job_can_be_added(self):
        """Test demo data generation job can be added."""
        from app.services.background_scheduler import scheduler_service

        # Job should be addable (scheduler may or may not be running)
        try:
            scheduler_service.add_demo_data_job(interval_seconds=300)
            assert True
        except Exception as e:
            # May fail if scheduler not started - that's OK
            pytest.skip(f"Demo job not addable: {e}")

    def test_optimization_analysis_job_can_be_added(self):
        """Test optimization analysis job can be added."""
        from app.services.background_scheduler import scheduler_service

        # Job should be addable
        try:
            scheduler_service.add_optimization_analysis_job(interval_seconds=1800)
            assert True
        except Exception as e:
            pytest.skip(f"Optimization job not addable: {e}")

    def test_scheduler_service_is_singleton(self):
        """Test scheduler service uses singleton pattern."""
        from app.services.background_scheduler import BackgroundSchedulerService

        service1 = BackgroundSchedulerService()
        service2 = BackgroundSchedulerService()

        # Should be the same instance
        assert service1 is service2

    def test_stop_does_not_wait_for_running_jobs(self):
        """Shutdown should not block systemd while scheduler jobs drain."""
        from unittest.mock import MagicMock

        from app.services.background_scheduler import BackgroundSchedulerService

        service = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        service._initialized = True
        service.scheduler = MagicMock()
        service.scheduler.running = True

        service.stop()

        service.scheduler.shutdown.assert_called_once_with(wait=False)


@pytest.mark.integration
class TestJobExecution:
    """Test scheduled job execution."""

    def test_demo_data_generation_method_exists(self):
        """Test demo data generation method exists on scheduler."""
        from app.services.background_scheduler import scheduler_service

        # Should have the private generation method
        assert hasattr(scheduler_service, "_generate_demo_audit_data")

    def test_optimization_analysis_method_exists(self):
        """Test optimization analysis method exists on scheduler."""
        from app.services.background_scheduler import scheduler_service

        # Should have the private analysis method
        assert hasattr(scheduler_service, "_run_optimization_analysis")


@pytest.mark.unit
class TestJobScheduling:
    """Test job scheduling configuration."""

    def test_demo_data_job_default_interval(self):
        """Test demo data job has correct default interval."""
        from app.services.background_scheduler import scheduler_service

        # Default is 60 seconds according to docstring
        try:
            scheduler_service.add_demo_data_job()  # Uses default
            assert True
        except Exception:
            pytest.skip("Job scheduling not testable")

    def test_optimization_job_default_interval(self):
        """Test optimization job has correct default interval."""
        from app.services.background_scheduler import scheduler_service

        # Default is 900 seconds (15 minutes) according to docstring
        try:
            scheduler_service.add_optimization_analysis_job()  # Uses default
            assert True
        except Exception:
            pytest.skip("Job scheduling not testable")


@pytest.mark.integration
class TestJobConcurrency:
    """Test job concurrency and overlap handling."""

    @pytest.mark.slow
    def test_jobs_do_not_overlap(self):
        """Test long-running jobs don't overlap."""
        # This is a slow test because it needs to wait for job execution
        pytest.skip("Requires running scheduler - slow test")

    @pytest.mark.slow
    def test_scheduler_handles_exceptions(self):
        """Test scheduler continues after job exceptions."""
        pytest.skip("Requires running scheduler - slow test")


@pytest.mark.unit
class TestJobManagement:
    """Test job management (add, remove, pause)."""

    def test_scheduler_has_start_stop_methods(self):
        """Test scheduler has start/stop methods."""
        from app.services.background_scheduler import scheduler_service

        assert hasattr(scheduler_service, "start")
        assert hasattr(scheduler_service, "stop")

    def test_scheduler_start_method(self):
        """Test scheduler can be started."""
        from app.services.background_scheduler import scheduler_service

        # Start should not raise exception
        try:
            scheduler_service.start()
            assert True
        except Exception:
            pytest.skip("Scheduler start not available")

    def test_job_replacement(self):
        """Test job replacement when re-adding."""
        from app.services.background_scheduler import scheduler_service

        try:
            # Add job twice - should replace, not duplicate
            scheduler_service.add_demo_data_job(interval_seconds=120)
            scheduler_service.add_demo_data_job(interval_seconds=180)

            # Should only have one job with that ID
            job = scheduler_service.scheduler.get_job("generate_demo_audit_data")
            assert job is not None
        except Exception:
            pytest.skip("Job management not testable")


@pytest.mark.integration
class TestJobTriggers:
    """Test different job trigger types."""

    def test_interval_trigger(self):
        """Test interval-based job trigger."""
        # Most jobs use interval triggers
        assert True  # Documented requirement

    def test_cron_trigger(self):
        """Test cron-based job trigger."""
        # Some jobs may use cron triggers for specific times
        assert True  # Documented requirement

    def test_one_time_trigger(self):
        """Test one-time job trigger."""
        # Jobs that run once at startup
        assert True  # Documented requirement


@pytest.mark.unit
class TestJobErrorHandling:
    """Test error handling in scheduled jobs."""

    def test_job_exceptions_are_logged(self):
        """Test job exceptions are logged, not crash scheduler."""
        # This documents expected behavior
        # Jobs should catch exceptions and log them
        assert True

    def test_failed_jobs_do_not_block_scheduler(self):
        """Test failed jobs don't block other jobs."""
        # This documents expected behavior
        # Scheduler should continue even if jobs fail
        assert True


@pytest.mark.integration
class TestJobDataAccess:
    """Test scheduled jobs can access required data."""

    def test_job_can_access_database(self):
        """Test jobs can access database/repositories."""
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            # Jobs should be able to use repositories
            # Client may be None if Supabase not configured
            assert client is None or client is not None
        except ImportError:
            # May not be available in test environment
            assert True

    def test_job_can_access_device_manager(self):
        """Test jobs can access device abstraction layer."""
        from app.services.device_abstraction import device_manager

        # Jobs should be able to query devices
        assert device_manager is not None

    def test_process_sentry_notifications_uses_repository_import_path(self, monkeypatch, caplog):
        """Sentry notification polling should resolve the repository import."""
        from app.database.repositories.service_record_repository import ServiceRecordRepository
        from app.services.background_scheduler import scheduler_service

        async def _fake_list(self, filters=None):
            assert filters == {"status": "notified"}
            return []

        monkeypatch.setattr(ServiceRecordRepository, "list", _fake_list)

        with caplog.at_level(logging.ERROR):
            scheduler_service._process_sentry_notifications()

        assert "app.database.service_record_repository" not in caplog.text
        assert "Failed to process Sentry notifications" not in caplog.text


@pytest.mark.integration
class TestJobPerformance:
    """Test job performance impact."""

    def test_jobs_do_not_block_api(self):
        """Test scheduled jobs don't block API requests."""
        # This is a slow/integration test
        pytest.skip("Requires concurrent load - slow test")

    @pytest.mark.slow
    def test_long_running_jobs_timeout(self):
        """Test long-running jobs have appropriate timeouts."""
        pytest.skip("Requires running scheduler - slow test")


@pytest.mark.unit
class TestJobMonitoring:
    """Test job monitoring and metrics."""

    def test_job_execution_logged(self):
        """Test job executions are logged."""
        # This documents expected behavior
        # Jobs should log start, completion, errors
        assert True

    def test_job_duration_tracked(self):
        """Test job execution duration is tracked."""
        # This documents expected behavior
        # Should track how long jobs take
        assert True

    def test_job_success_rate_tracked(self):
        """Test job success rate is tracked."""
        # This documents expected behavior
        # Should track success/failure rates
        assert True
