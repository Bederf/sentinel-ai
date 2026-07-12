"""
Unit tests for Plan 2 (Phase 239 M2.2 Real Drift Detection) — drift-detector-real-baselines.

Tests the integration of real trained model statistics (from ml_model_baselines)
into drift detection verdicts. Replaces hardcoded Gaussian distributions with
real baselines, implements fail-closed behavior (UNEVALUABLE when baseline missing).

Test coverage:
- test_load_trained_baselines_found() — baseline loaded successfully
- test_load_trained_baselines_missing() — no baseline found → INSUFFICIENT_BASELINES
- test_load_trained_baselines_schema_mismatch() — feature schema mismatch → FEATURE_MISMATCH
- test_drift_verdict_lstm_with_real_baseline() — LSTM drift detection using real baseline
- test_drift_verdict_autoencoder_with_real_baseline() — Autoencoder drift detection
- test_drift_detection_log_baseline_id() — log entries include baseline_id
- test_detect_model_drift_unevaluable() — missing baseline returns UNEVALUABLE verdict
"""

from unittest import mock

from ml.monitoring.drift import (
    _load_trained_baselines,
    DriftDetector,
)


class TestLoadTrainedBaselines:
    """Test _load_trained_baselines() function."""

    @mock.patch("ml.monitoring.drift.logger")
    @mock.patch(
        "ml.monitoring.drift.EQUIPMENT_TO_SENSORS",
        {
            "chiller": {
                "features": ["chw_supply_temp", "chw_return_temp", "compressor_current"],
                "uses_real_data": True,
            }
        },
    )
    @mock.patch("app.database.supabase_client.get_supabase_client")
    def test_load_trained_baselines_found(self, mock_get_client, mock_logger):
        """Test baseline loaded successfully from DB."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        # Mock baseline row with matching features
        baseline_row = {
            "model_id": "chiller_lstm_20260712",
            "site_id": "site-002",
            "equipment_type": "chiller",
            "feature_schema_hash": "abc123def456",
            "feature_schema": ["chw_supply_temp", "chw_return_temp", "compressor_current"],
            "mae_24h": 2.5,
            "mae_48h": 3.1,
            "mae_72h": 3.8,
            "mae_avg": 3.1,
            "r2_24h": 0.85,
            "r2_48h": 0.78,
            "r2_72h": 0.72,
            "r2_avg": 0.78,
            "created_at": "2026-07-12T10:00:00Z",
            "provenance_status": "valid",
            "training_dataset_details": {
                "target": "compressor_current",
            },
        }

        mock_table = mock.Mock()
        mock_query = mock.Mock()
        mock_select = mock.Mock()
        mock_eq1 = mock.Mock()
        mock_eq2 = mock.Mock()
        mock_order = mock.Mock()
        mock_limit = mock.Mock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_query
        mock_query.eq.side_effect = [mock_eq1, mock_eq2]
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.order.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.execute.return_value = mock.Mock(data=[baseline_row])

        # Call function
        result = _load_trained_baselines("site-002", "chiller", "lstm")

        # Verify result
        assert result["status"] == "LOADED"
        assert result["baseline_id"] == "chiller_lstm_20260712"
        assert result["baseline"] == baseline_row

    @mock.patch("ml.monitoring.drift.logger")
    @mock.patch("app.database.supabase_client.get_supabase_client")
    def test_load_trained_baselines_missing(self, mock_get_client, mock_logger):
        """Test missing baseline returns INSUFFICIENT_BASELINES."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        # Mock empty response
        mock_table = mock.Mock()
        mock_query = mock.Mock()
        mock_select = mock.Mock()
        mock_eq1 = mock.Mock()
        mock_eq2 = mock.Mock()
        mock_order = mock.Mock()
        mock_limit = mock.Mock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_query
        mock_query.eq.side_effect = [mock_eq1, mock_eq2]
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.order.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.execute.return_value = mock.Mock(data=[])

        # Call function
        result = _load_trained_baselines("site-002", "chiller", "lstm")

        # Verify result
        assert result["status"] == "INSUFFICIENT_BASELINES"
        assert result["reason"] == "no_baseline_found"
        assert result["baseline_id"] is None

    @mock.patch("app.database.supabase_client.get_supabase_client")
    def test_load_trained_baselines_supabase_unavailable(self, mock_get_client):
        """Test graceful handling when Supabase unavailable."""
        mock_get_client.return_value = None

        result = _load_trained_baselines("site-002", "chiller", "lstm")

        assert result["status"] == "INSUFFICIENT_BASELINES"
        assert result["reason"] == "supabase_unavailable"
        assert result["baseline_id"] is None

    @mock.patch("ml.monitoring.drift.logger")
    @mock.patch("app.database.supabase_client.get_supabase_client")
    def test_load_trained_baselines_site_scoped_priority(self, mock_get_client, mock_logger):
        """Test site-scoped baseline prioritized over global."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        # Mock multiple baselines: global and site-scoped
        global_baseline = {
            "model_id": "chiller_lstm_global",
            "site_id": None,
            "equipment_type": "chiller",
            "created_at": "2026-07-11T10:00:00Z",
            "provenance_status": "valid",
        }

        site_baseline = {
            "model_id": "chiller_lstm_site_002",
            "site_id": "site-002",
            "equipment_type": "chiller",
            "created_at": "2026-07-12T10:00:00Z",
            "provenance_status": "valid",
        }

        mock_table = mock.Mock()
        mock_query = mock.Mock()
        mock_select = mock.Mock()
        mock_eq1 = mock.Mock()
        mock_eq2 = mock.Mock()
        mock_order = mock.Mock()
        mock_limit = mock.Mock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_query
        mock_query.eq.side_effect = [mock_eq1, mock_eq2]
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.order.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        # Return both, site-scoped first (newer)
        mock_limit.execute.return_value = mock.Mock(data=[site_baseline, global_baseline])

        result = _load_trained_baselines("site-002", "chiller", "lstm")

        assert result["status"] == "LOADED"
        assert result["baseline_id"] == "chiller_lstm_site_002"

    @mock.patch("ml.monitoring.drift.logger")
    @mock.patch("app.database.supabase_client.get_supabase_client")
    def test_load_trained_baselines_db_error(self, mock_get_client, mock_logger):
        """Test error handling for database query failure."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        # Mock query raising exception
        mock_table = mock.Mock()
        mock_client.table.return_value = mock_table
        mock_table.select.side_effect = Exception("DB connection failed")

        result = _load_trained_baselines("site-002", "chiller", "lstm")

        assert result["status"] == "INSUFFICIENT_BASELINES"
        assert "query_error" in result["reason"]
        assert result["baseline_id"] is None


