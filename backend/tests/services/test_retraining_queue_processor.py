"""Tests for Plan 2: Retraining Queue Processor + Drift Verdict Evaluation.

Phase 241 M2.4: Drift-Driven Retraining
"""

from unittest.mock import MagicMock, patch

QUEUE_MOD = "app.ml.models.retraining_queue"
SCHED_MOD = "ml.training.retraining_scheduler"


def _make_service():
    from app.services.background_scheduler import BackgroundSchedulerService

    return BackgroundSchedulerService()


def _entry(attempts: int = 0) -> dict:
    return {
        "id": "q-1",
        "site_id": "site-005",
        "equipment_type": "chiller",
        "model_type": "lstm",
        "trigger_reason": "drift_detected",
        "attempts": attempts,
        "status": "pending",
    }


def _result(success: bool, error: str | None = None):
    result = MagicMock()
    result.success = success
    result.error = error
    result.new_model_id = "lstm_site-005_chiller_new" if success else None
    return result


class TestRetrainingQueueProcessor:
    """_run_retraining_queue_processor outcome handling."""

    def _run(self, entry, retrain_result):
        """Run the processor with mocked queue + scheduler; return transition mock."""
        service = _make_service()
        transition = MagicMock(return_value=True)
        scheduler = MagicMock()
        scheduler.trigger_retraining.return_value = retrain_result

        with (
            patch(f"{QUEUE_MOD}.get_oldest_pending", return_value=entry),
            patch(f"{QUEUE_MOD}.transition", transition),
            patch(f"{SCHED_MOD}.get_retraining_scheduler", return_value=scheduler),
        ):
            service._run_retraining_queue_processor()
        return transition, scheduler

    def test_success_completes_entry(self):
        """M2.5: after training succeeds, _run_champion_challenger handles completion.
        The processor delegates to champion/challenger comparison rather than
        transitioning to completed directly (that decision is now made after
        champion comparison, not inside the processor)."""
        transition, scheduler = self._run(_entry(), _result(True))
        scheduler.trigger_retraining.assert_called_once_with(
            model_type="lstm",
            equipment_type="chiller",
            reason="queue:drift_detected",
            site_id="site-005",
        )
        # Transition to 'running' is the only direct transition from the
        # processor; completion/escalation is handled by _run_champion_challenger.
        assert transition.call_args_list[0].args == ("q-1", "running")

    def test_lock_contention_repends_without_escalation(self):
        transition, _ = self._run(_entry(attempts=5), _result(False, "training_in_progress"))
        assert transition.call_args_list[1].args == ("q-1", "pending")

    def test_permanent_failure_escalates_immediately(self):
        transition, _ = self._run(_entry(attempts=0), _result(False, "ML training is disabled for site"))
        final = transition.call_args_list[1]
        assert final.args == ("q-1", "escalated")

    def test_transient_failure_under_cap_repends(self):
        transition, _ = self._run(_entry(attempts=0), _result(False, "telemetry query timeout"))
        final = transition.call_args_list[1]
        assert final.args == ("q-1", "pending")

    def test_transient_failure_at_cap_escalates(self):
        # attempts=2 before run → 3 after transition to running → cap reached
        transition, _ = self._run(_entry(attempts=2), _result(False, "telemetry query timeout"))
        final = transition.call_args_list[1]
        assert final.args == ("q-1", "escalated")

    def test_empty_queue_is_noop(self):
        service = _make_service()
        transition = MagicMock()
        with (
            patch(f"{QUEUE_MOD}.get_oldest_pending", return_value=None),
            patch(f"{QUEUE_MOD}.transition", transition),
        ):
            service._run_retraining_queue_processor()
        transition.assert_not_called()

    def test_job_registration(self):
        service = _make_service()
        service.add_retraining_queue_processor_job(interval_seconds=1800)
        assert service.scheduler.get_job("retraining_queue_processor") is not None


