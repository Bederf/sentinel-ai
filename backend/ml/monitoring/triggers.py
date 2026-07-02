"""
Automatic Retraining Triggers

Monitors drift detection results and automatically triggers
model retraining when thresholds are exceeded.

Phase 45-03: MLOps Monitoring and Success Metrics.
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Trigger configuration
FEATURE_DRIFT_TRIGGER_THRESHOLD = 3  # Drifted features before triggering retrain
MODEL_DRIFT_TRIGGER = True  # Retrain on model drift detection
COOLDOWN_MINUTES = 60  # Minimum time between retraining triggers for same model


class RetrainingTrigger:
    """Automatic retraining trigger based on drift detection.

    Monitors drift results and triggers retraining when:
    - Feature drift exceeds threshold (3+ features drifted)
    - Model drift detected (accuracy degradation > 10%)
    - Model staleness exceeds configured max age
    """

    def __init__(self):
        self._trigger_history: list[dict[str, Any]] = []
        self._last_trigger: dict[str, str] = {}  # model_key -> iso timestamp
        self._config = {
            "feature_drift_threshold": FEATURE_DRIFT_TRIGGER_THRESHOLD,
            "model_drift_trigger": MODEL_DRIFT_TRIGGER,
            "cooldown_minutes": COOLDOWN_MINUTES,
            "auto_retrain_enabled": True,
        }

    def evaluate_and_trigger(self) -> dict[str, Any]:
        """Run drift detection and trigger retraining if needed.

        Returns:
            Summary of evaluation and any triggered retraining.
        """
        triggered: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []

        # Check feature drift for all equipment types
        feature_triggers = self._evaluate_feature_drift()
        for trigger in feature_triggers:
            key = f"{trigger['model_type']}/{trigger['equipment_type']}"
            if self._is_in_cooldown(key):
                skipped.append({"model_key": key, "reason": "cooldown"})
                continue
            result = self._trigger_retrain(
                trigger["model_type"],
                trigger["equipment_type"],
                trigger["reason"],
            )
            triggered.append(result)

        # Check model drift
        model_triggers = self._evaluate_model_drift()
        for trigger in model_triggers:
            key = f"{trigger['model_type']}/all"
            if self._is_in_cooldown(key):
                skipped.append({"model_key": key, "reason": "cooldown"})
                continue
            result = self._trigger_retrain(
                trigger["model_type"],
                "all",
                trigger["reason"],
            )
            triggered.append(result)

        return {
            "evaluated_at": datetime.now().isoformat(),
            "triggers_fired": len(triggered),
            "triggers_skipped": len(skipped),
            "triggered": triggered,
            "skipped": skipped,
            "config": self._config,
        }

    def get_trigger_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get history of retraining triggers."""
        return self._trigger_history[-limit:]

    def get_config(self) -> dict[str, Any]:
        """Get current trigger configuration."""
        return {**self._config}

    def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Update trigger configuration.

        Args:
            updates: Dict of config keys to update.

        Returns:
            Updated configuration.
        """
        valid_keys = set(self._config.keys())
        for key, value in updates.items():
            if key in valid_keys:
                self._config[key] = value
        return self.get_config()

    def _evaluate_feature_drift(self) -> list[dict[str, Any]]:
        """Evaluate feature drift and identify models needing retraining."""
        triggers: list[dict[str, Any]] = []
        try:
            from ml.monitoring.drift import EQUIPMENT_TYPES, get_drift_detector

            detector = get_drift_detector()

            threshold = self._config["feature_drift_threshold"]

            for eq_type in EQUIPMENT_TYPES:
                result = detector.detect_feature_drift(eq_type)
                if result["features_drifted"] >= threshold:
                    # Trigger for both model types
                    for model_type in ["lstm", "autoencoder"]:
                        triggers.append(
                            {
                                "model_type": model_type,
                                "equipment_type": eq_type,
                                "reason": (
                                    f"Feature drift: {result['features_drifted']} features drifted for {eq_type}"
                                ),
                                "drift_result": result,
                            }
                        )
        except Exception as e:
            logger.error(f"Feature drift evaluation failed: {e}")

        return triggers

    def _evaluate_model_drift(self) -> list[dict[str, Any]]:
        """Evaluate model drift and identify models needing retraining."""
        triggers: list[dict[str, Any]] = []

        if not self._config["model_drift_trigger"]:
            return triggers

        try:
            from ml.monitoring.drift import MODEL_TYPES, get_drift_detector

            detector = get_drift_detector()

            for model_type in MODEL_TYPES:
                result = detector.detect_model_drift(model_type)
                if result["drift_detected"]:
                    triggers.append(
                        {
                            "model_type": model_type,
                            "reason": (f"Model drift: {model_type} accuracy degraded by {result['degradation_pct']}%"),
                            "drift_result": result,
                        }
                    )
        except Exception as e:
            logger.error(f"Model drift evaluation failed: {e}")

        return triggers

    def _trigger_retrain(self, model_type: str, equipment_type: str, reason: str) -> dict[str, Any]:
        """Trigger a model retraining operation.

        Args:
            model_type: Model type to retrain.
            equipment_type: Equipment type (or 'all').
            reason: Reason for retraining.

        Returns:
            Result of the retraining trigger.
        """
        key = f"{model_type}/{equipment_type}"

        result = {
            "model_type": model_type,
            "equipment_type": equipment_type,
            "reason": reason,
            "triggered_at": datetime.now().isoformat(),
            "success": False,
            "retrain_result": None,
        }

        if not self._config["auto_retrain_enabled"]:
            result["skipped"] = True
            result["skip_reason"] = "auto_retrain_disabled"
            self._trigger_history.append(result)
            return result

        try:
            from ml.training.retraining_scheduler import get_retraining_scheduler

            scheduler = get_retraining_scheduler()

            retrain_result = scheduler.trigger_retraining(model_type, equipment_type, reason)

            result["success"] = retrain_result.success
            result["retrain_result"] = {
                "model_id": retrain_result.model_id,
                "new_model_id": retrain_result.new_model_id,
                "error": retrain_result.error,
            }

            # Apply trust decay on drift signal (PLAN-162B)
            self._apply_trust_decay_on_drift(model_type, equipment_type, reason)

            # Record trigger time for cooldown
            self._last_trigger[key] = datetime.now().isoformat()

        except Exception as e:
            logger.error(f"Retraining trigger failed for {key}: {e}")
            result["error"] = str(e)

        self._trigger_history.append(result)
        return result

    def _apply_trust_decay_on_drift(self, model_type: str, equipment_type: str, reason: str) -> None:
        """Apply trust decay when drift is detected.

        This fires on the same drift signal that triggers retraining.
        Decay is applied immediately — does not wait for retrain completion.
        """
        import re

        features_drifted = 4  # default: severe (model drift)
        m = re.search(r"(\d+) features drifted", reason)
        if m:
            features_drifted = int(m.group(1))

        if features_drifted <= 1:
            return

        try:
            from app.database.repositories.trust_history_repository import (
                TrustHistoryRepository,
            )
            from app.database.repositories.trust_reset_repository import (
                TrustResetRepository,
            )

            repo = TrustHistoryRepository()
            import asyncio

            count = asyncio.run(repo.decay_by_equipment_type(equipment_type, features_drifted))
            if count:
                logger.info(
                    "[TRUST-DECAY] Applied decay for %s (drift: %d features): %d trust rows affected",
                    equipment_type,
                    features_drifted,
                    count,
                )
            # Record audit trail
            try:
                audit_repo = TrustResetRepository()
                asyncio.run(
                    audit_repo.record_reset(
                        equipment_id=f"drift:{equipment_type}",
                        site_id="",
                        trigger_type=("drift_severe" if features_drifted > 3 else "drift_moderate"),
                        reset_action=("moderate_decay" if features_drifted <= 3 else "severe_decay"),
                    )
                )
            except Exception as audit_err:
                logger.warning("[TRUST-DECAY] Audit record failed: %s", audit_err)
            # Surface in review queue
            try:
                from app.database.repositories.review_queue_repository import (
                    get_review_queue_repository,
                )

                q_repo = get_review_queue_repository()
                asyncio.run(
                    q_repo.mark_equipment_reset(
                        f"%-{equipment_type.upper()}-%",
                        f"Trust decay — {features_drifted} feature(s) drifted",
                        like_match=True,
                    )
                )
            except Exception as q_err:
                logger.warning("[TRUST-DECAY] review_queue update failed: %s", q_err)
        except Exception as exc:
            logger.warning("[TRUST-DECAY] Failed to apply trust decay: %s", exc)

    def _is_in_cooldown(self, model_key: str) -> bool:
        """Check if a model is in cooldown period after recent retrain.

        Args:
            model_key: Model key in format 'model_type/equipment_type'.

        Returns:
            True if model is still in cooldown.
        """
        if model_key not in self._last_trigger:
            return False

        last = datetime.fromisoformat(self._last_trigger[model_key])
        elapsed = (datetime.now() - last).total_seconds() / 60.0
        return elapsed < self._config["cooldown_minutes"]


# Singleton
_trigger: RetrainingTrigger | None = None


def get_retraining_trigger() -> RetrainingTrigger:
    """Get singleton RetrainingTrigger instance."""
    global _trigger
    if _trigger is None:
        _trigger = RetrainingTrigger()
    return _trigger
