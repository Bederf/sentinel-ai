"""
OCR API Endpoints (Phase 41-02)

REST API for service sheet OCR processing:
- POST /api/ocr/process - Process service sheet photo
- GET /api/ocr/status/{service_record_id} - Get processing status
- POST /api/ocr/correction/{service_record_id} - Submit correction
- GET /api/ocr/correction/{service_record_id}/status - Get correction status
"""

import logging
from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.services.ocr_service import get_ocr_service
from app.services.sentry_integration.ocr_correction_handler import get_ocr_correction_handler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["ocr"])

# Max image size: 5MB
MAX_IMAGE_SIZE = 5 * 1024 * 1024

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}


class CorrectionRequest(BaseModel):
    """Request for submitting a correction."""

    correction: str = Field(..., description="Corrected value for the field")
    telegram_user_id: Optional[str] = Field(None, description="Telegram user ID")


class OCRProcessRequest(BaseModel):
    """Request for processing service sheet via base64."""

    image: str = Field(..., description="Base64-encoded image data")
    media_type: str = Field(default="image/jpeg", description="Image MIME type")
    equipment_id: str = Field(..., description="Equipment identifier")
    service_type: str = Field(..., description="Service type (minor/major/breakdown)")
    service_record_id: str = Field(..., description="Unique service record ID")


@router.post("/process")
async def process_service_sheet(
    file: UploadFile = File(...),
    equipment_id: str = Form(...),
    service_type: str = Form(...),
    service_record_id: str = Form(...),
):
    """
    Process service sheet photo through 3-stage OCR pipeline.

    Stages:
    1. Claude Vision OCR extraction
    2. Template validation (type coercion, range checks)
    3. AI enhancement (fill gaps, suggest corrections)

    Returns extracted data with confidence scores and validation status.

    Example:
        POST /api/ocr/process
        Content-Type: multipart/form-data
        file: <service_sheet.jpg>
        equipment_id: "eqp-gen-001"
        service_type: "minor"
        service_record_id: "SR-2026-ABC123"
    """
    # Validate file type
    if file.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail=f"File must be an image. Allowed types: {ALLOWED_MEDIA_TYPES}")

    # Read image data
    image_data = await file.read()

    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail=f"Image exceeds {MAX_IMAGE_SIZE // (1024 * 1024)}MB limit")

    # Get OCR service
    ocr_service = get_ocr_service()

    try:
        result = await ocr_service.process_service_sheet(
            image_data=image_data,
            equipment_id=equipment_id,
            service_type=service_type,
            service_record_id=service_record_id,
            media_type=file.content_type,
        )

        return result

    except Exception as e:
        logger.error(f"OCR processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-base64")
async def process_service_sheet_base64(request: OCRProcessRequest):
    """
    Process service sheet from base64-encoded image.

    Alternative to multipart upload for Telegram/mobile clients
    that send images as base64.
    """
    import base64

    # Decode base64 image
    try:
        # Handle data URL format
        image_b64 = request.image
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        image_data = base64.b64decode(image_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")

    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail=f"Image exceeds {MAX_IMAGE_SIZE // (1024 * 1024)}MB limit")

    # Get OCR service
    ocr_service = get_ocr_service()

    try:
        result = await ocr_service.process_service_sheet(
            image_data=image_data,
            equipment_id=request.equipment_id,
            service_type=request.service_type,
            service_record_id=request.service_record_id,
            media_type=request.media_type,
        )

        return result

    except Exception as e:
        logger.error(f"OCR processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{service_record_id}")
async def get_ocr_status(service_record_id: str):
    """
    Get OCR processing status for a service record.

    Returns:
        - status: processing/needs_review/completed/unknown
        - corrections_pending: Number of corrections still needed
        - progress: Current correction progress if applicable
    """
    ocr_service = get_ocr_service()
    correction_handler = get_ocr_correction_handler()

    # Check if currently processing
    if service_record_id in ocr_service._currently_processing:
        return {"status": "processing", "message": "OCR in progress"}

    # Check if pending correction
    if correction_handler.has_pending_correction(service_record_id):
        status = correction_handler.get_correction_status(service_record_id)
        return {
            "status": "needs_review",
            "corrections_pending": status["total_issues"] - status["current_index"],
            "corrections_made": status["corrections_made"],
            "progress": f"{status['current_index']}/{status['total_issues']}",
        }

    return {"status": "unknown", "message": "No active processing for this record"}


@router.post("/correction/{service_record_id}")
async def submit_correction(service_record_id: str, request: CorrectionRequest):
    """
    Submit a correction for an OCR field.

    Called when technician provides corrected value for a field
    that failed validation.

    Returns the next field to correct, or completion status.
    """
    correction_handler = get_ocr_correction_handler()

    if not correction_handler.has_pending_correction(service_record_id):
        raise HTTPException(status_code=404, detail="No pending correction session for this service record")

    result = await correction_handler.process_correction_response(service_record_id, request.correction)

    return result


@router.get("/correction/{service_record_id}/status")
async def get_correction_status(service_record_id: str):
    """Get correction flow status for a service record."""
    correction_handler = get_ocr_correction_handler()
    return correction_handler.get_correction_status(service_record_id)


@router.post("/correction/{service_record_id}/start")
async def start_correction_flow(service_record_id: str, pipeline_result: dict, telegram_user_id: str = Form(...)):
    """
    Start correction flow for a service record.

    Called after OCR returns needs_review status.

    Returns the first field that needs correction.
    """
    correction_handler = get_ocr_correction_handler()

    result = await correction_handler.start_correction_flow(service_record_id, pipeline_result, telegram_user_id)

    return result


@router.post("/correction/{service_record_id}/cancel")
async def cancel_correction_flow(service_record_id: str):
    """Cancel an active correction flow."""
    correction_handler = get_ocr_correction_handler()

    if correction_handler.cancel_correction_flow(service_record_id):
        return {"success": True, "message": "Correction flow cancelled"}
    else:
        raise HTTPException(status_code=404, detail="No active correction flow for this service record")
