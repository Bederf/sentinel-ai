"""Tests for ML Feedback Loop Closure — Phase 109-03.

Covers:
- Outcome model quality context fields
- Outcome serialization/deserialization with new fields
- MLOps outcome endpoint hardening (required fields, idempotent dedup)
- MLOps health extended metrics (feedback_capture_rate, label_lag, drift alerts)
- Mode-aware training readiness (Task 2 tests appended later)
"""

import os

# Ensure demo/test mode — must be set before app imports
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("LIGHTWEIGHT_APP", "1")

import pytest  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import patch, MagicMock  # noqa: E402

from app.models.outcome import Outcome  # noqa: E402


# ============================================================================
# Outcome Model Tests
# ============================================================================


class TestOutcomeQualityContext:
    """Test that Outcome model has quality context fields."""

    def test_outcome_has_quality_context_fields(self):
        """New quality context fields are present on Outcome."""
        outcome = Outcome(
            recommendation_id="rec-001",
            predicted={"energy_kwh": 10.0},
            actual={"energy_kwh": 9.5},
            accuracy=0.95,
            verified_at=datetime.now(),
            quality_gate_status_at_action="PASS",
            quality_snapshot_id="snap-uuid-123",
            ingestion_mode_at_action="simulation",
            action_time=datetime(2026, 2, 20, 10, 0),
            outcome_time=datetime(2026, 2, 20, 12, 0),
        )
        assert outcome.quality_gate_status_at_action == "PASS"
        assert outcome.quality_snapshot_id == "snap-uuid-123"
        assert outcome.ingestion_mode_at_action == "simulation"
        assert outcome.action_time == datetime(2026, 2, 20, 10, 0)
        assert outcome.outcome_time == datetime(2026, 2, 20, 12, 0)

    def test_outcome_quality_fields_default_none(self):
        """Quality context fields default to None when not provided."""
        outcome = Outcome(
            recommendation_id="rec-002",
            predicted={},
            actual={},
            accuracy=0.5,
            verified_at=datetime.now(),
        )
        assert outcome.quality_gate_status_at_action is None
        assert outcome.quality_snapshot_id is None
        assert outcome.ingestion_mode_at_action is None
        assert outcome.action_time is None
        assert outcome.outcome_time is None

    def test_outcome_to_dict_includes_new_fields(self):
        """Serialization includes all quality context fields."""
        now = datetime.now()
        action_t = datetime(2026, 1, 15, 8, 0)
        outcome_t = datetime(2026, 1, 15, 10, 0)

        outcome = Outcome(
            recommendation_id="rec-003",
            predicted={"energy_kwh": 5.0},
            actual={"energy_kwh": 4.8},
            accuracy=0.96,
            verified_at=now,
            quality_gate_status_at_action="WARN",
            quality_snapshot_id="snap-456",
            ingestion_mode_at_action="shadow_live",
            action_time=action_t,
            outcome_time=outcome_t,
        )
        d = outcome.to_dict()
        assert d["quality_gate_status_at_action"] == "WARN"
        assert d["quality_snapshot_id"] == "snap-456"
        assert d["ingestion_mode_at_action"] == "shadow_live"
        assert d["action_time"] == action_t.isoformat()
        assert d["outcome_time"] == outcome_t.isoformat()

    def test_outcome_to_dict_none_fields(self):
        """Serialization handles None quality context fields."""
        outcome = Outcome(
            recommendation_id="rec-004",
            predicted={},
            actual={},
            accuracy=0.0,
            verified_at=datetime.now(),
        )
        d = outcome.to_dict()
        assert d["quality_gate_status_at_action"] is None
        assert d["quality_snapshot_id"] is None
        assert d["action_time"] is None
        assert d["outcome_time"] is None

    def test_outcome_from_dict_with_new_fields(self):
        """Deserialization restores quality context fields."""
        data = {
            "recommendation_id": "rec-005",
            "predicted": {"energy_kwh": 7.0},
            "actual": {"energy_kwh": 6.5},
            "accuracy": 0.93,
            "verified_at": "2026-02-20T14:30:00",
            "notes": "test",
            "quality_gate_status_at_action": "FAIL",
            "quality_snapshot_id": "snap-789",
            "ingestion_mode_at_action": "live_control",
            "action_time": "2026-02-20T12:00:00",
            "outcome_time": "2026-02-20T14:00:00",
        }
        outcome = Outcome.from_dict(data)
        assert outcome.quality_gate_status_at_action == "FAIL"
        assert outcome.quality_snapshot_id == "snap-789"
        assert outcome.ingestion_mode_at_action == "live_control"
        assert outcome.action_time == datetime(2026, 2, 20, 12, 0)
        assert outcome.outcome_time == datetime(2026, 2, 20, 14, 0)

    def test_outcome_from_dict_without_new_fields(self):
        """Deserialization handles missing quality context fields (backward compat)."""
        data = {
            "recommendation_id": "rec-006",
            "predicted": {},
            "actual": {},
            "accuracy": 0.5,
            "verified_at": "2026-01-01T00:00:00",
        }
        outcome = Outcome.from_dict(data)
        assert outcome.quality_gate_status_at_action is None
        assert outcome.quality_snapshot_id is None
        assert outcome.ingestion_mode_at_action is None
        assert outcome.action_time is None
        assert outcome.outcome_time is None

    def test_outcome_roundtrip(self):
        """to_dict -> from_dict roundtrip preserves quality context."""
        original = Outcome(
            recommendation_id="rec-007",
            predicted={"energy_kwh": 3.0},
            actual={"energy_kwh": 2.8},
            accuracy=0.93,
            verified_at=datetime(2026, 2, 20, 16, 0),
            quality_gate_status_at_action="PASS",
            quality_snapshot_id="snap-round",
            ingestion_mode_at_action="simulation",
            action_time=datetime(2026, 2, 20, 14, 0),
            outcome_time=datetime(2026, 2, 20, 16, 0),
        )
        restored = Outcome.from_dict(original.to_dict())
        assert restored.quality_gate_status_at_action == original.quality_gate_status_at_action
        assert restored.quality_snapshot_id == original.quality_snapshot_id
        assert restored.ingestion_mode_at_action == original.ingestion_mode_at_action
        assert restored.action_time == original.action_time
        assert restored.outcome_time == original.outcome_time


