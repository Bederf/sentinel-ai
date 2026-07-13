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
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CONTRACT_MODEL_TYPES = {"lstm", "autoencoder", "classifier"}
VALID_INFERENCE_SCOPES = {"equipment_type", "equipment_id"}
VALID_MISSING_FEATURE_POLICIES = {"fail_closed"}
REQUIRED_INPUT_CONTRACT_FIELDS = {
    "inference_scope",
    "feature_surface",
    "required_features",
    "target",
    "missing_feature_policy",
}


def build_input_contract_metadata(
    *,
    site_id: str | None,
    equipment_type: str,
    model_type: str,
    required_features: list[str],
    target: str,
    inference_scope: str = "equipment_type",
    feature_surface: str | None = None,
    missing_feature_policy: str = "fail_closed",
) -> dict:
    """Build standard model input contract metadata for feature-window models."""
    site_part = (site_id or "global").replace("-", "_")
    scope_part = inference_scope.replace("-", "_")
    return {
        "inference_scope": inference_scope,
        "feature_surface": feature_surface or f"{site_part}_{equipment_type}_{model_type}_{scope_part}_v1",
        "required_features": list(required_features),
        "target": target,
        "missing_feature_policy": missing_feature_policy,
    }


def validate_input_contract_metadata(model_type: str, metadata: dict | None) -> None:
    """Fail closed for new LSTM/autoencoder registrations without an input contract."""
    if model_type not in CONTRACT_MODEL_TYPES:
        return
    metadata = metadata or {}
    missing = sorted(REQUIRED_INPUT_CONTRACT_FIELDS - set(metadata))
    if missing:
        raise ValueError(f"{model_type} registration missing input contract metadata: {missing}")

    inference_scope = metadata.get("inference_scope")
    if inference_scope not in VALID_INFERENCE_SCOPES:
        raise ValueError(f"{model_type} registration has invalid inference_scope: {inference_scope!r}")

    policy = metadata.get("missing_feature_policy")
    if policy not in VALID_MISSING_FEATURE_POLICIES:
        raise ValueError(f"{model_type} registration has invalid missing_feature_policy: {policy!r}")

    required_features = metadata.get("required_features")
    if (
        not isinstance(required_features, list)
        or not required_features
        or not all(isinstance(feature, str) and feature for feature in required_features)
    ):
        raise ValueError(f"{model_type} registration requires a non-empty required_features list")

    target = metadata.get("target")
    if not isinstance(target, str) or not target:
        raise ValueError(f"{model_type} registration requires a non-empty target")

    feature_surface = metadata.get("feature_surface")
    if not isinstance(feature_surface, str) or not feature_surface:
        raise ValueError(f"{model_type} registration requires a non-empty feature_surface")


