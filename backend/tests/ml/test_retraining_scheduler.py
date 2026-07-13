"""
Tests for Phase 45-01 Online Learning & Automated Retraining.

Covers:
1. Fresh model — no retrain needed
2. Stale model — triggers retrain
3. Missing model — reported as missing
4. Hash-based A/B assignment consistency
5. Promotion updates registry active model
6. Performance monitor returns metrics structure
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from ml.ab_testing.ab_test_manager import ABTestManager
from ml.registry import ModelRegistry
from ml.training.retraining_scheduler import RetrainingScheduler


@pytest.fixture
def fresh_registry(tmp_path):
    """Create a registry with a fresh model."""
    registry_path = tmp_path / "registry.json"
    registry_data = {
        "models": {
            "lstm_chiller_20260205_120000": {
                "model_id": "lstm_chiller_20260205_120000",
                "model_type": "lstm",
                "equipment_type": "chiller",
                "model_path": "/tmp/model.h5",
                "metrics": {"r2_score": 0.82, "mae": 1.5},
                "metadata": {},
                "registered_at": (datetime.now() - timedelta(days=5)).isoformat(),
                "status": "active",
            }
        },
        "active": {
            "lstm_chiller": "lstm_chiller_20260205_120000",
        },
    }
    registry_path.write_text(json.dumps(registry_data))
    return ModelRegistry(registry_path=str(registry_path))


@pytest.fixture
def stale_registry(tmp_path):
    """Create a registry with a stale model (>30 days old)."""
    registry_path = tmp_path / "registry.json"
    registry_data = {
        "models": {
            "lstm_chiller_20251201_120000": {
                "model_id": "lstm_chiller_20251201_120000",
                "model_type": "lstm",
                "equipment_type": "chiller",
                "model_path": "/tmp/model.h5",
                "metrics": {"r2_score": 0.72, "mae": 2.1},
                "metadata": {},
                "registered_at": (datetime.now() - timedelta(days=60)).isoformat(),
                "status": "active",
            }
        },
        "active": {
            "lstm_chiller": "lstm_chiller_20251201_120000",
        },
    }
    registry_path.write_text(json.dumps(registry_data))
    return ModelRegistry(registry_path=str(registry_path))


@pytest.fixture
def empty_registry(tmp_path):
    """Create an empty registry."""
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    return ModelRegistry(registry_path=str(registry_path))


@pytest.fixture
def two_model_registry(tmp_path):
    """Create a registry with control + candidate models."""
    registry_path = tmp_path / "registry.json"
    registry_data = {
        "models": {
            "lstm_chiller_control": {
                "model_id": "lstm_chiller_control",
                "model_type": "lstm",
                "equipment_type": "chiller",
                "model_path": "/tmp/control.h5",
                "metrics": {"r2_score": 0.80},
                "metadata": {},
                "registered_at": datetime.now().isoformat(),
                "status": "active",
            },
            "lstm_chiller_candidate": {
                "model_id": "lstm_chiller_candidate",
                "model_type": "lstm",
                "equipment_type": "chiller",
                "model_path": "/tmp/candidate.h5",
                "metrics": {"r2_score": 0.88},
                "metadata": {},
                "registered_at": datetime.now().isoformat(),
                "status": "registered",
            },
        },
        "active": {
            "lstm_chiller": "lstm_chiller_control",
        },
    }
    registry_path.write_text(json.dumps(registry_data))
    return ModelRegistry(registry_path=str(registry_path))


class TestFreshModelNoRetrain:
    """A fresh, well-performing model should not need retraining."""

    def test_fresh_model_status(self, fresh_registry):
        with patch("ml.registry.get_model_registry", return_value=fresh_registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

            chiller_check = next(
                (c for c in checks if c["model_type"] == "lstm" and c["equipment_type"] == "chiller"),
                None,
            )
            assert chiller_check is not None
            assert chiller_check["status"] == "fresh"
            assert chiller_check["needs_retrain"] is False
            assert chiller_check["age_days"] <= 10


class TestStaleModelRetrain:
    """A stale model (>30 days) should be flagged for retraining."""

    def test_stale_model_triggers_retrain(self, stale_registry):
        with patch("ml.registry.get_model_registry", return_value=stale_registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

            chiller_check = next(
                (c for c in checks if c["model_type"] == "lstm" and c["equipment_type"] == "chiller"),
                None,
            )
            assert chiller_check is not None
            assert chiller_check["status"] == "stale"
            assert chiller_check["needs_retrain"] is True
            assert chiller_check["age_days"] >= 30

    def test_site_scoped_active_model_is_checked_when_no_site_filter(self, tmp_path):
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "models": {
                "lstm_site-002_chiller_old": {
                    "model_id": "lstm_site-002_chiller_old",
                    "model_type": "lstm",
                    "equipment_type": "chiller",
                    "site_id": "site-002",
                    "model_path": "/tmp/site-model.h5",
                    "metrics": {"r2_24h": 0.72},
                    "metadata": {"site_id": "site-002"},
                    "registered_at": (datetime.now() - timedelta(days=60)).isoformat(),
                    "status": "active",
                }
            },
            "active": {"site-002_lstm_chiller": "lstm_site-002_chiller_old"},
        }
        registry_path.write_text(json.dumps(registry_data))
        registry = ModelRegistry(registry_path=str(registry_path))

        with patch("ml.registry.get_model_registry", return_value=registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

        chiller_check = next(
            (
                c
                for c in checks
                if c["model_type"] == "lstm" and c["equipment_type"] == "chiller" and c["site_id"] == "site-002"
            ),
            None,
        )
        assert chiller_check is not None
        assert chiller_check["status"] == "stale"
        assert chiller_check["needs_retrain"] is True
        assert chiller_check["quality_metric"] == "r2_24h"


class TestModelQualityMetrics:
    def test_classifier_uses_cv_accuracy_quality_metric(self, tmp_path):
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "models": {
                "classifier_chiller_low": {
                    "model_id": "classifier_chiller_low",
                    "model_type": "classifier",
                    "equipment_type": "chiller",
                    "model_path": "/tmp/model.joblib",
                    "metrics": {"cv_accuracy": 0.50},
                    "metadata": {},
                    "registered_at": datetime.now().isoformat(),
                    "status": "active",
                }
            },
            "active": {"classifier_chiller": "classifier_chiller_low"},
        }
        registry_path.write_text(json.dumps(registry_data))
        registry = ModelRegistry(registry_path=str(registry_path))

        with patch("ml.registry.get_model_registry", return_value=registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

        chiller = next(c for c in checks if c["model_type"] == "classifier" and c["equipment_type"] == "chiller")
        assert chiller["needs_retrain"] is True
        assert chiller["quality_metric"] == "cv_accuracy"
        assert chiller["quality_score"] == 0.50
        assert chiller["r2_score"] is None

    def test_autoencoder_gates_reconstruction_error_ratio_when_available(self, tmp_path):
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "models": {
                "autoencoder_ahu_bad": {
                    "model_id": "autoencoder_ahu_bad",
                    "model_type": "autoencoder",
                    "equipment_type": "ahu",
                    "model_path": "/tmp/model.h5",
                    "metrics": {"threshold": 0.5, "val_error_mean": 0.75},
                    "metadata": {},
                    "registered_at": datetime.now().isoformat(),
                    "status": "active",
                }
            },
            "active": {"autoencoder_ahu": "autoencoder_ahu_bad"},
        }
        registry_path.write_text(json.dumps(registry_data))
        registry = ModelRegistry(registry_path=str(registry_path))

        with patch("ml.registry.get_model_registry", return_value=registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

        ahu = next(c for c in checks if c["model_type"] == "autoencoder" and c["equipment_type"] == "ahu")
        assert ahu["needs_retrain"] is True
        assert ahu["quality_metric"] == "val_error_threshold_ratio"
        assert ahu["quality_score"] == 1.5


class TestMissingModel:
    """A model slot with no active model should be reported as missing."""

    def test_missing_model_detected(self, empty_registry):
        with patch("ml.registry.get_model_registry", return_value=empty_registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

            missing = [c for c in checks if c["status"] == "missing"]
            assert len(missing) > 0
            assert all(c["needs_retrain"] for c in missing)


class TestHashAssignmentConsistency:
    """Same equipment_id should always get same model in an A/B test."""

    def test_consistent_assignment(self, two_model_registry):
        with patch("ml.registry.get_model_registry", return_value=two_model_registry):
            manager = ABTestManager()
            result = manager.create_test("lstm", "chiller", "lstm_chiller_candidate")
            assert result["success"] is True

            test_id = result["test_id"]

            # Same equipment should always get same assignment
            assignments = set()
            for _ in range(10):
                model = manager.assign_model(test_id, "S002-CHILLER-B1-001")
                assignments.add(model)

            # Hash-based: must be consistent (always same result)
            assert len(assignments) == 1


class TestPromotionUpdatesRegistry:
    """Promoting a candidate should update the registry's active model."""

    def test_promote_candidate(self, two_model_registry):
        with patch("ml.registry.get_model_registry", return_value=two_model_registry):
            manager = ABTestManager()
            create_result = manager.create_test("lstm", "chiller", "lstm_chiller_candidate")
            test_id = create_result["test_id"]

            promote_result = manager.promote_candidate(test_id)
            assert promote_result["success"] is True
            assert promote_result["promoted_model_id"] == "lstm_chiller_candidate"

            # Verify registry was updated
            active = two_model_registry.get_active_model("lstm", "chiller")
            assert active is not None
            assert active["model_id"] == "lstm_chiller_candidate"
            assert active["status"] == "active"

            # Test should be marked as promoted
            tests = manager.list_tests()
            test = next(t for t in tests if t["test_id"] == test_id)
            assert test["status"] == "promoted"


