"""
ML Inference Service - Run predictions and anomaly detection.

Provides:
- LSTM predictions (24/48/72h forecasts)
- Autoencoder anomaly detection
- Model management (loading, caching)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

# Lazy imports to avoid loading ML libraries on every import
_lstm_model = None
_autoencoder_model = None
_registry = None


def _get_registry():
    """Lazy load model registry."""
    global _registry
    if _registry is None:
        from ml.registry import get_model_registry
        _registry = get_model_registry()
    return _registry


class LSTMInferenceService:
    """Service for LSTM time-series predictions."""

    def __init__(self):
        self.registry = _get_registry()
        self._loaded_models: Dict[str, Any] = {}
        self._loaded_scalers: Dict[str, Any] = {}

    def _load_model(self, equipment_type: str):
        """Load model for equipment type (cached)."""
        if equipment_type in self._loaded_models:
            return self._loaded_models[equipment_type]

        model_info = self.registry.get_active_model("lstm", equipment_type)
        if not model_info:
            raise ValueError(f"No active LSTM model for {equipment_type}")

        # Lazy import
        from ml.lstm.model import SensorLSTM
        import joblib

        model = SensorLSTM.load(model_info["model_path"])
        scaler_path = model_info["metadata"].get("scaler_path")

        if scaler_path and Path(scaler_path).exists():
            scaler = joblib.load(scaler_path)
            self._loaded_scalers[equipment_type] = scaler

        self._loaded_models[equipment_type] = model
        logger.info(f"Loaded LSTM model for {equipment_type}")

        return model

    def predict(
        self,
        equipment_id: str,
        equipment_type: str,
        sensor_data: np.ndarray = None
    ) -> Dict[str, Any]:
        """
        Get 24/48/72h predictions for equipment.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Type of equipment (chiller, ahu, etc.)
            sensor_data: Optional pre-loaded sensor data (168 hours, N features)
                        If not provided, would fetch from database

        Returns:
            Prediction result with confidence
        """
        try:
            model = self._load_model(equipment_type)
        except ValueError as e:
            return {
                "equipment_id": equipment_id,
                "error": str(e),
                "predictions": None
            }

        # Use provided data or generate demo data
        if sensor_data is None:
            # In production, this would fetch from InfluxDB
            # For now, generate demo data
            sensor_data = self._generate_demo_input(equipment_type)

        # Validate shape
        if len(sensor_data) < 168:
            return {
                "equipment_id": equipment_id,
                "error": f"Insufficient data: {len(sensor_data)} hours (need 168)",
                "predictions": None
            }

        # Prepare input
        X = np.array(sensor_data[-168:]).reshape(1, 168, -1)

        # Scale if scaler available
        if equipment_type in self._loaded_scalers:
            scaler = self._loaded_scalers[equipment_type]
            X_flat = X.reshape(-1, X.shape[-1])
            X_scaled = scaler.transform(X_flat).reshape(X.shape)
        else:
            X_scaled = X

        # Predict
        predictions_raw = model.predict(X_scaled)[0]

        # Denormalize if needed
        if equipment_type in self._loaded_scalers:
            # Simple denorm for single feature target
            predictions = predictions_raw
        else:
            predictions = predictions_raw

        return {
            "equipment_id": equipment_id,
            "equipment_type": equipment_type,
            "predictions": {
                "24h": float(predictions[0]) if len(predictions) > 0 else None,
                "48h": float(predictions[1]) if len(predictions) > 1 else None,
                "72h": float(predictions[2]) if len(predictions) > 2 else None
            },
            "confidence": 0.85,  # Placeholder - would calculate from model uncertainty
            "timestamp": datetime.utcnow().isoformat(),
            "model_info": {
                "model_id": self.registry.get_active_model("lstm", equipment_type)["model_id"]
            }
        }

    def _generate_demo_input(self, equipment_type: str) -> np.ndarray:
        """Generate demo input data for testing."""
        np.random.seed(int(datetime.now().timestamp()) % 1000)

        # Equipment-specific feature counts
        feature_counts = {
            "chiller": 5,
            "ahu": 5,
            "generator": 4,
            "fcu": 3,
            "ups": 3
        }
        n_features = feature_counts.get(equipment_type, 3)

        # Generate 168 hours of synthetic data
        hours = np.arange(168)
        data = np.zeros((168, n_features))

        for i in range(n_features):
            daily = 5 * np.sin(2 * np.pi * hours / 24 + i * np.pi / 4)
            noise = 0.5 * np.random.randn(168)
            base = 20 + i * 3
            data[:, i] = base + daily + noise

        return data

    def get_trend(
        self,
        equipment_id: str,
        equipment_type: str,
        hours_history: int = 168
    ) -> Dict[str, Any]:
        """Get historical + predicted trend data for visualization."""
        # Get predictions
        prediction = self.predict(equipment_id, equipment_type)

        if prediction.get("error"):
            return prediction

        # Generate demo historical data
        historical = self._generate_demo_input(equipment_type)[:, 0].tolist()

        return {
            "equipment_id": equipment_id,
            "equipment_type": equipment_type,
            "historical": historical,
            "predicted": prediction["predictions"],
            "visualization_data": {
                "x_historical": list(range(-168, 0)),
                "y_historical": historical,
                "x_predicted": [24, 48, 72],
                "y_predicted": [
                    prediction["predictions"]["24h"],
                    prediction["predictions"]["48h"],
                    prediction["predictions"]["72h"]
                ]
            },
            "timestamp": datetime.utcnow().isoformat()
        }


class AnomalyDetectionService:
    """Service for real-time anomaly detection using autoencoders."""

    def __init__(self):
        self.registry = _get_registry()
        self._loaded_models: Dict[str, Any] = {}
        self._loaded_scalers: Dict[str, Any] = {}

    def _load_model(self, equipment_type: str):
        """Load autoencoder for equipment type (cached)."""
        if equipment_type in self._loaded_models:
            return self._loaded_models[equipment_type]

        model_info = self.registry.get_active_model("autoencoder", equipment_type)
        if not model_info:
            raise ValueError(f"No active autoencoder for {equipment_type}")

        # Lazy import
        from ml.autoencoder.model import SensorAutoencoder
        import joblib

        model = SensorAutoencoder.load(model_info["model_path"])
        scaler_path = model_info["metadata"].get("scaler_path")

        if scaler_path and Path(scaler_path).exists():
            scaler = joblib.load(scaler_path)
            self._loaded_scalers[equipment_type] = scaler

        self._loaded_models[equipment_type] = model
        logger.info(f"Loaded autoencoder for {equipment_type}")

        return model

    def check_equipment(
        self,
        equipment_id: str,
        equipment_type: str,
        sensor_data: np.ndarray = None
    ) -> Dict[str, Any]:
        """
        Check equipment for anomalies.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Type of equipment
            sensor_data: Optional 24-hour sensor window

        Returns:
            Anomaly detection result
        """
        try:
            model = self._load_model(equipment_type)
        except ValueError as e:
            return {
                "equipment_id": equipment_id,
                "error": str(e),
                "is_anomaly": None
            }

        # Use provided data or generate demo data
        if sensor_data is None:
            sensor_data = self._generate_demo_window(equipment_type)

        # Validate shape
        if len(sensor_data) < 24:
            return {
                "equipment_id": equipment_id,
                "error": f"Insufficient data: {len(sensor_data)} hours (need 24)",
                "is_anomaly": None
            }

        # Prepare input (last 24 hours)
        X = np.array(sensor_data[-24:]).reshape(1, 24, -1)

        # Scale if scaler available
        if equipment_type in self._loaded_scalers:
            scaler = self._loaded_scalers[equipment_type]
            X_flat = X.reshape(-1, X.shape[-1])
            X_scaled = scaler.transform(X_flat).reshape(X.shape)
        else:
            X_scaled = X

        # Detect anomalies
        is_anomaly, scores = model.is_anomaly(X_scaled)

        score = float(scores[0])
        threshold = float(model.threshold)

        return {
            "equipment_id": equipment_id,
            "equipment_type": equipment_type,
            "is_anomaly": bool(is_anomaly[0]),
            "anomaly_score": score,
            "threshold": threshold,
            "score_pct": (score / threshold * 100) if threshold > 0 else 0,
            "severity": self._classify_severity(score, threshold),
            "timestamp": datetime.utcnow().isoformat(),
            "model_info": {
                "model_id": self.registry.get_active_model("autoencoder", equipment_type)["model_id"]
            }
        }

    def _classify_severity(self, score: float, threshold: float) -> str:
        """Classify anomaly severity based on score vs threshold."""
        ratio = score / threshold if threshold > 0 else 0

        if ratio < 0.7:
            return "normal"
        elif ratio < 1.0:
            return "warning"  # Approaching threshold
        elif ratio < 1.5:
            return "elevated"  # Just above threshold
        elif ratio < 2.0:
            return "high"
        else:
            return "critical"

    def _generate_demo_window(
        self,
        equipment_type: str,
        inject_anomaly: bool = False
    ) -> np.ndarray:
        """Generate demo 24-hour window for testing."""
        np.random.seed(int(datetime.now().timestamp()) % 1000)

        feature_counts = {
            "chiller": 5,
            "ahu": 5,
            "generator": 5
        }
        n_features = feature_counts.get(equipment_type, 5)

        hours = np.arange(24)
        data = np.zeros((24, n_features))

        for i in range(n_features):
            daily = 3 * np.sin(2 * np.pi * hours / 24 + i * np.pi / 4)
            noise = 0.3 * np.random.randn(24)
            base = 20 + i * 2
            data[:, i] = base + daily + noise

        if inject_anomaly:
            # Inject anomaly at random position
            pos = np.random.randint(5, 20)
            feature = np.random.randint(0, n_features)
            data[pos, feature] += 20  # Large spike

        return data

    def check_all_equipment(
        self,
        equipment_list: List[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Check multiple equipment for anomalies.

        Args:
            equipment_list: List of {"equipment_id": ..., "equipment_type": ...}
                           If None, uses demo list

        Returns:
            List of anomaly detection results sorted by score
        """
        if equipment_list is None:
            # Demo equipment list
            equipment_list = [
                {"equipment_id": "chiller-001", "equipment_type": "chiller"},
                {"equipment_id": "chiller-002", "equipment_type": "chiller"},
                {"equipment_id": "ahu-001", "equipment_type": "ahu"},
                {"equipment_id": "ahu-002", "equipment_type": "ahu"},
                {"equipment_id": "gen-001", "equipment_type": "generator"},
            ]

        results = []
        for eq in equipment_list:
            try:
                result = self.check_equipment(
                    eq["equipment_id"],
                    eq["equipment_type"]
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "equipment_id": eq["equipment_id"],
                    "error": str(e)
                })

        # Sort by anomaly score (highest first)
        results.sort(
            key=lambda r: r.get("anomaly_score", 0),
            reverse=True
        )

        return results

    def get_anomaly_alerts(self) -> List[Dict[str, Any]]:
        """Get equipment currently flagged as anomalous."""
        all_results = self.check_all_equipment()
        return [r for r in all_results if r.get("is_anomaly", False)]

    def get_anomaly_history(
        self,
        equipment_id: str,
        equipment_type: str,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get anomaly score history for trending (demo implementation)."""
        try:
            model = self._load_model(equipment_type)
        except ValueError:
            return []

        # Generate demo history
        history = []
        np.random.seed(42)

        for day_offset in range(days, 0, -1):
            date = datetime.utcnow() - timedelta(days=day_offset)

            # Generate random but consistent score
            score = abs(np.random.normal(model.threshold * 0.6, model.threshold * 0.2))

            history.append({
                "date": date.date().isoformat(),
                "score": float(score),
                "threshold": float(model.threshold),
                "is_anomaly": score > model.threshold
            })

        return history


# Singleton instances
_lstm_service: Optional[LSTMInferenceService] = None
_anomaly_service: Optional[AnomalyDetectionService] = None


def get_lstm_service() -> LSTMInferenceService:
    """Get singleton LSTM inference service."""
    global _lstm_service
    if _lstm_service is None:
        _lstm_service = LSTMInferenceService()
    return _lstm_service


def get_anomaly_service() -> AnomalyDetectionService:
    """Get singleton anomaly detection service."""
    global _anomaly_service
    if _anomaly_service is None:
        _anomaly_service = AnomalyDetectionService()
    return _anomaly_service
