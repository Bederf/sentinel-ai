"""
Drift Detection for ML Models

Detects feature distribution drift and model prediction drift.
Uses simplified Kolmogorov-Smirnov test (no scipy dependency).

Phase 45-03: MLOps Monitoring and Success Metrics.
"""

import logging
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds
KS_DRIFT_THRESHOLD = 0.1  # KS statistic above this = drift detected
MODEL_DRIFT_THRESHOLD = 0.9  # Recent accuracy < 90% of historical = drift
EQUIPMENT_TYPES = ["chiller", "ahu", "fcu", "vav", "generator", "ups", "pump"]
MODEL_TYPES = ["lstm", "autoencoder"]

# Occupancy schedule (SAST = UTC+2)
OCCUPIED_HOURS_START = 6  # 06:00 SAST — occupied mode begins
OCCUPIED_HOURS_END = 22  # 22:00 SAST — occupied mode ends

# Minimum sample count per feature window before KS test is statistically meaningful
MIN_SAMPLES_PER_WINDOW = 30

# Lookup table for SA public holidays (pre-computed, matches site_holiday_service.py logic)
_SA_HOLIDAYS_2026 = frozenset(
    [
        "2026-01-01",
        "2026-03-21",
        "2026-04-27",
        "2026-05-01",
        "2026-06-16",
        "2026-08-09",
        "2026-09-24",
        "2026-12-16",
        "2026-12-25",
        "2026-12-26",
        # Easter-based 2026: Easter Sunday = April 5
        "2026-04-03",  # Good Friday
        "2026-04-06",  # Easter Monday
    ]
)


def _is_sa_holiday(target_date: date) -> bool:
    """Return True if target_date is a SA public holiday.

    Delegates to the dynamic per-year calendar (Easter-aware, no year lock);
    the frozen 2026 list is only a fallback if the app service is unavailable.
    """
    try:
        from app.services.site_holiday_service import _get_sa_public_holidays_cached

        return target_date.isoformat() in {h["date"] for h in _get_sa_public_holidays_cached(target_date.year)}
    except Exception:
        return target_date.isoformat() in _SA_HOLIDAYS_2026


def _get_occupancy_mode(ts: datetime | str) -> str:
    """Classify a UTC timestamp into occupancy mode (SAST hours).

    Args:
        ts: UTC timestamp (datetime or ISO string)

    Returns:
        "occupied"  — weekday 06:00-22:00 SAST
        "unoccupied" — weekday 22:00-06:00 SAST
        "holiday"   — SA public holiday (any hour)
        "weekend"   — Saturday/Sunday (any hour, non-holiday)
    """
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts

    # UTC → SAST (UTC+2)
    sa_hour = (dt.hour + 2) % 24
    sa_weekday = dt.weekday()  # Monday=0, Sunday=6
    sa_date = dt.date()

    if _is_sa_holiday(sa_date):
        return "holiday"
    if sa_weekday >= 5:
        return "weekend"
    if OCCUPIED_HOURS_START <= sa_hour < OCCUPIED_HOURS_END:
        return "occupied"
    return "unoccupied"