class TestPerformanceMonitorMetrics:
    """Performance monitor should return well-structured metrics."""

    def test_returns_metrics_structure(self):
        from ml.monitoring.performance_monitor import ModelPerformanceMonitor

        monitor = ModelPerformanceMonitor()

        mock_pred_instance = MagicMock()
        mock_pred_instance.get_all.return_value = [
            {
                "equipment": {"code": "S002-CHILLER-B1-001"},
                "probability_percent": 80,
                "status": "active",
            }
        ]

        mock_alert_instance = MagicMock()
        mock_alert_instance.get_all.return_value = [
            {
                "equipment": {"code": "S002-CHILLER-B1-001"},
                "severity": "high",
            }
        ]

        with (
            patch(
                "app.database.repositories.prediction_repository.PredictionRepository",
                return_value=mock_pred_instance,
            ),
            patch(
                "app.database.repositories.alert_repository.AlertRepository",
                return_value=mock_alert_instance,
            ),
        ):
            result = monitor.evaluate_predictions(days_back=7)

            assert "metrics" in result
            assert "accuracy" in result["metrics"]
            assert "precision" in result["metrics"]
            assert "recall" in result["metrics"]
            assert "f1_score" in result["metrics"]
            assert "evaluated_at" in result
            assert "confusion_matrix" in result
            assert result["confusion_matrix"]["true_positives"] == 1


