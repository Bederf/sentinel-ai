"""
Local Fine-Tuning - Fine-tune global models for site-specific conditions.

Takes a global model (trained on fleet data) and fine-tunes it using
site-local data to improve predictions for specific building conditions,
equipment configurations, and operational patterns.

Phase 45-02: Fleet Learning and Cross-Site Insights.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default fine-tuning hyperparameters
DEFAULT_FINE_TUNE_CONFIG = {
    "learning_rate": 0.0001,  # Lower LR for fine-tuning
    "epochs": 10,  # Fewer epochs to avoid overfitting
    "batch_size": 32,
    "early_stopping_patience": 3,
    "freeze_layers": 2,  # Freeze first N layers of global model
    "validation_split": 0.2,
}


@dataclass
class FineTuneResult:
    """Result of a fine-tuning operation."""

    site_code: str
    model_type: str
    equipment_type: str
    global_model_id: str
    fine_tuned_model_id: Optional[str] = None
    started_at: str = ""
    completed_at: Optional[str] = None
    success: bool = False
    global_metrics: Dict[str, float] = field(default_factory=dict)
    fine_tuned_metrics: Dict[str, float] = field(default_factory=dict)
    improvement: Dict[str, float] = field(default_factory=dict)
    samples_used: int = 0
    config: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now().isoformat()


class LocalFineTuner:
    """Fine-tunes global models for site-specific conditions.

    The fine-tuning process:
    1. Load the global model (pre-trained on fleet data)
    2. Freeze early layers (feature extraction)
    3. Train later layers on site-local data
    4. Evaluate improvement vs global model
    5. Register fine-tuned model if improved

    Benefits:
    - Faster convergence (starts from global knowledge)
    - Less data needed (leverages fleet patterns)
    - Better accuracy (adapted to local conditions)
    - Maintains fleet-wide failure recognition
    """

    def __init__(self):
        self._fine_tune_history: List[FineTuneResult] = []
        self._fine_tuned_models: Dict[str, Dict[str, Any]] = {}
        self._seed_demo_models()

    def _seed_demo_models(self):
        """Seed with demo fine-tuned models."""
        demo_configs = [
            # (site, model_type, eq_type, global_r2, local_r2, samples)
            ("site-002", "lstm", "chiller", 0.847, 0.912, 3200),
            ("site-002", "lstm", "ahu", 0.812, 0.878, 4800),
            ("site-002", "autoencoder", "chiller", 0.891, 0.934, 3200),
            ("site-001", "lstm", "chiller", 0.847, 0.895, 2800),
            ("site-003", "lstm", "ahu", 0.812, 0.856, 3600),
        ]

        for site, mt, et, global_r2, local_r2, samples in demo_configs:
            key = f"ft_{site}_{mt}_{et}"
            improvement = local_r2 - global_r2

            self._fine_tuned_models[key] = {
                "model_id": key,
                "site_code": site,
                "model_type": mt,
                "equipment_type": et,
                "variant": "fine_tuned",
                "global_model_id": f"global_{mt}_{et}",
                "metrics": {
                    "r2_score": local_r2,
                    "mae": round((1 - local_r2) * 10, 3),
                    "rmse": round((1 - local_r2) * 15, 3),
                },
                "global_metrics": {
                    "r2_score": global_r2,
                    "mae": round((1 - global_r2) * 10, 3),
                    "rmse": round((1 - global_r2) * 15, 3),
                },
                "improvement": {
                    "r2_score": round(improvement, 4),
                    "r2_pct": round((improvement / max(global_r2, 0.001)) * 100, 1),
                },
                "samples_used": samples,
                "config": DEFAULT_FINE_TUNE_CONFIG,
                "fine_tuned_at": "2026-02-02T10:00:00",
                "status": "active",
            }

    def fine_tune(
        self,
        site_code: str,
        model_type: str,
        equipment_type: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> FineTuneResult:
        """Fine-tune a global model for a specific site.

        In production, this would:
        1. Load the global model weights
        2. Freeze early layers
        3. Train on site-local data
        4. Compare against global baseline

        For demo, returns pre-computed or simulated results.

        Args:
            site_code: Target site (e.g., "site-002").
            model_type: Model architecture (lstm, autoencoder).
            equipment_type: Equipment type (chiller, ahu, etc.).
            config: Optional fine-tuning hyperparameters.

        Returns:
            Fine-tuning result with metrics comparison.
        """
        ft_config = {**DEFAULT_FINE_TUNE_CONFIG, **(config or {})}

        result = FineTuneResult(
            site_code=site_code,
            model_type=model_type,
            equipment_type=equipment_type,
            global_model_id=f"global_{model_type}_{equipment_type}",
            config=ft_config,
        )

        try:
            # Check if global model exists
            from ml.fleet.global_model import get_global_model_trainer

            trainer = get_global_model_trainer()
            global_model = trainer.get_global_model(model_type, equipment_type)

            if not global_model:
                result.error = f"No global model found for {model_type}/{equipment_type}. Train a global model first."
                self._fine_tune_history.append(result)
                return result

            result.global_metrics = global_model["metrics"]

            # Check for existing fine-tuned model
            key = f"ft_{site_code}_{model_type}_{equipment_type}"
            if key in self._fine_tuned_models:
                existing = self._fine_tuned_models[key]
                result.success = True
                result.fine_tuned_model_id = key
                result.fine_tuned_metrics = existing["metrics"]
                result.improvement = existing["improvement"]
                result.samples_used = existing["samples_used"]
            else:
                # Simulate fine-tuning with improvement
                global_r2 = result.global_metrics.get("r2_score", 0.8)
                # Fine-tuning typically improves R2 by 3-8%
                improvement_factor = 0.05
                local_r2 = min(0.98, global_r2 + improvement_factor)

                result.success = True
                result.fine_tuned_model_id = key
                result.fine_tuned_metrics = {
                    "r2_score": round(local_r2, 4),
                    "mae": round((1 - local_r2) * 10, 3),
                    "rmse": round((1 - local_r2) * 15, 3),
                }
                r2_diff = local_r2 - global_r2
                result.improvement = {
                    "r2_score": round(r2_diff, 4),
                    "r2_pct": round((r2_diff / max(global_r2, 0.001)) * 100, 1),
                }
                result.samples_used = 5000

                # Store for future retrieval
                self._fine_tuned_models[key] = {
                    "model_id": key,
                    "site_code": site_code,
                    "model_type": model_type,
                    "equipment_type": equipment_type,
                    "variant": "fine_tuned",
                    "global_model_id": result.global_model_id,
                    "metrics": result.fine_tuned_metrics,
                    "global_metrics": result.global_metrics,
                    "improvement": result.improvement,
                    "samples_used": result.samples_used,
                    "config": ft_config,
                    "fine_tuned_at": datetime.now().isoformat(),
                    "status": "active",
                }

            result.completed_at = datetime.now().isoformat()

            logger.info(
                f"Fine-tuned model: {key} "
                f"(global R2={result.global_metrics.get('r2_score', 0):.3f} -> "
                f"local R2={result.fine_tuned_metrics.get('r2_score', 0):.3f})"
            )

        except Exception as e:
            logger.error(f"Fine-tuning failed: {e}")
            result.error = str(e)

        self._fine_tune_history.append(result)
        return result

    def get_fine_tuned_model(
        self,
        site_code: str,
        model_type: str,
        equipment_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Get a fine-tuned model for a specific site.

        Args:
            site_code: Target site.
            model_type: Model architecture.
            equipment_type: Equipment type.

        Returns:
            Fine-tuned model metadata or None.
        """
        key = f"ft_{site_code}_{model_type}_{equipment_type}"
        return self._fine_tuned_models.get(key)

    def list_fine_tuned_models(
        self,
        site_code: Optional[str] = None,
        model_type: Optional[str] = None,
        equipment_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all fine-tuned models with optional filters.

        Args:
            site_code: Optional site filter.
            model_type: Optional model type filter.
            equipment_type: Optional equipment type filter.

        Returns:
            List of fine-tuned model metadata dicts.
        """
        models = list(self._fine_tuned_models.values())

        if site_code:
            models = [m for m in models if m["site_code"] == site_code]
        if model_type:
            models = [m for m in models if m["model_type"] == model_type]
        if equipment_type:
            models = [m for m in models if m["equipment_type"] == equipment_type]

        return sorted(models, key=lambda m: m.get("fine_tuned_at", ""), reverse=True)

    def get_fine_tune_history(
        self,
        site_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get history of fine-tuning operations.

        Args:
            site_code: Optional site filter.

        Returns:
            List of fine-tune result dicts.
        """
        history = self._fine_tune_history

        if site_code:
            history = [h for h in history if h.site_code == site_code]

        return [
            {
                "site_code": r.site_code,
                "model_type": r.model_type,
                "equipment_type": r.equipment_type,
                "global_model_id": r.global_model_id,
                "fine_tuned_model_id": r.fine_tuned_model_id,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "success": r.success,
                "global_metrics": r.global_metrics,
                "fine_tuned_metrics": r.fine_tuned_metrics,
                "improvement": r.improvement,
                "samples_used": r.samples_used,
                "error": r.error,
            }
            for r in history
        ]

    def get_improvement_summary(
        self,
        site_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get summary of fine-tuning improvements.

        Args:
            site_code: Optional site filter.

        Returns:
            Summary of improvements from fine-tuning.
        """
        models = self.list_fine_tuned_models(site_code=site_code)

        if not models:
            return {
                "models_count": 0,
                "avg_improvement_pct": 0,
                "message": "No fine-tuned models available",
            }

        improvements = [
            m["improvement"]["r2_pct"] for m in models if "improvement" in m and "r2_pct" in m["improvement"]
        ]

        avg_improvement = sum(improvements) / max(len(improvements), 1)
        max_improvement = max(improvements) if improvements else 0
        min_improvement = min(improvements) if improvements else 0

        return {
            "models_count": len(models),
            "avg_improvement_pct": round(avg_improvement, 1),
            "max_improvement_pct": round(max_improvement, 1),
            "min_improvement_pct": round(min_improvement, 1),
            "site_code": site_code or "all",
            "best_model": max(models, key=lambda m: m["metrics"].get("r2_score", 0)) if models else None,
        }


# Singleton
_fine_tuner: Optional[LocalFineTuner] = None


def get_local_fine_tuner() -> LocalFineTuner:
    """Get singleton LocalFineTuner instance."""
    global _fine_tuner
    if _fine_tuner is None:
        _fine_tuner = LocalFineTuner()
    return _fine_tuner
