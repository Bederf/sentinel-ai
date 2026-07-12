"""
Baseline Persistence Module — Plan 1 (Phase 239 M2.2 Real Drift Detection)

Captures trained model statistics (LSTM mae/r2, Autoencoder threshold/error)
and persists them to ml_model_baselines table with full provenance.

Enables Plan 2 (drift-detector-real-baselines) to detect model degradation
by comparing inference errors against trained baselines.
"""

import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _compute_md5_hash(data: str) -> str:
    """Compute MD5 hash of a string."""
    return hashlib.md5(data.encode()).hexdigest()


def _compute_feature_schema_hash(features: list[str], target: str) -> str:
    """
    Compute MD5 hash of sorted(features + target).

    Prevents silent feature substitutions: if training used different
    features, the hash will mismatch and baseline will be marked invalid.
    """
    combined = sorted([*features, target])
    schema_str = json.dumps(combined, sort_keys=True)
    return _compute_md5_hash(schema_str)


def _compute_training_dataset_hash(metadata: dict[str, Any]) -> str:
    """
    Compute MD5 hash from training dataset metadata.

    Includes data_source, real_data_start/end, site_id, equipment_type
    to ensure baseline provenance is captured.
    """
    # Use deterministic fields that describe the training dataset
    hashable = {
        "data_source": metadata.get("data_source"),
        "site_id": metadata.get("site_id"),
        "equipment_type": metadata.get("equipment_type"),
        "real_data_start": metadata.get("real_data_start"),
        "real_data_end": metadata.get("real_data_end"),
        "real_hours_available": metadata.get("real_hours_available"),
        "feature_columns": sorted(metadata.get("feature_columns", [])),
        "variance_gate_passed": metadata.get("variance_gate", {}).get("passed"),
    }
    dataset_str = json.dumps(hashable, sort_keys=True)
    return _compute_md5_hash(dataset_str)


