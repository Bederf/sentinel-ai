"""Phase 236-03: inference-time prediction logging.

Every site-scoped LSTM forecast and AE score is logged to ml_prediction_log
so the daily accuracy job can join forecasts to telemetry_hourly actuals and
produce a MEASURED drift signal. Global legacy models (no site_id — the known
false-provenance slots) are not logged; they are being retired, not measured.

Logging must never break inference: every path is wrapped and failures are
debug-logged only.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_HORIZON_KEYS = (("24h", 24), ("48h", 48), ("72h", 72))


def _utc_hour(ts: datetime) -> datetime:
    return ts.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def build_lstm_log_rows(result: dict[str, Any], model_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure row-builder for an LSTM predict() result. Empty list when the
    result should not be logged (error, no predictions, global model)."""
    if not result.get("predictions"):
        return []
    if not model_info.get("site_id"):
        return []  # global legacy slot — not measured

    metadata = model_info.get("metadata") or {}
    point_name = metadata.get("target") or (metadata.get("input_contract") or {}).get("target")
    if not point_name:
        return []  # no declared target → actuals join impossible; skip honestly

    predicted_at = datetime.now(UTC)
    rows = []
    for key, horizon in _HORIZON_KEYS:
        value = result["predictions"].get(key)
        if value is None:
            continue
        rows.append(
            {
                "model_id": model_info["model_id"],
                "model_kind": "lstm_forecast",
                "site_id": model_info.get("site_id"),
                "equipment_id": result.get("equipment_id"),
                "equipment_type": result.get("equipment_type"),
                "point_name": point_name,
                "predicted_at": predicted_at.isoformat(),
                "target_hour": _utc_hour(predicted_at + timedelta(hours=horizon)).isoformat(),
                "horizon_hours": horizon,
                "predicted_value": float(value),
            }
        )
    return rows


def build_ae_log_row(result: dict[str, Any], model_info: dict[str, Any]) -> dict[str, Any] | None:
    """Pure row-builder for an AE check_equipment() result."""
    if result.get("anomaly_score") is None:
        return None
    if not model_info.get("site_id"):
        return None
    return {
        "model_id": model_info["model_id"],
        "model_kind": "ae_score",
        "site_id": model_info.get("site_id"),
        "equipment_id": result.get("equipment_id"),
        "equipment_type": result.get("equipment_type"),
        "predicted_at": datetime.now(UTC).isoformat(),
        "predicted_value": float(result["anomaly_score"]),
        "threshold": float(result["threshold"]) if result.get("threshold") is not None else None,
    }


def log_lstm_prediction(result: dict[str, Any], model_info: dict[str, Any]) -> None:
    """Best-effort insert of LSTM forecast rows (sync — call sites are sync)."""
    try:
        rows = build_lstm_log_rows(result, model_info)
        if not rows:
            return
        from app.database.supabase_client import get_supabase_client

        get_supabase_client().table("ml_prediction_log").insert(rows).execute()
    except Exception as e:
        logger.debug("[ML-PREDLOG] LSTM log failed (non-fatal): %s", e)


def log_ae_score(result: dict[str, Any], model_info: dict[str, Any]) -> None:
    """Best-effort insert of one AE score row."""
    try:
        row = build_ae_log_row(result, model_info)
        if row is None:
            return
        from app.database.supabase_client import get_supabase_client

        get_supabase_client().table("ml_prediction_log").insert(row).execute()
    except Exception as e:
        logger.debug("[ML-PREDLOG] AE log failed (non-fatal): %s", e)
