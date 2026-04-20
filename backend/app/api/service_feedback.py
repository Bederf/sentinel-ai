"""
Service Feedback API Endpoints

REST API for collecting technician feedback after work order completion.
Equipment-type specific templates define required data.
Feedback updates equipment health scores.

Phase 59: Service Feedback & Health Score Integration
"""

import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.work_order_repository import get_work_order_repository
from app.services.feedback_collection_service import (
    FeedbackItemType,
    get_feedback_collection_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/service-feedback", tags=["service-feedback"])


# ============================================================================
# Request/Response Models
# ============================================================================


class StartFeedbackRequest(BaseModel):
    """Request to start feedback collection."""

    work_order_id: str
    equipment_code: str
    service_type: str = "minor"  # minor, major, breakdown


class StartFeedbackResponse(BaseModel):
    """Response when starting feedback session."""

    session_id: str
    equipment_code: str
    equipment_type: str
    service_type: str
    required_items: list[str]
    optional_items: list[str]
    first_prompt: dict | None = None


class SubmitReadingRequest(BaseModel):
    """Request to submit a reading."""

    item_key: str
    value: Any
    unit: str | None = None
    notes: str | None = None


class SubmitObservationRequest(BaseModel):
    """Request to submit an observation."""

    item_key: str = "observation"
    content: str
    notes: str | None = None


class FeedbackItemResponse(BaseModel):
    """Response for a submitted feedback item."""

    item_key: str
    item_type: str
    value: Any
    unit: str | None = None
    baseline_value: float | None = None
    deviation_percent: float | None = None
    health_impact: str
    notes: str | None = None


class SessionStatusResponse(BaseModel):
    """Response for session status."""

    session_id: str
    status: str
    equipment_code: str
    equipment_type: str
    service_type: str
    progress: dict
    items_collected: list[str]
    next_item: dict | None = None
    started_at: str | None = None
    completed_at: str | None = None


class CompleteFeedbackResponse(BaseModel):
    """Response when completing feedback session."""

    success: bool
    session_id: str
    equipment_code: str
    health_score_change: int
    items_collected: int
    feedback_summary: dict
    warnings: list[str] = []
    completed_at: str | None = None
    error: str | None = None
    message: str | None = None


class TemplateResponse(BaseModel):
    """Response containing feedback template."""

    equipment_type: str
    service_type: str
    required_items: list[str]
    optional_items: list[str]
    prompts: dict
    validation_rules: dict


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/start", response_model=StartFeedbackResponse)
async def start_feedback_session(request: StartFeedbackRequest):
    """
    Start a feedback collection session for a work order.

    This creates a session that tracks what feedback has been collected
    and provides prompts for the technician based on equipment type.
    """
    service = get_feedback_collection_service()
    work_order_repo = get_work_order_repository()
    equipment_repo = EquipmentRepository()

    # Verify work order exists
    work_order = await work_order_repo.get_work_order_by_code(request.work_order_id)
    if not work_order:
        # Try by ID
        work_order = await work_order_repo.get_work_order(request.work_order_id)

    if not work_order:
        raise HTTPException(status_code=404, detail=f"Work order not found: {request.work_order_id}")

    # Get equipment
    equipment = equipment_repo.get_by_id(request.equipment_code)
    if not equipment:
        raise HTTPException(status_code=404, detail=f"Equipment not found: {request.equipment_code}")

    equipment_id = equipment.get("id", request.equipment_code)

    # Start session
    session = await service.start_feedback_session(
        work_order_id=request.work_order_id,
        equipment_id=equipment_id,
        equipment_code=request.equipment_code,
        service_type=request.service_type,
    )

    # Get first prompt
    next_prompt = service.get_next_prompt(session.session_id)
    first_prompt = None
    if next_prompt:
        first_prompt = {"key": next_prompt[0], "prompt": next_prompt[1], "required": next_prompt[2]}

    return StartFeedbackResponse(
        session_id=session.session_id,
        equipment_code=session.equipment_code,
        equipment_type=session.equipment_type,
        service_type=session.service_type,
        required_items=session.template.required_items,
        optional_items=session.template.optional_items,
        first_prompt=first_prompt,
    )


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """
    Get the current status of a feedback session.

    Returns progress, collected items, and next prompt.
    """
    service = get_feedback_collection_service()
    status = service.get_session_status(session_id)

    if not status:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return SessionStatusResponse(**status)


@router.post("/session/{session_id}/reading", response_model=FeedbackItemResponse)
async def submit_reading(session_id: str, request: SubmitReadingRequest):
    """
    Submit a reading/measurement for the feedback session.

    The reading will be validated against equipment baselines and
    impact on health score will be calculated.
    """
    service = get_feedback_collection_service()

    try:
        item = await service.submit_feedback_item(
            session_id=session_id,
            item_key=request.item_key,
            value=request.value,
            item_type=FeedbackItemType.READING,
            unit=request.unit,
            notes=request.notes,
        )

        return FeedbackItemResponse(
            item_key=item.item_key,
            item_type=item.item_type.value,
            value=item.value,
            unit=item.unit,
            baseline_value=item.baseline_value,
            deviation_percent=item.deviation_percent,
            health_impact=item.health_impact.value,
            notes=item.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session/{session_id}/observation", response_model=FeedbackItemResponse)
async def submit_observation(session_id: str, request: SubmitObservationRequest):
    """
    Submit a text observation for the feedback session.

    This can be used for technician notes, findings, etc.
    """
    service = get_feedback_collection_service()

    try:
        item = await service.submit_feedback_item(
            session_id=session_id,
            item_key=request.item_key,
            value=request.content,
            item_type=FeedbackItemType.OBSERVATION,
            notes=request.notes,
        )

        return FeedbackItemResponse(
            item_key=item.item_key,
            item_type=item.item_type.value,
            value=item.value,
            unit=None,
            baseline_value=None,
            deviation_percent=None,
            health_impact=item.health_impact.value,
            notes=item.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session/{session_id}/photo", response_model=FeedbackItemResponse)
async def submit_photo(
    session_id: str, item_key: str = Form(...), notes: str | None = Form(None), file: UploadFile = File(...)
):
    """
    Submit a photo for the feedback session.

    Photos are stored and can be analyzed for condition assessment.
    """
    service = get_feedback_collection_service()

    # In a real implementation, save file to storage
    # For now, just record the filename
    file_path = f"/uploads/feedback/{session_id}/{item_key}_{file.filename}"

    try:
        item = await service.submit_feedback_item(
            session_id=session_id,
            item_key=item_key,
            value=file.filename,
            item_type=FeedbackItemType.PHOTO,
            file_path=file_path,
            notes=notes,
        )

        return FeedbackItemResponse(
            item_key=item.item_key,
            item_type=item.item_type.value,
            value=item.value,
            unit=None,
            baseline_value=None,
            deviation_percent=None,
            health_impact=item.health_impact.value,
            notes=item.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session/{session_id}/audio", response_model=FeedbackItemResponse)
async def submit_audio(
    session_id: str, item_key: str = Form(...), notes: str | None = Form(None), file: UploadFile = File(...)
):
    """
    Submit an audio recording for the feedback session.

    Audio can be analyzed for anomaly detection (bearing noise, etc).
    """
    service = get_feedback_collection_service()

    # In a real implementation, save file and analyze
    file_path = f"/uploads/feedback/{session_id}/{item_key}_{file.filename}"

    try:
        item = await service.submit_feedback_item(
            session_id=session_id,
            item_key=item_key,
            value=file.filename,
            item_type=FeedbackItemType.AUDIO,
            file_path=file_path,
            notes=notes,
        )

        return FeedbackItemResponse(
            item_key=item.item_key,
            item_type=item.item_type.value,
            value=item.value,
            unit=None,
            baseline_value=None,
            deviation_percent=None,
            health_impact=item.health_impact.value,
            notes=item.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session/{session_id}/complete", response_model=CompleteFeedbackResponse)
async def complete_feedback_session(
    session_id: str, force: bool = Query(False, description="Complete even if required items missing")
):
    """
    Complete the feedback session and update equipment health.

    This calculates the overall health impact from all feedback items
    and updates the equipment's health score in the database.
    """
    service = get_feedback_collection_service()

    try:
        result = await service.complete_feedback_session(session_id, force=force)

        return CompleteFeedbackResponse(
            success=result.get("success", False),
            session_id=session_id,
            equipment_code=result.get("equipment_code", ""),
            health_score_change=result.get("health_score_change", 0),
            items_collected=result.get("items_collected", 0),
            feedback_summary=result.get("feedback_summary", {}),
            warnings=result.get("warnings", []),
            completed_at=result.get("completed_at"),
            error=result.get("error"),
            message=result.get("message"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/template/{equipment_type}", response_model=TemplateResponse)
async def get_feedback_template(
    equipment_type: str, service_type: str = Query("minor", description="Service type: minor, major, breakdown")
):
    """
    Get the feedback template for an equipment type.

    Returns required items, optional items, prompts, and validation rules.
    """
    service = get_feedback_collection_service()
    template = service.get_template(equipment_type, service_type)

    if not template:
        raise HTTPException(status_code=404, detail=f"No template found for {equipment_type}/{service_type}")

    return TemplateResponse(
        equipment_type=template.equipment_type,
        service_type=template.service_type,
        required_items=template.required_items,
        optional_items=template.optional_items,
        prompts=template.prompts,
        validation_rules=template.validation_rules,
    )


@router.get("/templates")
async def list_available_templates():
    """
    List all available feedback templates.

    Returns equipment types and their service type configurations.
    """
    service = get_feedback_collection_service()

    templates_summary = {}
    for eq_type, service_types in service._templates.items():
        templates_summary[eq_type] = {"service_types": list(service_types.keys()), "configurations": {}}
        for svc_type, template in service_types.items():
            templates_summary[eq_type]["configurations"][svc_type] = {
                "required_count": len(template.required_items),
                "optional_count": len(template.optional_items),
                "has_audio": template.audio_duration_seconds > 0,
                "audio_duration": template.audio_duration_seconds,
            }

    return {
        "equipment_types": list(templates_summary.keys()),
        "count": len(templates_summary),
        "templates": templates_summary,
    }


@router.get("/health-impact-rules")
async def get_health_impact_rules():
    """
    Get the rules for health score impact calculation.

    Returns how different feedback affects equipment health scores.
    """
    return {
        "description": "Health score impact is calculated from feedback readings compared to baselines",
        "impact_levels": {
            "positive": {
                "description": "Reading improved or within 5% of baseline",
                "score_change": "+2 per item (max +10)",
            },
            "neutral": {"description": "Reading within 15% of baseline", "score_change": "0"},
            "negative": {"description": "Reading 15-30% deviation from baseline", "score_change": "-3 per item"},
            "critical": {"description": "Reading >30% deviation or out of range", "score_change": "-5 per item"},
        },
        "score_bounds": {"min_change": -20, "max_change": +10},
        "health_status_thresholds": {"normal": "health >= 80", "warning": "health >= 60", "critical": "health < 60"},
    }
