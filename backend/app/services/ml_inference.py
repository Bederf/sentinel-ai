"""
ML Inference Service - Run predictions and anomaly detection.

Provides:
- LSTM predictions (24/48/72h forecasts)
- Autoencoder anomaly detection
- Model management (loading, caching)
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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
        self._loaded_models: dict[str, Any] = {}
        self._loaded_scalers: dict[str, Any] = {}
        self._registry_generation: int = self.registry._generation

    def _load_model(self, equipment_type: str):
        """Load model for equipment type (cached, invalidated on registry update)."""
        # Check if registry has activated new models since last load
        if self.registry._generation != self._registry_generation:
            logger.info(
                f"Registry generation changed ({self._registry_generation} → {self.registry._generation}), "
                f"clearing LSTM model cache ({len(self._loaded_models)} models)"
            )
            self._loaded_models.clear()
            self._loaded_scalers.clear()
            self._registry_generation = self.registry._generation

        if equipment_type in self._loaded_models:
            return self._loaded_models[equipment_type]

        model_info = self.registry.get_active_model("lstm", equipment_type)
        if not model_info:
            raise ValueError(f"No active LSTM model for {equipment_type}")

        # Lazy import
        import joblib

        from ml.lstm.model import SensorLSTM

        model = SensorLSTM.load(model_info["model_path"])
        scaler_path = model_info["metadata"].get("scaler_path")

        if scaler_path and Path(scaler_path).exists():
            scaler = joblib.load(scaler_path)
            self._loaded_scalers[equipment_type] = scaler

        self._loaded_models[equipment_type] = model
        logger.info(f"Loaded LSTM model for {equipment_type}")

        return model

    def predict(self, equipment_id: str, equipment_type: str, sensor_data: np.ndarray = None) -> dict[str, Any]:
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
            return {"equipment_id": equipment_id, "error": str(e), "predictions": None}

        # Use provided data or generate seeded data
        if sensor_data is None:
            # In production, this would fetch from InfluxDB
            # For now, generate seeded data
            sensor_data = self._generate_demo_input(equipment_type)

        # Validate shape
        if len(sensor_data) < 168:
            return {
                "equipment_id": equipment_id,
                "error": f"Insufficient data: {len(sensor_data)} hours (need 168)",
                "predictions": None,
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
                "72h": float(predictions[2]) if len(predictions) > 2 else None,
            },
            "confidence": 0.85,  # Placeholder - would calculate from model uncertainty
            "timestamp": datetime.utcnow().isoformat(),
            "model_info": {"model_id": self.registry.get_active_model("lstm", equipment_type)["model_id"]},
        }

    def _generate_demo_input(self, equipment_type: str) -> np.ndarray:
        """Generate seeded input data for testing."""
        np.random.seed(int(datetime.now().timestamp()) % 1000)

        # Equipment-specific feature counts
        feature_counts = {"chiller": 5, "ahu": 5, "generator": 4, "fcu": 3, "ups": 3}
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

    def get_trend(self, equipment_id: str, equipment_type: str, hours_history: int = 168) -> dict[str, Any]:
        """Get historical + predicted trend data for visualization."""
        # Get predictions
        prediction = self.predict(equipment_id, equipment_type)

        if prediction.get("error"):
            return prediction

        # Generate seeded historical data
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
                    prediction["predictions"]["72h"],
                ],
            },
            "timestamp": datetime.utcnow().isoformat(),
        }


class AnomalyDetectionService:
    """Service for real-time anomaly detection using autoencoders."""

    def __init__(self):
        self.registry = _get_registry()
        self._loaded_models: dict[str, Any] = {}
        self._loaded_scalers: dict[str, Any] = {}
        self._registry_generation: int = self.registry._generation

    def _load_model(self, equipment_type: str):
        """Load autoencoder for equipment type (cached, invalidated on registry update)."""
        # Check if registry has activated new models since last load
        if self.registry._generation != self._registry_generation:
            logger.info(
                f"Registry generation changed ({self._registry_generation} → {self.registry._generation}), "
                f"clearing anomaly model cache ({len(self._loaded_models)} models)"
            )
            self._loaded_models.clear()
            self._loaded_scalers.clear()
            self._registry_generation = self.registry._generation

        if equipment_type in self._loaded_models:
            return self._loaded_models[equipment_type]

        model_info = self.registry.get_active_model("autoencoder", equipment_type)
        if not model_info:
            raise ValueError(f"No active autoencoder for {equipment_type}")

        # Lazy import
        import joblib

        from ml.autoencoder.model import SensorAutoencoder

        model = SensorAutoencoder.load(model_info["model_path"])
        scaler_path = model_info["metadata"].get("scaler_path")

        if scaler_path and Path(scaler_path).exists():
            scaler = joblib.load(scaler_path)
            self._loaded_scalers[equipment_type] = scaler

        self._loaded_models[equipment_type] = model
        logger.info(f"Loaded autoencoder for {equipment_type}")

        return model

    def check_equipment(self, equipment_id: str, equipment_type: str, sensor_data: np.ndarray = None) -> dict[str, Any]:
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
            return {"equipment_id": equipment_id, "error": str(e), "is_anomaly": None}

        # Use provided data or generate seeded data
        if sensor_data is None:
            sensor_data = self._generate_demo_window(equipment_type)

        # Validate shape
        if len(sensor_data) < 24:
            return {
                "equipment_id": equipment_id,
                "error": f"Insufficient data: {len(sensor_data)} hours (need 24)",
                "is_anomaly": None,
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
            "model_info": {"model_id": self.registry.get_active_model("autoencoder", equipment_type)["model_id"]},
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

    def _generate_demo_window(self, equipment_type: str, inject_anomaly: bool = False) -> np.ndarray:
        """Generate seeded 24-hour window for testing."""
        np.random.seed(int(datetime.now().timestamp()) % 1000)

        feature_counts = {"chiller": 5, "ahu": 5, "generator": 5}
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

    def check_all_equipment(self, equipment_list: list[dict[str, str]] = None) -> list[dict[str, Any]]:
        """
        Check multiple equipment for anomalies.

        Args:
            equipment_list: List of {"equipment_id": ..., "equipment_type": ...}
                           If None, uses seeded list

        Returns:
            List of anomaly detection results sorted by score
        """
        if equipment_list is None:
            # Demo equipment list
            equipment_list = [
                {"equipment_id": "S002-CHILLER-B1-001", "equipment_type": "chiller"},
                {"equipment_id": "S002-CHILLER-B1-002", "equipment_type": "chiller"},
                {"equipment_id": "S002-AHU-L0-01", "equipment_type": "ahu"},
                {"equipment_id": "S002-AHU-L1-01", "equipment_type": "ahu"},
                {"equipment_id": "S002-GEN-B1-001", "equipment_type": "generator"},
            ]

        results = []
        for eq in equipment_list:
            try:
                result = self.check_equipment(eq["equipment_id"], eq["equipment_type"])
                results.append(result)
            except Exception as e:
                results.append({"equipment_id": eq["equipment_id"], "error": str(e)})

        # Sort by anomaly score (highest first)
        results.sort(key=lambda r: r.get("anomaly_score", 0), reverse=True)

        return results

    def get_anomaly_alerts(self) -> list[dict[str, Any]]:
        """Get equipment currently flagged as anomalous."""
        all_results = self.check_all_equipment()
        return [r for r in all_results if r.get("is_anomaly", False)]

    def get_anomaly_history(self, equipment_id: str, equipment_type: str, days: int = 7) -> list[dict[str, Any]]:
        """Get anomaly score history for trending (seed implementation)."""
        try:
            model = self._load_model(equipment_type)
        except ValueError:
            return []

        # Generate seeded history
        history = []
        np.random.seed(42)

        for day_offset in range(days, 0, -1):
            date = datetime.utcnow() - timedelta(days=day_offset)

            # Generate random but consistent score
            score = abs(np.random.normal(model.threshold * 0.6, model.threshold * 0.2))

            history.append(
                {
                    "date": date.date().isoformat(),
                    "score": float(score),
                    "threshold": float(model.threshold),
                    "is_anomaly": score > model.threshold,
                }
            )

        return history

    def fetch_sensor_window_from_db(
        self, equipment_code: str, equipment_type: str, hours: int = 24
    ) -> np.ndarray | None:
        """Fetch sensor readings from equipment_sensor_readings and return a 24h numpy window.

        Queries the last `hours` of readings, pivots sensor_type columns into a
        2-D array (timesteps × features) using the feature order the autoencoder
        was trained on.  Returns None if there are insufficient rows.
        """
        import os

        import psycopg2

        feature_cols: dict[str, list[str]] = {
            "chiller": [
                "chilled_water_supply_temp",
                "chilled_water_return_temp",
                "power_kw",
                "valve_position",
                "fan_speed",
            ],
            "ahu": ["supply_temp", "return_temp", "fan_speed", "damper_position", "power_kw"],
            "generator": ["power_kw", "voltage", "current", "frequency", "power_factor"],
            "fcu": ["room_temp", "fan_speed", "valve_position", "power_kw", "damper_position"],
        }
        cols = feature_cols.get(equipment_type)
        if not cols:
            return None

        database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55322/postgres")
        since = datetime.utcnow() - timedelta(hours=hours)

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            placeholders = ",".join(["%s"] * len(cols))
            cur.execute(
                f"""
                SELECT recorded_at, sensor_type, value
                FROM equipment_sensor_readings
                WHERE equipment_id = %s
                  AND sensor_type IN ({placeholders})
                  AND recorded_at >= %s
                ORDER BY recorded_at ASC
                """,
                [equipment_code, *cols, since],
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning(f"fetch_sensor_window_from_db failed for {equipment_code}: {e}")
            return None

        if not rows:
            return None

        # Pivot: bucket by hour, then build feature matrix
        from collections import defaultdict

        hourly: dict[str, dict[str, float]] = defaultdict(dict)
        for recorded_at, sensor_type, value in rows:
            bucket = recorded_at.strftime("%Y-%m-%dT%H")
            hourly[bucket][sensor_type] = float(value)

        sorted_buckets = sorted(hourly.keys())
        if len(sorted_buckets) < 24:
            return None  # Insufficient coverage

        matrix = []
        for bucket in sorted_buckets[-24:]:
            readings = hourly[bucket]
            # Use 0.0 for missing sensors within an hour
            matrix.append([readings.get(col, 0.0) for col in cols])

        return np.array(matrix, dtype=np.float32)

    def run_anomaly_scan(self, site_id: str) -> list[dict[str, Any]]:
        """Run anomaly detection on all active equipment for a site using real DB data.

        Fetches sensor windows from equipment_sensor_readings, runs the autoencoder,
        and persists anomalies to the anomalies table.  Returns a list of result dicts.
        """
        import os
        import uuid

        import psycopg2

        database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55322/postgres")

        # Equipment types with trained autoencoders
        supported_types = {"chiller", "ahu", "generator", "fcu"}

        # Fetch active equipment for site
        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(
                """
                SELECT e.id, e.code, LOWER(e.type) AS type
                FROM equipment e
                JOIN sites s ON s.id = e.site_id
                WHERE s.code = %s
                  AND e.status != 'decommissioned'
                  AND LOWER(e.type) = ANY(%s)
                """,
                [site_id, list(supported_types)],
            )
            equipment_rows = cur.fetchall()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"run_anomaly_scan: equipment query failed for {site_id}: {e}")
            return []

        results = []
        anomalies_to_insert = []
        now = datetime.utcnow()

        for eq_id, eq_code, eq_type in equipment_rows:
            sensor_data = self.fetch_sensor_window_from_db(eq_code, eq_type)
            if sensor_data is None:
                logger.debug(f"Skipping {eq_code}: insufficient sensor data in DB")
                continue

            result = self.check_equipment(eq_code, eq_type, sensor_data=sensor_data)
            result["equipment_db_id"] = str(eq_id)
            results.append(result)

            if result.get("is_anomaly") and not result.get("error"):
                severity_map = {"elevated": "warning", "high": "warning", "critical": "critical"}
                raw_sev = result.get("severity", "warning")
                severity = severity_map.get(raw_sev, "warning")
                anomalies_to_insert.append(
                    {
                        "id": str(uuid.uuid4()),
                        "code": f"ANOM-{eq_code}-{now.strftime('%Y%m%d%H')}",
                        "equipment_id": str(eq_id),
                        "site_id": site_id,
                        "type": "autoencoder_reconstruction_error",
                        "severity": severity,
                        "status": "active",
                        "detected_at": now.isoformat(),
                        "confidence": min(1.0, result.get("score_pct", 0) / 100.0),
                        "sensor_values": {
                            "anomaly_score": result.get("anomaly_score"),
                            "threshold": result.get("threshold"),
                            "score_pct": result.get("score_pct"),
                        },
                    }
                )

        if anomalies_to_insert:
            try:
                conn = psycopg2.connect(database_url)
                conn.autocommit = True
                cur = conn.cursor()

                # site_id must be UUID in anomalies table — resolve it
                cur.execute("SELECT id FROM sites WHERE code = %s LIMIT 1", [site_id])
                row = cur.fetchone()
                site_uuid = str(row[0]) if row else None

                if site_uuid:
                    for a in anomalies_to_insert:
                        a["site_id"] = site_uuid
                        cur.execute(
                            """
                            INSERT INTO anomalies
                                (id, code, equipment_id, site_id, type, severity, status,
                                 detected_at, confidence, sensor_values)
                            VALUES
                                (%(id)s, %(code)s, %(equipment_id)s::uuid, %(site_id)s::uuid,
                                 %(type)s, %(severity)s, %(status)s,
                                 %(detected_at)s::timestamptz, %(confidence)s, %(sensor_values)s::jsonb)
                            ON CONFLICT DO NOTHING
                            """,
                            {**a, "sensor_values": __import__("json").dumps(a["sensor_values"])},
                        )
                    logger.info(f"[ANOMALY SCAN] Persisted {len(anomalies_to_insert)} anomalies for {site_id}")

                cur.close()
                conn.close()
            except Exception as e:
                logger.error(f"run_anomaly_scan: anomaly insert failed: {e}")

        logger.info(
            f"[ANOMALY SCAN] {site_id}: checked {len(results)} equipment, {len(anomalies_to_insert)} anomalies detected"
        )
        return results


# Singleton instances
_lstm_service: LSTMInferenceService | None = None
_anomaly_service: AnomalyDetectionService | None = None


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
