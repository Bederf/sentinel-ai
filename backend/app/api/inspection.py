"""
Inspection API - REST endpoints for routine inspection management

Phase 45: Routine Inspection & Maintenance

Provides endpoints for:
- Inspection schedule management
- Inspection task generation and assignment
- Inspection results capture
- Deficiency tracking
- Calendar and reporting
"""

from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query, Path, status

from app.models.inspection import (
    InspectionSchedule,
    InspectionScheduleCreate,
    InspectionTask,
    InspectionTaskAssignmentRequest,
    InspectionTaskRescheduleRequest,
    InspectionTaskCompleteRequest,
    InspectionResult,
    InspectionResultCreate,
    InspectionDeficiency,
    InspectionDeficiencyCreate,
    InspectionOverviewResponse,
    InspectionTaskStatus,
    DeficiencySeverity,
    InspectionSubmission,
    InspectionScheduleSummary,
)
from app.services.inspection_scheduler import get_inspection_scheduler
from app.services.auth_service import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/inspection", tags=["inspection"])


# ============================================================================
# Inspection Schedule Endpoints
# ============================================================================


@router.post(
    "/schedules",
    response_model=InspectionSchedule,
    status_code=status.HTTP_201_CREATED,
    summary="Create inspection schedule",
    description="Create a recurring inspection schedule for equipment",
)
async def create_inspection_schedule(
    schedule: InspectionScheduleCreate, current_user: User = Depends(get_current_user)
):
    """Create a new inspection schedule."""
    scheduler = get_inspection_scheduler()

    try:
        # Set created_by to current user
        schedule.created_by = current_user.username

        # Calculate next due date
        next_due = scheduler._calculate_next_due_date(schedule)

        schedule_data = schedule.dict()
        schedule_data["next_due_date"] = next_due

        created_schedule = await scheduler.repository.create_inspection_schedule(schedule_data)

        # Generate first task if no last generated date
        await scheduler.generate_inspection_tasks(schedule.equipment_id)

        return created_schedule

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create schedule: {str(e)}"
        )


@router.get(
    "/schedules/{schedule_id}",
    response_model=InspectionSchedule,
    summary="Get inspection schedule",
    description="Get inspection schedule by ID",
)
async def get_inspection_schedule(schedule_id: str, current_user: User = Depends(get_current_user)):
    """Get inspection schedule."""
    scheduler = get_inspection_scheduler()

    schedule = await scheduler.repository.get_inspection_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    return schedule


@router.get(
    "/schedules",
    response_model=List[InspectionSchedule],
    summary="List inspection schedules",
    description="List all active inspection schedules",
)
async def list_inspection_schedules(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    current_user: User = Depends(get_current_user),
):
    """List inspection schedules."""
    scheduler = get_inspection_scheduler()

    schedules = await scheduler.repository.get_active_schedules(equipment_id)
    return schedules


@router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate inspection schedule",
    description="Deactivate an inspection schedule",
)
async def deactivate_inspection_schedule(schedule_id: str, current_user: User = Depends(get_current_user)):
    """Deactivate inspection schedule."""
    scheduler = get_inspection_scheduler()

    try:
        await scheduler.repository.deactivate_schedule(schedule_id)
        return {"message": "Schedule deactivated successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to deactivate schedule: {str(e)}"
        )


# ============================================================================
# Inspection Task Endpoints
# ============================================================================


@router.post(
    "/tasks/generate",
    response_model=Dict[str, Any],
    summary="Generate inspection tasks",
    description="Generate inspection tasks from active schedules",
)
async def generate_inspection_tasks(
    equipment_id: Optional[str] = Query(None, description="Specific equipment (optional)"),
    current_user: User = Depends(get_current_user),
):
    """Generate inspection tasks from schedules."""
    scheduler = get_inspection_scheduler()

    try:
        tasks = await scheduler.generate_inspection_tasks(equipment_id)

        return {
            "success": True,
            "generated_count": len(tasks),
            "equipment_id": equipment_id or "all",
            "tasks": [{"id": t.id, "name": t.task_name} for t in tasks],
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate tasks: {str(e)}"
        )


