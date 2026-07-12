"""
Automated Model Retraining Scheduler

Monitors model freshness and performance metrics. Triggers retraining
when models are stale (>30 days) or underperforming (R² < 0.65).

Feature discovery runs once per week before any retraining cycle, updating
ml_model_config with the actual sensor types present for each site so that
training always uses the real BMS points — not hardcoded global defaults.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Phase 241 Plan 1: global training lock. trigger_retraining() is reached from
# multiple paths (feedback job, API, monitoring triggers, queued executor) with
# no mutual exclusion — concurrent trainings hammer the CPU. Every caller
# serializes through this lock, whichever path they arrive by.
_TRAINING_LOCK = threading.Lock()

# Thresholds
MAX_MODEL_AGE_DAYS = 30
MIN_R2_SCORE = 0.65
MIN_CLASSIFIER_CV_ACCURACY = 0.65
MAX_AE_VAL_ERROR_THRESHOLD_RATIO = 1.0
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
    site_id: str | None = None
    success: bool = False
    queued: bool = False
    new_model_id: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None


DISCOVERY_INTERVAL_DAYS = 7  # Re-discover features at most once per week


class RetrainingScheduler:
    """Monitors model staleness and triggers retraining."""

    def __init__(self):
        self._history: list[RetrainResult] = []
        self._last_discovery_at: datetime | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ml-retraining")

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
        from app.services.site_ai_policy_service import is_site_ml_training_enabled

        for site_id in active_sites:
            if not is_site_ml_training_enabled(site_id):
                logger.info("[ML DISCOVER] Skipping %s — site ML training disabled", site_id)
                continue
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

    def _iter_model_slots(self, registry: Any, site_id: str | None = None) -> list[tuple[str, str, str | None]]:
        """Return global slots plus active site-scoped slots that need health checks."""
        from app.services.site_ai_policy_service import is_site_ml_training_enabled

        slots: set[tuple[str, str, str | None]] = set()

        if site_id is not None:
            for model_type in MODEL_TYPES:
                for equipment_type in EQUIPMENT_TYPES:
                    slots.add((model_type, equipment_type, site_id))
            return sorted(slots, key=lambda slot: (slot[0], slot[1], slot[2] or ""))

        for model_type in MODEL_TYPES:
            for equipment_type in EQUIPMENT_TYPES:
                slots.add((model_type, equipment_type, None))

        for model_id in registry.registry.get("active", {}).values():
            model = registry.registry.get("models", {}).get(model_id)
            if not model:
                continue
            model_site_id = model.get("site_id") or model.get("metadata", {}).get("site_id")
            if model_site_id and not is_site_ml_training_enabled(model_site_id):
                continue
            if model_site_id:
                slots.add((model["model_type"], model["equipment_type"], model_site_id))

        return sorted(slots, key=lambda slot: (slot[0], slot[1], slot[2] or ""))

    def _quality_check(self, model_type: str, metrics: dict[str, Any]) -> dict[str, Any]:
        """Resolve model-family-specific quality metrics without conflating them as R²."""
        if model_type == "lstm":
            for metric_name in ("r2_score", "val_r2", "r2_24h"):
                value = metrics.get(metric_name)
                if value is not None:
                    score = float(value)
                    return {
                        "quality_metric": metric_name,
                        "quality_score": score,
                        "r2_score": score,
                        "is_underperforming": score < MIN_R2_SCORE,
                        "reason": f"{metric_name} {score:.3f} below {MIN_R2_SCORE} threshold",
                    }

        if model_type == "classifier":
            value = metrics.get("cv_accuracy")
            if value is not None:
                score = float(value)
                return {
                    "quality_metric": "cv_accuracy",
                    "quality_score": score,
                    "r2_score": None,
                    "is_underperforming": score < MIN_CLASSIFIER_CV_ACCURACY,
                    "reason": (f"cv_accuracy {score:.3f} below {MIN_CLASSIFIER_CV_ACCURACY} threshold"),
                }

        if model_type == "autoencoder":
            recall = metrics.get("recall")
            if recall is not None:
                score = float(recall)
                return {
                    "quality_metric": "recall",
                    "quality_score": score,
                    "r2_score": None,
                    "is_underperforming": score < MIN_CLASSIFIER_CV_ACCURACY,
                    "reason": f"recall {score:.3f} below {MIN_CLASSIFIER_CV_ACCURACY} threshold",
                }

            threshold = metrics.get("threshold")
            val_error_mean = metrics.get("val_error_mean")
            if threshold is not None and threshold != 0 and val_error_mean is not None:
                score = float(val_error_mean) / float(threshold)
                return {
                    "quality_metric": "val_error_threshold_ratio",
                    "quality_score": score,
                    "r2_score": None,
                    "is_underperforming": score > MAX_AE_VAL_ERROR_THRESHOLD_RATIO,
                    "reason": (
                        f"val_error_threshold_ratio {score:.3f} above {MAX_AE_VAL_ERROR_THRESHOLD_RATIO} threshold"
                    ),
                }

        if model_type in MODEL_TYPES:
            # Fail closed: a contract model whose metrics lack every recognized
            # quality field must be flagged, not silently reported fresh.
            return {
                "quality_metric": None,
                "quality_score": None,
                "r2_score": None,
                "is_underperforming": True,
                "reason": f"no recognized quality metric in training metrics for {model_type}",
            }

        return {
            "quality_metric": None,
            "quality_score": None,
            "r2_score": None,
            "is_underperforming": False,
            "reason": "",
        }

    def check_all_models(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Check freshness and performance of all active models.

        Returns a list of dicts with model_type, equipment_type, status (fresh/stale/missing),
        age_days, r2_score, needs_retrain bool.
        """
        from ml.registry import get_model_registry

        registry = get_model_registry()
        results = []

        for model_type, equipment_type, slot_site_id in self._iter_model_slots(registry, site_id=site_id):
            model = registry.get_active_model(model_type, equipment_type, site_id=slot_site_id)

            if model is None:
                results.append(
                    {
                        "model_type": model_type,
                        "equipment_type": equipment_type,
                        "site_id": slot_site_id,
                        "status": "missing",
                        "age_days": None,
                        "r2_score": None,
                        "quality_metric": None,
                        "quality_score": None,
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

            metrics = model.get("metrics", {})
            quality = self._quality_check(model_type, metrics)

            # Determine status
            is_stale = age_days > MAX_MODEL_AGE_DAYS
            is_underperforming = quality["is_underperforming"]
            needs_retrain = is_stale or is_underperforming

            reasons = []
            if is_stale:
                reasons.append(f"Model age {age_days}d exceeds {MAX_MODEL_AGE_DAYS}d threshold")
            if is_underperforming and quality["reason"]:
                reasons.append(quality["reason"])

            status = "stale" if is_stale else ("underperforming" if is_underperforming else "fresh")

            results.append(
                {
                    "model_type": model_type,
                    "equipment_type": equipment_type,
                    "site_id": slot_site_id or model.get("site_id") or model.get("metadata", {}).get("site_id"),
                    "model_id": model.get("model_id"),
                    "status": status,
                    "age_days": age_days,
                    "r2_score": quality["r2_score"],
                    "quality_metric": quality["quality_metric"],
                    "quality_score": quality["quality_score"],
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
        site_id: str | None = None,
    ) -> RetrainResult:
        """Trigger retraining for a specific model type and equipment type.

        Orchestrates train → baseline capture → audit log in a cohesive unit.
        For LSTM and Autoencoder, baseline metrics are persisted to ml_model_baselines.

        Serialized by a module-level lock: if a training is already in progress
        (from any caller path), returns immediately with success=False and
        error="training_in_progress" instead of running concurrently.
        """
        if not _TRAINING_LOCK.acquire(blocking=False):
            result = RetrainResult(
                model_id=f"{site_id + '_' if site_id else ''}{model_type}_{equipment_type}",
                model_type=model_type,
                equipment_type=equipment_type,
                triggered_at=datetime.now().isoformat(),
                reason=reason,
                site_id=site_id,
                success=False,
                error="training_in_progress",
            )
            self._history.append(result)
            logger.warning(
                "Retraining skipped for %s/%s site=%s: training already in progress",
                model_type,
                equipment_type,
                site_id,
            )
            return result
        try:
            return self._trigger_retraining_locked(
                model_type=model_type,
                equipment_type=equipment_type,
                reason=reason,
                site_id=site_id,
            )
        finally:
            _TRAINING_LOCK.release()

    def _trigger_retraining_locked(
        self,
        model_type: str,
        equipment_type: str,
        reason: str = "manual",
        site_id: str | None = None,
    ) -> RetrainResult:
        """Training body — always runs holding _TRAINING_LOCK (see trigger_retraining)."""
        if site_id is not None:
            from app.services.site_ai_policy_service import is_site_ml_training_enabled

            if not is_site_ml_training_enabled(site_id):
                result = RetrainResult(
                    model_id=f"{site_id}_{model_type}_{equipment_type}",
                    model_type=model_type,
                    equipment_type=equipment_type,
                    triggered_at=datetime.now().isoformat(),
                    reason=reason,
                    site_id=site_id,
                    success=False,
                    error="ML training is disabled for this site.",
                )
                self._history.append(result)
                return result

        result = RetrainResult(
            model_id=f"{site_id + '_' if site_id else ''}{model_type}_{equipment_type}",
            model_type=model_type,
            equipment_type=equipment_type,
            triggered_at=datetime.now().isoformat(),
            reason=reason,
            site_id=site_id,
        )

        try:
            logger.info("Retraining triggered: %s/%s site=%s - reason: %s", model_type, equipment_type, site_id, reason)

            if model_type == "lstm":
                from ml.lstm.train import LSTMTrainer

                trainer = LSTMTrainer(site_id=site_id)
                train_result = trainer.train_equipment_type(
                    equipment_type,
                    epochs=50,
                    use_demo_data=False,
                    site_id=site_id,
                    auto_activate=False,
                    allow_synthetic_fallback=False,
                )
                result.success = True
                result.metrics = train_result.get("metrics", {})
                result.new_model_id = train_result.get("model_id", "")

                # Plan 1: Capture baseline after successful training
                self._capture_and_persist_baseline(
                    model_type="lstm",
                    train_result=train_result,
                    equipment_type=equipment_type,
                    site_id=site_id,
                )

            elif model_type == "autoencoder":
                from ml.autoencoder.train import AutoencoderTrainer

                trainer = AutoencoderTrainer(site_id=site_id)
                train_result = trainer.train_equipment_type(
                    equipment_type,
                    epochs=50,
                    use_demo_data=False,
                    site_id=site_id,
                    auto_activate=False,
                    allow_synthetic_fallback=False,
                )
                result.success = True
                result.metrics = train_result.get("metrics", {})
                result.new_model_id = train_result.get("model_id", "")

                # Plan 1: Capture baseline after successful training
                self._capture_and_persist_baseline(
                    model_type="autoencoder",
                    train_result=train_result,
                    equipment_type=equipment_type,
                    site_id=site_id,
                )

            elif model_type == "classifier":
                from ml.classifier.train import ClassifierTrainer

                trainer = ClassifierTrainer()
                train_result = trainer.train_equipment_type(equipment_type, auto_activate=False)
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

    def _capture_and_persist_baseline(
        self,
        model_type: str,
        train_result: dict[str, Any],
        equipment_type: str,
        site_id: str | None = None,
    ) -> None:
        """Capture baseline from trained model and persist to DB.

        Part of Plan 1 (Phase 239 M2.2 Real Drift Detection).
        Wraps train→baseline_write→audit in atomic unit.
        """
        try:
            from app.ml.models.baseline_persistence import (
                capture_baseline_from_trained_model,
                persist_baseline_to_db,
                record_training_audit,
            )

            model_id = train_result.get("model_id")
            if not model_id:
                logger.warning("[BASELINE] No model_id in training result")
                return

            # Capture baseline from training result
            baseline = capture_baseline_from_trained_model(
                trained_model_result=train_result,
                model_type=model_type,
                equipment_type=equipment_type,
                site_id=site_id,
            )

            # Persist to database (atomic write)
            persist_baseline_to_db(baseline)

            # Record audit entry
            record_training_audit(model_id, status="baseline_written")

            logger.info(
                "[BASELINE] Successfully captured and persisted baseline for %s/%s (site=%s, model_id=%s)",
                model_type,
                equipment_type,
                site_id or "global",
                model_id,
            )

        except Exception as e:
            logger.error(
                "[BASELINE] Failed to capture/persist baseline for %s/%s: %s",
                model_type,
                equipment_type,
                e,
                exc_info=True,
            )

    def queue_retraining(
        self,
        model_type: str,
        equipment_type: str,
        reason: str = "manual",
        site_id: str | None = None,
    ) -> RetrainResult:
        """Queue retraining outside the scheduler thread."""
        queued = RetrainResult(
            model_id=f"{site_id + '_' if site_id else ''}{model_type}_{equipment_type}",
            model_type=model_type,
            equipment_type=equipment_type,
            triggered_at=datetime.now().isoformat(),
            reason=reason,
            site_id=site_id,
            success=True,
            queued=True,
        )

        future = self._executor.submit(
            self.trigger_retraining,
            model_type=model_type,
            equipment_type=equipment_type,
            reason=reason,
            site_id=site_id,
        )

        def _log_done(done_future):
            try:
                result = done_future.result()
                if result.success:
                    logger.info(
                        "Queued retraining completed: %s/%s site=%s -> %s",
                        result.model_type,
                        result.equipment_type,
                        result.site_id,
                        result.new_model_id,
                    )
                else:
                    logger.error(
                        "Queued retraining failed: %s/%s site=%s - %s",
                        result.model_type,
                        result.equipment_type,
                        result.site_id,
                        result.error,
                    )
            except Exception as exc:
                logger.error("Queued retraining crashed: %s", exc, exc_info=True)

        future.add_done_callback(_log_done)
        return queued

    def auto_retrain_stale(self) -> list[RetrainResult]:
        """Check all models and retrain the first stale one found.

        Called by the background scheduler daily.
        Returns list of retrain results (typically 0 or 1).
        """
        checks = self.check_all_models()
        results = []

        for check in checks:
            if check["needs_retrain"] and check["status"] != "missing":
                result = self.queue_retraining(
                    model_type=check["model_type"],
                    equipment_type=check["equipment_type"],
                    reason=check.get("reason", "auto_stale"),
                    site_id=check.get("site_id"),
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
                "queued": r.queued,
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
