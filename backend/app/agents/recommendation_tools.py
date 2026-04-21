"""Recommendation Agent Tool Functions
======================================
Thin wrappers around existing BMS services that the recommendation
agent graph nodes call. No new business logic — each function
delegates to one or more existing services.

LLM usage: Zero. All functions are pure Python service calls.
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _candidate_site_ids(site_id: str) -> list[str]:
    """Return normalized site-id variants for cross-service compatibility."""
    if not site_id:
        return []

    sid = site_id.strip()
    if not sid:
        return []

    candidates = [sid]
    lower = sid.lower()

    if lower.startswith("site-"):
        suffix = sid.split("-", 1)[1] if "-" in sid else ""
        if suffix.isdigit():
            candidates.append(f"S{suffix}")
    elif sid.startswith("S") and sid[1:].isdigit():
        candidates.append(f"site-{sid[1:]}")

    # Preserve order, remove duplicates
    deduped: list[str] = []
    for item in candidates:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _site_id_from_equipment_code(equipment_code: str) -> str:
    """Extract site prefix from equipment code (e.g., S002-FCU-201 -> S002)."""
    if not equipment_code:
        return ""
    return equipment_code.split("-")[0].strip()


def _is_control_module_active(site_id: str) -> bool:
    """Check if any control add-on is active across known site-id variants."""
    try:
        from app.models.module_registry import ModuleType
        from app.services.module_registry_service import module_registry

        control_types = [
            ModuleType.HVAC_CONTROL,
            ModuleType.ENERGY_CONTROL,
            ModuleType.LIGHTING_CONTROL,
            ModuleType.SOLAR_CONTROL,
        ]
        for candidate in _candidate_site_ids(site_id):
            for ct in control_types:
                if module_registry.is_module_active(candidate, ct):
                    return True
    except Exception as e:
        logger.debug("Control-module check failed for %s: %s", site_id, e)
    return False


async def _get_recommendation_by_id(recommendation_id: str) -> Any | None:
    """Load recommendation model from repository."""
    from app.database.repositories import get_recommendation_repository

    repo = get_recommendation_repository()
    try:
        # Repository implementations vary between `get` and `get_by_id`.
        if hasattr(repo, "get"):
            rec = await repo.get(recommendation_id)
            if rec:
                return rec
        if hasattr(repo, "get_by_id"):
            return await repo.get_by_id(recommendation_id)
    except Exception as e:
        logger.warning("Failed to load recommendation %s: %s", recommendation_id, e)
    return None


async def get_pending_recommendations(site_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch pending recommendations for a site.

    Wraps RecommendationService.get_pending_recommendations().

    Args:
        site_id: Building identifier (e.g., "S002")
        limit: Maximum number to return

    Returns:
        List of recommendation dicts (via Recommendation.to_dict())
    """
    from app.services.recommendation_service import get_recommendation_service

    service = get_recommendation_service()
    recs = await service.get_pending_recommendations(site_id, limit=limit)
    return [r.to_dict() for r in recs]


async def check_equipment_health(equipment_code: str) -> dict[str, Any]:
    """Check current health score for equipment.

    Args:
        equipment_code: Equipment code (e.g., "S002-FCU-201")

    Returns:
        Dict with health_score (0-100), is_healthy (bool), details
    """
    # Health simulation service removed — live telemetry drives health scoring
    # via the ML pipeline. Return default healthy until health score is
    # available from the ML service.
    return {"health_score": 100, "is_healthy": True, "details": {}}


async def check_maintenance_calendar(equipment_code: str) -> dict[str, Any]:
    """Check if there's an open work order for this equipment.

    Wraps WorkOrderRepository to detect schedule conflicts.

    Args:
        equipment_code: Equipment code (e.g., "S002-FCU-201")

    Returns:
        Dict with has_conflict (bool), work_orders (list of open WOs)
    """
    try:
        from app.database.repositories.work_order_repository import (
            get_work_order_repository,
        )

        repo = get_work_order_repository()
        open_wos = await repo.get_open_work_orders_for_equipment(equipment_code)

        if open_wos:
            return {
                "has_conflict": True,
                "work_orders": open_wos,
                "reason": f"{len(open_wos)} open work order(s) on {equipment_code}",
            }
    except Exception as e:
        logger.warning(f"Failed to check maintenance calendar for {equipment_code}: {e}")

    return {"has_conflict": False, "work_orders": [], "reason": ""}


