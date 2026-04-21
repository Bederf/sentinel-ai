"""
Model Registry - Manage ML model versions and deployments.

Tracks trained models, their metrics, and which version is active for inference.

Paths are stored RELATIVE to the models base directory (registry.json's parent)
so the registry remains portable across different installation paths (e.g.,
/opt/bms-intelligence/ vs /opt/sentinel-ai/). Absolute paths from older entries
are handled transparently at load time.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Registry for managing ML model versions."""

    def __init__(self, registry_path: str | None = None):
        if registry_path is None:
            registry_path = Path(__file__).parent / "models" / "registry.json"
        self.registry_path = Path(registry_path)
        self._models_base_dir = self.registry_path.parent
        self.registry = self._load_registry()
        self._generation: int = 0

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
        self.registry_path.write_text(json.dumps(self.registry, indent=2, default=str))

    def _to_relative_path(self, path_str: str) -> str:
        """Convert an absolute path to relative (relative to models base dir).

        If the path is already relative or cannot be made relative to the
        models base dir, it is returned unchanged.
        """
        p = Path(path_str)
        if not p.is_absolute():
            return path_str
        try:
            return str(p.relative_to(self._models_base_dir))
        except ValueError:
            logger.warning(f"Model path {path_str} is not under {self._models_base_dir}, storing as absolute")
            return path_str

    def _resolve_path(self, path_str: str) -> str:
        """Resolve a stored path to absolute.

        If the path is already absolute, return it as-is (backward compat).
        If relative, resolve against the models base directory.
        """
        p = Path(path_str)
        if p.is_absolute():
            return path_str
        return str(self._models_base_dir / p)

    def _resolve_model_paths(self, entry: dict) -> dict:
        """Return a copy of a model entry with all paths resolved to absolute.

        Handles both model_path (top-level) and scaler_path (in metadata).
        """
        resolved = dict(entry)

        if "model_path" in resolved:
            resolved["model_path"] = self._resolve_path(resolved["model_path"])

        if "metadata" in resolved and isinstance(resolved["metadata"], dict):
            metadata = dict(resolved["metadata"])
            if "scaler_path" in metadata:
                metadata["scaler_path"] = self._resolve_path(metadata["scaler_path"])
            resolved["metadata"] = metadata

        return resolved

    def register_model(
        self,
        model_type: str,  # e.g., "lstm", "autoencoder"
        equipment_type: str,  # e.g., "chiller", "generator"
        model_path: str,
        metrics: dict,
        metadata: dict | None = None,
        auto_activate: bool = True,
    ) -> str:
        """
        Register a new model version.

        Args:
            model_type: Type of model (lstm, autoencoder)
            equipment_type: Equipment type this model handles
            model_path: Path to saved model file (absolute or relative)
            metrics: Training/validation metrics
            metadata: Optional metadata (training params, etc.)
            auto_activate: Automatically set as active model

        Returns:
            Model ID
        """
        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_id = f"{model_type}_{equipment_type}_{version}"

        # Convert paths to relative for portability
        stored_metadata = dict(metadata) if metadata else {}
        if "scaler_path" in stored_metadata:
            stored_metadata["scaler_path"] = self._to_relative_path(str(stored_metadata["scaler_path"]))

        entry = {
            "model_id": model_id,
            "model_type": model_type,
            "equipment_type": equipment_type,
            "model_path": self._to_relative_path(str(model_path)),
            "metrics": metrics,
            "metadata": stored_metadata,
            "registered_at": datetime.now().isoformat(),
            "status": "registered",
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
        self._generation += 1
        self._save_registry()

        logger.info(f"Activated model: {model_id} (registry generation {self._generation})")

    def get_active_model(self, model_type: str, equipment_type: str) -> dict | None:
        """Get the currently active model for inference.

        Returns a copy with paths resolved to absolute.
        """
        key = f"{model_type}_{equipment_type}"
        model_id = self.registry["active"].get(key)

        if model_id and model_id in self.registry["models"]:
            return self._resolve_model_paths(self.registry["models"][model_id])
        return None

    def list_models(self, model_type: str | None = None, equipment_type: str | None = None, status: str | None = None) -> list[dict]:
        """List registered models with optional filters.

        Returns copies with paths resolved to absolute.
        """
        models = list(self.registry["models"].values())

        if model_type:
            models = [m for m in models if m["model_type"] == model_type]
        if equipment_type:
            models = [m for m in models if m["equipment_type"] == equipment_type]
        if status:
            models = [m for m in models if m["status"] == status]

        return sorted(
            [self._resolve_model_paths(m) for m in models],
            key=lambda m: m["registered_at"],
            reverse=True,
        )

    def get_model(self, model_id: str) -> dict | None:
        """Get a specific model by ID.

        Returns a copy with paths resolved to absolute.
        """
        entry = self.registry["models"].get(model_id)
        if entry is not None:
            return self._resolve_model_paths(entry)
        return None

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

    def get_model_comparison(self, model_type: str, equipment_type: str) -> list[dict]:
        """Compare all models for a specific type/equipment."""
        models = self.list_models(model_type, equipment_type)
        return [
            {
                "model_id": m["model_id"],
                "registered_at": m["registered_at"],
                "status": m["status"],
                **m["metrics"],
            }
            for m in models
        ]


# Singleton instance
_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    """Get singleton ModelRegistry instance."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
