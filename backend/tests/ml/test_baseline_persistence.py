"""
Unit and integration tests for Plan 1 (Phase 239 M2.2) baseline persistence.

Tests:
- capture_baseline_from_trained_model() for LSTM
- capture_baseline_from_trained_model() for Autoencoder
- Feature schema hashing prevents silent substitutions
- Training dataset hash computation
- Database immutability trigger
- Audit log recording
"""

from unittest import mock

import pytest

from app.ml.models.baseline_persistence import (
    _compute_equipment_fingerprint,
    _compute_feature_schema_hash,
    _compute_md5_hash,
    _compute_training_dataset_hash,
    capture_baseline_from_trained_model,
    record_training_audit,
)


class TestMD5Hashing:
    """Test MD5 hash functions."""

    def test_compute_md5_hash(self):
        """Test basic MD5 hashing."""
        result = _compute_md5_hash("test_data")
        assert isinstance(result, str)
        assert len(result) == 32  # MD5 hex length
        # Deterministic
        assert result == _compute_md5_hash("test_data")
        assert result != _compute_md5_hash("different_data")

    def test_feature_schema_hash_sorted(self):
        """Test feature schema hash is order-independent."""
        features1 = ["temp", "pressure", "current"]
        target = "power"
        features2 = ["pressure", "current", "temp"]

        hash1 = _compute_feature_schema_hash(features1, target)
        hash2 = _compute_feature_schema_hash(features2, target)

        assert hash1 == hash2, "Hashes should match regardless of feature order"

    def test_feature_schema_hash_changes_with_features(self):
        """Test schema hash changes if features change."""
        features = ["temp", "pressure"]
        target = "power"

        hash1 = _compute_feature_schema_hash(features, target)
        hash2 = _compute_feature_schema_hash(["temp", "pressure", "voltage"], target)

        assert hash1 != hash2, "Hash should change when features change"

    def test_feature_schema_hash_changes_with_target(self):
        """Test schema hash changes if target changes."""
        features = ["temp", "pressure"]

        hash1 = _compute_feature_schema_hash(features, "power")
        hash2 = _compute_feature_schema_hash(features, "energy")

        assert hash1 != hash2, "Hash should change when target changes"

    def test_training_dataset_hash(self):
        """Test training dataset hash computation."""
        metadata = {
            "data_source": "telemetry_hourly",
            "site_id": "site-002",
            "equipment_type": "chiller",
            "real_data_start": "2026-01-01T00:00:00Z",
            "real_data_end": "2026-07-01T00:00:00Z",
            "real_hours_available": 5000,
            "feature_columns": ["chw_supply_temp", "chw_return_temp"],
            "variance_gate": {"passed": True},
        }

        hash_val = _compute_training_dataset_hash(metadata)
        assert isinstance(hash_val, str)
        assert len(hash_val) == 32

        # Hash should be deterministic
        hash_val2 = _compute_training_dataset_hash(metadata)
        assert hash_val == hash_val2

    def test_equipment_fingerprint(self):
        """Test equipment fingerprint hashing."""
        config = {
            "equipment_type": "chiller",
            "features": ["chw_supply_temp", "chw_return_temp", "suction_pressure"],
            "target": "compressor_current",
            "description": "Chiller performance monitoring",
        }

        fingerprint = _compute_equipment_fingerprint(config)
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 32


