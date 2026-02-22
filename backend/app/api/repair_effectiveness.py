"""
Repair Effectiveness API Endpoints

REST API for post-repair validation, effectiveness scoring,
equipment health recalculation, repair history, follow-up scheduling,
cost-benefit analysis, and escalation tracking.

Phase 57: Repair Effectiveness
Plan 01: Core service and API endpoints (5 endpoints)
Plan 03: Follow-up scheduling and cost-benefit (3 endpoints)

Endpoints:
- POST /api/repair-effectiveness/validate - Validate repair effectiveness
- POST /api/repair-effectiveness/record-outcome - Record repair outcome
- GET  /api/repair-effectiveness/health/{equipment_id} - Equipment health score
- GET  /api/repair-effectiveness/history/{equipment_id} - Repair history
- GET  /api/repair-effectiveness/summary - Fleet-wide summary
- GET  /api/repair-effectiveness/followups - Pending follow-up tasks
- GET  /api/repair-effectiveness/cost-benefit/{work_order_id} - Cost-benefit analysis
- GET  /api/repair-effectiveness/escalations/{equipment_id} - Escalation status
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from app.models.repair_effectiveness import (
    RepairEffectivenessRequest,
    RepairOutcome,
    EffectivenessScore,
    HealthScoreUpdate,
    RepairHistoryEntry,
)
from app.services.repair_effectiveness_service import get_repair_effectiveness_service
from app.services.followup_scheduler import (
    get_followup_scheduler,
    FollowupTask,
    CostBenefitAnalysis,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/repair-effectiveness", tags=["repair-effectiveness"])


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/validate", response_model=EffectivenessScore)
async def validate_repair_effectiveness(
    request: RepairEffectivenessRequest,
) -> EffectivenessScore:
    """
    Validate repair effectiveness by comparing pre/post repair measurements.

    Compares pre-repair baseline to post-repair readings (or current BMS data)
    and calculates an effectiveness score (0-100).

    Returns element-level improvements and overall health score change.
    """
    try:
        service = get_repair_effectiveness_service()

        result = await service.validate_repair(
            equipment_id=request.equipment_id,
            work_order_id=request.work_order_id,
            post_readings=request.post_repair_readings,
        )

        logger.info(
            f"Repair validation: {request.equipment_id}, WO {request.work_order_id}, score={result.effectiveness_score}"
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error validating repair effectiveness: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/record-outcome")
async def record_repair_outcome(outcome: RepairOutcome):
    """
    Record repair outcome metadata before validation.

    Stores repair details (technician, parts, cost, etc.) for later
    correlation with effectiveness scores.
    """
    try:
        service = get_repair_effectiveness_service()

        await service.record_repair_outcome(outcome)

        return {"status": "recorded", "work_order_id": outcome.work_order_id, "equipment_id": outcome.equipment_id}

    except Exception as e:
        logger.error(f"Error recording repair outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/{equipment_id}", response_model=HealthScoreUpdate)
async def get_equipment_health(equipment_id: str) -> HealthScoreUpdate:
    """
    Get current equipment health score.

    Calculates health from element trend directions:
    - stable: 100, improving: 90, degrading: 70, rapid_degrading: 30

    Returns weighted average as overall health score.
    """
    try:
        service = get_repair_effectiveness_service()

        result = await service.get_equipment_health_score(equipment_id)

        return result

    except Exception as e:
        logger.error(f"Error getting health score for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{equipment_id}", response_model=List[RepairHistoryEntry])
async def get_repair_history(equipment_id: str) -> List[RepairHistoryEntry]:
    """
    Get repair history for equipment.

    Returns all effectiveness scores for the equipment, sorted by
    date (newest first). Includes cost and fault type from repair outcomes.
    """
    try:
        service = get_repair_effectiveness_service()

        history = await service.get_repair_history(equipment_id)

        return history

    except Exception as e:
        logger.error(f"Error getting repair history for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_effectiveness_summary():
    """
    Get fleet-wide effectiveness summary.

    Returns aggregate statistics across all repairs:
    - total_repairs: Number of validated repairs
    - avg_effectiveness: Average effectiveness score
    - success_rate: Percentage of successful repairs
    - total_cost: Total repair costs (ZAR)
    - repairs_by_type: Breakdown by repair type
    """
    try:
        service = get_repair_effectiveness_service()

        summary = await service.get_effectiveness_summary()

        return summary

    except Exception as e:
        logger.error(f"Error getting effectiveness summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Follow-up & Cost-Benefit Endpoints (Phase 57, Plan 03)
# ============================================================================


@router.get("/followups", response_model=List[FollowupTask])
async def get_followups(equipment_id: Optional[str] = None, status: Optional[str] = None) -> List[FollowupTask]:
    """
    Get pending follow-up tasks.

    Optionally filter by equipment_id and status (scheduled/completed/cancelled).
    Returns tasks sorted by scheduled date.
    """
    try:
        scheduler = get_followup_scheduler()
        return scheduler.get_pending_followups(equipment_id=equipment_id, status=status)
    except Exception as e:
        logger.error(f"Error getting followups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost-benefit/{work_order_id}", response_model=CostBenefitAnalysis)
async def get_cost_benefit(work_order_id: str) -> CostBenefitAnalysis:
    """
    Get cost-benefit analysis for a specific repair.

    Returns ROI calculation with ZAR figures including estimated failure cost,
    cost avoidance, and whether the repair was cost-effective.
    """
    try:
        scheduler = get_followup_scheduler()
        analyses = scheduler.get_cost_analyses()

        for analysis in analyses:
            if analysis.work_order_id == work_order_id:
                return analysis

        raise HTTPException(status_code=404, detail=f"No cost-benefit analysis found for work order {work_order_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cost-benefit for {work_order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/escalations/{equipment_id}")
async def get_escalation_status(equipment_id: str):
    """
    Check escalation status for equipment.

    Returns escalation record with level (1-3) and recommended action,
    or a no-escalation message if equipment has no failed repairs.
    """
    try:
        scheduler = get_followup_scheduler()
        escalation = scheduler.check_escalation(equipment_id)

        if escalation is None:
            return {"escalation_level": 0, "message": "No escalation needed", "equipment_id": equipment_id}

        return escalation
    except Exception as e:
        logger.error(f"Error checking escalation for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
