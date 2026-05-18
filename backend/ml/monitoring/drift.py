"""
Drift Detection for ML Models

Detects feature distribution drift and model prediction drift.
Uses simplified Kolmogorov-Smirnov test (no scipy dependency).

Phase 45-03: MLOps Monitoring and Success Metrics.
"""

import logging
import math
from datetime import datetime, timedelta, UTC
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds
KS_DRIFT_THRESHOLD = 0.1  # KS statistic above this = drift detected
MODEL_DRIFT_THRESHOLD = 0.9  # Recent accuracy < 90% of historical = drift
EQUIPMENT_TYPES = ["chiller", "ahu", "fcu", "vav", "generator", "ups", "pump"]
MODEL_TYPES = ["lstm", "autoencoder"]


def _ks_statistic(sample_a: list[float], sample_b: list[float]) -> float:
    """Compute two-sample Kolmogorov-Smirnov statistic.

    Simplified implementation using empirical CDFs without scipy.
    Returns the maximum absolute difference between the two ECDFs.

    Args:
        sample_a: First sample (e.g., training distribution).
        sample_b: Second sample (e.g., current distribution).

    Returns:
        KS statistic (0.0 to 1.0). Higher = more drift.
    """
    if not sample_a or not sample_b:
        return 0.0

    n_a = len(sample_a)
    n_b = len(sample_b)

    # Combine and sort all unique values
    all_values = sorted(set(sample_a + sample_b))

    max_diff = 0.0
    for val in all_values:
        # Empirical CDF for sample A
        ecdf_a = sum(1 for x in sample_a if x <= val) / n_a
        # Empirical CDF for sample B
        ecdf_b = sum(1 for x in sample_b if x <= val) / n_b
        diff = abs(ecdf_a - ecdf_b)
        if diff > max_diff:
            max_diff = diff

    return round(max_diff, 4)


# Equipment type → Supabase equipment_id prefixes → sensor features
# Only equipment types with real sensor data are marked uses_real_data=true
EQUIPMENT_TO_SENSORS: dict[str, dict[str, Any]] = {
    "chiller": {
        "equipment_ids": ["S002-CHILLER-B1-001"],
        "features": ["chw_return_temp", "chw_supply_temp", "compressor_current_1",
                     "compressor_current_2", "cond_return_temp", "cond_supply_temp",
                     "condenser_flow", "staging_state"],
        "uses_real_data": True,
    },
    "ahu": {
        "equipment_ids": ["S002-AHU-001", "S002-AHU-002", "S002-AHU-201"],
        "features": ["return_air_temp", "supply_air_temp", "fan_speed", "filter_dp"],
        "uses_real_data": True,
    },
    "fcu": {
        "equipment_ids": [f"S002-FCU-{u:03d}" for u in list(range(1, 6)) +
                         list(range(101, 106)) + list(range(201, 206)) + list(range(301, 306))],
        "features": ["room_temp", "co2_ppm"],
        "uses_real_data": True,
    },
    "vav": {
        "equipment_ids": [],
        "features": [],
        "uses_real_data": False,
    },
    "generator": {
        "equipment_ids": [],
        "features": [],
        "uses_real_data": False,
    },
    "ups": {
        "equipment_ids": [],
        "features": [],
        "uses_real_data": False,
    },
    "pump": {
        "equipment_ids": [],
        "features": [],
        "uses_real_data": False,
    },
}


