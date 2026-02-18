"""
Model Registry - Manage ML model versions and deployments.

Tracks trained models, their metrics, and which version is active for inference.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Registry for managing ML model versions."""

    def __init__(self, registry_path: str = None):
        if registry_path is None:
            registry_path = Path(__file__).parent / "models" / "registry.json"
        self.registry_path = Path(registry_path)
        self.registry = self._load_registry()

    def _load_registry(self) -> dict:
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                return json.loads(self.registry_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Corrupted registry, starting fresh")
                return {"models": {}, "active": {}}
        return {"models": {}, "active": {}}

    def _save_registry(self):
        """Save registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(self.registry, indent=2, default=str)
        )

    def register_model(
        self,
        model_type: str,  # e.g., "lstm", "autoencoder"
        equipment_type: str,  # e.g., "chiller", "generator"
        model_path: str,
        metrics: dict,
        metadata: dict = None,
        auto_activate: bool = True
    ) -> str:
        """
        Register a new model version.

        Args:
            model_type: Type of model (lstm, autoencoder)
            equipment_type: Equipment type this model handles
            model_path: Path to saved model file
            metrics: Training/validation metrics
            metadata: Optional metadata (training params, etc.)
            auto_activate: Automatically set as active model

        Returns:
            Model ID
        """
        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_id = f"{model_type}_{equipment_type}_{version}"

        entry = {
            "model_id": model_id,
            "model_type": model_type,
            "equipment_type": equipment_type,
            "model_path": str(model_path),
            "metrics": metrics,
            "metadata": metadata or {},
            "registered_at": datetime.now().isoformat(),
            "status": "registered"
        }

        self.registry["models"][model_id] = entry
        self._save_registry()

        logger.info(f"Registered model: {model_id}")

        if auto_activate:
            self.set_active(model_id)

        return model_id

    def set_active(self, model_id: str):
        """Set a model as the active version for inference."""
        if model_id not in self.registry["models"]:
            raise ValueError(f"Model {model_id} not found in registry")

        model = self.registry["models"][model_id]
        key = f"{model['model_type']}_{model['equipment_type']}"

        # Deactivate previous active model
        prev_active = self.registry["active"].get(key)
        if prev_active and prev_active in self.registry["models"]:
            self.registry["models"][prev_active]["status"] = "inactive"

        # Activate new model
        self.registry["active"][key] = model_id
        self.registry["models"][model_id]["status"] = "active"
        self._save_registry()

        logger.info(f"Activated model: {model_id}")

    def get_active_model(
        self, model_type: str, equipment_type: str
    ) -> Optional[dict]:
        """Get the currently active model for inference."""
        key = f"{model_type}_{equipment_type}"
        model_id = self.registry["active"].get(key)

        if model_id and model_id in self.registry["models"]:
            return self.registry["models"][model_id]
        return None

    def list_models(
        self,
        model_type: str = None,
        equipment_type: str = None,
        status: str = None
    ) -> List[dict]:
        """List registered models with optional filters."""
        models = list(self.registry["models"].values())

        if model_type:
            models = [m for m in models if m["model_type"] == model_type]
        if equipment_type:
            models = [m for m in models if m["equipment_type"] == equipment_type]
        if status:
            models = [m for m in models if m["status"] == status]

        return sorted(models, key=lambda m: m["registered_at"], reverse=True)

    def get_model(self, model_id: str) -> Optional[dict]:
        """Get a specific model by ID."""
        return self.registry["models"].get(model_id)

    def delete_model(self, model_id: str) -> bool:
        """Delete a model from registry (does not delete files)."""
        if model_id not in self.registry["models"]:
            return False

        model = self.registry["models"][model_id]

        # Can't delete active model
        key = f"{model['model_type']}_{model['equipment_type']}"
        if self.registry["active"].get(key) == model_id:
            raise ValueError(f"Cannot delete active model {model_id}")

        del self.registry["models"][model_id]
        self._save_registry()

        logger.info(f"Deleted model: {model_id}")
        return True

    def get_model_comparison(
        self, model_type: str, equipment_type: str
    ) -> List[dict]:
        """Compare all models for a specific type/equipment."""
        models = self.list_models(model_type, equipment_type)
        return [
            {
                "model_id": m["model_id"],
                "registered_at": m["registered_at"],
                "status": m["status"],
                **m["metrics"]
            }
            for m in models
        ]


# Singleton instance
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get singleton ModelRegistry instance."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
