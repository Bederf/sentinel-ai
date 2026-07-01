import json

from app.services.ml_inference import AnomalyDetectionService, LSTMInferenceService
from ml.registry import ModelRegistry


def _empty_registry(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    return ModelRegistry(registry_path=str(registry_path))


def test_lstm_missing_site_scoped_model_returns_error_without_global_fallback(tmp_path):
    registry = _empty_registry(tmp_path)
    service = LSTMInferenceService()
    service.registry = registry

    result = service.predict("S005-VAV-001", "vav", site_id="site-005")

    assert result["predictions"] is None
    assert "No active LSTM model for vav at site site-005" in result["error"]


def test_autoencoder_missing_site_scoped_model_returns_non_anomaly_error(tmp_path):
    registry = _empty_registry(tmp_path)
    service = AnomalyDetectionService()
    service.registry = registry

    result = service.check_equipment("S005-VAV-001", "vav", site_id="site-005")

    assert result["is_anomaly"] is None
    assert "No active autoencoder for vav at site site-005" in result["error"]