def _get_supabase_sensor_data(
    equipment_ids: list[str],
    features: list[str],
    window_hours: int = 12,
) -> dict[str, list[float]]:
    """Fetch sensor readings from Supabase for given equipment and features.

    Groups by sensor_type across all equipment of that type, returning
    the full list of values for each feature across the time window.

    Args:
        equipment_ids: List of equipment IDs to query (e.g. ["S002-CHILLER-B1-001"])
        features: List of sensor_type values to collect (e.g. ["chw_return_temp"])
        window_hours: How many hours of recent data to fetch (for current window)

    Returns:
        Dict mapping feature name → list of sensor values from Supabase
    """
    if not equipment_ids or not features:
        return {}

    result: dict[str, list[float]] = {f: [] for f in features}

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
    except Exception:
        return {}

    try:
        from app.config.settings import settings  # noqa: F401 - needed to ensure settings loaded
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=window_hours)
        cutoff_str = cutoff.isoformat()

        # Build query: select sensor_type + value for matching equipment IDs
        # Use .in_() for equipment_id filter
        resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, sensor_type, value")
            .in_("equipment_id", equipment_ids)
            .in_("sensor_type", features)
            .gte("recorded_at", cutoff_str)
            .order("recorded_at")
            .execute()
        )

        if not resp.data:
            return {}

        # Group values by sensor_type
        from collections import defaultdict

        by_sensor: dict[str, list[float]] = defaultdict(list)
        for row in resp.data:
            val = row.get("value")
            if val is not None:
                try:
                    by_sensor[row["sensor_type"]].append(float(val))
                except (TypeError, ValueError):
                    pass

        return dict(by_sensor)

    except Exception:
        return {}


def _generate_training_stats(equipment_type: str) -> dict[str, list[float]]:
    """Generate simulated training distribution statistics.

    In production, these would be saved during model training.
    For demo, we generate realistic baseline distributions.
    """
    import random

    random.seed(hash(equipment_type) % 2**31)

    base_distributions = {
        "chiller": {
            "supply_temp": [random.gauss(7.0, 0.5) for _ in range(100)],
            "return_temp": [random.gauss(12.0, 0.8) for _ in range(100)],
            "power_kw": [random.gauss(150.0, 20.0) for _ in range(100)],
            "cop": [random.gauss(4.5, 0.3) for _ in range(100)],
            "runtime_hours": [random.gauss(2000, 500) for _ in range(100)],
        },
        "ahu": {
            "supply_temp": [random.gauss(14.0, 1.0) for _ in range(100)],
            "return_temp": [random.gauss(24.0, 1.5) for _ in range(100)],
            "fan_speed": [random.gauss(75.0, 10.0) for _ in range(100)],
            "filter_dp": [random.gauss(150.0, 30.0) for _ in range(100)],
            "runtime_hours": [random.gauss(3000, 600) for _ in range(100)],
        },
        "generator": {
            "voltage": [random.gauss(400.0, 5.0) for _ in range(100)],
            "frequency": [random.gauss(50.0, 0.2) for _ in range(100)],
            "oil_pressure": [random.gauss(45.0, 3.0) for _ in range(100)],
            "coolant_temp": [random.gauss(82.0, 5.0) for _ in range(100)],
            "runtime_hours": [random.gauss(500, 200) for _ in range(100)],
        },
    }

    default = {
        "temperature": [random.gauss(22.0, 2.0) for _ in range(100)],
        "power_kw": [random.gauss(50.0, 10.0) for _ in range(100)],
        "runtime_hours": [random.gauss(2000, 500) for _ in range(100)],
        "vibration": [random.gauss(2.0, 0.5) for _ in range(100)],
    }

    return base_distributions.get(equipment_type, default)


def _generate_current_stats(equipment_type: str, drift_amount: float = 0.0) -> dict[str, list[float]]:
    """Generate simulated current distribution statistics.

    Args:
        equipment_type: Equipment type to generate stats for.
        drift_amount: Amount of drift to inject (0.0 = no drift, 1.0 = significant).
    """
    import random

    random.seed(int(datetime.now().timestamp()) % 2**31)

    training = _generate_training_stats(equipment_type)
    current = {}

    for feature, values in training.items():
        mean = sum(values) / len(values)
        std = math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))
        drifted_mean = mean + (std * drift_amount * 1.5)
        drifted_std = std * (1.0 + drift_amount * 0.5)
        current[feature] = [random.gauss(drifted_mean, drifted_std) for _ in range(80)]

    return current