class TestDriftVerdictLSTM:
    """Test drift verdict computation for LSTM models using real baselines."""

    @mock.patch("ml.monitoring.drift._load_trained_baselines")
    @mock.patch.object(DriftDetector, "_latest_measured_verdict")
    def test_drift_verdict_lstm_no_drift(self, mock_verdict, mock_load_baseline):
        """Test LSTM drift detection with real baseline — no drift."""
        # Mock measured verdict
        mock_verdict.return_value = {
            "model_id": "chiller_lstm_20260712",
            "measured": 2.4,  # 24h MAE
            "baseline": 2.5,  # baseline 24h MAE
            "drift_verdict": "no_drift",
            "degradation_pct": -4.0,
        }

        # Mock baseline load
        mock_load_baseline.return_value = {
            "status": "LOADED",
            "baseline": {
                "model_id": "chiller_lstm_20260712",
                "mae_24h": 2.5,
                "r2_24h": 0.85,
            },
            "baseline_id": "chiller_lstm_20260712",
        }

        detector = DriftDetector()
        result = detector.detect_model_drift("lstm", threshold=1.5, site_id="site-002")

        assert result["verdict"] == "no_drift_detected"
        assert result["drift_detected"] is False
        assert result["baseline_id"] == "chiller_lstm_20260712"
        assert result["site_id"] == "site-002"

    @mock.patch("ml.monitoring.drift._load_trained_baselines")
    @mock.patch.object(DriftDetector, "_latest_measured_verdict")
    def test_drift_verdict_lstm_drift_detected(self, mock_verdict, mock_load_baseline):
        """Test LSTM drift detection with real baseline — drift detected."""
        # Mock measured verdict with increased error
        mock_verdict.return_value = {
            "model_id": "chiller_lstm_20260712",
            "measured": 4.0,  # 24h MAE increased
            "baseline": 2.5,  # baseline 24h MAE
            "drift_verdict": "drift_suspected",
            "degradation_pct": 60.0,
        }

        # Mock baseline load
        mock_load_baseline.return_value = {
            "status": "LOADED",
            "baseline": {
                "model_id": "chiller_lstm_20260712",
                "mae_24h": 2.5,
                "r2_24h": 0.85,
            },
            "baseline_id": "chiller_lstm_20260712",
        }

        detector = DriftDetector()
        result = detector.detect_model_drift("lstm", threshold=1.5, site_id="site-002")

        assert result["verdict"] == "drift_detected"
        assert result["drift_detected"] is True
        assert result["baseline_id"] == "chiller_lstm_20260712"

    @mock.patch("ml.monitoring.drift._load_trained_baselines")
    @mock.patch.object(DriftDetector, "_latest_measured_verdict")
    def test_drift_verdict_autoencoder_no_drift(self, mock_verdict, mock_load_baseline):
        """Test Autoencoder drift detection with real baseline — no drift."""
        # Mock measured verdict
        mock_verdict.return_value = {
            "model_id": "chiller_ae_20260712",
            "measured": 0.010,  # error score
            "baseline": 0.015,  # baseline threshold
            "drift_verdict": "no_drift",
            "degradation_pct": None,
        }

        # Mock baseline load
        mock_load_baseline.return_value = {
            "status": "LOADED",
            "baseline": {
                "model_id": "chiller_ae_20260712",
                "threshold": 0.015,
                "val_error_mean": 0.008,
            },
            "baseline_id": "chiller_ae_20260712",
        }

        detector = DriftDetector()
        result = detector.detect_model_drift("autoencoder", threshold=1.5, site_id="site-002")

        assert result["verdict"] == "no_drift_detected"
        assert result["drift_detected"] is False
        assert result["baseline_id"] == "chiller_ae_20260712"

    @mock.patch("ml.monitoring.drift._load_trained_baselines")
    @mock.patch.object(DriftDetector, "_latest_measured_verdict")
    def test_drift_verdict_autoencoder_drift_detected(self, mock_verdict, mock_load_baseline):
        """Test Autoencoder drift detection with real baseline — drift detected."""
        # Mock measured verdict with increased error
        mock_verdict.return_value = {
            "model_id": "chiller_ae_20260712",
            "measured": 0.025,  # error score above threshold
            "baseline": 0.015,
            "drift_verdict": "drift_suspected",
            "degradation_pct": None,
        }

        # Mock baseline load
        mock_load_baseline.return_value = {
            "status": "LOADED",
            "baseline": {
                "model_id": "chiller_ae_20260712",
                "threshold": 0.015,
                "val_error_mean": 0.008,
            },
            "baseline_id": "chiller_ae_20260712",
        }

        detector = DriftDetector()
        result = detector.detect_model_drift("autoencoder", threshold=1.5, site_id="site-002")

        assert result["verdict"] == "drift_detected"
        assert result["drift_detected"] is True


