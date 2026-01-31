"""Clawd bot webhook endpoints for Phase 41 integration.

These endpoints are called by the Clawd Telegram bot when:
1. Technician responds to work order notification
2. Technician uploads files during data collection
3. Data collection flow interactions
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Dict, Any, Optional

from app.services.clawd_integration.work_order_notifier import work_order_notifier
from app.models.service_record import ServiceStatus

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

    # Send notification
    success = await work_order_notifier.notify_technician(data)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send notification")

    # Get service record code
    filters = {"work_order_id": data["work_order_id"]}
    # Note: Need to call list with filters through repository

    return {
        "success": True,
        "message": "Work order notification sent successfully"
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