@router.get(
    "/tasks/{task_id}",
    response_model=InspectionTask,
    summary="Get inspection task",
    description="Get inspection task by ID",
)
async def get_inspection_task(task_id: str, current_user: User = Depends(get_current_user)):
    """Get inspection task."""
    scheduler = get_inspection_scheduler()

    task = await scheduler.repository.get_inspection_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return task


@router.get(
    "/tasks",
    response_model=List[InspectionTask],
    summary="List inspection tasks",
    description="List inspection tasks with optional filters",
)
async def list_inspection_tasks(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    status: Optional[InspectionTaskStatus] = Query(None, description="Filter by status"),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned technician"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    current_user: User = Depends(get_current_user),
):
    """List inspection tasks."""
    scheduler = get_inspection_scheduler()

    if equipment_id and status:
        tasks = await scheduler.repository.get_tasks_by_equipment(equipment_id, status, limit)
    else:
        # Get all tasks (with equipment filter if provided)
        tasks = []
        if equipment_id:
            tasks = await scheduler.repository.get_tasks_by_equipment(equipment_id, limit=limit)
        else:
            # Note: This would need a repository method to get all tasks
            # For now, return empty list
            tasks = []

    return tasks


@router.get(
    "/tasks/due/days/{days_ahead}",
    response_model=List[InspectionTask],
    summary="Get due inspections",
    description="Get inspection tasks due within specified days",
)
async def get_due_inspections(
    days_ahead: int = Path(..., ge=1, le=365, description="Days ahead to check"),
    assigned_to: Optional[str] = Query(None, description="Filter by technician"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    current_user: User = Depends(get_current_user),
):
    """Get due inspections."""
    scheduler = get_inspection_scheduler()

    tasks = await scheduler.get_due_inspections(
        assigned_to=assigned_to, equipment_id=equipment_id, days_ahead=days_ahead
    )
    return tasks


@router.get(
    "/tasks/overdue",
    response_model=List[InspectionTask],
    summary="Get overdue inspections",
    description="Get overdue inspection tasks",
)
async def get_overdue_inspections(
    assigned_to: Optional[str] = Query(None, description="Filter by technician"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    current_user: User = Depends(get_current_user),
):
    """Get overdue inspections."""
    scheduler = get_inspection_scheduler()

    tasks = await scheduler.get_overdue_inspections(assigned_to=assigned_to, equipment_id=equipment_id)
    return tasks


@router.post(
    "/tasks/{task_id}/assign",
    response_model=InspectionTask,
    summary="Assign inspection task",
    description="Assign inspection task to a technician",
)
async def assign_inspection_task(
    task_id: str, assignment: InspectionTaskAssignmentRequest, current_user: User = Depends(get_current_user)
):
    """Assign inspection task."""
    scheduler = get_inspection_scheduler()

    task = await scheduler.update_task_assignment(
        task_id=task_id, assigned_to=assignment.assigned_to, assigned_by=assignment.assigned_by or current_user.username
    )

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return task


@router.post(
    "/tasks/{task_id}/start",
    response_model=InspectionTask,
    summary="Start inspection task",
    description="Mark inspection task as in progress",
)
async def start_inspection_task(
    task_id: str, started_by: Optional[str] = None, current_user: User = Depends(get_current_user)
):
    """Start inspection task."""
    scheduler = get_inspection_scheduler()

    task = await scheduler.mark_task_in_progress(task_id=task_id, started_by=started_by or current_user.username)

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return task


@router.post(
    "/tasks/{task_id}/complete",
    response_model=InspectionTask,
    summary="Complete inspection task",
    description="Mark inspection task as completed",
)
async def complete_inspection_task(
    task_id: str, completion: InspectionTaskCompleteRequest, current_user: User = Depends(get_current_user)
):
    """Complete inspection task."""
    scheduler = get_inspection_scheduler()

    task = await scheduler.mark_task_complete(
        task_id=task_id,
        completed_by=completion.completed_by or current_user.username,
        completion_notes=completion.completion_notes,
        actual_duration_minutes=completion.actual_duration_minutes,
    )

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return task


@router.post(
    "/tasks/{task_id}/reschedule",
    response_model=InspectionTask,
    summary="Reschedule inspection task",
    description="Reschedule inspection task to new due date",
)
async def reschedule_inspection_task(
    task_id: str, reschedule: InspectionTaskRescheduleRequest, current_user: User = Depends(get_current_user)
):
    """Reschedule inspection task."""
    scheduler = get_inspection_scheduler()

    task = await scheduler.reschedule_task(
        task_id=task_id,
        new_due_date=reschedule.new_due_date,
        reason=reschedule.reason,
        rescheduled_by=reschedule.rescheduled_by or current_user.username,
    )

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return task


# ============================================================================
# Inspection Results Endpoints
# ============================================================================


@router.post(
    "/results",
    response_model=InspectionResult,
    status_code=status.HTTP_201_CREATED,
    summary="Create inspection result",
    description="Submit completed inspection results",
)
async def create_inspection_result(result: InspectionResultCreate, current_user: User = Depends(get_current_user)):
    """Create inspection result."""
    scheduler = get_inspection_scheduler()

    try:
        # Verify task exists and is assigned to this equipment
        task = await scheduler.repository.get_inspection_task(result.task_id)
        if not task or task.equipment_id != result.equipment_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task or equipment mismatch")

        created_result = await scheduler.repository.create_inspection_result(result.dict())

        # Auto-update task status to completed
        if result.overall_status in ["pass", "fail", "partial"]:
            await scheduler.mark_task_complete(
                task_id=result.task_id,
                completed_by=result.inspected_by,
                completion_notes=f"Inspection {result.overall_status}",
            )

        return created_result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create result: {str(e)}"
        )


@router.get(
    "/results/{result_id}",
    response_model=InspectionResult,
    summary="Get inspection result",
    description="Get inspection result by ID",
)
async def get_inspection_result(result_id: str, current_user: User = Depends(get_current_user)):
    """Get inspection result."""
    scheduler = get_inspection_scheduler()

    result = await scheduler.repository.get_inspection_result(result_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    return result


@router.get(
    "/results/task/{task_id}",
    response_model=List[InspectionResult],
    summary="Get results for task",
    description="Get all inspection results for a task",
)
async def get_inspection_results_for_task(task_id: str, current_user: User = Depends(get_current_user)):
    """Get inspection results for task."""
    scheduler = get_inspection_scheduler()

    results = await scheduler.repository.get_results_by_task(task_id)
    return results


@router.get(
    "/results/equipment/{equipment_id}",
    response_model=List[InspectionResult],
    summary="Get results for equipment",
    description="Get inspection results for equipment",
)
async def get_inspection_results_for_equipment(
    equipment_id: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    current_user: User = Depends(get_current_user),
):
    """Get inspection results for equipment."""
    scheduler = get_inspection_scheduler()

    results = await scheduler.repository.get_results_by_equipment(equipment_id, limit)
    return results


# ============================================================================
# Inspection Deficiency Endpoints
# ============================================================================


@router.post(
    "/deficiencies",
    response_model=InspectionDeficiency,
    status_code=status.HTTP_201_CREATED,
    summary="Create inspection deficiency",
    description="Log deficiency found during inspection",
)
async def create_inspection_deficiency(
    deficiency: InspectionDeficiencyCreate, current_user: User = Depends(get_current_user)
):
    """Create inspection deficiency."""
    scheduler = get_inspection_scheduler()

    try:
        created_deficiency = await scheduler.repository.create_inspection_deficiency(deficiency.dict())

        # Workflow integration: auto-trigger for critical/safety deficiencies
        try:
            from app.services.workflow_triggers import get_trigger_engine, InspectionDeficiency as WorkflowDeficiency

            if str(created_deficiency.severity) in ["critical", "safety"]:
                trigger_engine = get_trigger_engine()
                workflow_def = WorkflowDeficiency(
                    id=created_deficiency.id,
                    inspection_id=created_deficiency.result_id,
                    equipment_id=created_deficiency.equipment_id,
                    severity=str(created_deficiency.severity),
                    deficiency_title=created_deficiency.deficiency_title,
                    deficiency_description=created_deficiency.deficiency_description or "",
                    recommended_action=created_deficiency.recommended_action or "",
                    estimated_repair_cost_min=created_deficiency.estimated_repair_cost_min or 0.0,
                    estimated_repair_cost_max=created_deficiency.estimated_repair_cost_max or 0.0,
                    estimated_repair_hours=float(created_deficiency.estimated_repair_hours or 0),
                )
                await trigger_engine.on_critical_deficiency(workflow_def)
        except Exception:
            # Non-blocking: workflow trigger failures should not break API
            pass

        return created_deficiency

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create deficiency: {str(e)}"
        )


@router.get(
    "/deficiencies/{deficiency_id}",
    response_model=InspectionDeficiency,
    summary="Get inspection deficiency",
    description="Get inspection deficiency by ID",
)
async def get_inspection_deficiency(deficiency_id: str, current_user: User = Depends(get_current_user)):
    """Get inspection deficiency."""
    scheduler = get_inspection_scheduler()

    deficiency = await scheduler.repository.get_inspection_deficiency(deficiency_id)
    if not deficiency:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deficiency not found")

    return deficiency


@router.get(
    "/deficiencies/equipment/{equipment_id}",
    response_model=List[InspectionDeficiency],
    summary="Get deficiencies for equipment",
    description="Get all deficiencies for specific equipment",
)
async def get_deficiencies_for_equipment(
    equipment_id: str,
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    current_user: User = Depends(get_current_user),
):
    """Get deficiencies for equipment."""
    scheduler = get_inspection_scheduler()

    deficiencies = await scheduler.repository.get_deficiencies_by_equipment(equipment_id, resolved)
    return deficiencies


@router.post(
    "/deficiencies/{deficiency_id}/resolve",
    response_model=InspectionDeficiency,
    summary="Resolve deficiency",
    description="Mark deficiency as resolved",
)
async def resolve_deficiency(
    deficiency_id: str, resolved_by: str, resolution_notes: str, current_user: User = Depends(get_current_user)
):
    """Resolve inspection deficiency."""
    scheduler = get_inspection_scheduler()

    deficiency = await scheduler.repository.resolve_deficiency(
        deficiency_id=deficiency_id, resolved_by=resolved_by, resolution_notes=resolution_notes
    )

    if not deficiency:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deficiency not found")

    return deficiency


@router.post(
    "/deficiencies/{deficiency_id}/escalate",
    response_model=InspectionDeficiency,
    summary="Escalate deficiency",
    description="Escalate deficiency severity",
)
async def escalate_deficiency(
    deficiency_id: str,
    new_severity: DeficiencySeverity,
    escalation_notes: str,
    current_user: User = Depends(get_current_user),
):
    """Escalate inspection deficiency."""
    scheduler = get_inspection_scheduler()

    deficiency = await scheduler.repository.escalate_deficiency(
        deficiency_id=deficiency_id, new_severity=new_severity, escalation_notes=escalation_notes
    )

    if not deficiency:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deficiency not found")

    return deficiency


@router.get(
    "/deficiencies/unresolved/critical",
    response_model=List[InspectionDeficiency],
    summary="Get critical unresolved deficiencies",
    description="Get all critical and safety deficiencies that are unresolved",
)
async def get_critical_unresolved_deficiencies(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    current_user: User = Depends(get_current_user),
):
    """Get critical unresolved deficiencies."""
    scheduler = get_inspection_scheduler()

    deficiencies = await scheduler.repository.get_unresolved_deficiencies(
        equipment_id=equipment_id, severity="critical"
    )
    return deficiencies


# ============================================================================
# Summary and Statistics Endpoints
# ============================================================================


@router.get(
    "/summary/equipment/{equipment_id}",
    response_model=InspectionOverviewResponse,
    summary="Get inspection overview",
    description="Get inspection overview for equipment",
)
async def get_inspection_overview(equipment_id: str, current_user: User = Depends(get_current_user)):
    """Get inspection overview for equipment."""
    # This would use the view v_inspection_overview
    # For now, return mock data
    return InspectionOverviewResponse(
        equipment_id=equipment_id,
        equipment_name="Generator 001",
        equipment_type="generator",
        active_schedules=2,
        scheduled_tasks=3,
        in_progress_tasks=1,
        overdue_tasks=0,
        completed_last_30_days=4,
        open_deficiencies=2,
        critical_deficiencies=1,
    )


@router.get("/statistics", summary="Get inspection statistics", description="Get inspection scheduling statistics")
async def get_inspection_statistics(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    current_user: User = Depends(get_current_user),
):
    """Get inspection statistics."""
    scheduler = get_inspection_scheduler()

    stats = await scheduler.get_schedule_statistics(equipment_id)
    return stats


@router.get("/deficiencies/statistics", summary="Get deficiency statistics", description="Get deficiency statistics")
async def get_deficiency_statistics(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment"),
    days_back: int = Query(30, ge=1, le=365, description="Days back to analyze"),
    current_user: User = Depends(get_current_user),
):
    """Get deficiency statistics."""
    scheduler = get_inspection_scheduler()

    stats = await scheduler.repository.get_deficiency_statistics(equipment_id, days_back)
    return stats


# ============================================================================
# Mobile Inspection Submission Endpoints
# ============================================================================


@router.post(
    "/submit-weekly",
    response_model=InspectionTask,
    status_code=status.HTTP_201_CREATED,
    summary="Submit weekly inspection results",
    description="Submit inspection with checklist responses, measurements, and photos (mobile-friendly)",
)
async def submit_weekly_inspection(submission: InspectionSubmission, current_user: User = Depends(get_current_user)):
    """
    Submit inspection results from mobile interface.

    Creates a completed inspection task with:
    - Checklist responses stored in checklist_data
    - Measurements extracted and stored separately
    - Photo attachments linked
    - Deficiency count calculated from responses
    """
    from app.services.checklist_service import get_checklist_service
    import uuid

    scheduler = get_inspection_scheduler()
    checklist_service = get_checklist_service()
    repo = scheduler.repository

    # Load template
    template = checklist_service.get_template(submission.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Template {submission.template_id} not found"
        )

    # Calculate completion status
    completion_status = checklist_service.calculate_completion_status(template, submission.checklist_responses)

    # Generate task number
    task_number = f"INS-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    # Determine overall status from completion
    if completion_status["critical_count"] > 0:
        overall_status = "fail"
    elif completion_status["warning_count"] > 0 or completion_status["failed_tolerances"] > 0:
        overall_status = "partial"
    else:
        overall_status = "pass"

    # Create task data
    task_data = {
        "task_name": f"Weekly Inspection - {submission.equipment_id}",
        "task_description": f"Weekly routine inspection using template {submission.template_id}",
        "equipment_id": submission.equipment_id,
        "scheduled_date": datetime.now(),
        "due_date": datetime.now(),
        "status": "completed",
        "priority": "normal",
        "completed_date": datetime.now(),
        "completed_by": submission.submitted_by or current_user.username,
        "estimated_duration_minutes": template.get("estimated_duration_minutes", 15),
        "actual_duration_minutes": submission.duration_minutes,
        "completion_notes": submission.notes,
        "checklist_template_id": submission.template_id,
    }

    task = await repo.create_inspection_task(task_data)

    # Create inspection result
    result_data = {
        "task_id": task.id,
        "equipment_id": submission.equipment_id,
        "inspected_by": submission.submitted_by or current_user.username,
        "inspection_date": datetime.now(),
        "overall_status": overall_status,
        "item_results": submission.checklist_responses,
        "deficiencies_found": completion_status["critical_count"] + completion_status["warning_count"],
        "critical_findings": completion_status["critical_count"],
        "general_notes": submission.notes,
        "photo_urls": [p.file_url for p in submission.photos] if submission.photos else [],
    }

    await repo.create_inspection_result(result_data)

    # Store measurements
    measurements = checklist_service.prepare_measurements_for_db(template, submission.checklist_responses, task.id)
    for measurement in measurements:
        measurement["result_id"] = task.id
        measurement["equipment_id"] = submission.equipment_id
        measurement["measured_by"] = submission.submitted_by or current_user.username
        measurement["measurement_date"] = datetime.now()
        await repo.create_inspection_measurement(measurement)

    return task


@router.get(
    "/schedule",
    response_model=List[InspectionScheduleSummary],
    summary="Get inspection schedule",
    description="Get upcoming inspections for user or equipment",
)
async def get_inspection_schedule(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID"),
    days_ahead: int = Query(30, ge=1, le=365, description="Days ahead to include"),
    current_user: User = Depends(get_current_user),
):
    """
    Get inspection schedule for mobile view.

    Returns active schedules with next due dates within the specified timeframe.
    """
    from datetime import timedelta

    scheduler = get_inspection_scheduler()

    if equipment_id:
        schedules = await scheduler.repository.get_active_schedules(equipment_id)
    else:
        schedules = await scheduler.repository.get_active_schedules()

    # Filter to only active schedules with next due date within range
    cutoff_date = datetime.now() + timedelta(days=days_ahead)

    result = []
    for schedule in schedules:
        if not schedule.is_active:
            continue

        # Skip if next due date is beyond cutoff
        if schedule.next_due_date and schedule.next_due_date > cutoff_date:
            continue

        result.append(
            InspectionScheduleSummary(
                id=schedule.id,
                equipment_id=schedule.equipment_id,
                schedule_name=schedule.schedule_name,
                frequency_type=schedule.frequency_type.value
                if hasattr(schedule.frequency_type, "value")
                else str(schedule.frequency_type),
                frequency_interval=schedule.frequency_days,
                inspection_type="routine",
                checklist_template_id=None,  # Could be added to schedule model later
                priority="normal" if schedule.frequency_type != "weekly" else "high",
                duration_minutes=schedule.estimated_duration_minutes or 30,
                next_due_date=schedule.next_due_date,
                is_active=schedule.is_active,
            )
        )

    return result


@router.get(
    "/history/{equipment_id}",
    response_model=List[InspectionTask],
    summary="Get inspection history",
    description="Get historical inspections for equipment with trending",
)
async def get_inspection_history(
    equipment_id: str = Path(..., description="Equipment ID"),
    months: int = Query(12, ge=1, le=60, description="Months of history to return"),
    current_user: User = Depends(get_current_user),
):
    """
    Get inspection history for equipment.

    Returns completed inspection tasks with results for trending analysis.
    """
    from datetime import timedelta

    scheduler = get_inspection_scheduler()

    start_date = datetime.now() - timedelta(days=months * 30)

    tasks = await scheduler.repository.get_tasks_in_date_range(
        start_date=start_date, end_date=datetime.now(), equipment_id=equipment_id
    )

    # Filter to completed tasks only
    completed_tasks = [t for t in tasks if t.status == InspectionTaskStatus.COMPLETED]

    return completed_tasks