def _split_by_occupancy_mode(
    values: list[float],
    timestamps: list[str],
    target_mode: str,
) -> tuple[list[float], list[float]]:
    """Split values into baseline (older half) and current (newer half),
    filtering to the specified occupancy mode only.

    Never compares occupied-to-unoccupied or weekday-to-weekend.

    Args:
        values: Parallel list of sensor values
        timestamps: Parallel list of ISO timestamp strings (same length as values)
        target_mode: "occupied" or "unoccupied"

    Returns:
        (baseline, current) — filtered to target_mode, split chronologically
        at midpoint; empty lists if insufficient samples after filtering
    """
    if len(values) != len(timestamps):
        return [], []

    # Filter to target mode only
    filtered = [(v, t) for v, t in zip(values, timestamps, strict=False) if _get_occupancy_mode(t) == target_mode]
    if not filtered:
        return [], []

    # Sort by timestamp
    filtered.sort(key=lambda x: x[1])
    sorted_vals = [v for v, _ in filtered]

    mid = len(sorted_vals) // 2
    if mid < MIN_SAMPLES_PER_WINDOW:
        return [], []
    return sorted_vals[:mid], sorted_vals[mid:]


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
        "features": [
            "chw_return_temp",
            "chw_supply_temp",
            "compressor_current_1",
            "compressor_current_2",
            "cond_return_temp",
            "cond_supply_temp",
            "condenser_flow",
            "staging_state",
        ],
        "uses_real_data": True,
    },
    "ahu": {
        "equipment_ids": ["S002-AHU-001", "S002-AHU-002", "S002-AHU-201"],
        "features": ["return_air_temp", "supply_air_temp", "fan_speed", "filter_dp"],
        "uses_real_data": True,
    },
    "fcu": {
        "equipment_ids": [
            f"S002-FCU-{u:03d}"
            for u in list(range(1, 6)) + list(range(101, 106)) + list(range(201, 206)) + list(range(301, 306))
        ],
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
    window_hours: int = 48,
) -> dict[str, tuple[list[float], list[str]]]:
    """Fetch sensor readings from Supabase for given equipment and features.

    Groups by sensor_type across all equipment of that type, returning
    both values and timestamps for each feature. Timestamps are used
    for occupancy-aware drift detection.

    Args:
        equipment_ids: List of equipment IDs to query (e.g. ["S002-CHILLER-B1-001"])
        features: List of sensor_type values to collect (e.g. ["chw_return_temp"])
        window_hours: How many hours of data to fetch (default 48h for two full days)

    Returns:
        Dict mapping feature name → (values_list, timestamps_list)
    """
    if not equipment_ids or not features:
        return {}

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

        resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, sensor_type, value, recorded_at")
            .in_("equipment_id", equipment_ids)
            .in_("sensor_type", features)
            .gte("recorded_at", cutoff_str)
            .order("recorded_at")
            .execute()
        )

        if not resp.data:
            return {}

        by_sensor: dict[str, tuple[list[float], list[str]]] = {}
        for feat in features:
            by_sensor[feat] = ([], [])

        for row in resp.data:
            sensor_type = row.get("sensor_type")
            val = row.get("value")
            ts = row.get("recorded_at")
            if sensor_type not in features:
                continue
            if val is None or ts is None:
                continue
            try:
                by_sensor[sensor_type][0].append(float(val))
                by_sensor[sensor_type][1].append(ts)
            except (TypeError, ValueError):
                pass

        return by_sensor

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

        Occupancy-aware: only compares readings within the same operational
        mode (occupied vs unoccupied). Never compares day-to-night readings.

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

        # Get the occupancy mode used for display in metrics/logs
        current_mode = _get_occupancy_mode(datetime.now(UTC))

        result = {
            "equipment_type": equipment_type,
            "detected_at": datetime.now().isoformat(),
            "drift_detected": len(drifted_features) > 0,
            "drifted_features": drifted_features,
            "feature_drift_scores": drift_scores,
            "threshold": threshold,
            "features_checked": len(drift_scores),
            "features_drifted": len(drifted_features),
            "occupancy_mode": current_mode,
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
        # Phase 236-03: verdicts derive ONLY from measured rolling accuracy
        # (ml_model_accuracy, written by the daily accuracy job). No measured
        # data → insufficient_data, never a fake verdict. The previous
        # hardcoded 0.89/0.85 baselines and demo fallbacks could never fire
        # and are removed.
        verdict_row = self._latest_measured_verdict(model_type)

        if verdict_row is None:
            result = {
                "model_type": model_type,
                "detected_at": datetime.now().isoformat(),
                "recent_accuracy": None,
                "historical_accuracy": None,
                "drift_detected": False,
                "verdict": "insufficient_data",
                "degradation_pct": None,
                "threshold": threshold,
            }
            self._detection_history.append(result)
            return result

        result = {
            "model_type": model_type,
            "detected_at": datetime.now().isoformat(),
            "model_id": verdict_row.get("model_id"),
            "recent_accuracy": verdict_row.get("measured"),
            "historical_accuracy": verdict_row.get("baseline"),
            "drift_detected": verdict_row.get("drift_verdict") == "drift_suspected",
            "verdict": verdict_row.get("drift_verdict"),
            "degradation_pct": verdict_row.get("degradation_pct"),
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
                governance_metrics.record_drift_score(eq_type, eq_type.upper(), score)
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
        48h window and splits by occupancy mode (occupied vs unoccupied),
        comparing within the same operational mode. Falls back to synthetic
        for equipment types without real data.
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

        sensor_data = _get_supabase_sensor_data(equipment_ids, features, window_hours=48)
        if not sensor_data:
            return _generate_training_stats(equipment_type)

        # Determine current occupancy mode to decide which split to return
        now_utc = datetime.now(UTC)
        current_mode = _get_occupancy_mode(now_utc)
        if current_mode not in ("occupied", "unoccupied"):
            current_mode = "occupied"  # default to occupied for holiday/weekend

        baseline: dict[str, list[float]] = {}
        for feat, (values, timestamps) in sensor_data.items():
            bl, cu = _split_by_occupancy_mode(values, timestamps, target_mode=current_mode)
            if bl and cu:
                baseline[feat] = bl

        if not baseline:
            return _generate_training_stats(equipment_type)
        return baseline

    def _get_current_stats(self, equipment_type: str) -> dict[str, list[float]]:
        """Get current feature statistics for equipment type.

        Queries Supabase with a 48h window and splits by occupancy mode,
        returning the current (newer) half within the same operational mode
        as the current time. Falls back to synthetic for types without real
        data or insufficient readings.
        """
        cfg = EQUIPMENT_TO_SENSORS.get(equipment_type, {})
        if not cfg.get("uses_real_data", False):
            return _generate_current_stats(equipment_type, drift_amount=0.0)

        equipment_ids = cfg["equipment_ids"]
        features = cfg["features"]
        if not equipment_ids or not features:
            return _generate_current_stats(equipment_type, drift_amount=0.0)

        sensor_data = _get_supabase_sensor_data(equipment_ids, features, window_hours=48)
        if not sensor_data:
            return _generate_current_stats(equipment_type, drift_amount=0.0)

        now_utc = datetime.now(UTC)
        current_mode = _get_occupancy_mode(now_utc)
        if current_mode not in ("occupied", "unoccupied"):
            current_mode = "occupied"

        current: dict[str, list[float]] = {}
        for feat, (values, timestamps) in sensor_data.items():
            bl, cu = _split_by_occupancy_mode(values, timestamps, target_mode=current_mode)
            if bl and cu:
                current[feat] = cu

        if not current:
            return _generate_current_stats(equipment_type, drift_amount=0.0)
        return current

    def _latest_measured_verdict(self, model_type: str) -> dict[str, Any] | None:
        """Latest measured drift verdict for a model type from ml_model_accuracy.

        Phase 236-03: the real drift signal. Returns None when no measured
        accuracy row exists for the model kind (cold start / no logged
        predictions joined yet) so the caller fails closed to
        insufficient_data instead of inventing a number.

        model_type is the drift-loop label ('lstm'/'autoencoder'); the
        accuracy table keys by model_kind ('lstm_forecast'/'ae_score').
        """
        model_kind = {"lstm": "lstm_forecast", "autoencoder": "ae_score"}.get(model_type)
        if model_kind is None:
            return None
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            # This is a COARSE per-kind summary: with several models of the same
            # kind, the authoritative signal is the per-model finding raised in
            # ml_accuracy_service.reconcile_drift_findings. Here we surface the
            # most recent run and, within it, prefer a drift_suspected row so the
            # summary never hides a drifting model behind an arbitrary healthy one.
            result = (
                client.table("ml_model_accuracy")
                .select("*")
                .eq("model_kind", model_kind)
                .eq("window_days", 7)
                .order("computed_at", desc=True)
                .limit(50)
                .execute()
            )
        except Exception as e:
            logger.debug("Measured verdict lookup failed for %s: %s", model_type, e)
            return None

        rows = result.data or []
        if not rows:
            return None
        latest_ts = rows[0].get("computed_at")
        latest_run = [r for r in rows if r.get("computed_at") == latest_ts]
        drifting = [r for r in latest_run if r.get("drift_verdict") == "drift_suspected"]
        candidate = drifting[0] if drifting else latest_run[0]
        if candidate.get("drift_verdict") == "insufficient_data":
            return None
        row = candidate

        if model_kind == "lstm_forecast":
            measured, baseline = row.get("mae"), row.get("baseline_mae")
            degradation = round((measured / baseline - 1.0) * 100, 1) if measured is not None and baseline else None
        else:
            measured, baseline = row.get("score_median"), row.get("baseline_threshold")
            degradation = None
        return {
            "model_id": row.get("model_id"),
            "measured": measured,
            "baseline": baseline,
            "drift_verdict": row.get("drift_verdict"),
            "degradation_pct": degradation,
        }


# Singleton
_detector: DriftDetector | None = None


def get_drift_detector() -> DriftDetector:
    """Get singleton DriftDetector instance."""
    global _detector
    if _detector is None:
        _detector = DriftDetector()
    return _detector
