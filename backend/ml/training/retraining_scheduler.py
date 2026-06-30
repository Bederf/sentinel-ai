"""
Automated Model Retraining Scheduler

Monitors model freshness and performance metrics. Triggers retraining
when models are stale (>30 days) or underperforming (R² < 0.65).

Feature discovery runs once per week before any retraining cycle, updating
ml_model_config with the actual sensor types present for each site so that
training always uses the real BMS points — not hardcoded global defaults.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

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
    new_model_id: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None


DISCOVERY_INTERVAL_DAYS = 7  # Re-discover features at most once per week


class RetrainingScheduler:
    """Monitors model staleness and triggers retraining."""

    def __init__(self):
        self._history: list[RetrainResult] = []
        self._last_discovery_at: datetime | None = None

    def refresh_features_for_active_sites(self, force: bool = False) -> dict[str, dict[str, list[str]]]:
        """Discover and register ML features for all supervised/autonomous sites.

        Runs at most once per week (DISCOVERY_INTERVAL_DAYS) unless force=True.
        Must be called before retraining so models train on the site's actual
        BMS sensor types, not hardcoded global defaults.

        Returns:
            Dict of {site_id: {equipment_type: [sensor_types]}} for what was registered.
        """
        now = datetime.now()
        if (
            not force
            and self._last_discovery_at is not None
            and (now - self._last_discovery_at) < timedelta(days=DISCOVERY_INTERVAL_DAYS)
        ):
            logger.info(
                "[ML DISCOVER] Skipping — last ran %s ago (interval: %dd)",
                now - self._last_discovery_at,
                DISCOVERY_INTERVAL_DAYS,
            )
            return {}

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            resp = (
                client.table("sites")
                .select("code,onboarding_phase")
                .not_.in_("onboarding_phase", ["pending", "blocked"])
                .execute()
            )
            active_sites = [row["code"] for row in (resp.data or []) if row.get("code")]
        except Exception as e:
            logger.warning("[ML DISCOVER] Could not load active sites: %s", e)
            active_sites = []

        if not active_sites:
            logger.info("[ML DISCOVER] No active sites found — skipping discovery")
            return {}

        from ml.model_config import discover_site_ml_features

        all_results: dict[str, dict[str, list[str]]] = {}
        for site_id in active_sites:
            logger.info("[ML DISCOVER] Running feature discovery for %s", site_id)
            try:
                result = discover_site_ml_features(site_id)
                if result:
                    all_results[site_id] = result
                    logger.info(
                        "[ML DISCOVER] %s: discovered features for %d equipment types",
                        site_id,
                        len(result),
                    )
            except Exception as e:
                logger.warning("[ML DISCOVER] Discovery failed for %s: %s", site_id, e)

        self._last_discovery_at = now
        return all_results

    def check_all_models(self) -> list[dict[str, Any]]:
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

    def auto_retrain_stale(self) -> list[RetrainResult]:
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

    def get_retrain_history(self) -> list[dict[str, Any]]:
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
_scheduler: RetrainingScheduler | None = None


def get_retraining_scheduler() -> RetrainingScheduler:
    """Get singleton RetrainingScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = RetrainingScheduler()
    return _scheduler