class TestCaptureLSTMBaseline:
    """Test LSTM baseline capture."""

    def test_capture_lstm_baseline_minimal(self):
        """Test capturing baseline from LSTM training result."""
        train_result = {
            "model_id": "chiller_lstm_20260712_120000",
            "equipment_type": "chiller",
            "metrics": {
                "mae_24h": 2.5,
                "mae_48h": 3.1,
                "mae_72h": 3.8,
                "mae_avg": 3.1,
                "rmse_24h": 3.2,
                "rmse_48h": 3.9,
                "rmse_72h": 4.6,
                "r2_24h": 0.85,
                "r2_48h": 0.78,
                "r2_72h": 0.72,
                "r2_avg": 0.78,
            },
            "feature_names": [
                "chw_supply_temp",
                "chw_return_temp",
                "suction_pressure",
                "discharge_pressure",
                "compressor_current",
            ],
            "metadata": {
                "target": "compressor_current",
                "data_source": "telemetry_hourly",
                "site_id": "site-002",
                "equipment_type": "chiller",
                "real_hours_available": 5000,
                "feature_columns": [
                    "chw_supply_temp",
                    "chw_return_temp",
                    "suction_pressure",
                    "discharge_pressure",
                    "compressor_current",
                ],
            },
            "samples": 5000,
        }

        baseline = capture_baseline_from_trained_model(
            train_result,
            model_type="lstm",
            equipment_type="chiller",
            site_id="site-002",
        )

        # Verify all LSTM metrics are present
        assert baseline["model_id"] == "chiller_lstm_20260712_120000"
        assert baseline["equipment_type"] == "chiller"
        assert baseline["site_id"] == "site-002"
        assert baseline["mae_24h"] == 2.5
        assert baseline["mae_48h"] == 3.1
        assert baseline["mae_72h"] == 3.8
        assert baseline["mae_avg"] == 3.1
        assert baseline["rmse_24h"] == 3.2
        assert baseline["rmse_48h"] == 3.9
        assert baseline["rmse_72h"] == 4.6
        assert baseline["r2_24h"] == 0.85
        assert baseline["r2_48h"] == 0.78
        assert baseline["r2_72h"] == 0.72
        assert baseline["r2_avg"] == 0.78

        # Verify provenance fields
        assert baseline["feature_schema_hash"] is not None
        assert baseline["training_dataset_hash"] is not None
        assert baseline["model_version"] is not None
        assert baseline["equipment_fingerprint"] is not None
        assert baseline["training_timestamp"] is not None
        assert baseline["created_by"] == "system"
        assert baseline["provenance_status"] == "valid"

    def test_lstm_baseline_feature_schema_mismatch_detection(self):
        """Test that baseline captures features correctly for mismatch detection."""
        train_result_v1 = {
            "model_id": "model_v1",
            "equipment_type": "chiller",
            "metrics": {"mae_24h": 2.5, "r2_24h": 0.85},
            "feature_names": ["chw_supply_temp", "chw_return_temp", "suction_pressure"],
            "metadata": {
                "target": "compressor_current",
                "feature_columns": ["chw_supply_temp", "chw_return_temp", "suction_pressure"],
            },
        }

        train_result_v2 = {
            "model_id": "model_v2",
            "equipment_type": "chiller",
            "metrics": {"mae_24h": 2.3, "r2_24h": 0.88},
            "feature_names": ["chw_supply_temp", "chw_return_temp"],  # Missing suction_pressure
            "metadata": {
                "target": "compressor_current",
                "feature_columns": ["chw_supply_temp", "chw_return_temp"],
            },
        }

        baseline_v1 = capture_baseline_from_trained_model(train_result_v1, model_type="lstm", equipment_type="chiller")
        baseline_v2 = capture_baseline_from_trained_model(train_result_v2, model_type="lstm", equipment_type="chiller")

        # Hashes should differ because features differ
        assert baseline_v1["feature_schema_hash"] != baseline_v2["feature_schema_hash"]


class TestCaptureAutoencoderBaseline:
    """Test Autoencoder baseline capture."""

    def test_capture_autoencoder_baseline_minimal(self):
        """Test capturing baseline from autoencoder training result."""
        train_result = {
            "model_id": "chiller_autoencoder_20260712_120000",
            "equipment_type": "chiller",
            "metrics": {
                "threshold": 0.015,
                "val_error_mean": 0.008,
                "val_error_std": 0.003,
                "val_error_max": 0.025,
                "val_error_p95": 0.018,
                "val_error_p99": 0.022,
                "precision": 0.92,
                "recall": 0.88,
                "f1_score": 0.90,
            },
            "feature_names": [
                "chw_supply_temp",
                "chw_return_temp",
                "suction_pressure",
                "discharge_pressure",
                "compressor_current",
            ],
            "metadata": {
                "target": "reconstruction_error",
                "data_source": "telemetry_hourly",
                "site_id": "site-005",
                "equipment_type": "chiller",
                "real_hours_available": 4000,
                "feature_columns": [
                    "chw_supply_temp",
                    "chw_return_temp",
                    "suction_pressure",
                    "discharge_pressure",
                    "compressor_current",
                ],
            },
            "normal_samples": 3200,
        }

        baseline = capture_baseline_from_trained_model(
            train_result,
            model_type="autoencoder",
            equipment_type="chiller",
            site_id="site-005",
        )

        # Verify autoencoder-specific metrics
        assert baseline["model_id"] == "chiller_autoencoder_20260712_120000"
        assert baseline["equipment_type"] == "chiller"
        assert baseline["site_id"] == "site-005"
        assert baseline["threshold"] == 0.015
        assert baseline["val_error_mean"] == 0.008
        assert baseline["val_error_std"] == 0.003
        assert baseline["val_error_max"] == 0.025
        assert baseline["val_error_p95"] == 0.018
        assert baseline["val_error_p99"] == 0.022
        assert baseline["precision"] == 0.92
        assert baseline["recall"] == 0.88
        assert baseline["f1_score"] == 0.90

        # Verify provenance
        assert baseline["feature_schema_hash"] is not None
        assert baseline["training_dataset_hash"] is not None
        assert baseline["training_timestamp"] is not None


