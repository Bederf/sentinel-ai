"""Tests for Plan 2: Sustained Drift Demotion mechanism.

Phase 240 M2.3: Drift→Trust Causality
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch


class TestIsDriftSustained:
    """Test _is_drift_sustained() logic."""

    def test_no_drift_detection_log_data(self):
        """No drift_detection_log entries → return False."""
        service = self._make_service()
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        result = service._is_drift_sustained("site-002", client)
        assert result is False

    def test_no_drift_detected_verdict(self):
        """All equipment verdicts are NO_DRIFT_DETECTED → return False."""
        service = self._make_service()
        client = MagicMock()

        now = datetime.now(UTC)
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {
                "equipment_type": "chiller",
                "verdict": "NO_DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=26)).isoformat(),
            },
            {
                "equipment_type": "ahu",
                "verdict": "NO_DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=10)).isoformat(),
            },
        ]

        result = service._is_drift_sustained("site-002", client)
        assert result is False

    def test_drift_detected_but_recent(self):
        """DRIFT_DETECTED verdict but only 2h old → return False (under 24h threshold)."""
        service = self._make_service()
        client = MagicMock()

        now = datetime.now(UTC)
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {
                "equipment_type": "chiller",
                "verdict": "DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=2)).isoformat(),
            },
        ]

        result = service._is_drift_sustained("site-002", client)
        assert result is False

    def test_drift_detected_sustained_24h(self):
        """DRIFT_DETECTED verdict 24h old → return True (at threshold)."""
        service = self._make_service()
        client = MagicMock()

        now = datetime.now(UTC)
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {
                "equipment_type": "chiller",
                "verdict": "DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=24)).isoformat(),
            },
        ]

        result = service._is_drift_sustained("site-002", client)
        assert result is True

    def test_drift_detected_sustained_26h(self):
        """DRIFT_DETECTED verdict 26h old → return True (over 24h threshold)."""
        service = self._make_service()
        client = MagicMock()

        now = datetime.now(UTC)
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {
                "equipment_type": "chiller",
                "verdict": "DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=26)).isoformat(),
            },
            {
                "equipment_type": "ahu",
                "verdict": "NO_DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=5)).isoformat(),
            },
        ]

        result = service._is_drift_sustained("site-002", client)
        assert result is True

    def test_database_query_fails(self):
        """Database query exception → return False (fail-closed)."""
        service = self._make_service()
        client = MagicMock()
        client.table.side_effect = Exception("DB error")

        result = service._is_drift_sustained("site-002", client)
        assert result is False

    @staticmethod
    def _make_service():
        """Create BackgroundSchedulerService instance."""
        from app.services.background_scheduler import BackgroundSchedulerService

        return BackgroundSchedulerService()


class TestCheckRecentDriftDemotion:
    """Test idempotency via _check_recent_drift_demotion()."""

    def test_no_recent_demotion(self):
        """No phase_transition_log entry in last 1h → return False."""
        service = self._make_service()
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.like.return_value.gte.return_value.limit.return_value.execute.return_value.data = []

        result = service._check_recent_drift_demotion("site-002", client)
        assert result is False

    def test_recent_drift_demotion_found(self):
        """phase_transition_log entry with drift reason in last 1h → return True."""
        service = self._make_service()
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.like.return_value.gte.return_value.limit.return_value.execute.return_value.data = [
            {"id": "entry-1"}
        ]

        result = service._check_recent_drift_demotion("site-002", client)
        assert result is True

    def test_database_query_fails_returns_false(self):
        """Database query exception → return False (safe default)."""
        service = self._make_service()
        client = MagicMock()
        client.table.side_effect = Exception("DB error")

        result = service._check_recent_drift_demotion("site-002", client)
        assert result is False

    @staticmethod
    def _make_service():
        """Create BackgroundSchedulerService instance."""
        from app.services.background_scheduler import BackgroundSchedulerService

        return BackgroundSchedulerService()


class TestCountDriftingEquipment:
    """Test _count_drifting_equipment() logic."""

    def test_no_equipment(self):
        """No drift_detection_log entries → return (0, [])."""
        service = self._make_service()
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        count, drifting = service._count_drifting_equipment("site-002", client)
        assert count == 0
        assert drifting == []

    def test_single_drifting_equipment(self):
        """One DRIFT_DETECTED equipment → return (1, ['chiller'])."""
        service = self._make_service()
        client = MagicMock()

        now = datetime.now(UTC)
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {
                "equipment_type": "chiller",
                "verdict": "DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=25)).isoformat(),
            },
        ]

        count, drifting = service._count_drifting_equipment("site-002", client)
        assert count == 1
        assert "chiller" in drifting

    def test_multiple_drifting_equipment(self):
        """Multiple DRIFT_DETECTED equipment → return count and list."""
        service = self._make_service()
        client = MagicMock()

        now = datetime.now(UTC)
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {
                "equipment_type": "chiller",
                "verdict": "DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=25)).isoformat(),
            },
            {
                "equipment_type": "ahu",
                "verdict": "DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=26)).isoformat(),
            },
            {
                "equipment_type": "fcu",
                "verdict": "NO_DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=5)).isoformat(),
            },
        ]

        count, drifting = service._count_drifting_equipment("site-002", client)
        assert count == 2
        assert set(drifting) == {"chiller", "ahu"}

    def test_database_error_returns_zeros(self):
        """Database error → return (0, []) (fail-closed)."""
        service = self._make_service()
        client = MagicMock()
        client.table.side_effect = Exception("DB error")

        count, drifting = service._count_drifting_equipment("site-002", client)
        assert count == 0
        assert drifting == []

    @staticmethod
    def _make_service():
        """Create BackgroundSchedulerService instance."""
        from app.services.background_scheduler import BackgroundSchedulerService

        return BackgroundSchedulerService()


class TestDemoteSiteOnDrift:
    """Test _demote_site_on_drift() atomic operation."""

    def test_site_not_found(self):
        """Site not in sites table → log warning and return."""
        service = self._make_service()
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        service._demote_site_on_drift("site-999", 1, ["chiller"], client)
        # Should complete without error

    def test_already_in_advisory(self):
        """Site already in advisory → log and return (no demotion)."""
        service = self._make_service()
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"onboarding_phase": "advisory"}
        ]

        service._demote_site_on_drift("site-002", 1, ["chiller"], client)
        # Should complete without error

    def test_demote_supervised_to_advisory(self):
        """Site in supervised → demote to advisory + write audit entry."""
        service = self._make_service()
        client = MagicMock()

        # Mock sites table query
        sites_mock = MagicMock()
        sites_mock.select.return_value.eq.return_value.execute.return_value.data = [{"onboarding_phase": "supervised"}]

        # Mock phase_transition_log insert
        log_mock = MagicMock()

        def table_side_effect(name):
            if name == "sites":
                return sites_mock
            elif name == "phase_transition_log":
                return log_mock
            return MagicMock()

        client.table.side_effect = table_side_effect

        service._demote_site_on_drift("site-002", 2, ["chiller", "ahu"], client)

        # Verify phase_transition_log insert was called with correct data
        log_mock.insert.assert_called_once()
        call_args = log_mock.insert.call_args[0][0]
        assert call_args["site_id"] == "site-002"
        assert call_args["from_phase"] == "supervised"
        assert call_args["to_phase"] == "advisory"
        assert call_args["reason"] == "sustained_drift_degradation"
        assert call_args["drift_verdict"] == "DRIFT_DETECTED"
        assert call_args["drift_equipment_count"] == 2
        assert call_args["trust_delta"] == -0.2

        # Verify sites table update was called
        assert sites_mock.update.called

    @staticmethod
    def _make_service():
        """Create BackgroundSchedulerService instance."""
        from app.services.background_scheduler import BackgroundSchedulerService

        return BackgroundSchedulerService()


class TestRunSustainedDriftDemotionCheck:
    """Integration test for _run_sustained_drift_demotion_check()."""

    @patch("app.core.site_resolver.get_registered_site_ids")
    @patch("app.database.supabase_client.get_supabase_client")
    def test_no_sustained_drift(self, mock_get_client, mock_get_sites):
        """No sustained drift at any site → no demotion."""
        from app.services.background_scheduler import BackgroundSchedulerService

        service = BackgroundSchedulerService()
        service._shutdown_requested.clear()

        mock_get_sites.return_value = ["site-002"]

        client = MagicMock()
        mock_get_client.return_value = client

        # Mock drift query: all NO_DRIFT_DETECTED
        now = datetime.now(UTC)
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {
                "equipment_type": "chiller",
                "verdict": "NO_DRIFT_DETECTED",
                "recorded_at": (now - timedelta(hours=5)).isoformat(),
            },
        ]

        service._run_sustained_drift_demotion_check()
        # Should complete without error; no demotion expected

    @patch("app.core.site_resolver.get_registered_site_ids")
    @patch("app.database.supabase_client.get_supabase_client")
    def test_sustained_drift_triggers_demotion(self, mock_get_client, mock_get_sites):
        """Sustained drift detected → site demoted to advisory."""
        from app.services.background_scheduler import BackgroundSchedulerService

        service = BackgroundSchedulerService()
        service._shutdown_requested.clear()

        mock_get_sites.return_value = ["site-002"]

        client = MagicMock()
        mock_get_client.return_value = client

        # Mock drift: DRIFT_DETECTED for 26h
        now = datetime.now(UTC)

        def side_effect_table(name):
            if name == "sites":
                sites_mock = MagicMock()
                sites_mock.select.return_value.eq.return_value.execute.return_value.data = [
                    {"onboarding_phase": "supervised"}
                ]
                return sites_mock
            elif name == "phase_transition_log":
                log_mock = MagicMock()
                # Return empty for idempotency check
                log_mock.select.return_value.eq.return_value.like.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
                return log_mock
            elif name == "drift_detection_log":
                drift_mock = MagicMock()
                drift_mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                    {
                        "equipment_type": "chiller",
                        "verdict": "DRIFT_DETECTED",
                        "recorded_at": (now - timedelta(hours=26)).isoformat(),
                    },
                ]
                return drift_mock
            return MagicMock()

        client.table.side_effect = side_effect_table

        service._run_sustained_drift_demotion_check()
        # Should complete and trigger demotion (verify via logs/mocks)


class TestAddSustainedDriftDemotionJob:
    """Test job registration."""

    def test_job_registered_with_correct_params(self):
        """Job is registered with 1h interval and correct settings."""
        from app.services.background_scheduler import BackgroundSchedulerService

        service = BackgroundSchedulerService()
        scheduler_mock = MagicMock()
        service.scheduler = scheduler_mock

        service.add_sustained_drift_demotion_job(interval_seconds=3600)

        scheduler_mock.add_job.assert_called_once()
        call_kwargs = scheduler_mock.add_job.call_args[1]

        assert call_kwargs["id"] == "sustained_drift_demotion_check"
        assert call_kwargs["max_instances"] == 1
        assert call_kwargs["coalesce"] is True
        assert call_kwargs["misfire_grace_time"] == 300

    def test_existing_job_removed_before_adding_new(self):
        """Removes existing job before registering new one."""
        from app.services.background_scheduler import BackgroundSchedulerService

        service = BackgroundSchedulerService()
        scheduler_mock = MagicMock()
        scheduler_mock.get_job.return_value = MagicMock()  # Job exists
        service.scheduler = scheduler_mock

        service.add_sustained_drift_demotion_job()

        scheduler_mock.get_job.assert_called_with("sustained_drift_demotion_check")
        scheduler_mock.remove_job.assert_called_with("sustained_drift_demotion_check")
        scheduler_mock.add_job.assert_called_once()
