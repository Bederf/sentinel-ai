"""
ML Registry Sync — writes JSON model registry → ml_models Supabase table.

Run at startup (idempotent via ON CONFLICT DO UPDATE) and after each retraining
cycle. Gives the DB-backed model management layer a live view of all models,
enabling drift tracking, accuracy queries, and retraining governance via SQL
instead of flat-file reads.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent.parent.parent / "ml" / "models" / "registry.json"
_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
)


def _parse_model_row(model_id: str, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map a registry.json entry to an ml_models table row."""
    metrics = entry.get("metrics") or {}
    metadata = entry.get("metadata") or {}

    # r² values — LSTM entries have per-horizon dicts; classifiers/survival use scalars
    r2_24h = metrics.get("r_squared_24h") or metrics.get("r2_24h")
    r2_48h = metrics.get("r_squared_48h") or metrics.get("r2_48h")
    r2_72h = metrics.get("r_squared_72h") or metrics.get("r2_72h")
    r2_avg = metrics.get("r_squared_avg") or metrics.get("r2_avg") or metrics.get("r2")

    # Feature names — stored as list in metadata under several keys
    feature_names = (
        metadata.get("feature_names")
        or metadata.get("feature_cols")
        or []
    )

    registered_at = entry.get("registered_at") or metadata.get("trained_at")
    if registered_at and isinstance(registered_at, str):
        # Strip timezone for timestamp-without-timezone column
        registered_at = registered_at.replace("Z", "").split("+")[0]

    return {
        "model_id": model_id,
        "model_type": entry.get("model_type", "unknown"),
        "equipment_type": entry.get("equipment_type", "unknown"),
        "model_path": entry.get("model_path", ""),
        "scaler_path": entry.get("scaler_path"),
        "r_squared_24h": r2_24h,
        "r_squared_48h": r2_48h,
        "r_squared_72h": r2_72h,
        "r_squared_avg": r2_avg,
        "status": entry.get("status", "active"),
        "training_samples": metrics.get("training_samples") or metrics.get("n_samples"),
        "validation_samples": metrics.get("validation_samples"),
        "feature_names": feature_names if feature_names else None,
        "target_name": metadata.get("target_name") or metadata.get("target"),
        "forecast_horizons": metadata.get("forecast_horizons"),
        "registered_at": registered_at or datetime.utcnow().isoformat(),
        "registered_by": "ml_registry_sync",
        "notes": None,
    }


def sync_registry_to_db(registry_path: Path = _REGISTRY_PATH) -> Dict[str, int]:
    """
    Upsert all models from registry.json into the ml_models table.

    Uses ON CONFLICT (model_id) DO UPDATE so it is safe to call repeatedly.
    Returns counts: {"upserted": N, "skipped": N, "errors": N}
    """
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        logger.warning("psycopg2 not available — skipping ml_models sync")
        return {"upserted": 0, "skipped": 0, "errors": 0}

    if not registry_path.exists():
        logger.warning(f"Registry not found at {registry_path}")
        return {"upserted": 0, "skipped": 0, "errors": 0}

    try:
        registry = json.loads(registry_path.read_text())
    except Exception as e:
        logger.error(f"Failed to read registry: {e}")
        return {"upserted": 0, "skipped": 0, "errors": 1}

    models = registry.get("models", {})
    rows = []
    parse_errors = 0

    for model_id, entry in models.items():
        try:
            row = _parse_model_row(model_id, entry)
            if row:
                rows.append(row)
        except Exception as e:
            logger.warning(f"Skipping model {model_id}: {e}")
            parse_errors += 1

    if not rows:
        return {"upserted": 0, "skipped": parse_errors, "errors": parse_errors}

    try:
        conn = psycopg2.connect(_DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()

        # Ensure model_id uniqueness constraint exists (idempotent)
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE tablename = 'ml_models' AND indexname = 'ml_models_model_id_key'
                ) THEN
                    ALTER TABLE ml_models ADD CONSTRAINT ml_models_model_id_key UNIQUE (model_id);
                END IF;
            EXCEPTION WHEN duplicate_table THEN NULL;
            END $$;
            """
        )

        upserted = 0
        for row in rows:
            try:
                cur.execute(
                    """
                    INSERT INTO ml_models (
                        model_id, model_type, equipment_type, model_path, scaler_path,
                        r_squared_24h, r_squared_48h, r_squared_72h, r_squared_avg,
                        status, training_samples, validation_samples,
                        feature_names, target_name, forecast_horizons,
                        registered_at, registered_by, notes
                    ) VALUES (
                        %(model_id)s, %(model_type)s, %(equipment_type)s, %(model_path)s, %(scaler_path)s,
                        %(r_squared_24h)s, %(r_squared_48h)s, %(r_squared_72h)s, %(r_squared_avg)s,
                        %(status)s, %(training_samples)s, %(validation_samples)s,
                        %(feature_names)s, %(target_name)s, %(forecast_horizons)s,
                        %(registered_at)s::timestamp, %(registered_by)s, %(notes)s
                    )
                    ON CONFLICT ON CONSTRAINT ml_models_model_id_key DO UPDATE SET
                        status          = EXCLUDED.status,
                        r_squared_avg   = EXCLUDED.r_squared_avg,
                        r_squared_24h   = EXCLUDED.r_squared_24h,
                        r_squared_48h   = EXCLUDED.r_squared_48h,
                        r_squared_72h   = EXCLUDED.r_squared_72h,
                        training_samples = EXCLUDED.training_samples,
                        registered_at   = EXCLUDED.registered_at
                    """,
                    row,
                )
                upserted += 1
            except Exception as e:
                logger.warning(f"Upsert failed for {row.get('model_id')}: {e}")
                parse_errors += 1

        cur.close()
        conn.close()

        logger.info(f"ml_models sync: {upserted} upserted, {parse_errors} errors from {len(models)} registry entries")
        return {"upserted": upserted, "skipped": 0, "errors": parse_errors}

    except Exception as e:
        logger.error(f"ml_models DB sync failed: {e}")
        return {"upserted": 0, "skipped": 0, "errors": 1}
