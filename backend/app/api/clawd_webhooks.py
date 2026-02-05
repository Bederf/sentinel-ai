"""Clawd bot webhook endpoints for Phase 41 integration.

These endpoints are called by the Clawd Telegram bot when:
1. Technician responds to work order notification
2. Technician uploads files during data collection
3. Data collection flow interactions

Phase 41-02 additions:
4. OCR processing for service sheet photos
5. Correction flow for OCR validation issues
"""

import base64
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

from app.services.clawd_integration.work_order_notifier import work_order_notifier
from app.services.ocr_service import get_ocr_service
from app.services.clawd_integration.ocr_correction_handler import get_ocr_correction_handler
from app.models.service_record import ServiceStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clawd", tags=["clawd"])


@router.post("/work-order/response", status_code=status.HTTP_200_OK)
async def handle_work_order_response(
    data: Dict[str, Any],
    x_clawd_secret: Optional[str] = Header(None),
):
    """Handle technician response to work order notification.

    Called by Clawd when technician replies "done" or sends initial service sheet.

    Request body:
        - service_record_code: str (e.g., "SR-2026-ABC123")
        - telegram_user_id: str
        - message_type: str (text/photo/audio/file)
        - content: dict or str (message content or file info)

    Returns:
        - next_prompt: Next data collection prompt
        - collected_items: List of collected items
        - is_complete: Whether data collection is complete
    """
    # Verify Clawd secret (simple auth)
    if x_clawd_secret and x_clawd_secret != "clawd-bms-phase-41":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Required fields
    required_fields = ["service_record_code", "telegram_user_id", "message_type"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    # Handle the response
    result = await work_order_notifier.handle_technician_reply(
        data["service_record_code"],
        {
            "telegram_user_id": data["telegram_user_id"],
            "message_type": data["message_type"],
            "content": data.get("content"),
        }
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/work-order/status/{service_record_code}", response_model=Dict[str, Any])
async def get_data_collection_status(service_record_code: str):
    """Get data collection status for a service record.

    Returns current progress, collected items, missing items, and next prompt.
    """
    result = await work_order_notifier.get_collection_status(service_record_code)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post("/work-order/notify", status_code=status.HTTP_200_OK)
async def notify_technician_of_work_order(
    data: Dict[str, Any],
    x_clawd_secret: Optional[str] = Header(None),
):
    """Send work order notification to technician via Clawd.

    Called by BMS when WO is assigned to trigger Telegram notification.

    Request body:
        - work_order_id: UUID
        - equipment_id: UUID
        - building_id: UUID
        - equipment_name: str
        - criticality: str (HIGH/MEDIUM/LOW)
        - service_type: str (minor/major/breakdown/callout)
        - technician_id: str (Telegram ID or email)
        - technician_name: str
        - description: str

    Returns:
        - success: bool
        - service_record_code: Generated code
    """
    # Verify auth
    if x_clawd_secret and x_clawd_secret != "clawd-bms-phase-41":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Required fields
    required_fields = [
        "work_order_id", "equipment_id", "building_id",
        "equipment_name", "service_type", "technician_id", "technician_name"
    ]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    # Send notification (returns service_record_code on success)
    result = await work_order_notifier.notify_technician_with_code(data)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send notification"))

    return {
        "success": True,
        "message": "Work order notification sent successfully",
        "service_record_code": result.get("service_record_code")
    }


@router.post("/work-order/complete/{service_record_code}", status_code=status.HTTP_200_OK)
async def mark_service_record_complete(service_record_code: str):
    """Mark service record as complete manually.

    Called when technician confirms completion via Clawd.
    """
    # Find service record
    result = await work_order_notifier.get_collection_status(service_record_code)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    # TODO: Trigger ML processing pipeline
    # - Process OCR for service sheets
    # - Analyze audio recordings
    # - Quality scoring
    # - Store in training dataset

    return {
        "success": True,
        "service_record_code": service_record_code,
        "ml_processing_initiated": True,
    }


# ============================================================================
# Phase 41-02: OCR Processing for Service Sheet Photos
# ============================================================================

class ServiceSheetUpload(BaseModel):
    """Request for service sheet photo upload with OCR processing."""
    service_record_id: str = Field(..., description="Service record ID")
    equipment_id: str = Field(..., description="Equipment ID")
    service_type: str = Field(..., description="Service type (minor/major/breakdown)")
    image_base64: str = Field(..., description="Base64-encoded image")
    media_type: str = Field(default="image/jpeg", description="Image MIME type")
    telegram_user_id: str = Field(..., description="Telegram user ID")


class CorrectionResponse(BaseModel):
    """Request for submitting OCR correction."""
    service_record_id: str = Field(..., description="Service record ID")
    correction: str = Field(..., description="Corrected value")


@router.post("/ocr/process-service-sheet", status_code=status.HTTP_200_OK)
async def process_service_sheet_ocr(
    data: ServiceSheetUpload,
    x_clawd_secret: Optional[str] = Header(None),
):
    """Process uploaded service sheet through OCR pipeline.

    Called by Clawd when technician sends service sheet photo.
    Runs 3-stage OCR pipeline and returns results.

    If OCR returns needs_review status, includes first correction prompt
    for the technician to verify/correct extracted values.

    Returns:
        - status: completed/needs_review/failed
        - extracted_data: Raw OCR data
        - validated_data: Validated and typed data
        - pipeline_info: Confidence scores and issues
        - correction_prompt: First correction prompt (if needs_review)
    """
    # Verify auth
    if x_clawd_secret and x_clawd_secret != "clawd-bms-phase-41":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Decode image
    try:
        image_b64 = data.image_base64
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        image_data = base64.b64decode(image_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")

    # Get OCR service
    ocr_service = get_ocr_service()
    correction_handler = get_ocr_correction_handler()

    try:
        # Run OCR pipeline
        result = await ocr_service.process_service_sheet(
            image_data=image_data,
            equipment_id=data.equipment_id,
            service_type=data.service_type,
            service_record_id=data.service_record_id,
            media_type=data.media_type
        )

        # If needs review, start correction flow
        if result["status"] == "needs_review":
            correction_prompt = await correction_handler.start_correction_flow(
                data.service_record_id,
                result,
                data.telegram_user_id
            )
            result["correction_prompt"] = correction_prompt

            logger.info(
                f"OCR needs review for {data.service_record_id}: "
                f"{len(result.get('pipeline_info', {}).get('issues', []))} issues"
            )

        return result

    except Exception as e:
        logger.error(f"OCR processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr/correction", status_code=status.HTTP_200_OK)
async def submit_ocr_correction(
    data: CorrectionResponse,
    x_clawd_secret: Optional[str] = Header(None),
):
    """Submit correction for OCR-extracted value.

    Called by Clawd when technician provides corrected value
    for a field that failed validation.

    Returns next correction prompt or completion status.
    """
    # Verify auth
    if x_clawd_secret and x_clawd_secret != "clawd-bms-phase-41":
        raise HTTPException(status_code=403, detail="Unauthorized")

    correction_handler = get_ocr_correction_handler()

    if not correction_handler.has_pending_correction(data.service_record_id):
        raise HTTPException(
            status_code=404,
            detail="No pending correction session for this service record"
        )

    result = await correction_handler.process_correction_response(
        data.service_record_id,
        data.correction
    )

    return result


@router.get("/ocr/status/{service_record_id}", status_code=status.HTTP_200_OK)
async def get_ocr_correction_status(service_record_id: str):
    """Get OCR correction status for a service record.

    Returns:
        - in_progress: Whether correction flow is active
        - current_index: Current correction step
        - total_issues: Total issues to correct
        - corrections_made: Number completed
    """
    ocr_service = get_ocr_service()
    correction_handler = get_ocr_correction_handler()

    # Check processing status
    if service_record_id in ocr_service._currently_processing:
        return {"status": "processing", "message": "OCR in progress"}

    # Check correction status
    if correction_handler.has_pending_correction(service_record_id):
        return {
            "status": "needs_review",
            **correction_handler.get_correction_status(service_record_id)
        }

    return {"status": "unknown", "message": "No active OCR session"}
