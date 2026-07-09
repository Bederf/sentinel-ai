"""
ML Inference Service - Run predictions and anomaly detection.

Provides:
- LSTM predictions (24/48/72h forecasts)
- Autoencoder anomaly detection
- Model management (loading, caching)
"""

import logging
import os
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from app.config.settings import settings
from app.services.equipment_labels import format_operator_equipment_reference, operator_equipment_label

logger = logging.getLogger(__name__)

# Lazy imports to avoid loading ML libraries on every import
_lstm_model = None
_autoencoder_model = None
_registry = None


@dataclass
class FeatureWindowResult:
    data: np.ndarray | None
    diagnostics: dict[str, Any]
    error: str | None = None


def _infer_site_id(equipment_code: str | None) -> str | None:
    """Infer canonical site ID from equipment code prefixes like S002-... or site-002-..."""
    if not equipment_code:
        return None
    parts = equipment_code.split("-")
    if len(parts) >= 2 and parts[0].lower() == "site":
        return f"site-{parts[1]}".lower()
    first = parts[0].upper()
    if first.startswith("S") and first[1:].isdigit():
        return f"site-{first[1:]}".lower()
    return None


def _fetch_sensor_window_from_db(
    equipment_code: str,
    equipment_type: str,
    hours: int = 24,
    feature_cols: list[str] | None = None,
    site_id: str | None = None,
) -> np.ndarray | None:
    """Fetch aggregate telemetry from telemetry_hourly as a model feature window."""
    import os

    import psycopg2

    default_feature_cols: dict[str, list[str]] = {
        "chiller": [
            "chw_supply_temp",
            "chw_return_temp",
            "compressor_current_1",
            "compressor_current_2",
            "staging_state",
        ],
        "ahu": ["filter_dp"],
        "generator": ["power_kw", "voltage", "current", "frequency", "power_factor"],
        "fcu": ["room_temp", "co2_ppm", "anomaly_score"],
        "vav": ["zone_temp", "co2_ppm", "damper_position", "airflow_lps"],
        "site_aggregate": ["hvac_kw", "lighting_kw", "total_kw", "total_occupancy", "occupied_zones"],
    }
    cols = feature_cols or default_feature_cols.get(equipment_type)
    if not cols:
        return None

    database_url = settings.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set; cannot fetch real ML telemetry window for %s", equipment_code)
        return None
    since = datetime.utcnow() - timedelta(hours=hours)

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute(
            """
            SELECT hour_bucket, point_name, value_avg::float
            FROM telemetry_hourly
            WHERE equipment_id = %s
              AND point_name = ANY(%s)
              AND hour_bucket >= %s
              AND (%s IS NULL OR site_id = %s)
            ORDER BY hour_bucket ASC
            """,
            [equipment_code, cols, since, site_id, site_id],
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"fetch_sensor_window_from_db failed for {equipment_code}: {e}")
        return None

    if not rows:
        return None

    from collections import defaultdict

    hourly: dict[str, dict[str, float]] = defaultdict(dict)
    for recorded_at, point_name, value in rows:
        bucket = recorded_at.strftime("%Y-%m-%dT%H")
        hourly[bucket][point_name] = float(value)

    sorted_buckets = sorted(hourly.keys())
    required_buckets = min(24, hours)
    if len(sorted_buckets) < required_buckets:
        return None

    matrix = []
    for bucket in sorted_buckets[-hours:]:
        readings = hourly[bucket]
        matrix.append([readings.get(col, 0.0) for col in cols])

    return np.array(matrix, dtype=np.float32)


def _model_input_contract(model_info: dict[str, Any]) -> dict[str, Any]:
    metadata = model_info.get("metadata") or {}
    return {
        "inference_scope": metadata.get("inference_scope"),
        "feature_surface": metadata.get("feature_surface"),
        "required_features": metadata.get("required_features") or metadata.get("feature_names") or [],
        "target": metadata.get("target"),
        "missing_feature_policy": metadata.get("missing_feature_policy"),
    }


