"""SENTINEL Phase E — BESS Dispatch Execution Consumer.

Polls the `recommendations` table for pending bess_dispatch records,
re-validates each against BESSDispatchEngine constraints, and either
simulates (DRY_RUN=True) or executes (DRY_RUN=False) the dispatch.

Phase 0A behaviour (default: DRY_RUN=True):
  Logs what would be dispatched, marks recommendation `executed`,
  writes a parasite_decision with execution_mode='simulated'.
  Never calls hardware writers.

Live dispatch (BESS_DISPATCH_DRY_RUN=false):
  Re-fetches current BESS state, re-runs constraint validation through
  BESSDispatchEngine, only executes if actual_power_kw > 0.

Integration:
  background_scheduler.add_bess_dispatch_job() → wired in startup/events.py
  recommendations table → status updated (executed / failed)
  parasite_decisions table → full audit trail per decision
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

DRY_RUN: bool = os.getenv("BESS_DISPATCH_DRY_RUN", "true").lower() != "false"
CONFIDENCE_THRESHOLD: float = float(os.getenv("BESS_DISPATCH_CONFIDENCE_MIN", "0.75"))
BATCH_SIZE: int = int(os.getenv("BESS_DISPATCH_BATCH_SIZE", "10"))
VALID_RECOMMENDATION_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "auto_executed",
    "expired",
    "executed",
    "rolled_back",
    "failed",
}


# ── DB helpers (psycopg2, sync — safe for APScheduler BackgroundScheduler) ────


def _fetch_pending(site_id: str, conn, limit: int = BATCH_SIZE) -> list[dict[str, Any]]:
    """Return up to `limit` pending bess_dispatch recommendations for site, highest confidence first."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, site_id, target_equipment, action, confidence_score, reason, timestamp
        FROM recommendations
        WHERE action_type = 'bess_dispatch'
          AND status = 'pending'
          AND site_id = %s
        ORDER BY confidence_score DESC NULLS LAST, timestamp ASC
        LIMIT %s
        """,
        (site_id, limit),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
    cur.close()
    return rows


def _mark_recommendation(
    rec_id: str,
    status: str,
    execution_result: dict | None,
    conn,
) -> None:
    normalized_status = status if status in VALID_RECOMMENDATION_STATUSES else "failed"
    if normalized_status != status:
        logger.warning("BESS consumer remapped unsupported recommendation status %s -> %s", status, normalized_status)

    cur = conn.cursor()
    cur.execute(
        """
        UPDATE recommendations
        SET status = %s,
            executed_at = CASE WHEN %s IN ('executed') THEN NOW() ELSE executed_at END,
            execution_result = %s::jsonb
        WHERE id = %s
        """,
        (
            normalized_status,
            normalized_status,
            json.dumps(execution_result) if execution_result else None,
            rec_id,
        ),
    )
    cur.close()


def _write_parasite_decision(
    rec: dict[str, Any],
    decision_type: str,
    tier: str,
    execution_mode: str,
    dispatch_result: dict[str, Any],
    conn,
) -> None:
    """Write audit record to parasite_decisions. execution_mode stored in contributing_factors."""
    action = rec.get("action") or {}
    action_value = action.get("value") or {}

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO parasite_decisions (
            id, recommendation_id, site_id, equipment_code,
            decision_type, tier,
            confidence_score,
            contributing_factors,
            decision_details,
            control_point, target_value,
            executed_at, created_at, updated_at
        ) VALUES (
            %s, %s::uuid, %s, %s,
            %s, %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s, %s,
            %s, NOW(), NOW()
        )
        """,
        (
            str(uuid.uuid4()),
            rec["id"],
            rec["site_id"],
            rec.get("target_equipment", "S002-BESS-B1-001"),
            decision_type,
            tier,
            rec.get("confidence_score"),
            json.dumps(
                {
                    "execution_mode": execution_mode,
                    "dry_run": DRY_RUN,
                    "source": "bess_dispatch_consumer",
                    "phase": "0A",
                }
            ),
            json.dumps(
                {
                    "action": action_value.get("action"),
                    "power_kw": action_value.get("power_kw"),
                    "duration_minutes": action_value.get("duration_minutes"),
                    "reason": rec.get("reason"),
                    "dispatch_result": dispatch_result,
                }
            ),
            "dispatch_command",
            str(action_value.get("action", "")),
            datetime.now(UTC) if decision_type == "tier3_auto_execute" else None,
        ),
    )
    cur.close()


# ── BESS state helper ──────────────────────────────────────────────────────────


def _get_current_bess_state(site_id: str):
    """Return a BESSState from the simulated SOC tracker (Phase 0A source of truth).

    Falls back to conservative defaults if the tracker is unavailable.
    """
    from app.services.bess_dispatch_engine import BESSState

    try:
        from app.services.solar_dispatch_service import get_solar_dispatch_service

        svc = get_solar_dispatch_service()
        soc = svc._simulated_soc.get(site_id, 50.0)
    except Exception:
        soc = 50.0

    return BESSState(
        soc_pct=soc,
        temperature_c=25.0,
        power_kw=0.0,
        grid_frequency_hz=50.0,
    )


# ── Core dispatch logic ────────────────────────────────────────────────────────


