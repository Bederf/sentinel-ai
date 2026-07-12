"""ML Retraining Queue

Persistent queue of retraining requests (ml_retraining_queue table).
Producers (drift metrics collection) enqueue when drift is detected;
the queue processor (Phase 241 Plan 2) consumes oldest-pending entries.

Dedupe and rate-limiting live here in enqueue() so every producer gets
the same guarantees. All DB failures are fail-closed: enqueue returns
None and never raises, so producers (metric scrapes) are never broken
by queue problems.

Phase 241 M2.4 Plan 1: Drift-Driven Retraining
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("sentinel.retraining_queue")

TABLE = "ml_retraining_queue"
RATE_LIMIT_HOURS = 24

# Error substrings that mark a failure as permanent (no retries — Plan 2
# escalates immediately). Matched case-insensitively against RetrainResult.error.
_PERMANENT_ERROR_MARKERS = (
    "ml processing disabled",
    "ml training is disabled",
    "unknown model type",
    "site not found",
)


def is_permanent_failure(error: str | None) -> bool:
    """Classify a retraining error as permanent (True) or transient (False).

    Permanent failures (site/model configuration problems) are escalated
    immediately by the queue processor; transient failures are retried.
    """
    if not error:
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in _PERMANENT_ERROR_MARKERS)


def _get_client() -> Any | None:
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


def enqueue(
    site_id: str,
    equipment_type: str,
    model_type: str,
    trigger_reason: str,
    drift_verdict: str | None = None,
    baseline_id: str | None = None,
) -> str | None:
    """Enqueue a retraining request. Returns queue id, or None if skipped/failed.

    Skips (returns None) when:
    - a pending/running entry already exists for (site_id, equipment_type, model_type)
    - a completed entry for the same key finished < RATE_LIMIT_HOURS ago
    - any DB error occurs (fail-closed: do not enqueue, log a warning)
    """
    try:
        client = _get_client()
        if not client:
            logger.warning("[RETRAIN-QUEUE] Supabase client unavailable — not enqueuing (fail-closed)")
            return None

        # Dedupe: skip if already pending/running for the same key
        pending = (
            client.table(TABLE)
            .select("id")
            .eq("site_id", site_id)
            .eq("equipment_type", equipment_type)
            .eq("model_type", model_type)
            .in_("status", ["pending", "running"])
            .limit(1)
            .execute()
        )
        if pending.data:
            logger.debug(
                "[RETRAIN-QUEUE] Dedupe skip: %s/%s/%s already pending/running",
                site_id,
                equipment_type,
                model_type,
            )
            return None

        # Rate-limit: skip if a completed entry for the same key finished < 24h ago
        cutoff = (datetime.now(UTC) - timedelta(hours=RATE_LIMIT_HOURS)).isoformat()
        recent = (
            client.table(TABLE)
            .select("id")
            .eq("site_id", site_id)
            .eq("equipment_type", equipment_type)
            .eq("model_type", model_type)
            .eq("status", "completed")
            .gte("updated_at", cutoff)
            .limit(1)
            .execute()
        )
        if recent.data:
            logger.debug(
                "[RETRAIN-QUEUE] Rate-limit skip: %s/%s/%s completed < %dh ago",
                site_id,
                equipment_type,
                model_type,
                RATE_LIMIT_HOURS,
            )
            return None

        resp = (
            client.table(TABLE)
            .insert(
                {
                    "site_id": site_id,
                    "equipment_type": equipment_type,
                    "model_type": model_type,
                    "trigger_reason": trigger_reason,
                    "drift_verdict": drift_verdict,
                    "baseline_id": baseline_id,
                    "status": "pending",
                }
            )
            .execute()
        )
        if resp.data:
            queue_id = resp.data[0].get("id")
            logger.info(
                "[RETRAIN-QUEUE] Enqueued %s/%s/%s reason=%s id=%s",
                site_id,
                equipment_type,
                model_type,
                trigger_reason,
                queue_id,
            )
            return queue_id
        logger.warning("[RETRAIN-QUEUE] Insert returned no data for %s/%s/%s", site_id, equipment_type, model_type)
        return None

    except Exception as e:
        logger.warning("[RETRAIN-QUEUE] Enqueue failed (fail-closed): %s", e)
        return None


def transition(queue_id: str, new_status: str, error: str | None = None) -> bool:
    """Transition a queue entry to new_status. Never raises.

    Increments attempts when entering 'running' (an attempt starts).
    Always bumps updated_at. Returns True on success, False otherwise.
    """
    try:
        client = _get_client()
        if not client:
            logger.warning("[RETRAIN-QUEUE] Supabase client unavailable — transition skipped")
            return False

        payload: dict[str, Any] = {
            "status": new_status,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if error is not None:
            payload["error"] = error

        if new_status == "running":
            current = client.table(TABLE).select("attempts").eq("id", queue_id).limit(1).execute()
            attempts = current.data[0].get("attempts", 0) if current.data else 0
            payload["attempts"] = attempts + 1

        resp = client.table(TABLE).update(payload).eq("id", queue_id).execute()
        return bool(resp.data)

    except Exception as e:
        logger.warning("[RETRAIN-QUEUE] Transition failed for %s -> %s: %s", queue_id, new_status, e)
        return False


def get_oldest_pending() -> dict | None:
    """Return the oldest pending queue entry, or None. Never raises."""
    try:
        client = _get_client()
        if not client:
            return None
        resp = (
            client.table(TABLE).select("*").eq("status", "pending").order("created_at", desc=False).limit(1).execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.warning("[RETRAIN-QUEUE] get_oldest_pending failed: %s", e)
        return None