class TestDriftVerdictFailClosed:
    """Test fail-closed behavior: UNEVALUABLE when baseline missing."""

    @mock.patch("ml.monitoring.drift._load_trained_baselines")
    @mock.patch.object(DriftDetector, "_latest_measured_verdict")
    def test_detect_model_drift_unevaluable_no_baseline(self, mock_verdict, mock_load_baseline):
        """Test missing baseline returns UNEVALUABLE verdict (fail-closed)."""
        # Mock measured verdict
        mock_verdict.return_value = {
            "model_id": "chiller_lstm_20260712",
            "measured": 3.5,
            "baseline": None,
            "drift_verdict": "insufficient_data",
            "degradation_pct": None,
        }

        # Mock baseline load — NO baseline found
        mock_load_baseline.return_value = {
            "status": "INSUFFICIENT_BASELINES",
            "reason": "no_baseline_found",
            "baseline_id": None,
        }

        detector = DriftDetector()
        result = detector.detect_model_drift("lstm", threshold=1.5, site_id="site-002")

        # Critical: UNEVALUABLE does NOT mean "healthy" — it means "cannot evaluate"
        assert result["verdict"] == "unevaluable"
        assert result["drift_detected"] is False  # No positive signal, but NOT healthy
        assert result["baseline_id"] is None
        assert result["reason"] == "no_baseline_found"

    @mock.patch("ml.monitoring.drift._load_trained_baselines")
    @mock.patch.object(DriftDetector, "_latest_measured_verdict")
    def test_detect_model_drift_feature_mismatch(self, mock_verdict, mock_load_baseline):
        """Test feature schema mismatch returns FEATURE_MISMATCH verdict."""
        # Mock measured verdict
        mock_verdict.return_value = {
            "model_id": "chiller_lstm_20260712",
            "measured": 2.5,
            "baseline": None,
            "drift_verdict": "insufficient_data",
            "degradation_pct": None,
        }

        # Mock baseline load — FEATURE_MISMATCH
        mock_load_baseline.return_value = {
            "status": "FEATURE_MISMATCH",
            "reason": "baseline features ['chw_supply_temp', 'chw_return_temp'] != current ['chw_supply_temp', 'chw_return_temp', 'suction_pressure']",
            "baseline_id": "chiller_lstm_20260712",
        }

        detector = DriftDetector()
        result = detector.detect_model_drift("lstm", threshold=1.5, site_id="site-002")

        assert result["verdict"] == "feature_mismatch"
        assert result["drift_detected"] is False
        assert result["baseline_id"] == "chiller_lstm_20260712"
        assert "baseline features" in result["reason"]

    @mock.patch.object(DriftDetector, "_latest_measured_verdict")
    def test_detect_model_drift_insufficient_measured_data(self, mock_verdict):
        """Test insufficient measured data (cold start) returns insufficient_data."""
        # No measured verdict yet (cold start)
        mock_verdict.return_value = None

        detector = DriftDetector()
        result = detector.detect_model_drift("lstm", threshold=1.5, site_id="site-002")

        assert result["verdict"] == "insufficient_data"
        assert result["recent_accuracy"] is None
        assert result["baseline_id"] is None


class TestDriftDetectionLogIntegration:
    """Test drift_detection_log includes baseline_id and verdict."""

    @mock.patch("ml.monitoring.drift._load_trained_baselines")
    @mock.patch.object(DriftDetector, "_latest_measured_verdict")
    def test_drift_detection_history_includes_baseline_id(self, mock_verdict, mock_load_baseline):
        """Test that drift detection history includes baseline_id."""
        mock_verdict.return_value = {
            "model_id": "chiller_lstm_20260712",
            "measured": 2.4,
            "baseline": 2.5,
            "drift_verdict": "no_drift",
            "degradation_pct": -4.0,
        }

        mock_load_baseline.return_value = {
            "status": "LOADED",
            "baseline": {"model_id": "chiller_lstm_20260712"},
            "baseline_id": "chiller_lstm_20260712",
        }

        detector = DriftDetector()
        detector.detect_model_drift("lstm", site_id="site-002")

        history = detector.get_detection_history(limit=1)
        assert len(history) > 0

        latest = history[-1]
        assert latest["baseline_id"] == "chiller_lstm_20260712"
        assert latest["site_id"] == "site-002"
        assert latest["verdict"] in ["drift_detected", "no_drift_detected", "unevaluable", "feature_mismatch"]
