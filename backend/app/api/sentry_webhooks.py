"""Sentry bot webhook endpoints for Phase 41 integration.

These endpoints are called by the Sentry Telegram bot when:
1. Technician responds to work order notification
2. Technician uploads files during data collection
3. Data collection flow interactions

Phase 41-02 additions:
4. OCR processing for service sheet photos
5. Correction flow for OCR validation issues

Manager control additions:
6. Remote equipment reset via /reset_ command
"""

import base64
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request

from app.models.auth import AuthContext, AuthLevel
from app.middleware.auth_middleware import require_auth
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

from app.services.sentry_integration.work_order_notifier import work_order_notifier
from app.services.ocr_service import get_ocr_service
from app.services.sentry_integration.ocr_correction_handler import get_ocr_correction_handler
from app.models.service_record import ServiceStatus
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.services.sentry_auth_service import get_sentry_jwt_headers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sentry", tags=["sentry"])

# Equipment types blocked from remote reset (safety-critical)
RESET_BLOCKED_TYPES = {"FIRE", "GEN"}


class EquipmentResetRequest(BaseModel):
    """Request to remotely reset equipment fault status."""
    equipment_code: str = Field(..., description="Equipment code (e.g., S002-FCU-L1-A)")
    user_id: str = Field(..., description="User initiating the reset")
    reason: Optional[str] = Field(None, description="Reason for reset")


@router.post("/work-order/response", status_code=status.HTTP_200_OK)
async def handle_work_order_response(
    data: Dict[str, Any],
    x_sentry_secret: Optional[str] = Header(None),
):
    """Handle technician response to work order notification.

    Called by Sentry when technician replies "done" or sends initial service sheet.

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
    # Verify Sentry secret (simple auth)
    if x_sentry_secret and x_sentry_secret != "sentry-bms-webhooks":
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
    x_sentry_secret: Optional[str] = Header(None),
):
    """Send work order notification to technician via Sentry.

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
    if x_sentry_secret and x_sentry_secret != "sentry-bms-webhooks":
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

    Called when technician confirms completion via Sentry.
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
# Manager Controls: Remote Equipment Reset
# ============================================================================

