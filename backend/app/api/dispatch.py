"""Smart Dispatch API - Intelligent dispatch with task bundling.

Phase 59-03: Remote Operations
Provides REST endpoints for dispatch decision-making, task bundling,
technician assignment, site briefing generation, and dispatch tracking.

Endpoints:
  POST /api/dispatch/evaluate              - Evaluate if dispatch needed
  POST /api/dispatch/create                - Create dispatch with bundled tasks
  GET  /api/dispatch/briefing/{dispatch_id} - Get/refresh site briefing
  POST /api/dispatch/{dispatch_id}/check-in - Technician check-in at site
  POST /api/dispatch/{dispatch_id}/complete - Complete dispatch
  GET  /api/dispatch/active                - List active dispatches
  GET  /api/dispatch/technicians           - List technicians with availability
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.smart_dispatch_service import get_smart_dispatch_service

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------------------------------------------------------------- #
#  Request / Response models
# --------------------------------------------------------------------- #


class EvaluateDispatchRequest(BaseModel):
    """Body for POST /api/dispatch/evaluate."""

    equipment_id: str = Field(..., description="Equipment ID to evaluate (v2.0 format, e.g. S002-CHILLER-B1-001)")


class AdditionalTask(BaseModel):
    """An additional task to include in a dispatch."""

    task_id: Optional[str] = None
    task_type: str = Field(default="work_order", description="Task type")
    description: str = Field(..., description="Task description")
    equipment_id: Optional[str] = None
    priority: str = Field(default="medium", description="Priority: critical, high, medium, low")
    estimated_minutes: int = Field(default=30, description="Estimated duration in minutes")


class CreateDispatchRequest(BaseModel):
    """Body for POST /api/dispatch/create."""

    site_id: str = Field(..., description="Target site ID (e.g. site-002)")
    equipment_id: str = Field(..., description="Primary equipment ID triggering dispatch")
    technician_id: Optional[str] = Field(None, description="Technician ID (auto-assigned if omitted)")
    additional_tasks: Optional[List[AdditionalTask]] = Field(None, description="Extra tasks to include")


class CompleteTaskItem(BaseModel):
    """A completed task within a dispatch."""

    task_id: str
    result: str = Field(default="completed", description="Result summary")
    notes: str = Field(default="", description="Technician notes")


class CompleteDispatchRequest(BaseModel):
    """Body for POST /api/dispatch/{dispatch_id}/complete."""

    tasks_completed: Optional[List[CompleteTaskItem]] = Field(None, description="Tasks completed with results")
    overall_notes: str = Field(default="", description="Overall dispatch notes")


# --------------------------------------------------------------------- #
#  Endpoints
# --------------------------------------------------------------------- #


@router.post("/evaluate")
async def evaluate_dispatch(body: EvaluateDispatchRequest):
    """Evaluate whether a technician dispatch is needed for equipment.

    Runs remote diagnostic, checks if issue is remotely resolvable,
    and if dispatch IS needed, bundles nearby tasks at the same site.

    Returns dispatch decision with urgency, bundled tasks, and
    recommended specialization.
    """
    svc = get_smart_dispatch_service()

    try:
        result = await svc.evaluate_dispatch(body.equipment_id)
        return result
    except Exception as exc:
        logger.error(f"Dispatch evaluation error for {body.equipment_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/create")
async def create_dispatch(body: CreateDispatchRequest):
    """Create a dispatch with bundled tasks and assigned technician.

    If technician_id is omitted, auto-assigns the best available
    technician based on specialization and proximity.

    Returns dispatch ID, assigned technician, site briefing, bundled
    tasks, and estimated time.
    """
    svc = get_smart_dispatch_service()

    try:
        additional = None
        if body.additional_tasks:
            additional = [t.model_dump() for t in body.additional_tasks]

        result = await svc.create_dispatch(
            site_id=body.site_id,
            equipment_id=body.equipment_id,
            technician_id=body.technician_id,
            additional_tasks=additional,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Dispatch creation failed"),
            )

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Dispatch creation error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/briefing/{dispatch_id}")
async def get_dispatch_briefing(dispatch_id: str):
    """Get or refresh the site briefing for an active dispatch.

    Returns the full site briefing with current building status,
    task list, floor routing, equipment details, and tools needed.
    """
    svc = get_smart_dispatch_service()

    dispatch = svc._active_dispatches.get(dispatch_id)
    if not dispatch:
        raise HTTPException(status_code=404, detail=f"Dispatch {dispatch_id} not found")

    try:
        briefing = await svc.generate_site_briefing(
            site_id=dispatch["site_id"],
            technician_id=dispatch["technician_id"],
            bundled_tasks=dispatch["tasks"],
        )
        return briefing
    except Exception as exc:
        logger.error(f"Briefing generation error for {dispatch_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{dispatch_id}/check-in")
async def check_in_dispatch(dispatch_id: str, request: Request):
    """Record technician arrival at site.

    Updates dispatch status to in_progress and records check-in time.
    Returns updated task count and confirmation.
    """
    svc = get_smart_dispatch_service()

    # Get technician from dispatch (or header)
    dispatch = svc._active_dispatches.get(dispatch_id)
    if not dispatch:
        raise HTTPException(status_code=404, detail=f"Dispatch {dispatch_id} not found")

    technician_id = request.headers.get("X-User-Id", dispatch["technician_id"])

    result = svc.check_in(dispatch_id, technician_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/{dispatch_id}/complete")
async def complete_dispatch(dispatch_id: str, body: CompleteDispatchRequest):
    """Complete a dispatch and record metrics.

    Marks individual tasks as completed, then closes the dispatch.
    Returns dispatch summary with efficiency metrics (time onsite,
    tasks completed, completion rate).
    """
    svc = get_smart_dispatch_service()

    dispatch = svc._active_dispatches.get(dispatch_id)
    if not dispatch:
        raise HTTPException(status_code=404, detail=f"Dispatch {dispatch_id} not found")

    # Mark individual tasks
    if body.tasks_completed:
        for item in body.tasks_completed:
            svc.complete_task(
                dispatch_id,
                item.task_id,
                {"result": item.result, "notes": item.notes},
            )

    # Complete the dispatch
    result = svc.complete_dispatch(dispatch_id, overall_notes=body.overall_notes)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/active")
async def list_active_dispatches():
    """List all active dispatches with their current status.

    Returns dispatch summaries including technician, site, task count,
    and progress.
    """
    svc = get_smart_dispatch_service()
    return {"dispatches": svc.get_active_dispatches()}


@router.get("/technicians")
async def list_technicians():
    """List all technicians with their current availability.

    Returns technician details including specializations, status,
    current site assignment, and work order count.
    """
    svc = get_smart_dispatch_service()
    return {"technicians": svc.get_technicians()}