class TestQualityCheckFailsClosed:
    """A contract model with no recognized quality metric must be flagged, not reported fresh."""

    def _registry_with_metrics(self, tmp_path, model_type, metrics):
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "models": {
                f"{model_type}_chiller_x": {
                    "model_id": f"{model_type}_chiller_x",
                    "model_type": model_type,
                    "equipment_type": "chiller",
                    "model_path": "/tmp/model.h5",
                    "metrics": metrics,
                    "metadata": {},
                    "registered_at": datetime.now().isoformat(),
                    "status": "active",
                }
            },
            "active": {f"{model_type}_chiller": f"{model_type}_chiller_x"},
        }
        registry_path.write_text(json.dumps(registry_data))
        return ModelRegistry(registry_path=str(registry_path))

    @pytest.mark.parametrize("model_type", ["lstm", "autoencoder", "classifier"])
    def test_missing_quality_metric_flags_retrain(self, tmp_path, model_type):
        registry = self._registry_with_metrics(tmp_path, model_type, {"unrelated": 1.0})

        with patch("ml.registry.get_model_registry", return_value=registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

        chiller = next(c for c in checks if c["model_type"] == model_type and c["equipment_type"] == "chiller")
        assert chiller["needs_retrain"] is True
        assert chiller["status"] == "underperforming"
        assert chiller["quality_metric"] is None
        assert "no recognized quality metric" in chiller["reason"]

    def test_autoencoder_with_val_error_ratio_still_passes(self, tmp_path):
        registry = self._registry_with_metrics(tmp_path, "autoencoder", {"threshold": 1.0, "val_error_mean": 0.5})

        with patch("ml.registry.get_model_registry", return_value=registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

        chiller = next(c for c in checks if c["model_type"] == "autoencoder" and c["equipment_type"] == "chiller")
        assert chiller["needs_retrain"] is False
        assert chiller["status"] == "fresh"

    def test_non_contract_model_type_is_not_failed_closed(self):
        scheduler = RetrainingScheduler()
        quality = scheduler._quality_check("survival", {"c_index": 0.7})
        assert quality["is_underperforming"] is False