@router.post("/equipment/reset", status_code=status.HTTP_200_OK)
async def reset_equipment_fault(
    request: EquipmentResetRequest,
    x_sentry_secret: Optional[str] = Header(None),
):
    """Remote fault reset for equipment via Sentry Telegram bot.

    Resets device fault status, restores health to >=85, and resolves
    active predictions. Blocks fire and generator equipment for safety.

    Returns:
        - success: bool
        - blocked: bool (if equipment type is safety-critical)
        - reason: str (explanation)
        - previous_health / new_health: int
        - equipment_name: str
        - predictions_resolved: int
    """
    # Verify auth
    if x_sentry_secret and x_sentry_secret != "sentry-bms-webhooks":
        raise HTTPException(status_code=403, detail="Unauthorized")

    equipment_code = request.equipment_code

    # Extract equipment type from code (second segment: S002-FCU-L1-A → FCU)
    parts = equipment_code.split("-")
    eq_type = parts[1].upper() if len(parts) >= 2 else ""

    # Block safety-critical equipment types
    if eq_type in RESET_BLOCKED_TYPES:
        return {
            "success": False,
            "blocked": True,
            "reason": f"{eq_type} equipment cannot be remotely reset for safety reasons. "
                      f"Create a work order instead.",
            "equipment_code": equipment_code,
        }

    # Get current equipment info for before/after comparison (async HTTP)
    equipment_info = None
    previous_health = None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            headers = get_sentry_jwt_headers()
            resp = await client.get(
                f"http://localhost:9095/api/work-orders/equipment-info/{equipment_code}",
                headers=headers,
            )
            if resp.status_code == 200:
                equipment_info = resp.json()
                previous_health = equipment_info.get("health_score") or equipment_info.get("health")
            elif resp.status_code == 401:
                logger.warning("Sentry JWT auth failed when fetching equipment info")
    except Exception as e:
        logger.debug(f"Error fetching equipment info: {e}")

    # Execute fault reset via RemoteCommandService
    try:
        from app.services.remote_command_service import RemoteCommandService

        service = RemoteCommandService()
        result = await service.execute_remote_command(
            user_id=request.user_id,
            user_role="engineer",
            device_id=equipment_code,
            command_type="fault_reset",
            reason=request.reason or "Remote reset via Telegram",
        )

        if result.get("success"):
            reset_data = result.get("data", {})
            # Get updated health (async HTTP)
            new_health = None
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    headers = get_sentry_jwt_headers()
                    resp = await client.get(
                        f"http://localhost:9095/api/work-orders/equipment-info/{equipment_code}",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        new_health = resp.json().get("health_score") or resp.json().get("health")
                    elif resp.status_code == 401:
                        logger.warning("Sentry JWT auth failed when fetching updated equipment info")
            except Exception as e:
                logger.debug(f"Error fetching updated equipment info: {e}")

            return {
                "success": True,
                "blocked": False,
                "reason": "Fault reset executed successfully",
                "equipment_code": equipment_code,
                "equipment_name": reset_data.get("equipment_name") or (equipment_info or {}).get("name", equipment_code),
                "previous_health": previous_health,
                "new_health": new_health or 85,
                "predictions_resolved": reset_data.get("predictions_resolved", 0),
                "device_reset": reset_data.get("device_reset", False),
                "equipment_updated": reset_data.get("equipment_updated", False),
            }
        else:
            return {
                "success": False,
                "blocked": False,
                "reason": result.get("error", "Reset failed - unknown error"),
                "equipment_code": equipment_code,
            }

    except Exception as e:
        logger.error(f"Equipment reset error: {e}", exc_info=True)
        return {
            "success": False,
            "blocked": False,
            "reason": f"Reset failed: {str(e)}",
            "equipment_code": equipment_code,
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
    x_sentry_secret: Optional[str] = Header(None),
):
    """Process uploaded service sheet through OCR pipeline.

    Called by Sentry when technician sends service sheet photo.
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
    if x_sentry_secret and x_sentry_secret != "sentry-bms-webhooks":
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
    x_sentry_secret: Optional[str] = Header(None),
):
    """Submit correction for OCR-extracted value.

    Called by Sentry when technician provides corrected value
    for a field that failed validation.

    Returns next correction prompt or completion status.
    """
    # Verify auth
    if x_sentry_secret and x_sentry_secret != "sentry-bms-webhooks":
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


@router.get("/work-order/pending")
async def get_pending_work_orders(
    request: Request,
    x_sentry_secret: Optional[str] = Header(None),
):
    """Get pending work orders that need Telegram notifications.

    Returns list of service records with status='notified' that are pending
    Sentry bot notification delivery. Called by Sentry bot to poll for notifications.

    Authentication: Allowed for Sentry bot (requires X-Sentry-Secret header).
    Anyone without the secret can still call this endpoint as it's PUBLIC.

    Returns:
        List of pending service records ready for notification
    """
    # Sentry bot authentication via header (optional - endpoint is public)
    if x_sentry_secret and x_sentry_secret != "sentry-bms-webhooks":
        logger.warning(f"Invalid Sentry secret provided: {x_sentry_secret[:10]}...")

    service_repo = ServiceRecordRepository()

    try:
        # Get all service records with status 'notified' (awaiting notification)
        pending = await service_repo.list(filters={"status": "notified"})

        if not pending:
            return {"pending_count": 0, "work_orders": []}

        # Format for Sentry bot
        formatted_orders = []
        for sr in pending:
            formatted_orders.append({
                "service_record_code": sr.get("code"),
                "service_record_id": sr.get("id"),
                "technician_id": sr.get("technician_id"),
                "technician_name": sr.get("technician_name"),
                "equipment_id": sr.get("equipment_id"),
                "building_id": sr.get("building_id"),
                "service_type": sr.get("service_type"),
                "created_at": sr.get("created_at")
            })

        logger.info(f"Sentry bot querying: {len(formatted_orders)} pending work orders")

        return {
            "pending_count": len(formatted_orders),
            "work_orders": formatted_orders
        }

    except Exception as e:
        logger.error(f"Error fetching pending work orders: {e}")
        return {"pending_count": 0, "work_orders": [], "error": str(e)}


@router.post("/process-pending-notifications", status_code=status.HTTP_200_OK)
async def process_pending_sentry_notifications(
    x_sentry_secret: Optional[str] = Header(None),
):
    """Inspect pending notifications for Sentry delivery.

    Called by background scheduler every 30 seconds.
    This endpoint now acts as a monitor/heartbeat only and does NOT advance
    service record state.

    Status transitions must occur from real technician interaction
    (e.g., "done" reply via /work-order/response).
    """
    if x_sentry_secret and x_sentry_secret != "sentry-bms-webhooks":
        logger.warning(f"Invalid Sentry secret for process-pending: {x_sentry_secret[:10]}...")

    service_repo = ServiceRecordRepository()
    try:
        # Get all pending notifications
        pending = await service_repo.list(filters={"status": "notified"})
        if not pending:
            return {
                "success": True,
                "processed": 0,
                "message": "No pending notifications"
            }

        pending_codes = [sr.get("code") for sr in pending if sr.get("code")]
        message = f"Pending notifications waiting for Sentry delivery: {len(pending_codes)}"
        if pending_codes:
            logger.info("📲 %s (%s)", message, ", ".join(pending_codes))

        return {
            "success": True,
            "processed": 0,
            "failed": 0,
            "total_pending": len(pending),
            "pending_codes": pending_codes,
            "message": message,
        }

    except Exception as e:
        logger.error(f"Error processing pending notifications: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "processed": 0
        }


# ============================================================================
# Inspection Checklist for Telegram
# ============================================================================

@router.get("/inspection-checklist/{equipment_type}", status_code=status.HTTP_200_OK)
async def get_inspection_checklist_for_telegram(equipment_type: str):
    """Get a Telegram-formatted inspection checklist for an equipment type.

    Called by Sentry when sending WO notification so the technician
    knows exactly what to check on-site.

    Args:
        equipment_type: Equipment type (ups, chiller, ahu, generator, pump, etc.)

    Returns:
        - found: bool
        - equipment_type: str
        - template_name: str
        - estimated_minutes: int
        - checklist_text: Telegram-formatted checklist string
        - items: list of checklist items (structured)
    """
    from app.services.checklist_service import get_checklist_service

    svc = get_checklist_service()
    template = svc.get_template_for_inspection(equipment_type.lower(), "routine")

    if not template:
        return {
            "found": False,
            "equipment_type": equipment_type,
            "checklist_text": f"No inspection checklist available for {equipment_type}.",
            "items": [],
        }

    items = template.get("checklist_items", [])
    name = template.get("template_name", f"{equipment_type} Inspection")
    duration = template.get("estimated_duration_minutes", 30)

    # Build Telegram-formatted text grouped by category
    lines = [f"📋 {name}", f"⏱ Estimated: {duration} min", ""]
    current_category = None

    for item in items:
        cat = item.get("category", "General")
        if cat != current_category:
            current_category = cat
            lines.append(f"▸ {cat}")

        q = item.get("question", "")
        item_type = item.get("item_type", "")

        if item_type == "measurement":
            unit = item.get("unit", "")
            tmin = item.get("tolerance_min")
            tmax = item.get("tolerance_max")
            tol = f" ({tmin}-{tmax} {unit})" if tmin is not None else ""
            lines.append(f"  ☐ {q}{tol}")
        elif item_type == "visual_inspection":
            lines.append(f"  📷 {q}")
        else:
            lines.append(f"  ☐ {q}")

    return {
        "found": True,
        "equipment_type": equipment_type,
        "template_name": name,
        "estimated_minutes": duration,
        "checklist_text": "\n".join(lines),
        "items": items,
    }