def _process_recommendation(
    rec: dict[str, Any],
    conn,
) -> str:
    """Process one recommendation. Returns outcome: executed | simulated | failed."""
    rec_id = str(rec["id"])
    confidence = float(rec.get("confidence_score") or 0.0)
    site_id = rec["site_id"]
    action = rec.get("action") or {}
    action_value = action.get("value") or {}

    bess_action = action_value.get("action", "")  # "charge" | "discharge"
    requested_kw = float(action_value.get("power_kw") or action_value.get("requested_power_kw") or 0.0)
    duration_min = int(action_value.get("duration_minutes") or 15)

    # 1. Confidence gate
    if confidence < CONFIDENCE_THRESHOLD:
        reason = f"confidence {confidence:.2f} < threshold {CONFIDENCE_THRESHOLD}"
        logger.debug("DEFER bess rec %s: %s", rec_id, reason)
        _write_parasite_decision(
            rec,
            "tier1_advisory",
            "tier1",
            "deferred",
            {"reason": reason},
            conn,
        )
        _mark_recommendation(rec_id, "failed", {"reason": reason, "failure_type": "confidence_below_threshold"}, conn)
        return "failed"

    # 2. Validate action type
    if bess_action not in ("charge", "discharge"):
        reason = f"invalid action '{bess_action}'"
        logger.warning("SKIP bess rec %s: %s", rec_id, reason)
        _mark_recommendation(rec_id, "failed", {"reason": reason}, conn)
        return "failed"

    # 3. Dry-run path
    if DRY_RUN:
        logger.info(
            "[DRY RUN] BESS %s → %s %.0f kW for %d min | conf=%.2f | rec=%s",
            site_id,
            bess_action,
            requested_kw,
            duration_min,
            confidence,
            rec_id,
        )
        dispatch_result = {
            "dry_run": True,
            "action": bess_action,
            "power_kw": requested_kw,
            "duration_minutes": duration_min,
        }
        _write_parasite_decision(
            rec,
            "tier3_auto_execute",
            "tier3",
            "simulated",
            dispatch_result,
            conn,
        )
        _mark_recommendation(rec_id, "executed", dispatch_result, conn)
        return "simulated"

    # 4. Live dispatch: re-validate constraints with current state
    try:
        from app.services.bess_dispatch_engine import get_bess_dispatch_engine

        bess_state = _get_current_bess_state(site_id)
        engine = get_bess_dispatch_engine()
        cmd = engine.execute_dispatch(
            site_id=site_id,
            action=bess_action,
            requested_power_kw=requested_kw,
            bess_state=bess_state,
            duration_minutes=duration_min,
            reason=rec.get("reason", "consumer_dispatch"),
        )

        if not cmd.success or cmd.actual_power_kw <= 0:
            reason = cmd.error_message or "constraint blocked dispatch (actual_power_kw=0)"
            logger.warning("DEFERRED bess rec %s after constraint: %s", rec_id, reason)
            _write_parasite_decision(
                rec,
                "tier2_supervised",
                "tier2",
                "blocked",
                {"reason": reason, "constraints": [c.to_dict() for c in cmd.constraints_applied]},
                conn,
            )
            _mark_recommendation(
                rec_id,
                "failed",
                {"reason": reason, "failure_type": "constraint_blocked_dispatch"},
                conn,
            )
            return "failed"

        dispatch_result = cmd.to_dict()
        logger.info(
            "DISPATCHED bess %s → %s %.0f kW (requested %.0f) for %d min | conf=%.2f",
            site_id,
            bess_action,
            cmd.actual_power_kw,
            requested_kw,
            duration_min,
            confidence,
        )
        _write_parasite_decision(
            rec,
            "tier3_auto_execute",
            "tier3",
            "live",
            dispatch_result,
            conn,
        )
        _mark_recommendation(rec_id, "executed", dispatch_result, conn)
        return "executed"

    except Exception as exc:
        logger.error("FAILED bess rec %s: %s", rec_id, exc, exc_info=True)
        _mark_recommendation(rec_id, "failed", {"error": str(exc)}, conn)
        return "failed"


# ── Entry point (called by scheduler) ─────────────────────────────────────────


def run_bess_dispatch_consumer(site_id: str) -> dict[str, Any]:
    """Single execution cycle for one site. Called by APScheduler (sync context)."""
    import psycopg2

    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55322/postgres")

    summary: dict[str, Any] = {
        "site_id": site_id,
        "processed": 0,
        "simulated": 0,
        "executed": 0,
        "failed": 0,
        "dry_run": DRY_RUN,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False  # Explicit transaction per recommendation

        # Guard: skip sites with no equipment
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM equipment e JOIN sites s ON s.id = e.site_id WHERE s.code = %s", (site_id,))
        count = cur.fetchone()[0]
        cur.close()

        if not count:
            logger.debug("BESS consumer: skipping %s — no equipment records", site_id)
            conn.close()
            return summary

        pending = _fetch_pending(site_id, conn)
        if not pending:
            logger.debug("BESS consumer: no pending dispatches for %s", site_id)
            conn.close()
            return summary

        logger.info(
            "BESS consumer: %d pending for %s (dry_run=%s, threshold=%.2f)",
            len(pending),
            site_id,
            DRY_RUN,
            CONFIDENCE_THRESHOLD,
        )

        for rec in pending:
            try:
                outcome = _process_recommendation(rec, conn)
                conn.commit()
                summary["processed"] += 1
                summary[outcome] = summary.get(outcome, 0) + 1
            except Exception as exc:
                conn.rollback()
                logger.error("BESS consumer: error processing rec %s: %s", rec.get("id"), exc)
                summary["failed"] += 1

        conn.close()

    except Exception as exc:
        logger.error("BESS dispatch consumer failed for %s: %s", site_id, exc, exc_info=True)
        summary["error"] = str(exc)

    if summary["processed"]:
        logger.info("BESS dispatch cycle: %s", summary)

    return summary