def _get_model_version() -> str:
    """Get git commit hash (HEAD), or 'demo' if git unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning("Could not get git commit hash: %s", e)
    return "demo"


def _compute_equipment_fingerprint(config: dict[str, Any]) -> str:
    """
    Compute hash of equipment config to track which equipment was trained on.

    Includes equipment_type, features, target to detect config changes.
    """
    hashable = {
        "equipment_type": config.get("equipment_type"),
        "features": sorted(config.get("features", [])),
        "target": config.get("target"),
        "description": config.get("description"),
    }
    config_str = json.dumps(hashable, sort_keys=True)
    return _compute_md5_hash(config_str)


def capture_baseline_from_trained_model(
    trained_model_result: dict[str, Any],
    model_type: str,
    equipment_type: str,
    site_id: str | None = None,
) -> dict[str, Any]:
    """
    Capture baseline statistics from a trained model.

    Args:
        trained_model_result: Result dict from LSTMTrainer.train_equipment_type()
                             or AutoencoderTrainer.train_equipment_type()
        model_type: "lstm" or "autoencoder"
        equipment_type: Equipment type (chiller, ahu, etc.)
        site_id: Optional site ID for site-scoped models

    Returns:
        Dict with baseline fields ready for DB insertion:
        {
            "model_id": str,
            "site_id": str | None,
            "equipment_type": str,
            # Metrics vary by model_type
            "feature_schema_hash": str,
            "feature_schema": list[str],
            "training_dataset_hash": str,
            "training_dataset_details": dict,
            "model_version": str,
            "equipment_fingerprint": str,
            "training_timestamp": str (ISO 8601),
            "created_by": "system",
        }

    Raises:
        ValueError: If required fields are missing or inconsistent.
    """
    if model_type not in ("lstm", "autoencoder"):
        raise ValueError(f"Unknown model_type: {model_type}")

    model_id = trained_model_result.get("model_id")
    if not model_id:
        raise ValueError("trained_model_result missing model_id")

    metrics = trained_model_result.get("metrics", {})
    if not metrics:
        raise ValueError("trained_model_result missing metrics")

    # Extract metadata
    metadata = trained_model_result.get("metadata", {})
    if not metadata:
        # Try to reconstruct from result fields
        metadata = {
            "data_source": trained_model_result.get("data_source", "unknown"),
            "site_id": site_id,
            "equipment_type": equipment_type,
            "real_hours_available": trained_model_result.get("samples", 0),
            "feature_columns": trained_model_result.get("feature_names", []),
        }

    # Extract features and target
    feature_names = trained_model_result.get("feature_names") or trained_model_result.get("metadata", {}).get(
        "feature_names", []
    )
    target = trained_model_result.get("metadata", {}).get("target", "")

    if not feature_names or not target:
        raise ValueError("trained_model_result missing feature_names or target")

    # Compute hashes
    feature_schema_hash = _compute_feature_schema_hash(feature_names, target)

    # Use training_dataset_hash from loader metadata if available, else compute
    dataset_metadata = trained_model_result.get("metadata", {}).get("training_dataset_details")
    if dataset_metadata:
        training_dataset_hash = _compute_md5_hash(json.dumps(dataset_metadata, sort_keys=True))
    else:
        training_dataset_hash = _compute_training_dataset_hash(metadata)

    # Get model version
    model_version = _get_model_version()

    # Compute equipment fingerprint
    equipment_config = {
        "equipment_type": equipment_type,
        "features": feature_names,
        "target": target,
    }
    equipment_fingerprint = _compute_equipment_fingerprint(equipment_config)

    # Build baseline dict
    baseline = {
        "model_id": model_id,
        "site_id": site_id,
        "equipment_type": equipment_type,
        "feature_schema_hash": feature_schema_hash,
        "feature_schema": feature_names,
        "training_dataset_hash": training_dataset_hash,
        "training_dataset_details": dataset_metadata or metadata,
        "model_version": model_version,
        "equipment_fingerprint": equipment_fingerprint,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "created_by": "system",
        "provenance_status": "valid",
    }

    # Extract model-type-specific metrics
    if model_type == "lstm":
        baseline.update(
            {
                "mae_24h": float(metrics.get("mae_24h", 0)),
                "mae_48h": float(metrics.get("mae_48h", 0)),
                "mae_72h": float(metrics.get("mae_72h", 0)),
                "mae_avg": float(metrics.get("mae_avg", 0)),
                "rmse_24h": float(metrics.get("rmse_24h", 0)),
                "rmse_48h": float(metrics.get("rmse_48h", 0)),
                "rmse_72h": float(metrics.get("rmse_72h", 0)),
                "r2_24h": float(metrics.get("r2_24h", 0)),
                "r2_48h": float(metrics.get("r2_48h", 0)),
                "r2_72h": float(metrics.get("r2_72h", 0)),
                "r2_avg": float(metrics.get("r2_avg", 0)),
            }
        )

    elif model_type == "autoencoder":
        baseline.update(
            {
                "threshold": float(metrics.get("threshold", 0)),
                "val_error_mean": float(metrics.get("val_error_mean", 0)),
                "val_error_std": float(metrics.get("val_error_std", 0)),
                "val_error_max": float(metrics.get("val_error_max", 0)),
                "val_error_p95": float(metrics.get("val_error_p95", 0)),
                "val_error_p99": float(metrics.get("val_error_p99", 0)),
                "precision": float(metrics.get("precision", 0)),
                "recall": float(metrics.get("recall", 0)),
                "f1_score": float(metrics.get("f1_score", 0)),
            }
        )

    return baseline


def persist_baseline_to_db(baseline_dict: dict[str, Any]) -> str:
    """
    Persist baseline to ml_model_baselines table.

    Args:
        baseline_dict: Dict from capture_baseline_from_trained_model()

    Returns:
        model_id (primary key)

    Raises:
        Exception: If database write fails
    """
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            raise RuntimeError("Supabase client unavailable")

        # Filter None values to avoid overwriting with nulls
        insert_data = {k: v for k, v in baseline_dict.items() if v is not None}

        response = client.table("ml_model_baselines").insert(insert_data).execute()

        if not response.data:
            raise ValueError("Database insert returned no data")

        model_id = response.data[0].get("model_id")
        logger.info(f"[BASELINE PERSISTENCE] Persisted baseline for {model_id}")

        return model_id

    except Exception as e:
        logger.error(f"[BASELINE PERSISTENCE] Failed to persist baseline: {e}")
        raise


def record_training_audit(model_id: str, status: str, error_msg: str | None = None) -> None:
    """
    Record training audit entry in ml_training_audit_log.

    Args:
        model_id: Model ID to audit
        status: "train_started", "train_complete", "baseline_written", or "error"
        error_msg: Optional error message
    """
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            logger.warning("[TRAINING AUDIT] Supabase client unavailable")
            return

        audit_entry = {
            "model_id": model_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "error_msg": error_msg,
        }

        client.table("ml_training_audit_log").insert(audit_entry).execute()
        logger.debug(f"[TRAINING AUDIT] Logged {status} for {model_id}")

    except Exception as e:
        logger.warning(f"[TRAINING AUDIT] Failed to record audit entry: {e}")
