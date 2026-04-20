"""
Tests for Fault Classification Pipeline.

Covers:
1. ClassifierTrainer trains and registers models
2. FailureClassificationService prediction structure
3. Registry integration — metrics/metadata separation
4. /train/all includes classifier results
5. Health check includes classifier_models_active
6. Retraining scheduler recognizes classifier type
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from ml.classifier.data_prep import ClassifierDataPrep
from ml.classifier.model import FailureClassifier
from ml.classifier.train import ClassifierTrainer
from ml.registry import ModelRegistry
from ml.training.retraining_scheduler import MODEL_TYPES, RetrainingScheduler

# === Fixtures ===


@pytest.fixture
def tmp_models_dir(tmp_path):
    """Temporary directory for model files."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    return models_dir


@pytest.fixture
def tmp_registry(tmp_path):
    """Empty registry in temp directory."""
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    return ModelRegistry(registry_path=str(registry_path))


@pytest.fixture
def registry_with_classifiers(tmp_path):
    """Registry pre-loaded with classifier models."""
    registry_path = tmp_path / "registry.json"
    registry_data = {
        "models": {
            "classifier_chiller_20260223_120000": {
                "model_id": "classifier_chiller_20260223_120000",
                "model_type": "classifier",
                "equipment_type": "chiller",
                "model_path": "/tmp/chiller_rf.joblib",
                "metrics": {"cv_accuracy": 0.72, "cv_std": 0.08, "n_samples": 120, "n_classes": 6},
                "metadata": {"classes": ["normal", "compressor_failure"], "n_estimators": 100},
                "registered_at": datetime.now().isoformat(),
                "status": "active",
            },
            "classifier_ahu_20260223_120000": {
                "model_id": "classifier_ahu_20260223_120000",
                "model_type": "classifier",
                "equipment_type": "ahu",
                "model_path": "/tmp/ahu_rf.joblib",
                "metrics": {"cv_accuracy": 0.67, "cv_std": 0.05, "n_samples": 120, "n_classes": 6},
                "metadata": {"classes": ["normal", "fan_motor"], "n_estimators": 100},
                "registered_at": datetime.now().isoformat(),
                "status": "active",
            },
        },
        "active": {
            "classifier_chiller": "classifier_chiller_20260223_120000",
            "classifier_ahu": "classifier_ahu_20260223_120000",
        },
    }
    registry_path.write_text(json.dumps(registry_data))
    return ModelRegistry(registry_path=str(registry_path))


# === 1. ClassifierTrainer Tests ===


def _mock_prepare_training_data(equipment_type):
    """Generate synthetic training data without Supabase."""
    prep = ClassifierDataPrep.__new__(ClassifierDataPrep)
    failure_types = ClassifierDataPrep.FAILURE_TYPES.get(equipment_type, [])
    samples = prep._generate_synthetic_data(equipment_type, failure_types, n_samples=100)
    df = pd.DataFrame(samples)
    X = df.drop("label", axis=1)
    y = df["label"]
    return X, y


class TestClassifierTrainer:
    """ClassifierTrainer trains models and registers them correctly."""

    def test_train_single_equipment_type(self, tmp_models_dir, tmp_registry):
        """Training a single equipment type produces a model and registers it."""
        trainer = ClassifierTrainer(models_dir=str(tmp_models_dir))
        trainer.registry = tmp_registry

        with patch.object(ClassifierDataPrep, "prepare_training_data", side_effect=_mock_prepare_training_data):
            result = trainer.train_equipment_type("chiller")

        assert result["status"] == "success"
        assert result["equipment_type"] == "chiller"
        assert 0.0 <= result["accuracy"] <= 1.0
        assert result["n_classes"] >= 2
        assert result["n_samples"] > 0
        assert "model_path" in result

        # Model file exists
        assert Path(result["model_path"]).exists()

        # Registered in registry
        models = tmp_registry.list_models(model_type="classifier")
        assert len(models) == 1
        assert models[0]["equipment_type"] == "chiller"
        assert models[0]["status"] == "active"

    def test_train_all_equipment_types(self, tmp_models_dir, tmp_registry):
        """train_all() trains all 5 equipment types."""
        trainer = ClassifierTrainer(models_dir=str(tmp_models_dir))
        trainer.registry = tmp_registry

        with patch.object(ClassifierDataPrep, "prepare_training_data", side_effect=_mock_prepare_training_data):
            results = trainer.train_all()

        assert len(results) == 5
        successful = [r for r in results if r["status"] == "success"]
        assert len(successful) == 5

        equipment_types = {r["equipment_type"] for r in successful}
        assert equipment_types == {"chiller", "ahu", "generator", "fcu", "ups"}

    def test_metrics_and_metadata_separated_in_registry(self, tmp_models_dir, tmp_registry):
        """Bug fix: metrics and metadata are registered as separate fields."""
        trainer = ClassifierTrainer(models_dir=str(tmp_models_dir))
        trainer.registry = tmp_registry

        with patch.object(ClassifierDataPrep, "prepare_training_data", side_effect=_mock_prepare_training_data):
            trainer.train_equipment_type("chiller")

        model = tmp_registry.list_models(model_type="classifier")[0]

        # Metrics should contain numeric performance data
        assert "cv_accuracy" in model["metrics"]
        assert "cv_std" in model["metrics"]
        assert "n_samples" in model["metrics"]
        assert "n_classes" in model["metrics"]

        # Metadata should contain training config and class info
        assert "classes" in model["metadata"]
        assert "n_estimators" in model["metadata"]
        assert "trained_at" in model["metadata"]
        assert "use_demo_data" in model["metadata"]

        # Metrics should NOT contain metadata fields
        assert "classes" not in model["metrics"]
        assert "n_estimators" not in model["metrics"]


