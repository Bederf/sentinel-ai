"""Inspection Recommendations API

Endpoints for analyzing inspection findings and recommending repair actions.
Powered by InspectionAnalyzer service that uses contextual analysis.
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.inspection_analyzer import get_inspection_analyzer
from app.database.supabase_client import get_supabase_client
from app.utils.ai_provenance import get_ml_provenance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/inspections", tags=["inspections"])


class GetRecommendationRequest(BaseModel):
    """Request to get recommendation for inspection work order."""

    work_order_id: str


class CreateRepairWorkOrderRequest(BaseModel):
    """Request to create repair work order from inspection recommendation."""

    work_order_id: str
    equipment_code: str
    recommendation_reason: str
    parts_needed: list = []
    priority: str = "medium"  # low, medium, high


@router.get("/{work_order_id}/recommendation")
async def get_inspection_recommendation(request: Request, work_order_id: str) -> dict:
    """
    Get recommendation after inspection work order is completed.

    Analyzes the inspection findings using contextual analysis to recommend:
    - RESOLVED: Issue was fixed during inspection
    - RECOMMEND_REPAIR: Repair work order should be created
    - MONITOR: Issue is minor, continue monitoring

    **Path Parameters:**
        work_order_id: Inspection work order ID

    **Returns:**
        Recommendation object with decision, reasoning, and confidence score
    """
    client = get_supabase_client()

    # Fetch work order
    wo_result = (
        client.table("work_orders")
        .select("id, equipment_id, status, notes, created_at")
        .eq("id", work_order_id)
        .execute()
    )

    if not wo_result.data:
        raise HTTPException(status_code=404, detail=f"Work order {work_order_id} not found")

    work_order = wo_result.data[0]

    # Verify it's an inspection work order
    if "inspection" not in work_order.get("notes", "").lower():
        logger.warning(f"Work order {work_order_id} is not an inspection WO")

    # Fetch equipment for context
    equipment = (
        client.table("equipment")
        .select("id, code, name, health_score, status")
        .eq("id", work_order["equipment_id"])
        .execute()
    )

    if not equipment.data:
        raise HTTPException(status_code=404, detail="Equipment not found")

    eq = equipment.data[0]

    # Get findings from work order notes
    findings = work_order.get("notes", "") or ""

    # Analyze inspection
    analyzer = get_inspection_analyzer()
    analysis = analyzer.analyze_inspection_completion(
        findings=findings, equipment_code=eq["code"], health_after=eq.get("health_score", 70)
    )

    return {
        "work_order_id": work_order_id,
        "equipment_code": eq["code"],
        "equipment_name": eq.get("name"),
        "current_health": eq.get("health_score"),
        "recommendation": analysis.to_dict(),
        "ai_provenance": get_ml_provenance("inspection-analyzer-v1").model_dump(),
    }


@router.post("/{work_order_id}/create-repair-wo")
async def create_repair_work_order_from_inspection(
    request: Request, work_order_id: str, body: CreateRepairWorkOrderRequest
) -> dict:
    """
    Create a repair/maintenance work order based on inspection recommendation.

    This is called after an inspection is completed and the technician/supervisor
    decides that repair is needed. Pre-fills the repair WO with inspection findings.

    **Path Parameters:**
        work_order_id: Original inspection work order ID

    **Request Body:**
        equipment_code: Equipment code
        recommendation_reason: Why repair is needed (from recommendation)
        parts_needed: List of parts required
        priority: Urgency (low, medium, high)

    **Returns:**
        Created repair work order with ID and details
    """
    import uuid
    from datetime import datetime

    client = get_supabase_client()

    # Fetch original inspection WO for reference
    inspection_wo = client.table("work_orders").select("id").eq("id", work_order_id).execute()

    if not inspection_wo.data:
        raise HTTPException(status_code=404, detail="Inspection WO not found")

    # Get equipment
    equipment = client.table("equipment").select("id, code, name, site_id").eq("code", body.equipment_code).execute()

    if not equipment.data:
        raise HTTPException(status_code=404, detail="Equipment not found")

    eq = equipment.data[0]

    # Get technician for this equipment
    try:
        from app.database.repositories.technician_repository import TechnicianRepository

        tech_repo = TechnicianRepository()
        technician = tech_repo.get_technician_for_equipment_code(body.equipment_code)
        assigned_to = technician.get("id") if technician else None
    except Exception as e:
        logger.warning(f"Failed to assign technician: {e}")
        assigned_to = None

    # Create repair work order
    repair_wo_id = str(uuid.uuid4())
    parts_description = ", ".join(body.parts_needed) if body.parts_needed else "TBD"

    repair_wo_data = {
        "id": repair_wo_id,
        "equipment_id": eq["id"],
        "site_id": eq.get("site_id"),
        "status": "assigned",
        "priority": body.priority,
        "work_order_type": "maintenance",
        "service_type": "repair",
        "title": f"Repair: {eq['name']} (from inspection)",
        "notes": (
            f"Inspection Findings: {body.recommendation_reason}\n\n"
            f"Parts Needed: {parts_description}\n\n"
            f"Original Inspection WO: {work_order_id}"
        ),
        "assigned_to": assigned_to,
        "created_by": "inspection_analyzer",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    # Insert repair work order
    result = client.table("work_orders").insert(repair_wo_data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create repair work order")

    logger.info(f"Created repair WO {repair_wo_id} from inspection WO {work_order_id}")

    # Emit event for real-time update
    try:
        from app.services.event_emitter import get_event_emitter
        import asyncio

        emitter = get_event_emitter()
        asyncio.create_task(
            emitter.emit_work_order_updated(
                work_order_id=repair_wo_id,
                equipment_id=eq["id"],
                equipment_code=body.equipment_code,
                status="assigned",
                work_order_type="maintenance",
                priority=body.priority,
            )
        )
    except Exception as e:
        logger.warning(f"Failed to emit work order event: {e}")

    return {
        "success": True,
        "work_order_id": repair_wo_id,
        "equipment_code": body.equipment_code,
        "status": "assigned",
        "priority": body.priority,
        "parts_needed": body.parts_needed,
        "message": "Repair work order created from inspection findings",
    }
