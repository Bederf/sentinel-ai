"""ML model drift score calculator.

Computes a drift score (0.0-1.0) per registered model by comparing
current R-squared against baseline.  Alert levels: ok / warning / critical.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to the JSON fallback for ML model registry
_ML_MODELS_JSON = Path(__file__).parent.parent.parent / "data" / "ml_models.json"

# Drift alert thresholds
DRIFT_OK_MAX = 0.3
DRIFT_WARNING_MAX = 0.6


def _load_json(path: Path) -> list[dict[str, Any]] | dict[str, Any]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.error("Failed reading %s: %s", path, exc)
        return []


class ModelDriftCalculator:
    """Calculate drift scores for registered ML models."""

    def __init__(self, *, models_path: Path | None = None) -> None:
        self._models_path = models_path or _ML_MODELS_JSON

    # ------------------------------------------------------------------
    # Core formula
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_drift_score(
        model_id: str,  # noqa: ARG004 – kept for API consistency
        baseline_r_squared: float,
        recent_r_squared: float,
    ) -> float:
        """Return drift score in ``[0.0, 1.0]``.

        * 0.0 = no drift (recent matches baseline)
        * 1.0 = complete drift (recent performance is zero or negative)

        If *baseline_r_squared* is <= 0 we cannot meaningfully compute
        drift, so we return 0.0 as a safe default.
        """
        if baseline_r_squared <= 0:
            return 0.0
        raw = 1.0 - (recent_r_squared / baseline_r_squared)
        return max(0.0, min(1.0, raw))

    # ------------------------------------------------------------------
    # Alert level
    # ------------------------------------------------------------------

    @staticmethod
    def _alert_level(score: float) -> str:
        if score < DRIFT_OK_MAX:
            return "ok"
        if score < DRIFT_WARNING_MAX:
            return "warning"
        return "critical"

    # ------------------------------------------------------------------
    # Batch scoring
    # ------------------------------------------------------------------

    async def get_all_drift_scores(self) -> list[dict[str, Any]]:
        """Score every active model in the registry.

        In local/dev mode we use the stored ``r_squared_avg`` as both
        baseline and current (drift = 0).  Production would fetch live
        evaluation metrics separately.
        """
        raw = _load_json(self._models_path)
        models: list[dict[str, Any]] = raw if isinstance(raw, list) else raw.get("models", [])

        results: list[dict[str, Any]] = []
        for m in models:
            status = (m.get("status") or "").lower()
            if status != "active":
                continue

            model_id = m.get("model_id", m.get("id", "unknown"))
            baseline = m.get("r_squared_avg") or 0.0
            # In local mode current == baseline; production would query
            # a live evaluation table.
            current = baseline

            score = self.calculate_drift_score(model_id, baseline, current)
            results.append(
                {
                    "model_id": model_id,
                    "model_type": m.get("model_type", "unknown"),
                    "model_name": m.get("notes", model_id),
                    "baseline_r_squared": baseline,
                    "current_r_squared": current,
                    "drift_score": round(score, 4),
                    "alert_level": self._alert_level(score),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    @staticmethod
    def get_drift_alerts(
        scores: list[dict[str, Any]],
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Return only entries whose drift score exceeds *threshold*,
        sorted by drift_score descending."""
        return sorted(
            [s for s in scores if s.get("drift_score", 0) > threshold],
            key=lambda s: s["drift_score"],
            reverse=True,
        )


def get_model_drift_calculator() -> ModelDriftCalculator:
    """Factory helper."""
    return ModelDriftCalculator()