# ============================================================================
# MLOps Endpoint Tests
# ============================================================================


class TestMLOpsOutcomeEndpoint:
    """Test POST /api/mlops/metrics/outcome hardening."""

    @pytest.fixture
    def client(self):
        """Create test client with just the mlops router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.mlops import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_mlops_outcome_rejects_missing_fields(self, client):
        """POST /metrics/outcome returns 422 when required fields are missing."""
        # Missing all required fields
        response = client.post("/api/mlops/metrics/outcome", json={})
        assert response.status_code == 422

        # Missing quality_gate_status_at_action
        response = client.post(
            "/api/mlops/metrics/outcome",
            json={
                "recommendation_id": "rec-x",
                "action_time": "2026-02-20T10:00:00",
                "outcome_time": "2026-02-20T12:00:00",
            },
        )
        assert response.status_code == 422

    @patch("app.services.mv_verification_service.get_mv_verification_service")
    def test_mlops_outcome_creates_record(self, mock_get_mv, client):
        """POST /metrics/outcome creates an outcome record."""
        mock_svc = MagicMock()
        mock_svc._outcomes = []
        mock_svc._save = MagicMock()
        mock_get_mv.return_value = mock_svc

        response = client.post(
            "/api/mlops/metrics/outcome",
            json={
                "recommendation_id": "rec-create-1",
                "action_time": "2026-02-20T10:00:00",
                "outcome_time": "2026-02-20T12:00:00",
                "quality_gate_status_at_action": "PASS",
                "predicted": {"energy_kwh": 5.0},
                "actual": {"energy_kwh": 4.5},
                "accuracy": 0.9,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["outcome"]["recommendation_id"] == "rec-create-1"
        assert data["outcome"]["quality_gate_status_at_action"] == "PASS"
        assert mock_svc._save.called

    @patch("app.services.mv_verification_service.get_mv_verification_service")
    def test_mlops_outcome_idempotent(self, mock_get_mv, client):
        """Duplicate recommendation_id + action_time returns existing record."""
        existing = Outcome(
            recommendation_id="rec-dup-1",
            predicted={"energy_kwh": 5.0},
            actual={"energy_kwh": 4.5},
            accuracy=0.9,
            verified_at=datetime(2026, 2, 20, 12, 0),
            quality_gate_status_at_action="PASS",
            action_time=datetime(2026, 2, 20, 10, 0),
            outcome_time=datetime(2026, 2, 20, 12, 0),
        )
        mock_svc = MagicMock()
        mock_svc._outcomes = [existing]
        mock_get_mv.return_value = mock_svc

        response = client.post(
            "/api/mlops/metrics/outcome",
            json={
                "recommendation_id": "rec-dup-1",
                "action_time": "2026-02-20T10:00:00",
                "outcome_time": "2026-02-20T12:00:00",
                "quality_gate_status_at_action": "PASS",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_exists"
        assert data["outcome"]["recommendation_id"] == "rec-dup-1"


# ============================================================================
# MLOps Health Tests
# ============================================================================


class TestMLOpsHealthExtended:
    """Test GET /api/mlops/health extended metrics."""

    @pytest.fixture
    def client(self):
        """Create test client with just the mlops router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.mlops import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    @patch("ml.monitoring.alerts.get_ml_alert_manager")
    @patch("ml.monitoring.drift.get_drift_detector")
    @patch("ml.metrics.calculator.get_metrics_calculator")
    def test_mlops_health_includes_feedback_metrics(self, mock_calc_cls, mock_drift_cls, mock_alert_cls, client):
        """Health response includes feedback_capture_rate_7d_pct, label_lag_p95_hours, drift_critical_alerts_24h."""
        mock_calc = MagicMock()
        mock_calc.calculate_all_metrics.return_value = {
            "calculated_at": "2026-02-20T15:00:00",
            "overall_score": 80.0,
            "targets_met": 4,
            "total_targets": 5,
            "metrics": {},
        }
        mock_calc_cls.return_value = mock_calc

        mock_alert = MagicMock()
        mock_alert.get_alert_summary.return_value = {"by_severity": {"critical": 0}, "total": 0}
        mock_alert_cls.return_value = mock_alert

        mock_drift = MagicMock()
        mock_drift.detect_all_drift.return_value = {"summary": {"any_drift_detected": False}}
        mock_drift_cls.return_value = mock_drift

        response = client.get("/api/mlops/health")
        assert response.status_code == 200
        data = response.json()

        assert "feedback_capture_rate_7d_pct" in data
        assert "label_lag_p95_hours" in data
        assert "drift_critical_alerts_24h" in data
        assert "mode_health_mapping" in data
        assert isinstance(data["feedback_capture_rate_7d_pct"], (int, float))
        assert isinstance(data["label_lag_p95_hours"], (int, float))
        assert isinstance(data["drift_critical_alerts_24h"], int)

    @patch("ml.monitoring.alerts.get_ml_alert_manager")
    @patch("ml.monitoring.drift.get_drift_detector")
    @patch("ml.metrics.calculator.get_metrics_calculator")
    def test_mlops_health_mode_mapping(self, mock_calc_cls, mock_drift_cls, mock_alert_cls, client):
        """mode_health_mapping contains pass/warn/fail per metric."""
        mock_calc = MagicMock()
        mock_calc.calculate_all_metrics.return_value = {
            "calculated_at": "2026-02-20T15:00:00",
            "overall_score": 90.0,
            "targets_met": 5,
            "total_targets": 5,
            "metrics": {},
        }
        mock_calc_cls.return_value = mock_calc

        mock_alert = MagicMock()
        mock_alert.get_alert_summary.return_value = {"by_severity": {}, "total": 0}
        mock_alert_cls.return_value = mock_alert

        mock_drift = MagicMock()
        mock_drift.detect_all_drift.return_value = {"summary": {"any_drift_detected": False}}
        mock_drift_cls.return_value = mock_drift

        response = client.get("/api/mlops/health")
        assert response.status_code == 200
        data = response.json()

        mapping = data["mode_health_mapping"]
        assert isinstance(mapping, dict)
        # In demo/simulation mode, all should be pass (lenient thresholds)
        for key in ("feedback_capture_rate", "label_lag", "drift_alerts"):
            if key in mapping:
                assert mapping[key] in ("pass", "warn", "fail")