class ModelRegistry:
    """Registry for managing ML model versions."""

    def __init__(self, registry_path: str | None = None):
        if registry_path is None:
            registry_path = Path(__file__).parent / "models" / "registry.json"
        self.registry_path = Path(registry_path)
        self._models_base_dir = self.registry_path.parent
        self.backup_path = self.registry_path.with_suffix(self.registry_path.suffix + ".bak")
        self.lock_path = self.registry_path.with_suffix(self.registry_path.suffix + ".lock")
        self.registry = self._load_registry()
        self._registry_mtime_ns: int = self._stat_mtime_ns()
        self._generation_counter: int = 0

    @contextmanager
    def _file_lock(self):
        """Serialize registry file access across backend workers on Linux."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.lock_path.open("a+")
        try:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                logger.warning("Registry file lock unavailable; continuing without cross-process lock")
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
            lock_file.close()

    def _read_registry_file(self, path: Path) -> dict:
        return json.loads(path.read_text())

    def _load_registry(self) -> dict:
        """Load registry from disk."""
        with self._file_lock():
            if self.registry_path.exists():
                try:
                    return self._read_registry_file(self.registry_path)
                except json.JSONDecodeError:
                    if self.backup_path.exists():
                        logger.error("Corrupted registry %s; recovering from %s", self.registry_path, self.backup_path)
                        return self._read_registry_file(self.backup_path)
                    logger.error("Corrupted registry %s and no backup available; starting fresh", self.registry_path)
                    return {"models": {}, "active": {}}
        return {"models": {}, "active": {}}

    def _stat_mtime_ns(self) -> int:
        try:
            return self.registry_path.stat().st_mtime_ns
        except OSError:
            return 0

    def _maybe_reload(self) -> None:
        """Reload from disk if another worker changed the registry file.

        Each backend worker holds its own in-memory copy; without this, an
        activation in one worker is invisible to the others until restart.
        """
        mtime_ns = self._stat_mtime_ns()
        if mtime_ns == self._registry_mtime_ns:
            return
        self.registry = self._load_registry()
        # Store the pre-load stat: if the file changed again mid-reload we
        # detect it on the next call rather than serving the missed write.
        self._registry_mtime_ns = mtime_ns
        self._generation_counter += 1
        logger.info(f"Registry changed on disk; reloaded (generation {self._generation_counter})")

    @property
    def _generation(self) -> int:
        """Cache-invalidation counter; bumps on local activation or cross-worker change."""
        self._maybe_reload()
        return self._generation_counter

    def _atomic_write_json(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _save_registry(self):
        """Save registry to disk."""
        payload = json.dumps(self.registry, indent=2, default=str)
        with self._file_lock():
            self._atomic_write_json(self.registry_path, payload)
            self._atomic_write_json(self.backup_path, payload)
            # Stat under the lock so our own write isn't mistaken for a
            # cross-worker change on the next read.
            self._registry_mtime_ns = self._stat_mtime_ns()

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

    def _active_key(self, model_type: str, equipment_type: str, site_id: str | None = None) -> str:
        """Build active-model key. Explicit site IDs are isolated from global legacy keys."""
        if site_id:
            return f"{site_id}_{model_type}_{equipment_type}"
        return f"{model_type}_{equipment_type}"

    def register_model(
        self,
        model_type: str,  # e.g., "lstm", "autoencoder"
        equipment_type: str,  # e.g., "chiller", "generator"
        model_path: str,
        metrics: dict,
        metadata: dict | None = None,
        auto_activate: bool = False,
        site_id: str | None = None,
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
        self._maybe_reload()
        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        site_part = f"{site_id}_" if site_id else ""
        model_id = f"{model_type}_{site_part}{equipment_type}_{version}"

        # Convert paths to relative for portability
        stored_metadata = dict(metadata) if metadata else {}
        validate_input_contract_metadata(model_type, stored_metadata)
        if "scaler_path" in stored_metadata:
            stored_metadata["scaler_path"] = self._to_relative_path(str(stored_metadata["scaler_path"]))
        if site_id:
            stored_metadata["site_id"] = site_id

        entry = {
            "model_id": model_id,
            "model_type": model_type,
            "equipment_type": equipment_type,
            "site_id": site_id,
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
            self.set_active(model_id, site_id=site_id)

        return model_id

    def set_active(self, model_id: str, site_id: str | None = None):
        """Set a model as the active version for inference."""
        self._maybe_reload()
        if model_id not in self.registry["models"]:
            raise ValueError(f"Model {model_id} not found in registry")

        model = self.registry["models"][model_id]
        model_site_id = site_id or model.get("site_id") or model.get("metadata", {}).get("site_id")
        key = self._active_key(model["model_type"], model["equipment_type"], model_site_id)

        # Deactivate previous active model
        prev_active = self.registry["active"].get(key)
        if prev_active and prev_active in self.registry["models"]:
            self.registry["models"][prev_active]["status"] = "inactive"

        # Activate new model
        self.registry["active"][key] = model_id
        self.registry["models"][model_id]["site_id"] = model_site_id
        if model_site_id:
            self.registry["models"][model_id].setdefault("metadata", {})["site_id"] = model_site_id
        self.registry["models"][model_id]["status"] = "active"
        self._generation_counter += 1
        self._save_registry()

        logger.info(f"Activated model: {model_id} (registry generation {self._generation_counter})")

    def get_active_model(self, model_type: str, equipment_type: str, site_id: str | None = None) -> dict | None:
        """Get the currently active model for inference.

        Returns a copy with paths resolved to absolute.
        """
        self._maybe_reload()
        key = self._active_key(model_type, equipment_type, site_id)
        model_id = self.registry["active"].get(key)

        if model_id and model_id in self.registry["models"]:
            return self._resolve_model_paths(self.registry["models"][model_id])
        return None

    def get_active_model_with_fallback(
        self, model_type: str, equipment_type: str, site_id: str | None = None
    ) -> tuple[dict | None, str | None]:
        """Resolve champion with global fallback (Phase 245 M2.6 N4).

        Tries site-scoped champion first; if none exists, falls back to the
        global (non-site-scoped) champion for the same model_type + equipment_type
        pair. Returns (model, resolution_path) where resolution_path is:

        - ``"site"`` — site-scoped champion found (most relevant scope)
        - ``"global_fallback"`` — no site champion, global champion used instead
        - ``None`` — neither site nor global champion exists (first-ever model)

        The caller records ``resolution_path`` in ``model_promotion_log.champion_source``
        so every comparison is auditable.
        """
        # 1. Try site-scoped
        champion = self.get_active_model(model_type, equipment_type, site_id=site_id)
        if champion is not None:
            return champion, "site"

        # 2. Fall back to global (only if a site_id was requested; if the
        #    caller already passed site_id=None, we've already tried global)
        if site_id is not None:
            champion = self.get_active_model(model_type, equipment_type, site_id=None)
            if champion is not None:
                return champion, "global_fallback"

        # 3. Neither exists
        return None, None

    def list_models(
        self,
        model_type: str | None = None,
        equipment_type: str | None = None,
        status: str | None = None,
        site_id: str | None = None,
    ) -> list[dict]:
        """List registered models with optional filters.

        Returns copies with paths resolved to absolute.
        """
        self._maybe_reload()
        models = list(self.registry["models"].values())

        if model_type:
            models = [m for m in models if m["model_type"] == model_type]
        if equipment_type:
            models = [m for m in models if m["equipment_type"] == equipment_type]
        if site_id is not None:
            models = [m for m in models if (m.get("site_id") or m.get("metadata", {}).get("site_id")) == site_id]
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
        self._maybe_reload()
        entry = self.registry["models"].get(model_id)
        if entry is not None:
            return self._resolve_model_paths(entry)
        return None

    def delete_model(self, model_id: str) -> bool:
        """Delete a model from registry (does not delete files)."""
        self._maybe_reload()
        if model_id not in self.registry["models"]:
            return False

        model = self.registry["models"][model_id]

        # Can't delete active model
        key = self._active_key(
            model["model_type"],
            model["equipment_type"],
            model.get("site_id") or model.get("metadata", {}).get("site_id"),
        )
        if self.registry["active"].get(key) == model_id:
            raise ValueError(f"Cannot delete active model {model_id}")

        del self.registry["models"][model_id]
        self._save_registry()

        logger.info(f"Deleted model: {model_id}")
        return True

    def get_model_comparison(self, model_type: str, equipment_type: str, site_id: str | None = None) -> list[dict]:
        """Compare all models for a specific type/equipment."""
        models = self.list_models(model_type, equipment_type, site_id=site_id)
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