async def estimate_cost_impact(recommendation: dict[str, Any]) -> dict[str, Any]:
    """Estimate the cost/energy/comfort impact of a recommendation.

    Uses expected_impact from the recommendation and enriches with
    tariff rates from EnergyCostService when available.

    Args:
        recommendation: Recommendation dict with expected_impact

    Returns:
        Dict with cost_zar, energy_kwh, comfort_delta, risk
    """
    expected = recommendation.get("expected_impact", {})

    # Start with what the recommendation already provides
    impact = {
        "cost_zar": expected.get("cost_zar", 0.0),
        "energy_kwh": expected.get("energy_kwh", 0.0),
        "comfort_delta": expected.get("comfort_delta", 0.0),
        "risk": recommendation.get("risk_level", "medium"),
    }

    # Enrich with tariff-based cost estimate if energy impact is known
    energy_kwh = impact["energy_kwh"]
    if energy_kwh and not impact["cost_zar"]:
        try:
            # Use the standard commercial rate (R5/kWh) for quick estimate
            impact["cost_zar"] = round(abs(energy_kwh) * 5.0, 2)
        except Exception as e:
            logger.debug(f"Could not enrich cost impact: {e}")

    return impact


async def cross_reference_similar_faults(equipment_code: str, fault_type: str) -> list[dict[str, Any]]:
    """Find similar past faults for the same equipment or type.

    Wraps recommendation history to find patterns.

    Args:
        equipment_code: Equipment code
        fault_type: Type of fault/action

    Returns:
        List of similar past recommendation dicts
    """
    try:
        from app.services.recommendation_service import get_recommendation_service

        service = get_recommendation_service()
        # Extract site_id from equipment code (e.g., "S002-FCU-201" -> "S002")
        parts = equipment_code.split("-")
        site_id = parts[0] if parts else ""

        history = await service.get_history(
            site_id=site_id,
            status_filter=None,
            limit=20,
        )

        # Filter for similar equipment type or action type
        equipment_type = parts[1] if len(parts) >= 2 else ""
        similar = []
        for rec in history:
            rec_dict = rec.to_dict()
            rec_equipment = rec_dict.get("target_equipment", "")
            rec_action = rec_dict.get("action_type", "")

            # Match on same equipment OR same equipment type + action type
            if rec_equipment == equipment_code or (
                equipment_type and equipment_type in rec_equipment and rec_action == fault_type
            ):
                similar.append(rec_dict)

        return similar[:5]  # Limit to 5 most recent

    except Exception as e:
        logger.warning(f"Failed to cross-reference faults for {equipment_code}: {e}")
        return []