def _fetch_contract_sensor_window_from_db(
    equipment_code: str,
    equipment_type: str,
    hours: int,
    model_info: dict[str, Any],
    site_id: str | None = None,
) -> FeatureWindowResult:
    """Fetch a contract-declared feature window and fail closed on incompleteness."""
    import pandas as pd
    import psycopg2

    contract = _model_input_contract(model_info)
    features = contract["required_features"]
    diagnostics: dict[str, Any] = {
        "equipment_id": equipment_code,
        "equipment_type": equipment_type,
        "site_id": site_id,
        "model_id": model_info.get("model_id"),
        "inference_scope": contract["inference_scope"],
        "feature_surface": contract["feature_surface"],
        "required_features": features,
        "missing_feature_policy": contract["missing_feature_policy"],
    }

    if contract["missing_feature_policy"] != "fail_closed":
        return FeatureWindowResult(None, diagnostics, "input_contract_missing_or_not_fail_closed")
    if contract["inference_scope"] not in {"equipment_id", "equipment_type"}:
        return FeatureWindowResult(None, diagnostics, f"invalid_inference_scope:{contract['inference_scope']}")
    if not features:
        return FeatureWindowResult(None, diagnostics, "required_features_missing")

    database_url = settings.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        return FeatureWindowResult(None, diagnostics, "database_url_missing")

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor()
        if contract["inference_scope"] == "equipment_type":
            equipment_filter = f"%-{equipment_type.upper()}-%"
            cur.execute(
                """
                SELECT hour_bucket, point_name, AVG(value_avg)::float AS value
                FROM telemetry_hourly
                WHERE equipment_id LIKE %s
                  AND point_name = ANY(%s)
                  AND (%s IS NULL OR site_id = %s)
                  AND value_avg IS NOT NULL
                GROUP BY hour_bucket, point_name
                ORDER BY hour_bucket ASC
                """,
                [equipment_filter, features, site_id, site_id],
            )
        else:
            cur.execute(
                """
                SELECT hour_bucket, point_name, value_avg::float AS value
                FROM telemetry_hourly
                WHERE equipment_id = %s
                  AND point_name = ANY(%s)
                  AND (%s IS NULL OR site_id = %s)
                  AND value_avg IS NOT NULL
                ORDER BY hour_bucket ASC
                """,
                [equipment_code, features, site_id, site_id],
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as exc:
        return FeatureWindowResult(None, diagnostics, f"telemetry_query_failed:{exc}")

    diagnostics["raw_rows"] = len(rows)
    if not rows:
        return FeatureWindowResult(None, diagnostics, "no_contract_telemetry_rows")

    df = pd.DataFrame(rows, columns=["hour_bucket", "point_name", "value"])
    df["hour_bucket"] = pd.to_datetime(df["hour_bucket"], utc=True).dt.floor("h")
    pivot = df.pivot_table(index="hour_bucket", columns="point_name", values="value", aggfunc="mean").sort_index()
    missing_columns = [feature for feature in features if feature not in pivot.columns]
    diagnostics["missing_columns"] = missing_columns
    if missing_columns:
        return FeatureWindowResult(None, diagnostics, "contract_features_absent")

    full_index = pd.date_range(pivot.index.min(), pivot.index.max(), freq="h", tz="UTC")
    raw_feature_frame = pivot.reindex(full_index)[features]
    cleaned = raw_feature_frame.ffill(limit=3).dropna()
    diagnostics["raw_start"] = raw_feature_frame.index.min().isoformat()
    diagnostics["raw_end"] = raw_feature_frame.index.max().isoformat()
    diagnostics["complete_hours_after_cleaning"] = len(cleaned)
    diagnostics["latest_complete_hour"] = cleaned.index.max().isoformat() if not cleaned.empty else None

    if len(cleaned) < hours:
        return FeatureWindowResult(None, diagnostics, "insufficient_complete_contract_window")

    window = cleaned.tail(hours)
    raw_window = raw_feature_frame.reindex(window.index)
    diagnostics["window_start"] = window.index.min().isoformat()
    diagnostics["window_end"] = window.index.max().isoformat()
    diagnostics["real_value_counts"] = {feature: int(raw_window[feature].notna().sum()) for feature in features}
    diagnostics["hours_required"] = hours
    diagnostics["hours_returned"] = len(window)

    return FeatureWindowResult(window.values.astype(np.float32), diagnostics)


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

    def _load_model(self, equipment_type: str, site_id: str | None = None):
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

        cache_key = f"{site_id or 'global'}:{equipment_type}"
        if cache_key in self._loaded_models:
            return self._loaded_models[cache_key]

        model_info = self.registry.get_active_model("lstm", equipment_type, site_id=site_id)
        if not model_info:
            raise ValueError(f"No active LSTM model for {equipment_type} at site {site_id or 'global'}")

        # Lazy import
        import joblib

        from ml.lstm.model import SensorLSTM

        model = SensorLSTM.load(model_info["model_path"])
        scaler_path = model_info["metadata"].get("scaler_path")

        if scaler_path and Path(scaler_path).exists():
            scaler = joblib.load(scaler_path)
            self._loaded_scalers[cache_key] = scaler

        self._loaded_models[cache_key] = (model, model_info)
        logger.info("Loaded LSTM model for %s site=%s", equipment_type, site_id or "global")

        return model, model_info

    def predict(
        self,
        equipment_id: str,
        equipment_type: str,
        sensor_data: np.ndarray = None,
        site_id: str | None = None,
    ) -> dict[str, Any]:
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
            site_id = site_id or _infer_site_id(equipment_id)
            model, model_info = self._load_model(equipment_type, site_id=site_id)
        except Exception as e:
            return {"equipment_id": equipment_id, "error": str(e), "predictions": None}

        if sensor_data is None:
            metadata = model_info.get("metadata", {})
            contract_result: FeatureWindowResult | None = None
            if metadata.get("missing_feature_policy") == "fail_closed":
                contract_result = _fetch_contract_sensor_window_from_db(
                    equipment_id,
                    equipment_type,
                    hours=168,
                    model_info=model_info,
                    site_id=site_id,
                )
                sensor_data = contract_result.data
            else:
                feature_names = metadata.get("feature_names")
                sensor_data = _fetch_sensor_window_from_db(
                    equipment_id,
                    equipment_type,
                    hours=168,
                    feature_cols=feature_names,
                    site_id=site_id,
                )
            if sensor_data is None:
                return {
                    "equipment_id": equipment_id,
                    "equipment_type": equipment_type,
                    "error": "model_unavailable: insufficient contract-complete telemetry for LSTM prediction",
                    "contract_diagnostics": contract_result.diagnostics if contract_result else None,
                    "predictions": None,
                }

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
        cache_key = f"{site_id or 'global'}:{equipment_type}"
        if cache_key in self._loaded_scalers:
            scaler = self._loaded_scalers[cache_key]
            X_flat = X.reshape(-1, X.shape[-1])
            X_scaled = scaler.transform(X_flat).reshape(X.shape)
        else:
            X_scaled = X

        # Predict
        predictions_raw = model.predict(X_scaled)[0]

        # Denormalize if needed
        if cache_key in self._loaded_scalers:
            # Simple denorm for single feature target
            predictions = predictions_raw
        else:
            predictions = predictions_raw

        result = {
            "equipment_id": equipment_id,
            "equipment_type": equipment_type,
            "site_id": site_id,
            "predictions": {
                "24h": float(predictions[0]) if len(predictions) > 0 else None,
                "48h": float(predictions[1]) if len(predictions) > 1 else None,
                "72h": float(predictions[2]) if len(predictions) > 2 else None,
            },
            "confidence": 0.85,  # Placeholder - would calculate from model uncertainty
            "timestamp": datetime.utcnow().isoformat(),
            "model_info": {
                "model_id": model_info["model_id"],
                "site_id": model_info.get("site_id"),
                "input_contract": _model_input_contract(model_info),
            },
        }

        # Phase 236-03: log site-scoped forecasts for the measured drift signal.
        from app.services.ml_prediction_logger import log_lstm_prediction

        log_lstm_prediction(result, model_info)
        return result

    def get_trend(
        self,
        equipment_id: str,
        equipment_type: str,
        hours_history: int = 168,
        site_id: str | None = None,
    ) -> dict[str, Any]:
        """Get historical + predicted trend data for visualization."""
        site_id = site_id or _infer_site_id(equipment_id)
        model_info = self.registry.get_active_model("lstm", equipment_type, site_id=site_id)
        contract_result: FeatureWindowResult | None = None
        if model_info and (model_info.get("metadata") or {}).get("missing_feature_policy") == "fail_closed":
            contract_result = _fetch_contract_sensor_window_from_db(
                equipment_id,
                equipment_type,
                hours=hours_history,
                model_info=model_info,
                site_id=site_id,
            )
            sensor_data = contract_result.data
        else:
            feature_names = model_info.get("metadata", {}).get("feature_names") if model_info else None
            sensor_data = _fetch_sensor_window_from_db(
                equipment_id,
                equipment_type,
                hours=hours_history,
                feature_cols=feature_names,
                site_id=site_id,
            )
        if sensor_data is None:
            return {
                "equipment_id": equipment_id,
                "equipment_type": equipment_type,
                "error": "model_unavailable: insufficient contract-complete telemetry for trend",
                "contract_diagnostics": contract_result.diagnostics if contract_result else None,
            }

        prediction = self.predict(equipment_id, equipment_type, sensor_data=sensor_data, site_id=site_id)

        if prediction.get("error"):
            return prediction

        historical = sensor_data[:, 0].tolist()

        return {
            "equipment_id": equipment_id,
            "equipment_type": equipment_type,
            "site_id": site_id,
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

    def _load_model(self, equipment_type: str, site_id: str | None = None):
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

        cache_key = f"{site_id or 'global'}:{equipment_type}"
        if cache_key in self._loaded_models:
            return self._loaded_models[cache_key]

        model_info = self.registry.get_active_model("autoencoder", equipment_type, site_id=site_id)
        if not model_info:
            raise ValueError(f"No active autoencoder for {equipment_type} at site {site_id or 'global'}")

        # Lazy import
        import joblib

        from ml.autoencoder.model import SensorAutoencoder

        model = SensorAutoencoder.load(model_info["model_path"])
        scaler_path = model_info["metadata"].get("scaler_path")

        if scaler_path and Path(scaler_path).exists():
            scaler = joblib.load(scaler_path)
            self._loaded_scalers[cache_key] = scaler

        self._loaded_models[cache_key] = (model, model_info)
        logger.info("Loaded autoencoder for %s site=%s", equipment_type, site_id or "global")

        return model, model_info

    def check_equipment(
        self,
        equipment_id: str,
        equipment_type: str,
        sensor_data: np.ndarray = None,
        site_id: str | None = None,
    ) -> dict[str, Any]:
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
            site_id = site_id or _infer_site_id(equipment_id)
            model, model_info = self._load_model(equipment_type, site_id=site_id)
        except Exception as e:
            return {"equipment_id": equipment_id, "error": str(e), "is_anomaly": None}

        if sensor_data is None:
            metadata = model_info.get("metadata", {})
            contract_result: FeatureWindowResult | None = None
            if metadata.get("missing_feature_policy") == "fail_closed":
                contract_result = _fetch_contract_sensor_window_from_db(
                    equipment_id,
                    equipment_type,
                    hours=24,
                    model_info=model_info,
                    site_id=site_id,
                )
                sensor_data = contract_result.data
            else:
                feature_names = metadata.get("feature_names")
                sensor_data = _fetch_sensor_window_from_db(
                    equipment_id,
                    equipment_type,
                    hours=24,
                    feature_cols=feature_names,
                    site_id=site_id,
                )
            if sensor_data is None:
                return {
                    "equipment_id": equipment_id,
                    "equipment_type": equipment_type,
                    "error": "model_unavailable: insufficient contract-complete telemetry for anomaly detection",
                    "contract_diagnostics": contract_result.diagnostics if contract_result else None,
                    "is_anomaly": None,
                }

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
        cache_key = f"{site_id or 'global'}:{equipment_type}"
        if cache_key in self._loaded_scalers:
            scaler = self._loaded_scalers[cache_key]
            X_flat = X.reshape(-1, X.shape[-1])
            X_scaled = scaler.transform(X_flat).reshape(X.shape)
        else:
            X_scaled = X

        # Detect anomalies
        is_anomaly, scores = model.is_anomaly(X_scaled)

        score = float(scores[0])
        threshold = float(model.threshold)

        result = {
            "equipment_id": equipment_id,
            "equipment_type": equipment_type,
            "site_id": site_id,
            "is_anomaly": bool(is_anomaly[0]),
            "anomaly_score": score,
            "threshold": threshold,
            "score_pct": (score / threshold * 100) if threshold > 0 else 0,
            "severity": self._classify_severity(score, threshold),
            "timestamp": datetime.utcnow().isoformat(),
            "model_info": {
                "model_id": model_info["model_id"],
                "site_id": model_info.get("site_id"),
                "input_contract": _model_input_contract(model_info),
            },
        }

        # Phase 236-03: log site-scoped AE scores for the measured drift signal.
        from app.services.ml_prediction_logger import log_ae_score

        log_ae_score(result, model_info)
        return result

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

    def check_all_equipment(self, equipment_list: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
        """
        Check multiple equipment for anomalies.

        Args:
            equipment_list: List of {"equipment_id": ..., "equipment_type": ...}
                           If None, returns an empty list.

        Returns:
            List of anomaly detection results sorted by score
        """
        if equipment_list is None:
            return []

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
        """Get anomaly score history from persisted telemetry when available."""
        return []

    def _surface_critical_anomaly(
        self,
        *,
        conn: Any,
        site_id: str,
        site_uuid: str,
        equipment_uuid: str,
        equipment_code: str,
        equipment_type: str,
        result: dict[str, Any],
        detected_at: datetime,
    ) -> dict[str, str | None]:
        """Persist a critical AE anomaly as alert + recommendation and notify operators."""
        import asyncio
        import uuid

        from app.models.notification import AlertLevel
        from app.services.notification_service import NotificationService

        operator_label = operator_equipment_label(equipment_code)
        equipment_ref = format_operator_equipment_reference(equipment_code)
        model_info = result.get("model_info") or {}
        contract = model_info.get("input_contract") or {}
        anomaly_score = float(result.get("anomaly_score") or 0.0)
        threshold = float(result.get("threshold") or 0.0)
        ratio = anomaly_score / threshold if threshold > 0 else 0.0
        score_pct = float(result.get("score_pct") or 0.0)
        source_dedupe_key = f"ml:autoencoder:{site_id}:{equipment_code}:critical"
        title = f"ML critical anomaly: {operator_label}"
        message = (
            f"{equipment_ref} has a critical autoencoder anomaly. "
            f"Score {anomaly_score:.4f} vs threshold {threshold:.4f} ({ratio:.2f}x). "
            "Check BMS trend and physical plant before clearing."
        )
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id
                FROM alerts
                WHERE site_id = %s::uuid
                  AND equipment_id = %s::uuid
                  AND source = 'ml_inference'
                  AND type = 'ml_autoencoder_anomaly'
                  AND severity = 'critical'
                  AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [site_uuid, equipment_uuid],
            )
            row = cur.fetchone()
            if row:
                alert_id = str(row[0])
                cur.execute(
                    """
                    UPDATE alerts
                    SET title = %s,
                        message = %s,
                        event_at = %s::timestamptz,
                        last_seen_at = %s::timestamptz,
                        updated_at = %s::timestamptz,
                        occurrence_count = occurrence_count + 1
                    WHERE id = %s::uuid
                    """,
                    [
                        title,
                        message,
                        detected_at.isoformat(),
                        detected_at.isoformat(),
                        detected_at.isoformat(),
                        alert_id,
                    ],
                )
            else:
                alert_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO alerts
                        (id, site_id, equipment_id, type, severity, status, title, message,
                         created_at, updated_at, source, source_dedupe_key, event_at,
                         first_seen_at, last_seen_at, lifecycle_state, occurrence_count)
                    VALUES
                        (%s::uuid, %s::uuid, %s::uuid, 'ml_autoencoder_anomaly', 'critical',
                         'active', %s, %s, %s::timestamptz, %s::timestamptz, 'ml_inference',
                         %s, %s::timestamptz, %s::timestamptz, %s::timestamptz, 'active', 1)
                    ON CONFLICT (site_id, source, source_dedupe_key) DO UPDATE
                    SET title = EXCLUDED.title,
                        message = EXCLUDED.message,
                        status = 'active',
                        lifecycle_state = 'active',
                        event_at = EXCLUDED.event_at,
                        last_seen_at = EXCLUDED.last_seen_at,
                        updated_at = EXCLUDED.updated_at,
                        occurrence_count = alerts.occurrence_count + 1
                    RETURNING id
                    """,
                    [
                        alert_id,
                        site_uuid,
                        equipment_uuid,
                        title,
                        message,
                        detected_at.isoformat(),
                        detected_at.isoformat(),
                        source_dedupe_key,
                        detected_at.isoformat(),
                        detected_at.isoformat(),
                        detected_at.isoformat(),
                    ],
                )
                alert_id = str(cur.fetchone()[0])

            cur.execute(
                """
                SELECT id
                FROM recommendations
                WHERE site_id = %s
                  AND source = 'ml_inference'
                  AND status IN ('pending', 'advisory_info', 'approved')
                  AND (
                    metadata->>'source_dedupe_key' = %s
                    OR metadata->>'alert_id' = %s
                  )
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                [site_id, source_dedupe_key, alert_id],
            )
            rec_row = cur.fetchone()
            if rec_row:
                recommendation_id = str(rec_row[0])
                created_recommendation = False
            else:
                recommendation_id = str(uuid.uuid4())
                created_recommendation = True
                action = {
                    "type": "inspect_chiller_critical_anomaly",
                    "operator_equipment_label": operator_label,
                    "internal_asset_id": equipment_code,
                    "required_outcome": ["real_fault", "sensor_fault", "alarm_cleared", "false_positive"],
                    "point_safety_classes": [{"point": "autoencoder_critical_anomaly", "safety_class": "HIGH"}],
                }
                expected_impact = {
                    "risk_reduction": "critical_fault_triage",
                    "energy_savings_kwh": 0,
                    "comfort_impact": "unknown_until_triage",
                }
                metadata = {
                    "recommendation_type": "fault_triage",
                    "recommendation_family": "ml_autoencoder_critical",
                    "equipment_type": equipment_type,
                    "operator_equipment_label": operator_label,
                    "internal_asset_reference": equipment_code,
                    "alert_id": alert_id,
                    "source_dedupe_key": source_dedupe_key,
                    "model_id": model_info.get("model_id"),
                    "model_type": "autoencoder",
                    "model_site_id": model_info.get("site_id"),
                    "input_contract": contract,
                    "anomaly_score": anomaly_score,
                    "threshold": threshold,
                    "score_pct": score_pct,
                    "severity": "critical",
                    "phase185_cutover": True,
                    "phase188_cutover_metadata": "post_phase185_cutover",
                    "point_safety_classes": [{"point": "autoencoder_critical_anomaly", "safety_class": "HIGH"}],
                }
                reason = (
                    f"{equipment_ref}: autoencoder critical anomaly score {anomaly_score:.4f} "
                    f"exceeds threshold {threshold:.4f} ({ratio:.2f}x). "
                    "Create/confirm operator triage and record whether this is a real fault, "
                    "sensor fault, cleared alarm, or false positive."
                )
                cur.execute(
                    """
                    INSERT INTO recommendations
                        (id, site_id, timestamp, action_type, risk_level, target_equipment,
                         action, reason, expected_impact, confidence, confidence_score, profile,
                         multi_objective_score, status, requires_approval, approval_status,
                         shadow_mode, metadata, source, source_type,
                         phase188_evidence_epoch, phase188_evidence_epoch_set_at,
                         phase188_evidence_epoch_reason)
                    VALUES
                        (%s::uuid, %s, %s::timestamptz, 'fault_triage', 'high', %s,
                         %s::jsonb, %s, %s::jsonb, 'high', %s, 'supervised',
                         %s, 'pending', false, 'not_required',
                         false, %s::jsonb, 'ml_inference', 'autoencoder',
                         'post_phase185_cutover', %s::timestamptz,
                         'Phase 188 evidence starts after Phase 185 site-scoped model cutover')
                    """,
                    [
                        recommendation_id,
                        site_id,
                        detected_at.isoformat(),
                        equipment_code,
                        json.dumps(action),
                        reason,
                        json.dumps(expected_impact),
                        min(1.0, score_pct / 100.0),
                        min(1.0, ratio / 3.0) if ratio else 0.0,
                        json.dumps(metadata),
                        detected_at.isoformat(),
                    ],
                )

            notify_result = {"success": False, "skipped": "existing_recommendation"}
            if created_recommendation:
                body = f"{message}\n\nRecommendation: {recommendation_id}\nAlert: {alert_id}"
                notify_result = asyncio.run(
                    NotificationService().send_alert_direct(title=title, body=body, alert_level=AlertLevel.CRITICAL)
                )
            logger.info(
                "[AE CRITICAL] Surfaced %s alert=%s recommendation=%s notify=%s",
                equipment_code,
                alert_id,
                recommendation_id,
                notify_result,
            )
            return {"alert_id": alert_id, "recommendation_id": recommendation_id}
        finally:
            cur.close()

    def fetch_sensor_window_from_db(
        self,
        equipment_code: str,
        equipment_type: str,
        hours: int = 24,
        site_id: str | None = None,
        feature_cols: list[str] | None = None,
    ) -> np.ndarray | None:
        """Fetch hourly aggregate telemetry and return a numpy feature window.

        Queries the last `hours` of readings, pivots sensor_type columns into a
        2-D array (timesteps × features) using the feature order the autoencoder
        was trained on.  Returns None if there are insufficient rows.
        """
        return _fetch_sensor_window_from_db(
            equipment_code,
            equipment_type,
            hours=hours,
            site_id=site_id,
            feature_cols=feature_cols,
        )

    def run_anomaly_scan(self, site_id: str) -> list[dict[str, Any]]:
        """Run anomaly detection on all active equipment for a site using real DB data.

        Fetches sensor windows from telemetry_hourly, runs the autoencoder,
        and persists anomalies to the anomalies table.  Returns a list of result dicts.
        """
        import os
        import uuid

        import psycopg2

        database_url = settings.database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL not set")

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
        critical_to_surface = []
        now = datetime.utcnow()

        for eq_id, eq_code, eq_type in equipment_rows:
            result = self.check_equipment(eq_code, eq_type, site_id=site_id)
            if result.get("error"):
                logger.debug("Skipping %s: %s", eq_code, result.get("error"))
                continue
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
                if raw_sev == "critical" and (result.get("model_info") or {}).get("input_contract"):
                    critical_to_surface.append(
                        {
                            "equipment_uuid": str(eq_id),
                            "equipment_code": eq_code,
                            "equipment_type": eq_type,
                            "result": result,
                        }
                    )

        site_uuid = None
        if anomalies_to_insert or critical_to_surface:
            try:
                conn = psycopg2.connect(database_url)
                conn.autocommit = True
                cur = conn.cursor()

                cur.execute("SELECT id FROM sites WHERE code = %s LIMIT 1", [site_id])
                row = cur.fetchone()
                site_uuid = str(row[0]) if row else None
                cur.close()
                conn.close()
            except Exception as e:
                logger.error(f"run_anomaly_scan: site lookup failed for {site_id}: {e}")

        if anomalies_to_insert and site_uuid:
            try:
                conn = psycopg2.connect(database_url)
                conn.autocommit = True
                cur = conn.cursor()
                try:
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
                finally:
                    cur.close()
                    conn.close()
            except Exception as e:
                logger.error(f"run_anomaly_scan: anomaly insert failed: {e}")

        if critical_to_surface and site_uuid:
            try:
                conn = psycopg2.connect(database_url)
                conn.autocommit = True
                for item in critical_to_surface:
                    self._surface_critical_anomaly(
                        conn=conn,
                        site_id=site_id,
                        site_uuid=site_uuid,
                        equipment_uuid=item["equipment_uuid"],
                        equipment_code=item["equipment_code"],
                        equipment_type=item["equipment_type"],
                        result=item["result"],
                        detected_at=now,
                    )
                conn.close()
            except Exception as e:
                logger.error(f"run_anomaly_scan: AE critical surfacing failed: {e}", exc_info=True)

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