class TestDriftVerdictEvaluation:
    """_run_drift_verdict_evaluation writes verdict rows and enqueues on drift."""

    def _run(self, drift_results: dict):
        """drift_results: model_type → detect_model_drift return dict."""
        service = _make_service()
        client = MagicMock()
        detector = MagicMock()
        detector.detect_model_drift.side_effect = lambda model_type, site_id=None: drift_results[model_type]
        enqueue = MagicMock(return_value="q-new")

        with (
            patch("app.core.site_resolver.get_registered_site_ids", return_value=["site-005"]),
            patch("app.database.supabase_client.get_supabase_client", return_value=client),
            patch("ml.monitoring.drift.get_drift_detector", return_value=detector),
            patch(f"{QUEUE_MOD}.enqueue", enqueue),
        ):
            service._run_drift_verdict_evaluation()
        return client, enqueue

    def test_writes_uppercase_verdict_rows_per_model_family(self):
        results = {
            "lstm": {"verdict": "no_drift_detected", "equipment_type": "chiller", "baseline_id": "b-1"},
            "autoencoder": {"verdict": "unevaluable", "equipment_type": None, "baseline_id": None},
        }
        client, enqueue = self._run(results)

        inserts = [c.args[0] for c in client.table.return_value.insert.call_args_list]
        assert len(inserts) == 2
        verdicts = {row["model_type"]: row["verdict"] for row in inserts}
        assert verdicts == {"lstm": "NO_DRIFT_DETECTED", "autoencoder": "UNEVALUABLE"}
        assert all(row["site_id"] == "site-005" for row in inserts)
        assert all(row["source"] == "drift_verdict_evaluation" for row in inserts)
        enqueue.assert_not_called()  # no DRIFT_DETECTED → no enqueue

    def test_drift_detected_enqueues_retraining(self):
        results = {
            "lstm": {
                "verdict": "drift_detected",
                "drift_detected": True,
                "equipment_type": "chiller",
                "baseline_id": "b-1",
            },
            "autoencoder": {"verdict": "insufficient_data", "equipment_type": None, "baseline_id": None},
        }
        _, enqueue = self._run(results)

        enqueue.assert_called_once_with(
            site_id="site-005",
            equipment_type="chiller",
            model_type="lstm",
            trigger_reason="drift_detected",
            drift_verdict="DRIFT_DETECTED",
            baseline_id="b-1",
        )

    def test_unevaluable_enqueues_bootstrap_retraining(self):
        """M2.5: UNEVALUABLE with equipment_type → bootstrap retraining.
        (Supersedes M2.4 behavior, where UNEVALUABLE was deliberately deferred.)"""
        results = {
            "lstm": {"verdict": "unevaluable", "equipment_type": "chiller", "baseline_id": None},
            "autoencoder": {"verdict": "unevaluable", "equipment_type": "chiller", "baseline_id": None},
        }
        _, enqueue = self._run(results)
        assert enqueue.call_count == 2
        enqueue.assert_any_call(
            site_id="site-005",
            equipment_type="chiller",
            model_type="lstm",
            trigger_reason="unevaluable_bootstrap",
            drift_verdict="UNEVALUABLE",
            baseline_id=None,
        )
        enqueue.assert_any_call(
            site_id="site-005",
            equipment_type="chiller",
            model_type="autoencoder",
            trigger_reason="unevaluable_bootstrap",
            drift_verdict="UNEVALUABLE",
            baseline_id=None,
        )

    def test_job_registration(self):
        service = _make_service()
        service.add_drift_verdict_evaluation_job(interval_seconds=3600)
        assert service.scheduler.get_job("drift_verdict_evaluation") is not None


class TestGetActiveStatusesForSite:
    """Readiness helper: equipment_type → worst active queue status (AC-6)."""

    def _run(self, rows):
        from app.ml.models import retraining_queue

        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = rows
        with patch(f"{QUEUE_MOD}._get_client", return_value=client):
            return retraining_queue.get_active_statuses_for_site("site-005")

    def test_worst_status_wins(self):
        rows = [
            {"equipment_type": "chiller", "status": "pending"},
            {"equipment_type": "chiller", "status": "escalated"},
            {"equipment_type": "ahu", "status": "running"},
        ]
        assert self._run(rows) == {"chiller": "escalated", "ahu": "running"}

    def test_empty_on_no_entries(self):
        assert self._run([]) == {}

    def test_fail_closed_on_error(self):
        from app.ml.models import retraining_queue

        with patch(f"{QUEUE_MOD}._get_client", side_effect=RuntimeError("db down")):
            assert retraining_queue.get_active_statuses_for_site("site-005") == {}