async def route_through_tier_engine(
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    """Route recommendation through PARASITE tier engine.

    Wraps TierRoutingEngine.route_recommendation().

    Args:
        recommendation: Recommendation dict

    Returns:
        TierRoutingResult as dict
    """
    from app.services.tier_routing_engine import get_tier_routing_engine

    # Base package behavior: if control module is inactive, force advisory-only.
    site_id = (recommendation.get("site_id") or "").strip()
    if not site_id:
        site_id = _site_id_from_equipment_code(recommendation.get("target_equipment", ""))

    if site_id and not _is_control_module_active(site_id):
        return {
            "tier": "tier1",
            "action": "advisory",
            "confidence_score": float(recommendation.get("confidence_score", 0.0) or 0.0),
            "threshold_source": "control_module_gate",
            "tier2_threshold": 0.0,
            "tier3_threshold": 1.0,
            "reason": "Control module inactive for site; manual BMS execution required",
            "equipment_type": recommendation.get("target_equipment", ""),
            "risk_level": recommendation.get("risk_level", "medium"),
        }

    engine = get_tier_routing_engine()
    result = await engine.route_recommendation(recommendation)

    return {
        "tier": result.tier,
        "action": result.action,
        "confidence_score": result.confidence_score,
        "threshold_source": result.threshold_source,
        "tier2_threshold": result.tier2_threshold,
        "tier3_threshold": result.tier3_threshold,
        "reason": result.reason,
        "equipment_type": result.equipment_type,
        "risk_level": result.risk_level,
    }


async def execute_tier3_auto(recommendation_id: str, tier_result: dict[str, Any]) -> dict[str, Any]:
    """Auto-execute a Tier 3 recommendation.

    Wraps ApprovalService.auto_execute_recommendation().

    Args:
        recommendation_id: Recommendation ID
        tier_result: TierRoutingResult dict from route_through_tier_engine

    Returns:
        ApprovalResult as dict
    """
    from app.services.approval_service import get_approval_service
    from app.services.tier_routing_engine import TierRoutingResult

    service = get_approval_service()

    rec = await _get_recommendation_by_id(recommendation_id)
    site_id = getattr(rec, "site_id", "") if rec else ""
    if site_id and not _is_control_module_active(site_id):
        return {
            "success": False,
            "recommendation_id": recommendation_id,
            "status": "blocked",
            "executed_at": None,
            "error_message": "Control module inactive for site; manual BMS execution required",
            "cov_verified": False,
            "execution_result": None,
        }

    # Reconstruct TierRoutingResult from dict
    routing_result = TierRoutingResult(
        tier=tier_result["tier"],
        action=tier_result["action"],
        confidence_score=tier_result["confidence_score"],
        threshold_source=tier_result["threshold_source"],
        tier2_threshold=tier_result["tier2_threshold"],
        tier3_threshold=tier_result["tier3_threshold"],
        reason=tier_result["reason"],
        equipment_type=tier_result["equipment_type"],
        risk_level=tier_result["risk_level"],
    )

    result = await service.auto_execute_recommendation(
        recommendation_id=recommendation_id,
        routing_result=routing_result,
    )

    return {
        "success": result.success,
        "recommendation_id": result.recommendation_id,
        "status": result.status,
        "executed_at": result.executed_at.isoformat() if result.executed_at else None,
        "error_message": result.error_message,
        "cov_verified": result.cov_verified,
        "execution_result": result.execution_result,
    }


async def execute_approved_recommendation(
    recommendation_id: str, approved_by: str, notes: str | None = None
) -> dict[str, Any]:
    """Execute an approved (Tier 2) recommendation.

    Wraps ApprovalService.execute_approval().

    Args:
        recommendation_id: Recommendation ID
        approved_by: User/technician who approved
        notes: Optional approval notes

    Returns:
        ApprovalResult as dict
    """
    from app.services.approval_service import get_approval_service

    service = get_approval_service()

    rec = await _get_recommendation_by_id(recommendation_id)
    site_id = getattr(rec, "site_id", "") if rec else ""
    if site_id and not _is_control_module_active(site_id):
        return {
            "success": False,
            "recommendation_id": recommendation_id,
            "status": "blocked",
            "executed_at": None,
            "error_message": "Control module inactive for site; manual BMS execution required",
            "cov_verified": False,
            "execution_result": None,
        }
    result = await service.execute_approval(
        recommendation_id=recommendation_id,
        approved_by=approved_by,
        approval_notes=notes,
    )

    return {
        "success": result.success,
        "recommendation_id": result.recommendation_id,
        "status": result.status,
        "executed_at": result.executed_at.isoformat() if result.executed_at else None,
        "error_message": result.error_message,
        "cov_verified": result.cov_verified,
        "execution_result": result.execution_result,
    }


async def reject_recommendation(recommendation_id: str, rejected_by: str, reason: str) -> dict[str, Any]:
    """Reject a Tier 2 recommendation.

    Wraps ApprovalService.reject_approval().

    Args:
        recommendation_id: Recommendation ID
        rejected_by: User/technician who rejected
        reason: Reason for rejection

    Returns:
        ApprovalResult as dict
    """
    from app.services.approval_service import get_approval_service

    service = get_approval_service()
    result = await service.reject_approval(
        recommendation_id=recommendation_id,
        rejected_by=rejected_by,
        reason=reason,
    )

    return {
        "success": result.success,
        "recommendation_id": result.recommendation_id,
        "status": result.status,
        "error_message": result.error_message,
    }


async def submit_feedback_to_model(
    recommendation_id: str,
    equipment_id: str,
    successful: bool,
    outcome_status: str,
    confidence_score: float = 0.0,
) -> bool:
    """Submit recommendation outcome to ML feedback loop.

    Wraps MLFeedbackService.record_module_outcome().

    Args:
        recommendation_id: Recommendation ID
        equipment_id: Equipment code
        successful: Whether outcome was successful
        outcome_status: Status string (e.g., "executed", "rejected")
        confidence_score: Confidence score for tracking

    Returns:
        True if feedback recorded successfully
    """
    try:
        from app.services.ml_feedback_service import get_ml_feedback_service

        ml_feedback = get_ml_feedback_service()

        # Extract equipment type from code for module inference
        parts = equipment_id.split("-") if equipment_id else []
        equipment_type = parts[1].lower() if len(parts) >= 2 else "control"

        # Map equipment type to module type
        type_to_module = {
            "chiller": "hvac",
            "ahu": "hvac",
            "fcu": "hvac",
            "vav": "hvac",
            "split": "hvac",
            "ct": "hvac",
            "crac": "hvac",
            "dali": "lighting",
            "lum": "lighting",
            "gen": "energy",
            "ups": "energy",
            "tx": "energy",
        }
        module_type = type_to_module.get(equipment_type, "control")

        # Extract/normalize site_id for module eligibility checks.
        raw_site_id = parts[0] if parts else ""
        site_id = raw_site_id
        for candidate in _candidate_site_ids(raw_site_id):
            site_id = candidate
            break

        ml_feedback.record_module_outcome(
            site_id=site_id,
            module_type=module_type,
            recommendation_id=recommendation_id,
            action_type=outcome_status,
            successful=successful,
            outcome_status=outcome_status,
            confidence_score=confidence_score,
            equipment_id=equipment_id,
            metadata={"source": "recommendation_agent"},
        )
        return True

    except Exception as e:
        logger.warning(f"Failed to submit ML feedback for {recommendation_id}: {e}")
        return False


def check_recommendation_freshness(recommendation: dict[str, Any], max_age_minutes: int = 30) -> dict[str, Any]:
    """Check if a recommendation is still fresh (not stale/expired).

    Pure function — no service dependency.

    Args:
        recommendation: Recommendation dict with "timestamp"
        max_age_minutes: Maximum age in minutes before considering stale

    Returns:
        Dict with is_fresh (bool), age_minutes (float), reason
    """
    timestamp_str = recommendation.get("timestamp", "")
    if not timestamp_str:
        return {"is_fresh": False, "age_minutes": 999, "reason": "No timestamp"}

    try:
        rec_time = datetime.fromisoformat(timestamp_str) if isinstance(timestamp_str, str) else timestamp_str

        age = datetime.utcnow() - rec_time
        age_minutes = age.total_seconds() / 60

        if age_minutes > max_age_minutes:
            return {
                "is_fresh": False,
                "age_minutes": round(age_minutes, 1),
                "reason": f"Recommendation is {round(age_minutes)}min old (max {max_age_minutes}min)",
            }

        return {
            "is_fresh": True,
            "age_minutes": round(age_minutes, 1),
            "reason": "Within freshness window",
        }

    except Exception as e:
        logger.warning(f"Failed to parse recommendation timestamp: {e}")
        return {"is_fresh": False, "age_minutes": 999, "reason": f"Parse error: {e}"}


async def update_recommendation_status(recommendation_id: str, status: str) -> bool:
    """Update recommendation status in the repository.

    Args:
        recommendation_id: Recommendation ID
        status: New status value (e.g., "expired")

    Returns:
        True if updated successfully
    """
    try:
        from app.database.repositories import get_recommendation_repository
        from app.models.recommendation import RecommendationStatus

        repo = get_recommendation_repository()
        rec = await repo.get(recommendation_id)
        if rec:
            rec.status = RecommendationStatus(status)
            await repo.update(recommendation_id, rec)
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed to update recommendation {recommendation_id} status: {e}")
        return False