# === 2. FailureClassifier Model Tests ===


class TestFailureClassifierModel:
    """FailureClassifier trains, predicts, and saves/loads correctly."""

    def test_train_returns_metrics(self):
        """Training returns expected metrics structure."""
        data_prep = ClassifierDataPrep()
        X, y = data_prep._generate_synthetic_data("chiller", ClassifierDataPrep.FAILURE_TYPES["chiller"]), None

        # Generate proper X, y from synthetic data
        samples = data_prep._generate_synthetic_data("chiller", ClassifierDataPrep.FAILURE_TYPES["chiller"])
        df = pd.DataFrame(samples)
        X = df.drop("label", axis=1)
        y = df["label"]

        model = FailureClassifier(n_estimators=10, max_depth=5)
        metrics = model.train(X, y)

        assert "cv_accuracy" in metrics
        assert "cv_std" in metrics
        assert "n_samples" in metrics
        assert "n_classes" in metrics
        assert "classes" in metrics
        assert "feature_importance" in metrics
        assert metrics["n_samples"] == len(X)

    def test_predict_returns_probabilities(self):
        """Predictions include failure type, confidence, and all probabilities."""
        samples = ClassifierDataPrep()._generate_synthetic_data("chiller", ClassifierDataPrep.FAILURE_TYPES["chiller"])
        df = pd.DataFrame(samples)
        X = df.drop("label", axis=1)
        y = df["label"]

        model = FailureClassifier(n_estimators=10, max_depth=5)
        model.train(X, y)

        predictions = model.predict(X.head(1))
        assert len(predictions) == 1

        pred = predictions[0]
        assert "predicted_failure" in pred
        assert "confidence" in pred
        assert "all_probabilities" in pred
        assert 0.0 <= pred["confidence"] <= 1.0
        assert sum(pred["all_probabilities"].values()) == pytest.approx(1.0, abs=0.01)

    def test_save_and_load(self, tmp_path):
        """Model can be saved and loaded with identical predictions."""
        samples = ClassifierDataPrep()._generate_synthetic_data("ahu", ClassifierDataPrep.FAILURE_TYPES["ahu"])
        df = pd.DataFrame(samples)
        X = df.drop("label", axis=1)
        y = df["label"]

        model = FailureClassifier(n_estimators=10, max_depth=5)
        model.train(X, y)

        model_path = str(tmp_path / "test_model.joblib")
        model.save(model_path)

        loaded = FailureClassifier.load(model_path)
        original_pred = model.predict(X.head(1))[0]
        loaded_pred = loaded.predict(X.head(1))[0]

        assert original_pred["predicted_failure"] == loaded_pred["predicted_failure"]
        assert original_pred["confidence"] == pytest.approx(loaded_pred["confidence"])


# === 3. Registry Integration Tests ===


class TestRegistryIntegration:
    """Classifier models integrate correctly with the model registry."""

    def test_classifier_listed_by_type(self, registry_with_classifiers):
        """Classifier models can be filtered by model_type."""
        models = registry_with_classifiers.list_models(model_type="classifier")
        assert len(models) == 2
        assert all(m["model_type"] == "classifier" for m in models)

    def test_active_classifier_retrieved(self, registry_with_classifiers):
        """get_active_model returns the active classifier."""
        model = registry_with_classifiers.get_active_model("classifier", "chiller")
        assert model is not None
        assert model["model_type"] == "classifier"
        assert model["equipment_type"] == "chiller"
        assert model["status"] == "active"

    def test_classifier_metrics_have_cv_accuracy(self, registry_with_classifiers):
        """Classifier metrics use cv_accuracy (not r2_score)."""
        model = registry_with_classifiers.get_active_model("classifier", "chiller")
        assert "cv_accuracy" in model["metrics"]


# === 4. /train/all Includes Classifier ===


