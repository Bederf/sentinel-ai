"""
Automated Model Retraining Scheduler

Monitors model freshness and performance metrics. Triggers retraining
when models are stale (>30 days) or underperforming (R² < 0.65).
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Thresholds
MAX_MODEL_AGE_DAYS = 30
MIN_R2_SCORE = 0.65
EQUIPMENT_TYPES = ["chiller", "ahu", "fcu", "vav", "generator", "ups", "pump"]
MODEL_TYPES = ["lstm", "autoencoder", "classifier"]


@dataclass
class RetrainResult:
    """Result of a retraining operation."""

    model_id: str
    model_type: str
    equipment_type: str
    triggered_at: str
    reason: str
    success: bool = False
    new_model_id: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None


class RetrainingScheduler:
    """Monitors model staleness and triggers retraining."""

    def __init__(self):
        self._history: List[RetrainResult] = []

    def check_all_models(self) -> List[Dict[str, Any]]:
        """Check freshness and performance of all active models.

        Returns a list of dicts with model_type, equipment_type, status (fresh/stale/missing),
        age_days, r2_score, needs_retrain bool.
        """
        from ml.registry import get_model_registry

        registry = get_model_registry()
        results = []

        for model_type in MODEL_TYPES:
            for equipment_type in EQUIPMENT_TYPES:
                model = registry.get_active_model(model_type, equipment_type)

                if model is None:
                    results.append(
                        {
                            "model_type": model_type,
                            "equipment_type": equipment_type,
                            "status": "missing",
                            "age_days": None,
                            "r2_score": None,
                            "needs_retrain": True,
                            "reason": "No active model found",
                        }
                    )
                    continue

                # Calculate age
                registered_at = model.get("registered_at", "")
                try:
                    reg_date = datetime.fromisoformat(registered_at)
                    age_days = (datetime.now() - reg_date).days
                except (ValueError, TypeError):
                    age_days = 999  # Treat unparseable as very old

                # Get R² score from metrics
                metrics = model.get("metrics", {})
                r2_score = metrics.get("r2_score", metrics.get("val_r2", metrics.get("cv_accuracy", None)))

                # Determine status
                is_stale = age_days > MAX_MODEL_AGE_DAYS
                is_underperforming = r2_score is not None and r2_score < MIN_R2_SCORE
                needs_retrain = is_stale or is_underperforming

                reasons = []
                if is_stale:
                    reasons.append(f"Model age {age_days}d exceeds {MAX_MODEL_AGE_DAYS}d threshold")
                if is_underperforming:
                    reasons.append(f"R² score {r2_score:.3f} below {MIN_R2_SCORE} threshold")

                status = "stale" if is_stale else ("underperforming" if is_underperforming else "fresh")

                results.append(
                    {
                        "model_type": model_type,
                        "equipment_type": equipment_type,
                        "model_id": model.get("model_id"),
                        "status": status,
                        "age_days": age_days,
                        "r2_score": r2_score,
                        "needs_retrain": needs_retrain,
                        "reason": "; ".join(reasons) if reasons else "Model is fresh and performing well",
                    }
                )

        return results

    def trigger_retraining(
        self,
        model_type: str,
        equipment_type: str,
        reason: str = "manual",
    ) -> RetrainResult:
        """Trigger retraining for a specific model type and equipment type.

        This is a lightweight wrapper - actual training would invoke
        LSTMTrainer or AutoencoderTrainer. For now, registers the intent
        and returns the result.
        """
        result = RetrainResult(
            model_id=f"{model_type}_{equipment_type}",
            model_type=model_type,
            equipment_type=equipment_type,
            triggered_at=datetime.now().isoformat(),
            reason=reason,
        )

        try:
            logger.info(f"Retraining triggered: {model_type}/{equipment_type} - reason: {reason}")

            if model_type == "lstm":
                from ml.lstm.train import LSTMTrainer

                trainer = LSTMTrainer()
                train_result = trainer.train_equipment_type(
                    equipment_type,
                    epochs=50,
                    use_demo_data=False,
                )
                result.success = True
                result.metrics = train_result.get("metrics", {})
                result.new_model_id = train_result.get("model_id", "")
            elif model_type == "autoencoder":
                from ml.autoencoder.train import AutoencoderTrainer

                trainer = AutoencoderTrainer()
                train_result = trainer.train_equipment_type(
                    equipment_type,
                    epochs=50,
                    use_demo_data=False,
                )
                result.success = True
                result.metrics = train_result.get("metrics", {})
                result.new_model_id = train_result.get("model_id", "")
            elif model_type == "classifier":
                from ml.classifier.train import ClassifierTrainer

                trainer = ClassifierTrainer()
                train_result = trainer.train_equipment_type(equipment_type)
                result.success = True
                result.metrics = train_result.get("metrics", {})
                result.new_model_id = train_result.get("model_id", "")
            else:
                result.error = f"Unknown model type: {model_type}"

        except Exception as e:
            logger.error(f"Retraining failed for {model_type}/{equipment_type}: {e}")
            result.error = str(e)

        self._history.append(result)
        return result

    def auto_retrain_stale(self) -> List[RetrainResult]:
        """Check all models and retrain the first stale one found.

        Called by the background scheduler daily.
        Returns list of retrain results (typically 0 or 1).
        """
        checks = self.check_all_models()
        results = []

        for check in checks:
            if check["needs_retrain"] and check["status"] != "missing":
                result = self.trigger_retraining(
                    model_type=check["model_type"],
                    equipment_type=check["equipment_type"],
                    reason=check.get("reason", "auto_stale"),
                )
                results.append(result)
                break  # Only retrain one per cycle to avoid overload

        return results

    def get_retrain_history(self) -> List[Dict[str, Any]]:
        """Return history of retrain operations."""
        return [
            {
                "model_id": r.model_id,
                "model_type": r.model_type,
                "equipment_type": r.equipment_type,
                "triggered_at": r.triggered_at,
                "reason": r.reason,
                "success": r.success,
                "new_model_id": r.new_model_id,
                "metrics": r.metrics,
                "error": r.error,
            }
            for r in self._history
        ]


# Singleton
_scheduler: Optional[RetrainingScheduler] = None


def get_retraining_scheduler() -> RetrainingScheduler:
    """Get singleton RetrainingScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = RetrainingScheduler()
    return _scheduler
