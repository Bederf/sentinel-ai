"""
Global Model Trainer - Train fleet-wide models on aggregated data.

Trains a single global model per equipment type using anonymized,
aggregated data from all sites. The global model provides a baseline
that can be fine-tuned per site.

Phase 45-02: Fleet Learning and Cross-Site Insights.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GlobalTrainResult:
    """Result of a global model training run."""

    model_type: str
    equipment_type: str
    training_started: str
    training_completed: Optional[str] = None
    sites_included: int = 0
    samples_used: int = 0
    success: bool = False
    metrics: Dict[str, float] = field(default_factory=dict)
    global_model_id: Optional[str] = None
    error: Optional[str] = None


class GlobalModelTrainer:
    """Trains global models on aggregated fleet data.

    Global models are trained using anonymized data from all sites,
    providing a shared baseline that captures fleet-wide patterns.
    Individual sites can then fine-tune these models for local conditions.

    Training approach:
    1. Aggregate training data from all sites (anonymized)
    2. Train a single model per (model_type, equipment_type)
    3. Register in model registry as global variant
    4. Make available for local fine-tuning
    """

    def __init__(self):
        self._training_history: List[GlobalTrainResult] = []
        self._global_models: Dict[str, Dict[str, Any]] = {}
        self._seed_global_models()

    def _seed_global_models(self):
        """Seed with pre-trained global model metadata for demo."""
        model_configs = [
            ("lstm", "chiller", 0.847, 15, 12500),
            ("lstm", "ahu", 0.812, 15, 18200),
            ("lstm", "fcu", 0.798, 15, 25600),
            ("lstm", "vav", 0.775, 15, 31000),
            ("lstm", "generator", 0.865, 15, 4800),
            ("autoencoder", "chiller", 0.891, 15, 12500),
            ("autoencoder", "ahu", 0.856, 15, 18200),
            ("autoencoder", "fcu", 0.823, 15, 25600),
        ]

        for model_type, eq_type, r2, sites, samples in model_configs:
            key = f"global_{model_type}_{eq_type}"
            self._global_models[key] = {
                "model_id": key,
                "model_type": model_type,
                "equipment_type": eq_type,
                "variant": "global",
                "sites_included": sites,
                "samples_used": samples,
                "metrics": {
                    "r2_score": r2,
                    "mae": round((1 - r2) * 10, 3),
                    "rmse": round((1 - r2) * 15, 3),
                },
                "trained_at": "2026-02-01T08:00:00",
                "status": "active",
            }

    def train_global_model(
        self,
        model_type: str,
        equipment_type: str,
    ) -> GlobalTrainResult:
        """Train a global model for the given type and equipment.

        In production, this would:
        1. Pull anonymized feature data from all sites
        2. Train a model using the combined dataset
        3. Register the model in the registry

        For demo, returns pre-computed results.

        Args:
            model_type: Model architecture (lstm, autoencoder)
            equipment_type: Equipment type (chiller, ahu, etc.)

        Returns:
            Training result with metrics.
        """
        result = GlobalTrainResult(
            model_type=model_type,
            equipment_type=equipment_type,
            training_started=datetime.now().isoformat(),
        )

        try:
            key = f"global_{model_type}_{equipment_type}"

            if key in self._global_models:
                existing = self._global_models[key]
                result.success = True
                result.sites_included = existing["sites_included"]
                result.samples_used = existing["samples_used"]
                result.metrics = existing["metrics"]
                result.global_model_id = key
            else:
                # New model type - create with reasonable defaults
                result.success = True
                result.sites_included = 15
                result.samples_used = 10000
                result.metrics = {
                    "r2_score": 0.78,
                    "mae": 2.2,
                    "rmse": 3.3,
                }
                result.global_model_id = key

                self._global_models[key] = {
                    "model_id": key,
                    "model_type": model_type,
                    "equipment_type": equipment_type,
                    "variant": "global",
                    "sites_included": result.sites_included,
                    "samples_used": result.samples_used,
                    "metrics": result.metrics,
                    "trained_at": datetime.now().isoformat(),
                    "status": "active",
                }

            result.training_completed = datetime.now().isoformat()

            logger.info(
                f"Global model trained: {key} "
                f"(R2={result.metrics.get('r2_score', 0):.3f}, "
                f"sites={result.sites_included})"
            )

        except Exception as e:
            logger.error(f"Global model training failed: {e}")
            result.error = str(e)

        self._training_history.append(result)
        return result

    def get_global_model(
        self,
        model_type: str,
        equipment_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Get a trained global model.

        Args:
            model_type: Model architecture
            equipment_type: Equipment type

        Returns:
            Global model metadata or None if not trained.
        """
        key = f"global_{model_type}_{equipment_type}"
        return self._global_models.get(key)

    def list_global_models(
        self,
        model_type: Optional[str] = None,
        equipment_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all available global models.

        Args:
            model_type: Optional filter by model architecture.
            equipment_type: Optional filter by equipment type.

        Returns:
            List of global model metadata dicts.
        """
        models = list(self._global_models.values())

        if model_type:
            models = [m for m in models if m["model_type"] == model_type]
        if equipment_type:
            models = [m for m in models if m["equipment_type"] == equipment_type]

        return sorted(models, key=lambda m: m.get("trained_at", ""), reverse=True)

    def get_training_history(self) -> List[Dict[str, Any]]:
        """Get history of global model training runs."""
        return [
            {
                "model_type": r.model_type,
                "equipment_type": r.equipment_type,
                "training_started": r.training_started,
                "training_completed": r.training_completed,
                "sites_included": r.sites_included,
                "samples_used": r.samples_used,
                "success": r.success,
                "metrics": r.metrics,
                "global_model_id": r.global_model_id,
                "error": r.error,
            }
            for r in self._training_history
        ]

    def compare_global_vs_local(
        self,
        model_type: str,
        equipment_type: str,
        local_metrics: Dict[str, float],
    ) -> Dict[str, Any]:
        """Compare global model performance against a local model.

        Args:
            model_type: Model architecture.
            equipment_type: Equipment type.
            local_metrics: Metrics from the local model.

        Returns:
            Comparison results with recommendation.
        """
        global_model = self.get_global_model(model_type, equipment_type)

        if not global_model:
            return {
                "comparison": "no_global_model",
                "message": f"No global model available for {model_type}/{equipment_type}",
                "recommendation": "train_global",
            }

        global_metrics = global_model["metrics"]
        global_r2 = global_metrics.get("r2_score", 0)
        local_r2 = local_metrics.get("r2_score", 0)

        improvement = local_r2 - global_r2
        pct_improvement = (improvement / max(global_r2, 0.001)) * 100

        if local_r2 > global_r2 * 1.05:
            recommendation = "keep_local"
            message = "Local model outperforms global - keep local fine-tuned version"
        elif global_r2 > local_r2 * 1.05:
            recommendation = "use_global"
            message = "Global model outperforms local - consider switching to global"
        else:
            recommendation = "fine_tune"
            message = "Models perform similarly - fine-tuning may improve further"

        return {
            "model_type": model_type,
            "equipment_type": equipment_type,
            "global_r2": round(global_r2, 4),
            "local_r2": round(local_r2, 4),
            "improvement": round(improvement, 4),
            "pct_improvement": round(pct_improvement, 1),
            "recommendation": recommendation,
            "message": message,
        }


# Singleton
_trainer: Optional[GlobalModelTrainer] = None


def get_global_model_trainer() -> GlobalModelTrainer:
    """Get singleton GlobalModelTrainer instance."""
    global _trainer
    if _trainer is None:
        _trainer = GlobalModelTrainer()
    return _trainer
