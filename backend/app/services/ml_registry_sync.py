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
from typing import Any

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent.parent.parent / "ml" / "models" / "registry.json"
_DATABASE_URL = os.getenv("DATABASE_URL")
if not _DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")


def _parse_model_row(model_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Map a registry.json entry to an ml_models table row."""
    metrics = entry.get("metrics") or {}
    metadata = entry.get("metadata") or {}

    # r² values — LSTM entries have per-horizon dicts; classifiers/survival use scalars
    r2_24h = metrics.get("r_squared_24h") or metrics.get("r2_24h")
    r2_48h = metrics.get("r_squared_48h") or metrics.get("r2_48h")
    r2_72h = metrics.get("r_squared_72h") or metrics.get("r2_72h")
    r2_avg = metrics.get("r_squared_avg") or metrics.get("r2_avg") or metrics.get("r2")

    # Feature names — stored as list in metadata under several keys
    feature_names = metadata.get("feature_names") or metadata.get("feature_cols") or []

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


def sync_registry_to_db(registry_path: Path = _REGISTRY_PATH) -> dict[str, int]:
    """
    Upsert the latest model per (equipment_type, model_type) group into ml_models.

    The registry accumulates every retrained version but the DB enforces a unique
    constraint on (equipment_type, model_type, status).  We pick only the most
    recently registered entry per group so each active slot is updated to the
    latest model without hitting duplicate-key errors.

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
    parse_errors = 0

    # Parse all rows first
    all_rows: list[dict] = []
    for model_id, entry in models.items():
        try:
            row = _parse_model_row(model_id, entry)
            if row:
                all_rows.append(row)
        except Exception as e:
            logger.warning(f"Skipping model {model_id}: {e}")
            parse_errors += 1

    if not all_rows:
        return {"upserted": 0, "skipped": parse_errors + len(models) - len(all_rows), "errors": parse_errors}

    # Keep only the latest model per (equipment_type, model_type) group, and only
    # for 'active' status.  This avoids spurious ON CONFLICT violations from
    # historical entries that were superseded but retained in the JSON.
    latest: dict[tuple, dict] = {}
    skipped = 0
    for row in all_rows:
        if row["status"] != "active":
            skipped += 1
            continue
        key = (row["equipment_type"], row["model_type"])
        existing = latest.get(key)
        if existing is None or row["registered_at"] > existing["registered_at"]:
            if existing is not None:
                skipped += 1
            latest[key] = row
        else:
            skipped += 1

    rows = list(latest.values())
    logger.debug(
        f"Registry has {len(all_rows)} entries; syncing {len(rows)} (latest per group), skipping {skipped} older versions"
    )

    try:
        conn = psycopg2.connect(_DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()

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
                    ON CONFLICT (equipment_type, model_type) DO UPDATE SET
                        model_id         = EXCLUDED.model_id,
                        status           = EXCLUDED.status,
                        model_path       = EXCLUDED.model_path,
                        scaler_path      = EXCLUDED.scaler_path,
                        r_squared_avg    = EXCLUDED.r_squared_avg,
                        r_squared_24h    = EXCLUDED.r_squared_24h,
                        r_squared_48h    = EXCLUDED.r_squared_48h,
                        r_squared_72h    = EXCLUDED.r_squared_72h,
                        training_samples = EXCLUDED.training_samples,
                        registered_at    = EXCLUDED.registered_at
                    """,
                    row,
                )
                upserted += 1
            except Exception as e:
                logger.warning(f"Upsert failed for {row.get('model_id')}: {e}")
                parse_errors += 1

        cur.close()
        conn.close()

        logger.info(
            f"ml_models sync: {upserted} upserted, {skipped} older versions skipped, "
            f"{parse_errors} errors (from {len(models)} registry entries)"
        )
        return {"upserted": upserted, "skipped": skipped, "errors": parse_errors}

    except Exception as e:
        logger.error(f"ml_models DB sync failed: {e}")
        return {"upserted": 0, "skipped": 0, "errors": 1}
