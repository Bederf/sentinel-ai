"""Decision Memory API — exposes decision records, patterns, and statistics.

Phase 145: Decision Memory Layer.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/decisions", tags=["Decision Memory"])


class RecordDecisionRequest(BaseModel):
    event_type: str
    equipment_id: str
    equipment_type: str
    site_id: str
    diagnosis: str
    diagnosis_confidence: float = 0.0
    diagnosis_source: str = "ai_reasoning"
    action_type: str = ""
    action_details: dict = {}
    correlation_id: Optional[str] = None
    recommendation_id: Optional[str] = None
    event_id: Optional[str] = None


class RecordOutcomeRequest(BaseModel):
    outcome: str  # DecisionOutcome value
    outcome_details: Optional[str] = None
    work_order_id: Optional[str] = None


@router.post("/record")
async def record_decision(req: RecordDecisionRequest):
    """Record a new decision."""
    from app.services.decision_memory_service import get_decision_memory_service

    svc = get_decision_memory_service()
    record = await svc.record_decision(
        event_type=req.event_type,
        equipment_id=req.equipment_id,
        equipment_type=req.equipment_type,
        site_id=req.site_id,
        diagnosis=req.diagnosis,
        diagnosis_confidence=req.diagnosis_confidence,
        diagnosis_source=req.diagnosis_source,
        action_type=req.action_type,
        action_details=req.action_details,
        correlation_id=req.correlation_id,
        recommendation_id=req.recommendation_id,
        event_id=req.event_id,
    )
    return record.to_dict()


@router.put("/{record_id}/outcome")
async def record_outcome(record_id: str, req: RecordOutcomeRequest):
    """Record outcome for a decision."""
    from app.models.decision_memory import DecisionOutcome
    from app.services.decision_memory_service import get_decision_memory_service

    svc = get_decision_memory_service()
    try:
        outcome = DecisionOutcome(req.outcome)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid outcome: {req.outcome}")

    record = await svc.record_outcome(
        record_id=record_id,
        outcome=outcome,
        outcome_details=req.outcome_details,
        work_order_id=req.work_order_id,
    )
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return record.to_dict()


@router.get("/history")
async def get_decision_history(
    site_id: Optional[str] = Query(None),
    equipment_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Get decision history with filters."""
    from app.services.decision_memory_service import get_decision_memory_service

    svc = get_decision_memory_service()
    svc._ensure_loaded()

    records = svc._records
    if site_id:
        records = [r for r in records if r.site_id == site_id]
    if equipment_id:
        records = [r for r in records if r.equipment_id == equipment_id]
    if event_type:
        records = [r for r in records if r.event_type == event_type]

    # Most recent first
    records = sorted(records, key=lambda r: r.created_at, reverse=True)[:limit]
    return {"records": [r.to_dict() for r in records]}


@router.get("/patterns")
async def list_patterns(min_confidence: float = Query(0.0, ge=0.0, le=1.0)):
    """Get learned patterns."""
    from app.services.decision_memory_service import get_decision_memory_service

    svc = get_decision_memory_service()
    svc._ensure_loaded()

    patterns = [p for p in svc._patterns if p.diagnosis_confidence >= min_confidence]
    patterns.sort(key=lambda p: p.success_rate, reverse=True)
    return {"patterns": [p.to_dict() for p in patterns]}


@router.get("/patterns/match")
async def match_patterns(
    event_type: str = Query(...),
    equipment_type: str = Query(...),
):
    """Find patterns matching event_type + equipment_type."""
    from app.services.decision_memory_service import get_decision_memory_service

    svc = get_decision_memory_service()
    result = await svc.get_active_events_with_history(event_type, equipment_type)
    return result


@router.get("/recommend")
async def get_recommendation(
    event_type: str = Query(...),
    equipment_type: str = Query(...),
):
    """Get recommended action for an event based on learned patterns."""
    from app.services.decision_memory_service import get_decision_memory_service

    svc = get_decision_memory_service()
    pattern = await svc.get_recommended_action(event_type, equipment_type)
    if not pattern:
        return {"recommendation": None, "message": "No learned pattern for this combination"}
    return {
        "recommendation": pattern.to_dict(),
        "message": f"Based on {pattern.total_occurrences} occurrences ({pattern.success_rate:.0%} success rate)",
    }


@router.get("/stats")
async def get_stats(site_id: Optional[str] = Query(None)):
    """Get decision memory statistics."""
    from app.services.decision_memory_service import get_decision_memory_service

    svc = get_decision_memory_service()
    return await svc.get_decision_stats(site_id)


@router.get("/{record_id}")
async def get_record(record_id: str):
    """Get a specific decision record."""
    from app.services.decision_memory_service import get_decision_memory_service

    svc = get_decision_memory_service()
    svc._ensure_loaded()
    record = svc._find_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return record.to_dict()
