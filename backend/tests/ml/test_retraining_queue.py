"""Unit tests for the ML retraining queue (Phase 241 M2.4 Plan 1).

Tests:
- enqueue() happy path, dedupe skip, rate-limit skip, fail-closed on DB error
- transition() status/attempts updates
- is_permanent_failure() classification
- global training lock in RetrainingScheduler.trigger_retraining
- producer hook: drift metric collection enqueues on DRIFT_DETECTED

All Supabase access is mocked — no real DB, no real training.
"""

import threading
from unittest import mock

from app.ml.models import retraining_queue


class FakeResp:
    def __init__(self, data):
        self.data = data


class FakeClient:
    """Chainable Supabase client stub. Pops one response per execute() call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.inserted: list[dict] = []
        self.updated: list[dict] = []

    def table(self, name):
        return self

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def insert(self, payload):
        self.inserted.append(payload)
        return self

    def update(self, payload):
        self.updated.append(payload)
        return self

    def execute(self):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)


class TestEnqueue:
    def test_enqueue_happy_path(self):
        """No pending entry, no recent completion → row inserted, id returned."""
        client = FakeClient([[], [], [{"id": "q-123"}]])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            queue_id = retraining_queue.enqueue(
                site_id="site-002",
                equipment_type="chiller",
                model_type="lstm",
                trigger_reason="drift_detected",
                drift_verdict="DRIFT_DETECTED",
                baseline_id="bl-1",
            )
        assert queue_id == "q-123"
        assert len(client.inserted) == 1
        payload = client.inserted[0]
        assert payload["site_id"] == "site-002"
        assert payload["equipment_type"] == "chiller"
        assert payload["model_type"] == "lstm"
        assert payload["trigger_reason"] == "drift_detected"
        assert payload["drift_verdict"] == "DRIFT_DETECTED"
        assert payload["baseline_id"] == "bl-1"
        assert payload["status"] == "pending"

    def test_enqueue_dedupe_skip(self):
        """Pending entry exists for the same key → skip, no insert."""
        client = FakeClient([[{"id": "existing"}]])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            queue_id = retraining_queue.enqueue(
                site_id="site-002",
                equipment_type="chiller",
                model_type="lstm",
                trigger_reason="drift_detected",
            )
        assert queue_id is None
        assert client.inserted == []

    def test_enqueue_rate_limit_skip(self):
        """Completed entry < 24h ago for the same key → skip, no insert."""
        client = FakeClient([[], [{"id": "recent-completed"}]])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            queue_id = retraining_queue.enqueue(
                site_id="site-002",
                equipment_type="chiller",
                model_type="lstm",
                trigger_reason="drift_detected",
            )
        assert queue_id is None
        assert client.inserted == []

    def test_enqueue_fail_closed_on_db_error(self):
        """DB error during dedupe check → returns None, never raises."""
        client = FakeClient([RuntimeError("db down")])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            queue_id = retraining_queue.enqueue(
                site_id="site-002",
                equipment_type="chiller",
                model_type="lstm",
                trigger_reason="drift_detected",
            )
        assert queue_id is None
        assert client.inserted == []

    def test_enqueue_fail_closed_on_no_client(self):
        """No Supabase client → returns None, never raises."""
        with mock.patch.object(retraining_queue, "_get_client", return_value=None):
            queue_id = retraining_queue.enqueue(
                site_id="site-002",
                equipment_type="chiller",
                model_type="lstm",
                trigger_reason="drift_detected",
            )
        assert queue_id is None


class TestTransition:
    def test_transition_to_running_increments_attempts(self):
        """pending → running bumps attempts and updated_at."""
        client = FakeClient([[{"attempts": 2}], [{"id": "q-1"}]])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            ok = retraining_queue.transition("q-1", "running")
        assert ok is True
        assert len(client.updated) == 1
        payload = client.updated[0]
        assert payload["status"] == "running"
        assert payload["attempts"] == 3
        assert "updated_at" in payload

    def test_transition_to_failed_records_error(self):
        """running → failed records error, does not touch attempts."""
        client = FakeClient([[{"id": "q-1"}]])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            ok = retraining_queue.transition("q-1", "failed", error="training crashed")
        assert ok is True
        payload = client.updated[0]
        assert payload["status"] == "failed"
        assert payload["error"] == "training crashed"
        assert "attempts" not in payload

    def test_transition_never_raises(self):
        """DB error → returns False, never raises."""
        client = FakeClient([RuntimeError("db down")])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            ok = retraining_queue.transition("q-1", "running")
        assert ok is False


class TestGetOldestPending:
    def test_returns_oldest_row(self):
        row = {"id": "q-old", "status": "pending"}
        client = FakeClient([[row]])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            assert retraining_queue.get_oldest_pending() == row

    def test_returns_none_when_empty(self):
        client = FakeClient([[]])
        with mock.patch.object(retraining_queue, "_get_client", return_value=client):
            assert retraining_queue.get_oldest_pending() is None


class TestIsPermanentFailure:
    def test_disabled_site_is_permanent(self):
        assert retraining_queue.is_permanent_failure("ML training is disabled for this site.") is True

    def test_unknown_model_type_is_permanent(self):
        assert retraining_queue.is_permanent_failure("Unknown model type: foobar") is True

    def test_transient_error_is_not_permanent(self):
        assert retraining_queue.is_permanent_failure("connection timeout to supabase") is False

    def test_none_error_is_not_permanent(self):
        assert retraining_queue.is_permanent_failure(None) is False


class TestGlobalTrainingLock:
    def test_concurrent_trigger_returns_training_in_progress(self):
        """Second concurrent trigger_retraining → success=False, error=training_in_progress."""
        import ml.training.retraining_scheduler as rs

        scheduler = rs.RetrainingScheduler()
        started = threading.Event()
        release = threading.Event()
        first_result: list = []

        def fake_locked(self, model_type, equipment_type, reason="manual", site_id=None):
            started.set()
            release.wait(timeout=10)
            return rs.RetrainResult(
                model_id=f"{model_type}_{equipment_type}",
                model_type=model_type,
                equipment_type=equipment_type,
                triggered_at="now",
                reason=reason,
                site_id=site_id,
                success=True,
            )

        def run_first():
            first_result.append(scheduler.trigger_retraining("lstm", "chiller", reason="test"))

        with mock.patch.object(rs.RetrainingScheduler, "_trigger_retraining_locked", fake_locked):
            thread = threading.Thread(target=run_first)
            thread.start()
            try:
                assert started.wait(timeout=5), "first training never started"
                # Lock is held by the first call — second must be rejected
                second = scheduler.trigger_retraining("lstm", "chiller", reason="test")
                assert second.success is False
                assert second.error == "training_in_progress"
            finally:
                release.set()
                thread.join(timeout=10)

            assert not thread.is_alive()
            assert first_result[0].success is True
            # Lock released — a third call must acquire it again
            third = scheduler.trigger_retraining("lstm", "chiller", reason="test")
            assert third.success is True


class TestProducerHook:
    def test_drift_detected_metric_row_enqueues_retraining(self):
        """Writing a drift-detected row in _collect_drift_metrics calls enqueue."""
        from app.api import metrics as metrics_mod

        fake_detector = mock.Mock()
        fake_detector.detect_feature_drift.return_value = {
            "equipment_type": "chiller",
            "drift_detected": True,
            "features_checked": 40,
            "features_drifted": 5,
        }

        # Responses: baseline-span min(recorded_at) query, then drift log insert
        client = FakeClient([[{"recorded_at": "2026-01-01T00:00:00Z"}], [{}]])

        with (
            mock.patch("ml.monitoring.drift.EQUIPMENT_TYPES", ["chiller"]),
            mock.patch(
                "ml.monitoring.drift.EQUIPMENT_TO_SENSORS",
                {
                    "chiller": {
                        "uses_real_data": True,
                        "equipment_ids": ["S002-CHILLER-B1-001"],
                        "features": ["supply_temp"],
                    }
                },
            ),
            mock.patch("ml.monitoring.drift.get_drift_detector", return_value=fake_detector),
            mock.patch("app.database.supabase_client.get_supabase_client", return_value=client),
            mock.patch.object(retraining_queue, "enqueue", return_value="q-1") as enqueue_mock,
        ):
            metrics_mod._collect_drift_metrics()

        # Feature drift invalidates both trainable model families
        assert enqueue_mock.call_count == 2
        model_types = {call.kwargs["model_type"] for call in enqueue_mock.call_args_list}
        assert model_types == {"lstm", "autoencoder"}
        for call in enqueue_mock.call_args_list:
            assert call.kwargs["site_id"] == "site-002"
            assert call.kwargs["equipment_type"] == "chiller"
            assert call.kwargs["trigger_reason"] == "drift_detected"
            assert call.kwargs["drift_verdict"] == "DRIFT_DETECTED"

    def test_no_drift_does_not_enqueue(self):
        """No drift detected → enqueue never called."""
        from app.api import metrics as metrics_mod

        fake_detector = mock.Mock()
        fake_detector.detect_feature_drift.return_value = {
            "equipment_type": "chiller",
            "drift_detected": False,
            "features_checked": 40,
            "features_drifted": 0,
        }
        client = FakeClient([[{"recorded_at": "2026-01-01T00:00:00Z"}], [{}]])

        with (
            mock.patch("ml.monitoring.drift.EQUIPMENT_TYPES", ["chiller"]),
            mock.patch(
                "ml.monitoring.drift.EQUIPMENT_TO_SENSORS",
                {
                    "chiller": {
                        "uses_real_data": True,
                        "equipment_ids": ["S002-CHILLER-B1-001"],
                        "features": ["supply_temp"],
                    }
                },
            ),
            mock.patch("ml.monitoring.drift.get_drift_detector", return_value=fake_detector),
            mock.patch("app.database.supabase_client.get_supabase_client", return_value=client),
            mock.patch.object(retraining_queue, "enqueue", return_value="q-1") as enqueue_mock,
        ):
            metrics_mod._collect_drift_metrics()

        enqueue_mock.assert_not_called()