class DriftDetector:
    """Detects feature and model drift for ML models.

    Compares current data distributions against training-time baselines
    using the Kolmogorov-Smirnov statistic.
    """

    def __init__(self):
        self._detection_history: list[dict[str, Any]] = []
        self._feature_baselines: dict[str, dict[str, list[float]]] = {}

    def detect_feature_drift(
        self,
        equipment_type: str,
        threshold: float = KS_DRIFT_THRESHOLD,
    ) -> dict[str, Any]:
        """Compare current feature distributions to training distribution.

        Args:
            equipment_type: Equipment type to check.
            threshold: KS statistic threshold for drift detection.

        Returns:
            Dict with drift detection results per feature.
        """
        training_stats = self._get_training_stats(equipment_type)
        current_stats = self._get_current_stats(equipment_type)

        drift_scores: dict[str, float] = {}
        drifted_features: list[str] = []

        for feature in training_stats:
            if feature not in current_stats:
                continue

            score = _ks_statistic(training_stats[feature], current_stats[feature])
            drift_scores[feature] = score

            if score > threshold:
                drifted_features.append(feature)

        result = {
            "equipment_type": equipment_type,
            "detected_at": datetime.now().isoformat(),
            "drift_detected": len(drifted_features) > 0,
            "drifted_features": drifted_features,
            "feature_drift_scores": drift_scores,
            "threshold": threshold,
            "features_checked": len(drift_scores),
            "features_drifted": len(drifted_features),
        }

        self._detection_history.append(result)
        return result

    def detect_model_drift(
        self,
        model_type: str,
        threshold: float = MODEL_DRIFT_THRESHOLD,
    ) -> dict[str, Any]:
        """Detect degradation in model predictions over time.

        Compares recent accuracy (last 7 days) to historical baseline.

        Args:
            model_type: Model type to check (lstm, autoencoder).
            threshold: Recent accuracy must be >= threshold * historical.

        Returns:
            Dict with model drift detection results.
        """
        recent_accuracy = self._get_recent_accuracy(model_type, days=7)
        historical_accuracy = self._get_historical_accuracy(model_type)

        drift_detected = recent_accuracy < (historical_accuracy * threshold)
        degradation_pct = (
            round((1.0 - recent_accuracy / max(historical_accuracy, 0.001)) * 100, 1)
            if historical_accuracy > 0
            else 0.0
        )

        result = {
            "model_type": model_type,
            "detected_at": datetime.now().isoformat(),
            "recent_accuracy": round(recent_accuracy, 3),
            "historical_accuracy": round(historical_accuracy, 3),
            "drift_detected": drift_detected,
            "degradation_pct": degradation_pct,
            "threshold": threshold,
        }

        self._detection_history.append(result)
        return result

    def detect_all_drift(self) -> dict[str, Any]:
        """Run drift detection across all equipment types and model types.

        Returns:
            Comprehensive drift report.
        """
        feature_results = []
        model_results = []

        for eq_type in EQUIPMENT_TYPES:
            result = self.detect_feature_drift(eq_type)
            feature_results.append(result)

        for model_type in MODEL_TYPES:
            result = self.detect_model_drift(model_type)
            model_results.append(result)

        total_feature_drift = sum(1 for r in feature_results if r["drift_detected"])
        total_model_drift = sum(1 for r in model_results if r["drift_detected"])

        # Prometheus metrics instrumentation (best-effort)
        try:
            from app.api.metrics import sentinel_model_drift_alerts, sentinel_model_drift_score
            from app.services.governance_metrics_collector import governance_metrics

            for result in feature_results:
                eq_type = result["equipment_type"]
                drift_detected = result["drift_detected"]
                sentinel_model_drift_alerts.labels(
                    site_id="site-002",
                    model_type=eq_type.upper(),
                ).set(1 if drift_detected else 0)
                # Compute aggregate drift score: ratio of drifted features to checked features
                features_checked = result.get("features_checked", 0)
                features_drifted = result.get("features_drifted", 0)
                score = features_drifted / features_checked if features_checked > 0 else 0.0
                sentinel_model_drift_score.labels(
                    model_id=eq_type,
                    model_type=eq_type.upper(),
                ).set(score)
                governance_metrics.record_drift_score(
                    eq_type, eq_type.upper(), score
                )
        except Exception:
            pass  # Metrics are best-effort, never block business logic

        return {
            "detected_at": datetime.now().isoformat(),
            "summary": {
                "equipment_types_checked": len(feature_results),
                "equipment_types_with_drift": total_feature_drift,
                "model_types_checked": len(model_results),
                "model_types_with_drift": total_model_drift,
                "any_drift_detected": total_feature_drift > 0 or total_model_drift > 0,
            },
            "feature_drift": feature_results,
            "model_drift": model_results,
        }

    def get_detection_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent drift detection results."""
        return self._detection_history[-limit:]

    def set_training_baseline(self, equipment_type: str, features: dict[str, list[float]]) -> None:
        """Store training-time feature distributions as baseline.

        In production, called after model training completes.
        """
        self._feature_baselines[equipment_type] = features

    def _get_training_stats(self, equipment_type: str) -> dict[str, list[float]]:
        """Get training-time statistics for equipment type.

        Uses stored baseline if set; otherwise queries Supabase with a
        long window and splits time-range in half (older half = baseline).
        Falls back to synthetic for equipment types without real data.
        """
        if equipment_type in self._feature_baselines:
            return self._feature_baselines[equipment_type]

        cfg = EQUIPMENT_TO_SENSORS.get(equipment_type, {})
        if not cfg.get("uses_real_data", False):
            return _generate_training_stats(equipment_type)

        equipment_ids = cfg["equipment_ids"]
        features = cfg["features"]
        if not equipment_ids or not features:
            return _generate_training_stats(equipment_type)

        # Fetch all available data for this equipment type (up to 48h window)
        sensor_data = _get_supabase_sensor_data(equipment_ids, features, window_hours=48)
        if not sensor_data:
            return _generate_training_stats(equipment_type)

        # Split each feature's time series: first half = baseline, second half = current
        baseline: dict[str, list[float]] = {}
        for feat, values in sensor_data.items():
            mid = len(values) // 2
            if mid < 2:
                return _generate_training_stats(equipment_type)
            baseline[feat] = values[:mid]

        return baseline

    def _get_current_stats(self, equipment_type: str) -> dict[str, list[float]]:
        """Get current feature statistics for equipment type.

        Queries Supabase with a long window and splits time-range in half
        (newer half = current). Falls back to synthetic for types without
        real data or insufficient readings.
        """
        cfg = EQUIPMENT_TO_SENSORS.get(equipment_type, {})
        if not cfg.get("uses_real_data", False):
            return _generate_current_stats(equipment_type, drift_amount=0.0)

        equipment_ids = cfg["equipment_ids"]
        features = cfg["features"]
        if not equipment_ids or not features:
            return _generate_current_stats(equipment_type, drift_amount=0.0)

        # Fetch all available data for this equipment type (up to 48h window)
        sensor_data = _get_supabase_sensor_data(equipment_ids, features, window_hours=48)
        if not sensor_data:
            return _generate_current_stats(equipment_type, drift_amount=0.0)

        # Split each feature's time series: second half = current
        current: dict[str, list[float]] = {}
        for feat, values in sensor_data.items():
            mid = len(values) // 2
            if mid < 2:
                return _generate_current_stats(equipment_type, drift_amount=0.0)
            current[feat] = values[mid:]

        return current

    def _get_recent_accuracy(self, model_type: str, days: int = 7) -> float:
        """Get recent prediction accuracy for model type.

        In production, this would query actual prediction outcomes.
        """
        try:
            from ml.monitoring.performance_monitor import get_performance_monitor

            monitor = get_performance_monitor()
            result = monitor.evaluate_predictions(days_back=days)
            metrics = result.get("metrics", {})
            return metrics.get("accuracy", 0.85)
        except Exception:
            # Demo seeded accuracy values
            base_accuracy = {"lstm": 0.87, "autoencoder": 0.83}
            return base_accuracy.get(model_type, 0.80)

    def _get_historical_accuracy(self, model_type: str) -> float:
        """Get historical baseline accuracy for model type.

        In production, this would be stored during model validation.
        """
        baseline_accuracy = {"lstm": 0.89, "autoencoder": 0.85}
        return baseline_accuracy.get(model_type, 0.82)


# Singleton
_detector: DriftDetector | None = None


def get_drift_detector() -> DriftDetector:
    """Get singleton DriftDetector instance."""
    global _detector
    if _detector is None:
        _detector = DriftDetector()
    return _detector