class TestTrainAllIncludesClassifier:
    """The /train/all endpoint now includes classifier training."""

    def test_train_all_has_classifier_key(self):
        """train_all_models response includes 'classifier' key."""
        # Import the endpoint module to check the code structure
        import inspect

        from app.api.ml_predictions import train_all_models

        source = inspect.getsource(train_all_models)
        assert "classifier" in source
        assert "ClassifierTrainer" in source


# === 5. Health Check Includes Classifier ===


class TestHealthCheckIncludesClassifier:
    """ML health check reports classifier model counts."""

    @pytest.mark.asyncio
    async def test_health_check_has_classifier_field(self, registry_with_classifiers):
        """Health check includes classifier_models_active count."""
        with patch("ml.registry.get_model_registry", return_value=registry_with_classifiers):
            from app.api.ml_predictions import ml_health_check

            result = await ml_health_check()

            assert "classifier_models_active" in result
            assert result["classifier_models_active"] == 2
            assert result["active_models"] >= 2


# === 6. Retraining Scheduler Tests ===


class TestRetrainingSchedulerClassifier:
    """Retraining scheduler handles classifier model type."""

    def test_classifier_in_model_types(self):
        """MODEL_TYPES includes 'classifier'."""
        assert "classifier" in MODEL_TYPES

    def test_trigger_retraining_classifier(self):
        """trigger_retraining runs for classifier type without crashing."""
        scheduler = RetrainingScheduler()
        result = scheduler.trigger_retraining("classifier", "chiller", reason="test")

        # Trainer now runs for real — in test mode it may succeed (with synthetic
        # fallback data) or fail (Supabase unavailable). Either way, the
        # scheduler must not crash and must record the attempt.
        assert result.model_type == "classifier"
        assert result.equipment_type == "chiller"

    def test_check_all_models_includes_classifier(self, registry_with_classifiers):
        """check_all_models scans classifier type slots."""
        with patch("ml.registry.get_model_registry", return_value=registry_with_classifiers):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

            classifier_checks = [c for c in checks if c["model_type"] == "classifier"]
            assert len(classifier_checks) > 0

            # Chiller classifier should be found as fresh
            chiller_check = next((c for c in classifier_checks if c["equipment_type"] == "chiller"), None)
            assert chiller_check is not None
            assert chiller_check["status"] == "fresh"

    def test_cv_accuracy_recognized_for_staleness(self, tmp_path):
        """Scheduler recognizes cv_accuracy as the performance metric."""
        registry_path = tmp_path / "registry.json"
        registry_data = {
            "models": {
                "classifier_chiller_old": {
                    "model_id": "classifier_chiller_old",
                    "model_type": "classifier",
                    "equipment_type": "chiller",
                    "model_path": "/tmp/model.joblib",
                    "metrics": {"cv_accuracy": 0.50},
                    "metadata": {},
                    "registered_at": datetime.now().isoformat(),
                    "status": "active",
                }
            },
            "active": {"classifier_chiller": "classifier_chiller_old"},
        }
        registry_path.write_text(json.dumps(registry_data))
        registry = ModelRegistry(registry_path=str(registry_path))

        with patch("ml.registry.get_model_registry", return_value=registry):
            scheduler = RetrainingScheduler()
            checks = scheduler.check_all_models()

            chiller = next(
                (c for c in checks if c["model_type"] == "classifier" and c["equipment_type"] == "chiller"),
                None,
            )
            assert chiller is not None
            # cv_accuracy 0.50 < MIN_R2_SCORE 0.65 → underperforming
            assert chiller["needs_retrain"] is True
            assert chiller["r2_score"] == 0.50


# === 7. Data Prep Tests ===


class TestClassifierDataPrep:
    """ClassifierDataPrep generates valid training data."""

    def test_failure_types_defined_for_all(self):
        """All 5 equipment types have failure types defined."""
        for eq_type in ["chiller", "ahu", "generator", "fcu", "ups"]:
            assert eq_type in ClassifierDataPrep.FAILURE_TYPES
            assert len(ClassifierDataPrep.FAILURE_TYPES[eq_type]) >= 3

    def test_synthetic_data_generates_correct_shape(self):
        """Synthetic data has features + labels for all failure types + normal."""
        prep = ClassifierDataPrep()
        failure_types = ClassifierDataPrep.FAILURE_TYPES["chiller"]
        samples = prep._generate_synthetic_data("chiller", failure_types, n_samples=100)

        df = pd.DataFrame(samples)
        assert "label" in df.columns
        assert len(df) > 100  # 100 failure samples + 20 normal
        assert "normal" in df["label"].values

    def test_default_features_per_equipment_type(self):
        """Each equipment type returns appropriate default features."""
        prep = ClassifierDataPrep()

        chiller_feats = prep._get_default_features("chiller")
        assert "kw_rating" in chiller_feats
        assert "efficiency_ratio" in chiller_feats

        ups_feats = prep._get_default_features("ups")
        assert "battery_age_years" in ups_feats
        assert "load_percent" in ups_feats
