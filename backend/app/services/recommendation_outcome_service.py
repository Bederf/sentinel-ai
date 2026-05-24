"""Recommendation outcome verification — closes the AI feedback loop.

After a recommendation is executed, waits for a settling period (default 30 min),
then compares actual sensor readings against predicted impact. Records whether
the recommendation achieved its goal and feeds the result back into:
  1. The recommendation record (outcome_validated, outcome_notes)
  2. Decision Memory Service (diagnosis -> action -> outcome triple)
  3. ML Feedback Service (module success rates for prompt injection)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# How long to wait after execution before verifying outcome
SETTLING_MINUTES = 30

# Maximum age of recommendations to verify (avoid processing ancient records)
MAX_AGE_HOURS = 24


async def validate_outcome(rec_id: str) -> dict[str, Any] | None:
    """Validate a single recommendation's outcome by comparing sensor data.

    Reads the recommendation's target equipment + action, queries current
    telemetry, and determines if the action achieved its intended effect.

    Returns dict with validation results, or None if unable to verify.
    """
    from app.database.repositories.recommendation_repository import (
        get_recommendation_repository,
    )

    repo = get_recommendation_repository()
    rec = await repo.get_by_id(rec_id)

    if not rec:
        logger.warning("Outcome validation: recommendation %s not found", rec_id)
        return None

    if rec.outcome_validated is not None:
        logger.debug("Outcome validation: %s already validated", rec_id)
        return None

    # Extract what was recommended
    action = rec.action or {}
    target_point = action.get("point", action.get("point_name", ""))
    recommended_value = action.get("value", action.get("recommended_value"))
    equipment_id = rec.target_equipment

    if not equipment_id or recommended_value is None:
        notes = "Cannot verify: missing equipment_id or recommended_value"
        await _mark_outcome(repo, rec, validated=None, notes=notes)
        return {"rec_id": rec_id, "outcome": None, "notes": notes}

    # Try to get current sensor reading for this equipment
    current_reading = await _get_current_reading(equipment_id, target_point)

    if current_reading is None:
        notes = f"Cannot verify: no telemetry available for {equipment_id}/{target_point}"
        await _mark_outcome(repo, rec, validated=None, notes=notes)
        return {"rec_id": rec_id, "outcome": None, "notes": notes}

    # Determine success based on direction of change
    success, notes = _evaluate_outcome(
        action_type=rec.action_type,
        target_point=target_point,
        recommended_value=recommended_value,
        current_reading=current_reading,
        equipment_id=equipment_id,
    )

    # Write result to recommendation record
    await _mark_outcome(repo, rec, validated=success, notes=notes)

    # Feed back into Decision Memory Service
    await _record_to_decision_memory(rec, success, notes)

    # Feed back into ML Feedback Service
    _record_to_ml_feedback(rec, success, notes)

    logger.info(
        "Outcome verified for %s: %s — %s",
        rec_id,
        "SUCCESS" if success else "FAILURE",
        notes,
    )

    return {
        "rec_id": rec_id,
        "equipment_id": equipment_id,
        "outcome": success,
        "notes": notes,
        "current_reading": current_reading,
        "recommended_value": recommended_value,
    }


async def process_single_verification(recommendation_id: str) -> dict[str, Any] | None:
    """Verify outcome for a single recommendation — called 30 minutes after WO closure."""
    rec = await validate_outcome(recommendation_id)
    return rec


async def process_pending_verifications() -> list[dict[str, Any]]:
    """Find and verify all recommendations ready for outcome checking.

    Queries for recommendations that are:
      - Status: EXECUTED or AUTO_EXECUTED
      - Executed more than SETTLING_MINUTES ago
      - outcome_validated is NULL (not yet verified)
      - Not older than MAX_AGE_HOURS

    Returns list of verification results.
    """
    from app.core.site_resolver import get_registered_site_ids
    from app.database.repositories.recommendation_repository import (
        get_recommendation_repository,
    )
    from app.models.recommendation import RecommendationStatus

    repo = get_recommendation_repository()
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=SETTLING_MINUTES)
    max_age_cutoff = now - timedelta(hours=MAX_AGE_HOURS)

    results = []

    for site_id in get_registered_site_ids():
        for status in [RecommendationStatus.EXECUTED, RecommendationStatus.AUTO_EXECUTED]:
            try:
                recs = await repo.get_by_status(site_id, status, limit=50)
            except Exception as e:
                logger.debug("Error fetching %s recs for %s: %s", status, site_id, e)
                continue

            for rec in recs:
                # Skip already verified
                if rec.outcome_validated is not None:
                    continue

                # Check timing: must be past settling period but not too old
                exec_time = rec.executed_at
                if not exec_time:
                    continue

                # Normalize to UTC-aware
                if exec_time.tzinfo is None:
                    exec_time = exec_time.replace(tzinfo=UTC)

                if exec_time > cutoff:
                    continue  # Too recent, not settled yet
                if exec_time < max_age_cutoff:
                    # Too old — mark as unable to verify
                    hours_ago = (now - exec_time).total_seconds() / 3600
                    await _mark_outcome(
                        repo,
                        rec,
                        validated=None,
                        notes=f"Skipped: executed {hours_ago:.0f}h ago (max {MAX_AGE_HOURS}h)",
                    )
                    continue

                try:
                    result = await validate_outcome(rec.id)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error("Outcome verification failed for %s: %s", rec.id, e)

    logger.info(
        "Outcome verification complete: %d recommendations verified (%d success, %d failure, %d inconclusive)",
        len(results),
        sum(1 for r in results if r.get("outcome") is True),
        sum(1 for r in results if r.get("outcome") is False),
        sum(1 for r in results if r.get("outcome") is None),
    )
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _evaluate_outcome(
    action_type: str,
    target_point: str,
    recommended_value: Any,
    current_reading: float,
    equipment_id: str,
) -> tuple[bool, str]:
    """Compare current reading against recommended value to determine success.

    Returns (success: bool, notes: str).
    """
    try:
        rec_val = float(recommended_value)
    except (TypeError, ValueError):
        return False, f"Cannot evaluate: recommended_value '{recommended_value}' is not numeric"

    delta = abs(current_reading - rec_val)

    # Determine acceptable tolerance based on action type
    if "setpoint" in action_type.lower() or "setpoint" in target_point.lower():
        # Temperature setpoints: within 1.5 degrees is success
        tolerance = 1.5
        if delta <= tolerance:
            return True, (
                f"Setpoint achieved: reading={current_reading:.1f}, "
                f"target={rec_val:.1f}, delta={delta:.1f} (within {tolerance} tolerance)"
            )
        else:
            return False, (
                f"Setpoint NOT achieved: reading={current_reading:.1f}, "
                f"target={rec_val:.1f}, delta={delta:.1f} (exceeds {tolerance} tolerance)"
            )

    elif "brightness" in target_point.lower() or "dim" in target_point.lower():
        # Lighting: within 15% of target
        tolerance_pct = 0.15
        success = current_reading < 5 if rec_val == 0 else delta / rec_val <= tolerance_pct
        return success, (
            f"Lighting: reading={current_reading:.0f}, target={rec_val:.0f}, "
            f"delta={delta:.0f} ({'within' if success else 'exceeds'} 15% tolerance)"
        )

    else:
        # Generic: within 10% of recommended value
        success = abs(current_reading) < 1 if rec_val == 0 else delta / abs(rec_val) <= 0.1
        return success, (
            f"Measured={current_reading:.2f}, target={rec_val:.2f}, "
            f"delta={delta:.2f} ({'within' if success else 'exceeds'} 10% tolerance)"
        )


async def _get_current_reading(equipment_id: str, point_name: str) -> float | None:
    """Query current telemetry value for an equipment point.

    Tries device manager first, falls back to Supabase telemetry table.
    """
    # Try device manager (in-memory latest values)
    try:
        from app.services.device_manager import get_device_manager

        dm = await get_device_manager()
        device = await dm.get_device(equipment_id)
        if device and hasattr(device, "points"):
            points = device.points or {}
            if point_name in points:
                val = points[point_name]
                if isinstance(val, (int, float)):
                    return float(val)
                elif isinstance(val, dict):
                    v = val.get("value", val.get("presentValue"))
                    if isinstance(v, (int, float)):
                        return float(v)
    except Exception as e:
        logger.debug("Device manager read failed for %s/%s: %s", equipment_id, point_name, e)

    # Fallback: query Supabase telemetry
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        resp = (
            client.table("telemetry")
            .select("value")
            .eq("equipment_id", equipment_id)
            .eq("point_name", point_name)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            val = resp.data[0].get("value")
            if isinstance(val, (int, float)):
                return float(val)
    except Exception as e:
        logger.debug("Supabase telemetry query failed for %s/%s: %s", equipment_id, point_name, e)

    return None


async def _mark_outcome(
    repo: Any,
    rec: Any,
    validated: bool | None,
    notes: str,
) -> None:
    """Update the recommendation record with outcome validation results."""
    rec.outcome_validated = validated
    rec.outcome_notes = notes
    rec.outcome_validated_at = datetime.now(UTC)
    try:
        await repo.update(rec.id, rec)
    except Exception as e:
        logger.error("Failed to save outcome for %s: %s", rec.id, e)


async def _record_to_decision_memory(rec: Any, success: bool, notes: str) -> None:
    """Feed outcome back into Decision Memory Service for pattern learning."""
    try:
        from app.models.decision_memory import DecisionOutcome
        from app.services.decision_memory_service import get_decision_memory_service

        dms = get_decision_memory_service()

        # Record the decision if not already recorded
        decision = await dms.record_decision(
            event_type=rec.action_type or "optimization",
            equipment_id=rec.target_equipment or "",
            equipment_type=_extract_equipment_type(rec.target_equipment),
            site_id=rec.site_id or "",
            diagnosis=rec.reason or "",
            diagnosis_confidence=rec.confidence_score or 0.5,
            diagnosis_source="ai_optimizer",
            action_type=rec.action_type or "",
            action_details=rec.action or {},
            recommendation_id=rec.id,
        )

        # Record the outcome
        outcome = DecisionOutcome.RESOLVED if success else DecisionOutcome.FAILED
        await dms.record_outcome(
            record_id=decision.record_id,
            outcome=outcome,
            outcome_details=notes,
        )

    except Exception as e:
        logger.debug("Failed to record to decision memory: %s", e)


def _record_to_ml_feedback(rec: Any, success: bool, notes: str) -> None:
    """Feed outcome back into ML Feedback Service for success rate tracking."""
    try:
        from app.services.ml_feedback_service import get_ml_feedback_service

        ml_fb = get_ml_feedback_service()
        module_type = _extract_module_type(rec.action_type, rec.target_equipment)

        ml_fb.record_module_outcome(
            site_id=rec.site_id or "",
            module_type=module_type,
            recommendation_id=rec.id,
            action_type=rec.action_type or "",
            successful=success,
            outcome_status="verified",
            predicted_impact=rec.expected_impact or {},
            actual_impact={"outcome_notes": notes, "outcome_validated": success},
            confidence_score=rec.confidence_score,
            equipment_id=rec.target_equipment,
        )

    except Exception as e:
        logger.debug("Failed to record to ML feedback: %s", e)


def _extract_equipment_type(equipment_id: str | None) -> str:
    """Extract equipment type from ID like S002-FCU-101 -> fcu."""
    if not equipment_id:
        return "unknown"
    parts = equipment_id.split("-")
    if len(parts) >= 2:
        return parts[1].lower()
    return "unknown"


def _extract_module_type(action_type: str | None, equipment_id: str | None) -> str:
    """Infer module type from action_type or equipment_id."""
    action = (action_type or "").lower()
    eq_type = _extract_equipment_type(equipment_id)

    if any(k in action for k in ("setpoint", "cooling", "heating", "hvac", "damper")):
        return "hvac"
    if any(k in action for k in ("brightness", "dim", "lighting", "dali")):
        return "lighting"
    if any(k in action for k in ("bess", "battery", "charge", "discharge", "soc")):
        return "bess"
    if any(k in action for k in ("solar", "inverter", "curtail")):
        return "solar"
    if any(k in action for k in ("generator", "genset")):
        return "generator"

    # Fall back to equipment type
    type_map = {
        "fcu": "hvac",
        "ahu": "hvac",
        "vav": "hvac",
        "chiller": "hvac",
        "split": "hvac",
        "dali": "lighting",
        "inv": "solar",
        "bess": "bess",
        "gen": "generator",
    }
    return type_map.get(eq_type, eq_type)