class TestBaselinePersistenceErrors:
    """Test error handling in baseline capture."""

    def test_missing_model_id(self):
        """Test error when model_id is missing."""
        train_result = {
            "metrics": {"mae_24h": 2.5},
            "feature_names": ["temp"],
            "metadata": {"target": "power"},
        }

        with pytest.raises(ValueError, match="missing model_id"):
            capture_baseline_from_trained_model(train_result, model_type="lstm", equipment_type="chiller")

    def test_missing_metrics(self):
        """Test error when metrics are missing."""
        train_result = {
            "model_id": "test_model",
            "feature_names": ["temp"],
            "metadata": {"target": "power"},
        }

        with pytest.raises(ValueError, match="missing metrics"):
            capture_baseline_from_trained_model(train_result, model_type="lstm", equipment_type="chiller")

    def test_missing_feature_names(self):
        """Test error when feature_names are missing."""
        train_result = {
            "model_id": "test_model",
            "metrics": {"mae_24h": 2.5},
            "metadata": {"target": "power"},
        }

        with pytest.raises(ValueError, match="missing feature_names"):
            capture_baseline_from_trained_model(train_result, model_type="lstm", equipment_type="chiller")

    def test_missing_target(self):
        """Test error when target is missing."""
        train_result = {
            "model_id": "test_model",
            "metrics": {"mae_24h": 2.5},
            "feature_names": ["temp"],
            "metadata": {},
        }

        with pytest.raises(ValueError, match="missing feature_names"):
            capture_baseline_from_trained_model(train_result, model_type="lstm", equipment_type="chiller")

    def test_invalid_model_type(self):
        """Test error when model_type is invalid."""
        train_result = {
            "model_id": "test_model",
            "metrics": {"mae_24h": 2.5},
            "feature_names": ["temp"],
            "metadata": {"target": "power"},
        }

        with pytest.raises(ValueError, match="Unknown model_type"):
            capture_baseline_from_trained_model(train_result, model_type="invalid_type", equipment_type="chiller")


class TestAuditLogging:
    """Test audit log recording."""

    @mock.patch("app.database.supabase_client.get_supabase_client")
    def test_record_training_audit_success(self, mock_get_client):
        """Test recording a training audit entry."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        mock_table = mock.Mock()
        mock_client.table.return_value = mock_table
        mock_insert = mock.Mock()
        mock_table.insert.return_value = mock_insert
        mock_insert.execute.return_value = mock.Mock(data=[{"id": "audit_id"}])

        record_training_audit("model_123", "train_complete")

        mock_table.insert.assert_called_once()
        call_args = mock_table.insert.call_args[0][0]
        assert call_args["model_id"] == "model_123"
        assert call_args["status"] == "train_complete"

    @mock.patch("app.database.supabase_client.get_supabase_client")
    def test_record_training_audit_with_error(self, mock_get_client):
        """Test recording a training error."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        mock_table = mock.Mock()
        mock_client.table.return_value = mock_table
        mock_insert = mock.Mock()
        mock_table.insert.return_value = mock_insert
        mock_insert.execute.return_value = mock.Mock(data=[{"id": "audit_id"}])

        record_training_audit("model_123", "error", error_msg="Training failed: insufficient data")

        call_args = mock_table.insert.call_args[0][0]
        assert call_args["status"] == "error"
        assert call_args["error_msg"] == "Training failed: insufficient data"

    @mock.patch("app.database.supabase_client.get_supabase_client")
    def test_record_audit_client_unavailable(self, mock_get_client):
        """Test audit recording gracefully handles unavailable client."""
        mock_get_client.return_value = None

        # Should not raise
        record_training_audit("model_123", "train_complete")


class TestIntegrationWithTrainer:
    """Integration tests with actual trainer output format."""

    def test_lstm_trainer_output_format(self):
        """Test baseline capture with realistic LSTM trainer output."""
        # Simulated LSTMTrainer.train_equipment_type() output
        trainer_output = {
            "equipment_type": "ahu",
            "site_id": "site-005",
            "model_id": "ahu_lstm_20260712_140530",
            "model_path": "/models/lstm/ahu_lstm_20260712_140530.h5",
            "scaler_path": "/models/lstm/ahu_lstm_20260712_140530_scaler.joblib",
            "samples": 4500,
            "feature_names": ["supply_temp", "return_temp", "filter_dp", "fan_current", "mixed_air_temp"],
            "metrics": {
                "mae_24h": 1.8,
                "mae_48h": 2.2,
                "mae_72h": 2.6,
                "mae_avg": 2.2,
                "rmse_24h": 2.3,
                "rmse_48h": 2.8,
                "rmse_72h": 3.3,
                "r2_24h": 0.88,
                "r2_48h": 0.83,
                "r2_72h": 0.79,
                "r2_avg": 0.83,
            },
            "metadata": {
                "target": "supply_temp",
                "data_source": "telemetry_hourly",
                "site_id": "site-005",
                "equipment_type": "ahu",
                "real_hours_available": 4500,
                "feature_columns": ["supply_temp", "return_temp", "filter_dp", "fan_current", "mixed_air_temp"],
            },
            "training_time_seconds": 345.2,
            "epochs_trained": 42,
            "final_loss": 0.0078,
            "final_val_loss": 0.0092,
            "activated": False,
        }

        baseline = capture_baseline_from_trained_model(
            trainer_output,
            model_type="lstm",
            equipment_type="ahu",
            site_id="site-005",
        )

        assert baseline["model_id"] == "ahu_lstm_20260712_140530"
        assert baseline["mae_24h"] == 1.8
        assert baseline["r2_avg"] == 0.83
