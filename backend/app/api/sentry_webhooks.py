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
import hmac
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.security.prompt_guard import score_prompt
from app.services.ocr_service import get_ocr_service
from app.services.popia_consent_guard import (
    enforce_active_processing_consent,
    evaluate_ingress_processing_consent,
)
from app.services.sentry_auth_service import get_sentry_jwt_headers
from app.services.sentry_integration.config import get_sentry_webhook_secret
from app.services.sentry_integration.ocr_correction_handler import get_ocr_correction_handler
from app.services.sentry_integration.work_order_notifier import work_order_notifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sentry", tags=["sentry"])


async def _transcribe_voice_note(voice_file_id: str) -> str | None:
    """Download a Telegram voice note and transcribe it via ElevenLabs STT.

    Args:
        voice_file_id: Telegram file_id from the voice message

    Returns:
        Transcribed text, or None if transcription failed
    """
    if not settings.telegram_bot_token:
        logger.warning("telegram_bot_token not configured — cannot download voice note")
        return None

    if not settings.elevenlabs_api_key:
        logger.warning("elevenlabs_api_key not configured — cannot transcribe voice note")
        return None

    try:
        # Step 1: Get file path from Telegram
        async with httpx.AsyncClient(timeout=30.0) as client:
            file_resp = await client.get(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
                params={"file_id": voice_file_id},
            )
        file_resp.raise_for_status()
        file_data = file_resp.json()
        if not file_data.get("ok"):
            logger.warning(f"Telegram getFile failed: {file_data}")
            return None

        file_path = file_data["result"]["file_path"]

        # Step 2: Download the audio file
        async with httpx.AsyncClient(timeout=60.0) as client:
            audio_resp = await client.get(
                f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}",
            )
        audio_resp.raise_for_status()
        audio_bytes = audio_resp.content

    except Exception as e:
        logger.error(f"Failed to download voice note {voice_file_id}: {e}")
        return None

    # Step 3: Transcribe via ElevenLabs STT
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            stt_resp = await client.post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                },
                data={"model_id": "s2t_medium"},
                files={"file": ("voice.ogg", audio_bytes, "audio/ogg")},
                timeout=60.0,
            )
        stt_resp.raise_for_status()
        result = stt_resp.json()
        text = result.get("text", "").strip()
        if text:
            logger.info(f"ElevenLabs STT transcribed {len(text)} chars")
            return text
        logger.warning(f"ElevenLabs STT returned empty text for {voice_file_id}")
        return None

    except httpx.HTTPStatusError as e:
        logger.error(f"ElevenLabs STT HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"ElevenLabs STT failed: {e}")
        return None


# Equipment types blocked from remote reset (safety-critical)
RESET_BLOCKED_TYPES = {"FIRE", "GEN"}


def _require_sentry_secret(
    provided_secret: str | None,
    *,
    endpoint_name: str,
    allow_public_in_simulation: bool = False,
) -> None:
    """Validate Sentry webhook secret with live-mode fail-closed behavior."""
    configured_secret = get_sentry_webhook_secret()

    if not configured_secret:
        if settings.is_live_mode:
            logger.error("Missing SENTRY_WEBHOOK_SECRET in live mode for endpoint %s", endpoint_name)
            raise HTTPException(status_code=503, detail="Sentry integration misconfigured")
        if allow_public_in_simulation:
            return
        return

    if allow_public_in_simulation and not settings.is_live_mode and not provided_secret:
        return

    if not provided_secret or not hmac.compare_digest(provided_secret, configured_secret):
        raise HTTPException(status_code=403, detail="Unauthorized")


def _require_sentry_secret_or_key(
    secret: str | None,
    api_key: str | None,
    *,
    endpoint_name: str,
) -> None:
    """Validate either Sentry secret or API key.

    Allow public in simulation if neither is provided.
    """
    configured_secret = get_sentry_webhook_secret()
    configured_key = os.getenv("SENTRY_BOT_API_KEY", "").strip()

    if settings.is_live_mode and not configured_secret and not configured_key:
        logger.error("Missing Sentry auth in live mode for endpoint %s", endpoint_name)
        raise HTTPException(status_code=503, detail="Sentry integration misconfigured")

    if settings.is_live_mode:
        secret_ok = secret and hmac.compare_digest(secret, configured_secret)
        key_ok = api_key and hmac.compare_digest(api_key, configured_key)
        if not secret_ok and not key_ok:
            raise HTTPException(status_code=403, detail="Unauthorized")
        return

    # Simulation: allow if any credential matches, or allow public
    if not secret and not api_key:
        return
    if secret and configured_secret and hmac.compare_digest(secret, configured_secret):
        return
    if api_key and configured_key and hmac.compare_digest(api_key, configured_key):
        return
    raise HTTPException(status_code=403, detail="Unauthorized")


def _require_operator_password(
    provided_password: str | None,
    *,
    endpoint_name: str,
) -> None:
    """Validate SENTINEL operator password for sensitive operations.

    Falls back to allow if no password is configured (backward compatibility
    in dev/simulation mode). Blocks in live mode if misconfigured.
    """
    configured_password = settings.sentinel_operator_password

    # Backward-compatible fallback: allow env var
    if not configured_password:
        configured_password = (os.getenv("SENTINEL_OPERATOR_PASSWORD", "") or "").strip()

    # If no password configured anywhere, decide based on live mode
    if not configured_password:
        if settings.is_live_mode:
            logger.error("Missing SENTINEL_OPERATOR_PASSWORD in live mode for %s", endpoint_name)
            raise HTTPException(status_code=503, detail="Sentry operator password not configured")
        # Simulation mode: skip password check
        return

    # Validate password
    if not provided_password or not hmac.compare_digest(provided_password, configured_password):
        raise HTTPException(status_code=403, detail="Invalid operator password")


def _extract_reply_text(content: Any) -> str:
    """Best-effort extraction of technician reply text from webhook payload."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "body", "caption", "message"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


class EquipmentResetRequest(BaseModel):
    """Request to remotely reset equipment fault status."""

    equipment_code: str = Field(..., description="Equipment code (e.g., S002-FCU-L1-A)")
    user_id: str = Field(..., description="User initiating the reset")
    reason: str | None = Field(None, description="Reason for reset")
    operator_password: str | None = Field(None, description="SENTINEL operator password for sensitive operations")


@router.post("/work-order/response", status_code=status.HTTP_200_OK, tags=["llm_touching"])
async def handle_work_order_response(
    data: dict[str, Any],
    x_sentry_secret: str | None = Header(None),
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
    _require_sentry_secret(x_sentry_secret, endpoint_name="work_order_response")

    # Required fields
    required_fields = ["service_record_code", "telegram_user_id", "message_type"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    reply_text = _extract_reply_text(data.get("content"))

    # --- Prompt guard: score technician reply as webhook source ---
    if reply_text:
        guard_result = score_prompt(reply_text, "webhook")
        if not guard_result.allow:
            logger.warning(
                "Sentry WO response prompt guard BLOCKED: user=%s score=%.2f",
                data.get("telegram_user_id"),
                guard_result.score,
            )
            return {
                "success": False,
                "error": "Message blocked by security filter",
                "collected_items": [],
                "is_complete": False,
            }

    consent_decision = evaluate_ingress_processing_consent(
        data_subject_id=data["telegram_user_id"],
        platform="telegram",
        message_text=reply_text,
    )
    if not consent_decision.allow_processing:
        return {
            "success": False,
            "requires_consent": True,
            "consent_status": consent_decision.status,
            "next_prompt": consent_decision.response_message,
            "collected_items": [],
            "is_complete": False,
        }

    # Handle the response
    result = await work_order_notifier.handle_technician_reply(
        data["service_record_code"],
        {
            "telegram_user_id": data["telegram_user_id"],
            "message_type": data["message_type"],
            "content": data.get("content"),
        },
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/work-order/status/{service_record_code}", response_model=dict[str, Any])
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
    data: dict[str, Any],
    x_sentry_secret: str | None = Header(None),
):
    """Send work order notification to technician via Sentry.

    Called by BMS when WO is assigned to trigger Telegram notification.

    Request body:
        - work_order_id: UUID
        - equipment_id: UUID
        - site_id: UUID
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
    _require_sentry_secret(x_sentry_secret, endpoint_name="work_order_notify")

    # Required fields
    required_fields = [
        "work_order_id",
        "equipment_id",
        "site_id",
        "equipment_name",
        "service_type",
        "technician_id",
        "technician_name",
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
        "service_record_code": result.get("service_record_code"),
    }


@router.post("/work-order/complete/{service_record_code}", status_code=status.HTTP_200_OK)
async def mark_service_record_complete(
    service_record_code: str,
    force: bool = Query(True, description="Allow completion even if some evidence items are missing"),
    x_sentry_secret: str | None = Header(None),
):
    """Mark service record as complete manually.

    Called when technician confirms completion via Sentry.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="work_order_complete")
    result = await work_order_notifier.complete_service_record(service_record_code, force=force)
    if "error" in result:
        error_code = result.get("error")
        if error_code in ("Service record not found", "Equipment not found"):
            raise HTTPException(status_code=404, detail=error_code)
        if error_code == "incomplete_data_collection":
            raise HTTPException(status_code=400, detail=result)
        raise HTTPException(status_code=500, detail=error_code)

    return {
        "success": True,
        "service_record_code": service_record_code,
        "status": result.get("status"),
        "forced": result.get("forced", False),
        "already_complete": result.get("already_complete", False),
        "completion_percentage": result.get("completion_percentage"),
        "missing_items": result.get("missing_items", []),
        "ml_processing_initiated": True,
    }


# ============================================================================
# Manager Controls: Remote Equipment Reset
# ============================================================================


@router.post("/equipment/reset", status_code=status.HTTP_200_OK)
async def reset_equipment_fault(
    request: EquipmentResetRequest,
    x_sentry_secret: str | None = Header(None),
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
    _require_sentry_secret(x_sentry_secret, endpoint_name="equipment_reset")
    _require_operator_password(request.operator_password, endpoint_name="equipment_reset")

    equipment_code = request.equipment_code

    # Extract equipment type from code (second segment: S002-FCU-L1-A → FCU)
    parts = equipment_code.split("-")
    eq_type = parts[1].upper() if len(parts) >= 2 else ""

    # Block safety-critical equipment types
    if eq_type in RESET_BLOCKED_TYPES:
        return {
            "success": False,
            "blocked": True,
            "reason": f"{eq_type} equipment cannot be remotely reset for safety reasons. Create a work order instead.",
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
        # Use provenance-formatted user_id for audit trail
        who = f"sentry:telegram:{request.user_id}" if request.user_id else "sentry"

        result = await service.execute_remote_command(
            user_id=who,
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
                "equipment_name": reset_data.get("equipment_name")
                or (equipment_info or {}).get("name", equipment_code),
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
            "reason": f"Reset failed: {e!s}",
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
    x_sentry_secret: str | None = Header(None),
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
    _require_sentry_secret(x_sentry_secret, endpoint_name="ocr_process_service_sheet")
    if not enforce_active_processing_consent(data_subject_id=data.telegram_user_id):
        raise HTTPException(
            status_code=403,
            detail="Active POPIA consent is required for Telegram OCR processing",
        )

    # Decode image
    try:
        image_b64 = data.image_base64
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        image_data = base64.b64decode(image_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid base64 image: " + str(e)) from e

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
            media_type=data.media_type,
        )

        # If needs review, start correction flow
        if result["status"] == "needs_review":
            correction_prompt = await correction_handler.start_correction_flow(
                data.service_record_id, result, data.telegram_user_id
            )
            result["correction_prompt"] = correction_prompt

            logger.info(
                f"OCR needs review for {data.service_record_id}: "
                f"{len(result.get('pipeline_info', {}).get('issues', []))} issues"
            )

        return result

    except Exception as e:
        logger.error(f"OCR processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ocr/correction", status_code=status.HTTP_200_OK)
async def submit_ocr_correction(
    data: CorrectionResponse,
    x_sentry_secret: str | None = Header(None),
):
    """Submit correction for OCR-extracted value.

    Called by Sentry when technician provides corrected value
    for a field that failed validation.

    Returns next correction prompt or completion status.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="ocr_correction")

    correction_handler = get_ocr_correction_handler()

    if not correction_handler.has_pending_correction(data.service_record_id):
        raise HTTPException(status_code=404, detail="No pending correction session for this service record")

    result = await correction_handler.process_correction_response(data.service_record_id, data.correction)

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
        return {"status": "needs_review", **correction_handler.get_correction_status(service_record_id)}

    return {"status": "unknown", "message": "No active OCR session"}


@router.get("/work-order/pending")
async def get_pending_work_orders(
    request: Request,
    x_sentry_secret: str | None = Header(None),
):
    """Get pending work orders that need Telegram notifications.

    Returns list of service records with status='notified' that are pending
    Sentry bot notification delivery. Called by Sentry bot to poll for notifications.

    Authentication: Allowed for Sentry bot (requires X-Sentry-Secret header).
    Anyone without the secret can still call this endpoint as it's PUBLIC.

    Returns:
        List of pending service records ready for notification
    """
    _require_sentry_secret(
        x_sentry_secret,
        endpoint_name="work_order_pending",
        allow_public_in_simulation=True,
    )

    service_repo = ServiceRecordRepository()

    try:
        # Get all service records with status 'notified' (awaiting notification)
        pending = await service_repo.list(filters={"status": "notified"})

        if not pending:
            return {"pending_count": 0, "work_orders": []}

        # Format for Sentry bot
        formatted_orders = []
        for sr in pending:
            formatted_orders.append(
                {
                    "service_record_code": sr.get("code"),
                    "service_record_id": sr.get("id"),
                    "technician_id": sr.get("technician_id"),
                    "technician_name": sr.get("technician_name"),
                    "equipment_id": sr.get("equipment_id"),
                    "site_id": sr.get("site_id"),
                    "service_type": sr.get("service_type"),
                    "created_at": sr.get("created_at"),
                }
            )

        logger.info(f"Sentry bot querying: {len(formatted_orders)} pending work orders")

        return {"pending_count": len(formatted_orders), "work_orders": formatted_orders}

    except Exception as e:
        logger.error(f"Error fetching pending work orders: {e}")
        return {"pending_count": 0, "work_orders": [], "error": str(e)}


@router.get("/freshness/breaches")
async def get_freshness_breaches(
    x_sentry_secret: str | None = Header(None),
):
    """Get active (unresolved) data freshness breaches.

    Returns breaches from data_freshness_breaches where resolved_at is NULL.
    Used by the dashboard notification bell to alert managers of data freshness issues.

    Authentication: Requires X-Sentry-Secret header.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="freshness_breaches")

    try:
        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()

        result = (
            supabase.table("data_freshness_breaches")
            .select("*")
            .is_("resolved_at", None)
            .order("breach_time", desc=True)
            .limit(50)
            .execute()
        )

        breaches = []
        for row in result.data or []:
            site_name = None
            if row.get("site_id"):
                site_result = supabase.table("sites").select("name").eq("id", row["site_id"]).limit(1).execute()
                site_name = site_result.data[0]["name"] if site_result.data else None
            breaches.append(
                {
                    "id": row.get("id"),
                    "site_id": row.get("site_id"),
                    "site_name": site_name,
                    "data_source": row.get("data_source"),
                    "age_seconds": row.get("age_seconds"),
                    "sli_target": row.get("sli_target"),
                    "breach_time": row.get("breach_time"),
                    "duration_seconds": row.get("duration_seconds"),
                }
            )

        return {"breach_count": len(breaches), "breaches": breaches}

    except Exception as e:
        logger.error(f"Error fetching freshness breaches: {e}")
        return {"breach_count": 0, "breaches": [], "error": str(e)}


@router.post("/process-pending-notifications", status_code=status.HTTP_200_OK)
async def process_pending_sentry_notifications(
    x_sentry_secret: str | None = Header(None),
):
    """Inspect pending notifications for Sentry delivery.

    Called by background scheduler every 30 seconds.
    This endpoint now acts as a monitor/heartbeat only and does NOT advance
    service record state.

    Status transitions must occur from real technician interaction
    (e.g., "done" reply via /work-order/response).
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="process_pending_notifications")

    service_repo = ServiceRecordRepository()
    try:
        # Get all pending notifications
        pending = await service_repo.list(filters={"status": "notified"})
        if not pending:
            return {"success": True, "processed": 0, "message": "No pending notifications"}

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
        return {"success": False, "error": str(e), "processed": 0}


# ============================================================================
# Building Handbook (GET + POST)
# ============================================================================


class BuildingHandbookPost(BaseModel):
    site_id: str
    content: str
    uploaded_by: str | None = None


@router.get("/building-handbook")
async def get_building_handbook(
    site_id: str = Query(..., description="Site ID"),
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
):
    """Fetch the building handbook for a site.

    Reads from site_handbooks table. Falls back to filesystem
    BUILDING_HANDBOOK.md if not found in DB.

    Authentication: X-Sentry-API-Key or X-Sentry-Secret header.
    """
    _require_sentry_secret_or_key(x_sentry_secret, x_sentry_api_key, endpoint_name="building-handbook")

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()

    # Try DB first
    result = (
        supabase.table("site_handbooks")
        .select("content, uploaded_by, version, updated_at")
        .eq("site_id", site_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return {
            "content": result.data[0]["content"],
            "source": "database",
            "version": result.data[0]["version"],
            "uploaded_by": result.data[0].get("uploaded_by"),
            "updated_at": result.data[0].get("updated_at"),
        }

    # Fallback: check filesystem
    handbook_path = (
        Path(__file__).parent.parent.parent.parent / "sentry-agents" / "staff-workspace" / "BUILDING_HANDBOOK.md"
    )
    if handbook_path.exists():
        return {
            "content": handbook_path.read_text(),
            "source": "filesystem",
            "version": 0,
        }

    return {"content": "", "source": "not_found", "version": 0}


@router.post("/building-handbook", status_code=status.HTTP_200_OK)
async def save_building_handbook(
    data: BuildingHandbookPost,
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
):
    """Save the building handbook for a site.

    Upserts into site_handbooks table.

    Authentication: X-Sentry-API-Key or X-Sentry-Secret header.
    """
    _require_sentry_secret_or_key(x_sentry_secret, x_sentry_api_key, endpoint_name="building-handbook")

    from datetime import UTC

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    now = datetime.now(UTC).isoformat()

    # Check if exists
    existing = supabase.table("site_handbooks").select("version").eq("site_id", data.site_id).limit(1).execute()
    next_version = (existing.data[0]["version"] + 1) if existing.data else 1

    payload = {
        "site_id": data.site_id,
        "content": data.content,
        "version": next_version,
        "updated_at": now,
    }
    if data.uploaded_by:
        payload["uploaded_by"] = data.uploaded_by

    if existing.data:
        supabase.table("site_handbooks").update(payload).eq("site_id", data.site_id).execute()
    else:
        payload["created_at"] = now
        supabase.table("site_handbooks").insert(payload).execute()

    return {"success": True, "version": next_version, "source": "database"}


@router.get("/inspection-checklist/{equipment_type}", status_code=status.HTTP_200_OK)
async def get_inspection_checklist_for_telegram(
    equipment_type: str,
    description: str | None = Query(None, description="WO description for dynamic checklist generation"),
    fault_code: str | None = Query(None, description="Optional fault code for targeted checklist"),
):
    """Get a Telegram-formatted inspection checklist for an equipment type.

    Called by Sentry when sending WO notification so the technician
    knows exactly what to check on-site.

    When `description` is provided, generates a targeted checklist
    based on the specific issue using LLM + 46-category taxonomy.
    Falls back to static template if generation fails.

    Enriches each checklist item with OEM spec context from indexed manuals
    via doc_rag_service, so the technician gets manufacturer-specific
    guidance, not generic questions.

    Args:
        equipment_type: Equipment type (ups, chiller, ahu, generator, pump, etc.)
        description: WO description for dynamic checklist generation
        fault_code: Optional fault code for targeted checklist

    Returns:
        - found: bool
        - equipment_type: str
        - template_name: str
        - estimated_minutes: int
        - checklist_text: Telegram-formatted checklist string
        - items: list of checklist items (structured) with optional oem_spec field
    """
    from app.services.checklist_service import get_checklist_service

    svc = get_checklist_service()

    # Dynamic generation when description is provided
    if description:
        generated = await svc.generate_checklist(
            equipment_type=equipment_type.lower(),
            description=description,
            fault_code=fault_code,
        )
        if generated.get("source") != "none":
            items = generated.get("items", [])
            name = generated.get("template_name", f"{equipment_type} Inspection")
            duration = generated.get("estimated_minutes", 30)
            # Skip static fallback logic — use generated result
            if items:
                return await _build_checklist_response(equipment_type, items, name, duration)

    # Static template fallback
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

    return await _build_checklist_response(equipment_type, items, name, duration)


async def _build_checklist_response(
    equipment_type: str,
    items: list[dict[str, Any]],
    name: str,
    duration: int,
) -> dict[str, Any]:
    """Build the standard checklist response with OEM enrichment and Telegram formatting."""
    # --- OEM spec enrichment via doc_rag_service ---
    oem_contexts = {}
    try:
        from app.services.doc_rag_service import search_documentation

        for item in items:
            item_id = item.get("item_id", "")
            question = item.get("description") or item.get("question", "") or ""
            if question and item_id:
                try:
                    results = await search_documentation(
                        query=f"{equipment_type} {question}",
                        n_results=2,
                        site_id=None,
                    )
                    if results and len(results) > 0:
                        spec_text = results[0].get("content", "")[:500]
                        if spec_text:
                            oem_contexts[item_id] = spec_text
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[INSPECTION] Could not enrich OEM specs: {e}")

    # Build Telegram-formatted text grouped by category
    lines = [f"📋 {name}", f"⏱ Estimated: {duration} min", ""]
    current_category = None

    for item in items:
        cat = item.get("category", "General")
        if cat != current_category:
            current_category = cat
            lines.append(f"▸ {cat}")

        item_id = item.get("item_id", "")
        item_type = item.get("item_type", "")
        q = item.get("description") or item.get("question", "") or ""
        oem_spec = oem_contexts.get(item_id, "")

        spec_hint = f" | OEM: {oem_spec[:150]}..." if oem_spec else ""
        q_with_spec = f"{q}{spec_hint}"

        if item_type == "measurement":
            unit = item.get("unit", "")
            tmin = item.get("tolerance_min")
            tmax = item.get("tolerance_max")
            tol = f" ({tmin}-{tmax} {unit})" if tmin is not None else ""
            lines.append(f"  ☐ {q_with_spec}{tol}")
        elif item_type == "visual_inspection":
            lines.append(f"  📷 {q_with_spec}")
        else:
            lines.append(f"  ☐ {q_with_spec}")

        if oem_spec:
            item["oem_spec"] = oem_spec[:300]

    return {
        "found": True,
        "equipment_type": equipment_type,
        "template_name": name,
        "estimated_minutes": duration,
        "checklist_text": "\n".join(lines),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Inspection Result Submission (Sentry-authenticated)
# ---------------------------------------------------------------------------


class SentryInspectionItem(BaseModel):
    """Single checklist item result."""

    item_id: str = Field(..., description="Checklist item ID (e.g., filter_condition)")
    question: str = Field(..., description="Question text")
    answer: str = Field(..., description="Technician's answer")
    status: str = Field("ok", description="ok, warning, or critical")


class SentryInspectionResultRequest(BaseModel):
    """Inspection result submission from Sentry bot after guided debrief."""

    equipment_code: str = Field(..., description="Equipment code (e.g., S002-FCU-301)")
    work_order_code: str = Field(..., description="WO code (e.g., WO-2026-0030)")
    technician_name: str = Field(..., description="Name of technician who performed inspection")
    telegram_user_id: str | None = Field(None, description="Telegram user ID for audit")
    items: list[SentryInspectionItem] = Field(..., description="Checklist item results")
    ai_diagnosis: str | None = Field(None, description="AI-curated diagnosis summary")
    recommendations: str | None = Field(None, description="AI recommendations for FM")
    operator_password: str | None = Field(None, description="SENTINEL operator password for sensitive operations")


@router.post("/inspection-result", status_code=status.HTTP_200_OK)
async def sentry_submit_inspection_result(
    req: SentryInspectionResultRequest,
    x_sentry_secret: str | None = Header(None),
):
    """Submit inspection results from Sentry bot after technician guided debrief.

    Stores results in inspection_results, inspection_deficiencies, and
    inspection_measurements tables. Links to equipment and work order.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="inspection_result")
    _require_operator_password(req.operator_password, endpoint_name="inspection_result")

    from app.database.repositories.inspection_repository import InspectionRepository

    try:
        inspection_repo = InspectionRepository()

        # Resolve equipment ID from code
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        eq_result = sb.table("equipment").select("id").eq("code", req.equipment_code).execute()
        if not eq_result.data:
            raise HTTPException(status_code=404, detail=f"Equipment not found: {req.equipment_code}")

        equipment_id = eq_result.data[0]["id"]

        # Build provenance
        who = req.technician_name
        if req.telegram_user_id:
            who = f"sentry:telegram:{req.telegram_user_id}"

        # Build item_results as list and count deficiencies
        item_results = []
        deficiencies = []
        deficiency_count = 0
        critical_count = 0

        for item in req.items:
            item_results.append(
                {
                    "item_id": item.item_id,
                    "question": item.question,
                    "status": item.status,
                    "measurement_value": item.answer,
                    "notes": item.answer,
                }
            )
            if item.status in ("warning", "critical"):
                deficiency_count += 1
                if item.status == "critical":
                    critical_count += 1
                deficiencies.append(
                    {
                        "equipment_id": equipment_id,
                        "deficiency_title": item.question,
                        "deficiency_description": f"{item.question}: {item.answer}",
                        "severity": item.status,
                        "category": "operational",
                        "checklist_item_id": item.item_id,
                        "work_order_id": req.work_order_code,
                        "reported_by": who,
                    }
                )

        # Determine overall status
        if critical_count > 0:
            overall_status = "fail"
        elif deficiency_count > 0:
            overall_status = "pass_with_issues"
        else:
            overall_status = "pass"

        # Create inspection task first (required FK for result)
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        task_data = {
            "task_name": f"Inspection — {req.equipment_code}",
            "task_description": f"Telegram inspection via {req.work_order_code}",
            "equipment_id": equipment_id,
            "scheduled_date": now,
            "due_date": now,
            "assigned_to": req.technician_name,
            "assigned_by": "sentry",
            "status": "completed",
            "completed_date": now,
            "completed_by": who,
            "priority": "normal",
        }
        created_task = await inspection_repo.create_inspection_task(task_data)
        task_id = str(created_task.id)

        # Create inspection result
        result_data = {
            "task_id": task_id,
            "inspected_by": who,
            "inspection_date": datetime.now(UTC).isoformat(),
            "overall_status": overall_status,
            "item_results": item_results,
            "deficiencies_found": deficiency_count,
            "critical_findings": critical_count,
            "recommendations": req.recommendations,
            "general_notes": req.ai_diagnosis,
        }
        import uuid as uuid_mod

        result_data["id"] = str(uuid_mod.uuid4())
        result_data["created_at"] = now
        result_data["updated_at"] = now
        sb.table("inspection_results").insert(result_data).execute()
        result_id = result_data["id"]

        # Create deficiency records for any warnings/criticals
        for deficiency in deficiencies:
            deficiency["id"] = str(uuid_mod.uuid4())
            deficiency["result_id"] = result_id
            deficiency["task_id"] = task_id
            deficiency["reported_date"] = now
            deficiency["updated_at"] = now
            sb.table("inspection_deficiencies").insert(deficiency).execute()

        # Update work order status to completed
        from app.database.repositories.work_order_repository import get_work_order_repository

        wo_repo = get_work_order_repository()
        wo = await wo_repo.get_work_order_by_code(req.work_order_code)
        if wo:
            await wo_repo.update_work_order(
                wo["id"],
                {
                    "status": "completed",
                    "completed_by": who,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "resolution_notes": req.ai_diagnosis,
                },
            )

        logger.info(
            "Inspection result saved: %s on %s — %s (%d deficiencies, %d critical)",
            req.work_order_code,
            req.equipment_code,
            overall_status,
            deficiency_count,
            critical_count,
        )

        return {
            "success": True,
            "inspection_id": result_id,
            "task_id": task_id,
            "equipment_code": req.equipment_code,
            "work_order_code": req.work_order_code,
            "overall_status": overall_status,
            "deficiencies_found": deficiency_count,
            "critical_findings": critical_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sentry inspection result submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Work Order Creation (Sentry-authenticated)
# ---------------------------------------------------------------------------


class SentryWorkOrderRequest(BaseModel):
    """Work order creation request from Sentry bot."""

    equipment_code: str = Field(..., description="Equipment code (e.g., S002-LUM-202-14)")
    title: str = Field(..., description="Work order title")
    description: str = Field(..., description="Full description")
    priority: str = Field("medium", description="low, medium, high, urgent, critical")
    created_by: str = Field("SENTINEL", description="Creator identifier")
    telegram_user_id: str | None = Field(None, description="Telegram user ID for audit provenance")
    assigned_to: str | None = Field(None, description="Override auto-assignment: technician name")
    operator_password: str | None = Field(None, description="SENTINEL operator password for sensitive operations")


@router.post("/create-work-order", status_code=status.HTTP_200_OK)
async def sentry_create_work_order(
    req: SentryWorkOrderRequest,
    x_sentry_secret: str | None = Header(None),
):
    """Create a work order in Supabase, authenticated via Sentry webhook secret.

    Returns the created WO with code, assigned technician, and equipment info.
    Used by Sentry bot agents for inspection WOs, health-triggered WOs, etc.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="create_work_order")
    _require_operator_password(req.operator_password, endpoint_name="create_work_order")

    from app.database.repositories.technician_repository import get_technician_repository
    from app.database.repositories.work_order_repository import get_work_order_repository

    try:
        wo_repo = get_work_order_repository()
        tech_repo = get_technician_repository()

        tech = None
        if req.assigned_to:
            # Manual override: look up technician by name
            all_techs = await tech_repo.get_all_technicians(active_only=True)
            needle = req.assigned_to.strip().lower()
            tech = next(
                (t for t in all_techs if t.get("name", "").lower() == needle),
                None,
            )
            if not tech:
                # Fuzzy: partial match
                tech = next(
                    (t for t in all_techs if needle in t.get("name", "").lower()),
                    None,
                )

        if not tech:
            # Auto-assign by equipment specialty
            tech = await tech_repo.get_technician_for_equipment_code(req.equipment_code)

        # Build provenance: include Telegram user_id when available
        who = req.created_by
        if req.telegram_user_id:
            who = f"sentry:telegram:{req.telegram_user_id}"

        wo_data = {
            "equipment_code": req.equipment_code,
            "title": req.title,
            "description": req.description,
            "priority": req.priority if req.priority != "critical" else "urgent",
            "status": "scheduled",
            "created_by": who,
        }

        if tech:
            wo_data["assigned_to"] = tech.get("name")
            wo_data["assigned_team"] = tech.get("specialty")

        created = await wo_repo.create_work_order(wo_data)

        if not created:
            raise HTTPException(status_code=500, detail="Failed to create work order")

        return {
            "success": True,
            "code": created.get("code"),
            "id": created.get("id"),
            "equipment_code": req.equipment_code,
            "equipment_name": created.get("equipment_name", req.title),
            "assigned_to": wo_data.get("assigned_to"),
            "technician_email": tech.get("email") if tech else None,
            "technician_telegram_id": tech.get("telegram_id") if tech else None,
            "priority": req.priority,
            "status": "scheduled",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sentry WO creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Call Logging — General Staff Facilities Defect Reports
# ---------------------------------------------------------------------------


class CallLogRequest(BaseModel):
    """Facilities defect report from general staff via Sentry bot."""

    site_id: str = Field(..., description="Site identifier")
    zone_id: str = Field("", description="Zone from desk mapping")
    floor: str = Field("", description="Floor level (L0, L1, L2)")
    desk_id: str = Field("", description="Desk number (e.g., 120)")
    location_text: str = Field("", description="Free-text location if no desk")
    category: str = Field(..., description="Discipline (Plumbing, Electrical, HVAC, etc.)")
    sub_category: str = Field("", description="Sub-category from fixed taxonomy")
    specialty: str = Field("general", description="Team specialty for routing")
    priority: str = Field("medium", description="Auto-classified priority")
    title: str = Field(..., description="Brief issue title")
    description: str = Field(..., description="Full description with context")
    reported_by: str = Field("", description="Reporter display name")
    reporter_telegram_id: str = Field("", description="Reporter Telegram ID")
    reporter_phone: str = Field("", description="Reporter mobile number (WhatsApp/SMS)")
    channel: str = Field("telegram", description="Source channel (telegram|whatsapp|mobile|email)")
    original_message: str = Field("", description="Raw message from user")
    operator_password: str | None = Field(None, description="SENTINEL operator password for sensitive operations")


class CallLogEscalationRequest(BaseModel):
    """Escalation for unmatched complaints that don't fit the fixed taxonomy."""

    reporter_name: str = Field("", description="Reporter display name")
    reporter_telegram_id: str = Field("", description="Reporter Telegram ID")
    original_message: str = Field(..., description="The complaint text that couldn't be classified")
    reason: str = Field("", description="Why it was escalated")
    site_id: str = Field(..., description="Site identifier")
    timestamp: str = Field("", description="ISO timestamp of the complaint")
    operator_password: str | None = Field(None, description="SENTINEL operator password for sensitive operations")


class CallLogLocationMemoryLookupResponse(BaseModel):
    """Response payload for call-log location memory lookup."""

    success: bool
    found: bool
    reporter_phone: str = ""
    reporter_telegram_id: str = ""
    reporter_name: str = ""
    site_id: str = ""
    zone_id: str = ""
    floor: str = ""
    desk_id: str = ""
    location_text: str = ""
    last_confirmed_at: str = ""
    last_work_order_code: str = ""


@router.post("/call-log", status_code=status.HTTP_200_OK)
async def sentry_call_log(
    req: CallLogRequest,
    x_sentry_secret: str | None = Header(None),
):
    """Log a facilities defect from general staff and create an inspection work order.

    Called by the Sentry bot call-logging conversation handler when a
    non-technical user (office worker, cleaner, security guard) reports
    a building issue via Telegram.

    Creates a work order, assigns a technician by specialty, and returns
    the WO reference for the user.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="call_log")

    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

        wo_repo = WorkOrderRepository()

        # Build who-provenance string
        who = f"sentry:call_log:{req.reporter_telegram_id or req.reported_by or 'unknown'}"

        # Build location string for WO
        if req.desk_id:
            location = f"Desk {req.desk_id}, {req.floor}, {req.zone_id}"
        elif req.location_text:
            location = req.location_text
        else:
            location = "Location not specified"

        # Resolve site code to UUID
        resolved_site_uuid = None
        tech = None
        try:
            from app.database.supabase_client import get_supabase_client

            sb = get_supabase_client()
            if sb:
                bld = sb.table("sites").select("id").eq("code", req.site_id).execute()
                if bld.data:
                    resolved_site_uuid = bld.data[0]["id"]

                    # Try specialty match via site_technicians (if table exists)
                    try:
                        tech_result = (
                            sb.table("site_technicians")
                            .select("specialty, technicians(id, name, email, phone, telegram_id)")
                            .eq("site_id", site_id)
                            .eq("specialty", req.specialty)
                            .eq("is_primary", True)
                            .execute()
                        )
                        if tech_result.data:
                            tech = tech_result.data[0].get("technicians", {})

                        # Fallback: general specialty
                        if not tech and req.specialty != "general":
                            tech_result = (
                                sb.table("site_technicians")
                                .select("specialty, technicians(id, name, email, phone, telegram_id)")
                                .eq("site_id", site_id)
                                .eq("specialty", "general")
                                .eq("is_primary", True)
                                .execute()
                            )
                            if tech_result.data:
                                tech = tech_result.data[0].get("technicians", {})
                    except Exception:
                        pass  # site_technicians table may not exist

                    # Last resort: any active technician with a Telegram ID
                    if not tech:
                        try:
                            tech_result = (
                                sb.table("technicians")
                                .select("id, name, email, phone, telegram_id")
                                .eq("active", True)
                                .execute()
                            )
                            # Filter to ones with telegram_id
                            with_telegram = [t for t in (tech_result.data or []) if t.get("telegram_id")]
                            if with_telegram:
                                tech = with_telegram[0]
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Technician lookup failed for call-log: {e}")

        # Map priority for WO (critical -> urgent in WO system)
        wo_priority = "urgent" if req.priority == "critical" else req.priority

        wo_data = {
            "title": req.title,
            "description": req.description,
            "priority": wo_priority,
            "status": "scheduled",
            "created_by": who,
            "service_type": "callout",
            "category": req.category,
            "notes": req.original_message,
        }

        if resolved_site_uuid:
            wo_data["site_id"] = resolved_site_uuid

        if tech:
            wo_data["assigned_to"] = tech.get("name")
            wo_data["assigned_team"] = req.specialty

        created = await wo_repo.create_work_order(wo_data)

        if not created:
            raise HTTPException(status_code=500, detail="Failed to create work order")

        wo_code = created.get("code", "pending")
        wo_uuid = created.get("id")
        assigned_name = tech.get("name", "maintenance team") if tech else "maintenance team"

        logger.info(
            f"Call log WO created: {wo_code} | "
            f"Category: {req.category} | Priority: {req.priority} | "
            f"Location: {location} | Reporter: {req.reported_by} | "
            f"Assigned: {assigned_name}"
        )

        # Staff call-log never creates a service record — only WO + notification
        notify_sent = False
        wo_notify_data = {
            "code": wo_code,
            "work_order_id": str(wo_uuid) if wo_uuid else wo_code,
            "equipment_id": req.site_id,
            "equipment_name": req.title,
            "site_id": req.site_id,
            "zone_id": req.zone_id or "",
            "desk_id": req.desk_id or "",
            "location": location,
            "technician_id": tech.get("telegram_id") if tech else None,
            "technician_name": tech.get("name") if tech else None,
            "technician_email": tech.get("email") if tech else None,
            "service_type": "callout",
            "criticality": req.priority.upper(),
            "problem_description": req.description,
            "original_message": req.original_message,
            "reported_by": req.reported_by,
            "reporter_phone": req.reporter_phone,
            "create_service_record": False,
        }
        logger.info(f"Call-log invoking notify_technician with data={wo_notify_data}")
        try:
            notify_response = await work_order_notifier.notify_technician(wo_notify_data)
            is_success = notify_response.get("success") if isinstance(notify_response, dict) else bool(notify_response)
            notify_sent = is_success and bool(notify_response)
        except Exception as e:
            logger.warning(f"Notification failed for call-log WO: {e}")

        # Persist reporter -> last confirmed location memory for next mobile report.
        location_memory_saved = False
        if req.desk_id or req.location_text or req.floor or req.zone_id:
            try:
                from app.database.repositories.reporter_location_repository import (
                    get_reporter_location_repository,
                )

                location_repo = get_reporter_location_repository()
                saved = location_repo.upsert(
                    {
                        "reporter_phone": req.reporter_phone,
                        "reporter_telegram_id": req.reporter_telegram_id,
                        "reporter_name": req.reported_by,
                        "site_id": req.site_id,
                        "zone_id": req.zone_id,
                        "floor": req.floor,
                        "desk_id": req.desk_id,
                        "location_text": location,
                        "last_work_order_code": wo_code,
                        "last_confirmed_at": datetime.utcnow().isoformat(),
                        "channel": req.channel,
                        "source": "call_log",
                    }
                )
                location_memory_saved = bool(saved)
            except Exception as e:
                logger.warning(f"Failed to persist call-log location memory: {e}")

        return {
            "success": True,
            "work_order_code": wo_code,
            "work_order_id": created.get("id"),
            "category": req.category,
            "priority": req.priority,
            "location": location,
            "assigned_to": assigned_name,
            "technician_telegram_id": tech.get("telegram_id", "") if tech else "",
            "technician_notified": notify_sent,
            "location_memory_saved": location_memory_saved,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Call log creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/call-log/location-memory", response_model=CallLogLocationMemoryLookupResponse)
async def lookup_call_log_location_memory(
    reporter_phone: str = Query("", description="Reporter mobile number"),
    reporter_telegram_id: str = Query("", description="Reporter Telegram user ID"),
    x_sentry_secret: str | None = Header(None),
):
    """Lookup the reporter's last confirmed location for call logging.

    The gateway can use this to prefill location and ask:
    \"Use Desk 208 again?\" before creating a new call/WO.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="call_log_location_memory")

    if not reporter_phone and not reporter_telegram_id:
        raise HTTPException(status_code=400, detail="Provide reporter_phone or reporter_telegram_id")

    try:
        from app.database.repositories.reporter_location_repository import (
            ReporterLocationRepository,
            get_reporter_location_repository,
        )

        repo = get_reporter_location_repository()
        memory = repo.get_latest(
            reporter_phone=reporter_phone,
            reporter_telegram_id=reporter_telegram_id,
        )

        normalized_phone = ReporterLocationRepository.normalize_phone(reporter_phone)
        if not memory:
            return CallLogLocationMemoryLookupResponse(
                success=True,
                found=False,
                reporter_phone=normalized_phone or "",
                reporter_telegram_id=reporter_telegram_id or "",
            )

        return CallLogLocationMemoryLookupResponse(
            success=True,
            found=True,
            reporter_phone=memory.get("reporter_phone") or normalized_phone or "",
            reporter_telegram_id=memory.get("reporter_telegram_id") or reporter_telegram_id or "",
            reporter_name=memory.get("reporter_name") or "",
            site_id=memory.get("site_id") or "",
            zone_id=memory.get("zone_id") or "",
            floor=memory.get("floor") or "",
            desk_id=memory.get("desk_id") or "",
            location_text=memory.get("location_text") or "",
            last_confirmed_at=memory.get("last_confirmed_at") or "",
            last_work_order_code=memory.get("last_work_order_code") or "",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Call-log location memory lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/call-log/location-memory", status_code=status.HTTP_200_OK)
async def save_call_log_location_memory(
    req: dict,
    x_sentry_secret: str | None = Header(None),
):
    """Save reporter location memory for future pre-fill.

    Called by bms_desk_wo.py after a work order is created so the
    reporter's desk is remembered for their next report.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="call_log_location_memory_save")

    try:
        from app.database.repositories.reporter_location_repository import (
            get_reporter_location_repository,
        )

        repo = get_reporter_location_repository()
        saved = repo.upsert(
            {
                "reporter_telegram_id": req.get("reporter_telegram_id", ""),
                "reporter_phone": req.get("reporter_phone", ""),
                "reporter_name": req.get("reporter_name", ""),
                "site_id": req.get("site_id", "site-002"),
                "zone_id": req.get("zone_id", ""),
                "floor": req.get("floor", ""),
                "desk_id": req.get("desk_id", ""),
                "location_text": req.get("location", ""),
                "last_work_order_code": req.get("wo_code", ""),
                "last_confirmed_at": datetime.utcnow().isoformat(),
                "channel": "telegram",
                "source": "call_log",
            }
        )
        return {"success": True, "saved": bool(saved)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Call-log location memory save failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class WoStatusResponse(BaseModel):
    """Work order status response for staff WO lookup."""

    success: bool
    found: bool
    code: str = ""
    status: str = ""
    priority: str = ""
    category: str = ""
    title: str = ""
    description: str = ""
    notes: str = ""
    assigned_to: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""


@router.get("/wo-status", response_model=WoStatusResponse)
async def sentry_wo_status(
    code: str = Query(..., description="Work order code (e.g. WO-2026-0001)"),
    reporter_telegram_id: str = Query("", description="Reporter Telegram ID for privacy filter"),
    x_sentry_secret: str | None = Header(None),
):
    """Return work order status for staff WO lookup.

    Staff can check their own WO by code. Results are filtered by reporter
    Telegram ID to ensure privacy — staff only see their own WOs.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="wo_status")

    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

        wo_repo = WorkOrderRepository()
        wo = await wo_repo.get_work_order_by_code(code)

        if not wo:
            return WoStatusResponse(success=True, found=False)

        # Privacy filter: if reporter_telegram_id is provided, verify ownership
        if reporter_telegram_id:
            created_by = wo.get("created_by", "")
            # created_by format: "sentry:call_log:{telegram_id}" or "sentry:telegram:{telegram_id}"
            if reporter_telegram_id not in created_by:
                return WoStatusResponse(success=True, found=False, code=code)

        # Also fetch equipment notes if equipment exists on the WO
        equipment_notes = ""
        equipment_id = wo.get("equipment_id")
        if equipment_id and len(str(equipment_id)) > 5:
            try:
                from app.database.supabase_client import get_supabase_client

                sb = get_supabase_client()
                eq_result = sb.table("equipment").select("notes").eq("id", equipment_id).limit(1).execute()
                if eq_result.data and eq_result.data[0].get("notes"):
                    equipment_notes = eq_result.data[0]["notes"]
            except Exception:
                pass

        notes = wo.get("notes") or ""
        if equipment_notes:
            notes = (notes + "\n" + equipment_notes).strip()

        return WoStatusResponse(
            success=True,
            found=True,
            code=wo.get("code") or "",
            status=wo.get("status") or "",
            priority=wo.get("priority") or "",
            category=wo.get("category") or "",
            title=wo.get("title") or "",
            description=wo.get("description") or "",
            notes=notes,
            assigned_to=wo.get("assigned_to") or "",
            created_at=str(wo.get("created_at") or ""),
            updated_at=str(wo.get("updated_at") or ""),
            completed_at=str(wo.get("completed_at") or ""),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WO status lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class WoMilestoneRequest(BaseModel):
    """Advance a work order's SLA milestone."""

    wo_code: str = Field(..., description="Work order code (e.g. WO-2026-0001)")
    milestone: str = Field(..., description="New milestone: assigned|in_progress|resolved|verified")
    notes: str = Field("", description="Technician notes for the work order")
    outcome: str = Field("", description="Outcome: fixed|parts_needed|escalate (for logging/context)")
    operator_password: str | None = Field(None, description="SENTINEL operator password")


class WoMilestoneResponse(BaseModel):
    """Response after advancing a work order milestone."""

    success: bool
    wo_id: str = ""
    wo_code: str = ""
    milestone_status: str = ""
    assigned_at: str = ""
    in_progress_at: str = ""
    resolved_at: str = ""
    verified_at: str = ""
    sla_deadline_at: str = ""
    status: str = ""


@router.patch("/wo-milestone", response_model=WoMilestoneResponse)
async def advance_wo_milestone(
    req: WoMilestoneRequest,
    x_sentry_secret: str | None = Header(None),
):
    """Advance a work order's SLA milestone and update notes.

    Called by technician bot after closeout inspection.
    - Resolves the SLA deadline clock
    - Updates notes with technician's findings
    - Notifies staff (via Telegram) when resolved
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="wo_milestone")

    from app.database.repositories.work_order_repository import WorkOrderRepository
    from app.services.telegram_message_sender import get_telegram_sender

    VALID_MILESTONES = {"assigned", "in_progress", "resolved", "verified"}

    if req.milestone not in VALID_MILESTONES:
        raise HTTPException(status_code=400, detail=f"Invalid milestone: {req.milestone}")

    try:
        wo_repo = WorkOrderRepository()
        wo = await wo_repo.get_work_order_by_code(req.wo_code)

        if not wo:
            raise HTTPException(status_code=404, detail=f"Work order not found: {req.wo_code}")

        wo_id = wo["id"]
        wo.get("milestone_status", "assigned")
        created_by = wo.get("created_by", "")

        # Advance milestone
        updated = await wo_repo.advance_work_order_milestone(wo_id, req.milestone)
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to advance milestone")

        # Update notes field
        existing_notes = wo.get("notes", "") or ""
        new_notes = req.notes
        if existing_notes:
            new_notes = f"{existing_notes}\n---\n{new_notes}"
        await wo_repo.update_work_order(wo_id, {"notes": new_notes})

        # Notify staff if resolved or verified
        if req.milestone in ("resolved", "verified"):
            # Extract reporter Telegram ID from created_by (format: sentry:call_log:{telegram_id})
            reporter_telegram_id = None
            if "sentry:call_log:" in created_by:
                reporter_telegram_id = created_by.split("sentry:call_log:")[-1].split(":")[0]
            elif "sentry:telegram:" in created_by:
                reporter_telegram_id = created_by.split("sentry:telegram:")[-1].split(":")[0]

            if reporter_telegram_id:
                try:
                    from app.services.telegram_message_sender import TelegramMessageSender

                    staff_bot_token = (
                        os.getenv("SENTRY_CLIENT_BOT_TOKEN") or "***TELEGRAM_BOT_TOKEN_REDACTED***"
                    )
                    sender = TelegramMessageSender(staff_bot_token)
                    outcome_emoji = {
                        "fixed": "✅",
                        "parts_needed": "⏳",
                        "escalate": "⚠️",
                    }.get(req.outcome, "✅")

                    label = "resolved" if req.milestone == "resolved" else "completed"
                    notify_text = (
                        f"{outcome_emoji} Work order {req.wo_code} {label}.\n"
                        f"Technician notes: {req.notes or 'No additional notes.'}"
                    )
                    await sender.send_text(reporter_telegram_id, notify_text)
                except Exception as notify_err:
                    logger.warning(f"Staff notification failed for WO {req.wo_code}: {notify_err}")

        # If escalated, notify manager
        if req.outcome == "escalate":
            try:
                sender = get_telegram_sender()
                escalate_text = (
                    f"⚠️ Escalation: WO {req.wo_code}\n"
                    f"Equipment: {wo.get('equipment_id', 'unknown')}\n"
                    f"Notes: {req.notes or 'No notes.'}\n"
                    f"Outcome: {req.outcome}"
                )
                await sender.send_text(8359288792, escalate_text)
            except Exception as esc_err:
                logger.warning(f"Escalation notification failed for WO {req.wo_code}: {esc_err}")

        return WoMilestoneResponse(
            success=True,
            wo_id=updated.get("id", ""),
            wo_code=updated.get("code", ""),
            milestone_status=updated.get("milestone_status", ""),
            assigned_at=_dt_iso(updated.get("assigned_at")),
            in_progress_at=_dt_iso(updated.get("in_progress_at")),
            resolved_at=_dt_iso(updated.get("resolved_at")),
            verified_at=_dt_iso(updated.get("verified_at")),
            sla_deadline_at=_dt_iso(updated.get("sla_deadline_at")),
            status="success",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WO milestone advance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _dt_iso(val) -> str:
    """Convert datetime to SAST ISO string, returns empty string for None."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    from datetime import timedelta, timezone

    sast = timezone(timedelta(hours=2))
    if val.tzinfo is None:
        val = val.replace(tzinfo=UTC)
    return val.astimezone(sast).isoformat()


@router.post("/call-log/escalate", status_code=status.HTTP_200_OK)
async def sentry_call_log_escalate(
    req: CallLogEscalationRequest,
    x_sentry_secret: str | None = Header(None),
):
    """Escalate an unmatched complaint to the facilities supervisor.

    Called by the call-log handler when a user's complaint doesn't match
    any discipline/sub-category in the fixed taxonomy. The complaint is
    logged as an anomaly and the supervisor is notified.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="call_log_escalate")
    _require_operator_password(req.operator_password, endpoint_name="call_log_escalate")

    logger.warning(
        f"[CALL_LOG_ESCALATION] Unmatched complaint from "
        f"{req.reporter_name} ({req.reporter_telegram_id}): "
        f"{req.original_message[:100]}"
    )

    # Store escalation record
    escalation_record = {
        "reporter_name": req.reporter_name,
        "reporter_telegram_id": req.reporter_telegram_id,
        "original_message": req.original_message,
        "reason": req.reason,
        "site_id": req.site_id,
        "timestamp": req.timestamp,
        "status": "pending_review",
    }

    # Try to persist to file-based log
    import json
    from pathlib import Path

    escalation_file = Path("app/data/call_log_escalations.json")
    try:
        existing = []
        if escalation_file.exists():
            existing = json.loads(escalation_file.read_text())
        existing.append(escalation_record)
        escalation_file.write_text(json.dumps(existing, indent=2))
    except Exception as e:
        logger.warning(f"Failed to persist escalation record: {e}")

    # Try to notify supervisor via Telegram
    supervisor_notified = False
    supervisor_telegram_id = os.getenv("CALL_LOG_SUPERVISOR_TELEGRAM_ID", "")
    if supervisor_telegram_id:
        try:
            notify_msg = (
                f"⚠️ CALL LOG ESCALATION\n\n"
                f"A complaint was received that doesn't match any "
                f"known discipline:\n\n"
                f"Reporter: {req.reporter_name}\n"
                f"Message: {req.original_message}\n"
                f"Site: {req.site_id}\n"
                f"Time: {req.timestamp}\n\n"
                f"Please review and follow up."
            )
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            if bot_token:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": supervisor_telegram_id,
                            "text": notify_msg,
                        },
                        timeout=10,
                    )
                supervisor_notified = True
        except Exception as e:
            logger.warning(f"Failed to notify supervisor: {e}")

    return {
        "success": True,
        "escalated": True,
        "supervisor_notified": supervisor_notified,
        "message": "Complaint flagged for supervisor review",
    }


# ============================================================================
# Telegram Conversation Flow Endpoints (Phase 147)
# ============================================================================


class TelegramMessagePayload(BaseModel):
    """Incoming Telegram message forwarded by the gateway."""

    chat_id: str
    user_id: str
    username: str = ""
    display_name: str = ""
    text: str = ""
    has_photo: bool = False
    photo_file_id: str | None = None
    has_document: bool = False
    document_file_id: str | None = None
    has_voice: bool = False
    voice_file_id: str | None = None
    message_id: int | None = None


class TelegramCallbackPayload(BaseModel):
    """Incoming Telegram callback_query forwarded by the gateway."""

    callback_query_id: str
    chat_id: str
    user_id: str
    message_id: int
    data: str


@router.post("/telegram/message", status_code=status.HTTP_200_OK)
async def handle_telegram_message(
    request: Request,
    payload: TelegramMessagePayload,
):
    """Handle incoming Telegram free-text message via conversation flow.

    The gateway forwards non-slash-command messages here for intent
    classification and multi-step conversation handling.
    """
    # Accept either header — X-Sentry-Secret (legacy) or X-Telegram-Bot-Api-Secret-Token (gateway-forwarded)
    secret = request.headers.get("X-Sentry-Secret") or request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    _require_sentry_secret(secret, endpoint_name="telegram_message")

    # Prompt guard
    if payload.text:
        guard_result = score_prompt(payload.text, "webhook")
        if not guard_result.allow:
            logger.warning(
                "Telegram message blocked by prompt guard: user=%s score=%.2f",
                payload.user_id,
                guard_result.score,
            )
            return {"success": False, "error": "Message blocked by security filter"}

    # POPIA consent check
    consent_decision = evaluate_ingress_processing_consent(
        data_subject_id=payload.user_id,
        platform="telegram",
        message_text=payload.text,
    )
    if not consent_decision.allow_processing:
        return {
            "success": False,
            "requires_consent": True,
            "consent_status": consent_decision.status,
        }

    telegram_file_id = None
    if payload.has_voice and payload.voice_file_id:
        # Voice note: transcribe via ElevenLabs STT, then process as text
        transcribed = await _transcribe_voice_note(payload.voice_file_id)
        if transcribed:
            payload.text = transcribed
            logger.info(f"Voice note transcribed for user {payload.user_id}: {transcribed[:100]}")
        else:
            return {
                "success": False,
                "error": "Failed to transcribe voice note. Please try again or send a text message.",
            }
    elif payload.has_photo and payload.photo_file_id:
        telegram_file_id = payload.photo_file_id
    elif payload.has_document and payload.document_file_id:
        telegram_file_id = payload.document_file_id

    if telegram_file_id:
        from app.services.telegram_document_intake_service import get_telegram_document_intake_service

        intake_service = get_telegram_document_intake_service()
        started = await intake_service.start_intake(
            chat_id=payload.chat_id,
            telegram_user_id=payload.user_id,
            telegram_file_id=telegram_file_id,
        )
        if not started:
            return {"success": False, "error": "Technician site mapping not configured"}
        return {
            "success": True,
            "intent": "document_intake",
            "confidence": 1.0,
        }

    from app.services.telegram_conversation_manager import get_conversation_manager

    mgr = get_conversation_manager()
    session = mgr.get_session(payload.chat_id)
    if session is not None and session.flow == "document_intake":
        from app.services.telegram_document_intake_service import get_telegram_document_intake_service

        intake_service = get_telegram_document_intake_service()
        handled = await intake_service.handle_text(
            chat_id=payload.chat_id,
            telegram_user_id=payload.user_id,
            text=payload.text,
        )
        if handled:
            return {
                "success": True,
                "intent": "document_intake",
                "confidence": 1.0,
            }

    # Classify and route
    from app.services.telegram_flow_handlers import route_to_handler
    from app.services.telegram_intent_classifier import classify_intent

    session = mgr.get_session(payload.chat_id)
    has_session = session is not None

    intent, confidence = classify_intent(payload.text, has_session)

    try:
        await route_to_handler(
            intent,
            payload.chat_id,
            payload.text,
            message_id=payload.message_id,
        )
    except Exception as e:
        logger.error("Telegram flow handler error: %s", e, exc_info=True)
        return {"success": False, "error": "Internal flow error"}

    return {
        "success": True,
        "intent": intent.value,
        "confidence": confidence,
    }


@router.post("/telegram/callback", status_code=status.HTTP_200_OK)
async def handle_telegram_callback(
    payload: TelegramCallbackPayload,
    x_sentry_secret: str | None = Header(None),
):
    """Handle incoming Telegram callback_query (inline button tap).

    The gateway forwards button presses here. We dismiss the spinner,
    classify intent with callback_data, and route to the flow handler.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="telegram_callback")

    # Dismiss spinner
    from app.services.telegram_message_sender import get_telegram_sender

    try:
        sender = get_telegram_sender()
        await sender.answer_callback_query(payload.callback_query_id)
    except Exception as e:
        logger.warning("Failed to answer callback query: %s", e)

    # Certified notification acknowledgement
    if payload.data.startswith("ack:"):
        from app.services.notification_service import notification_service

        result = await notification_service.handle_acknowledgement(
            callback_data=payload.data,
            acknowledged_by_telegram_id=payload.user_id,
        )
        if result["success"]:
            # Confirm to user
            try:
                sender = get_telegram_sender()
                await sender.send_text(
                    chat_id=payload.chat_id,
                    text="✅ Acknowledgement recorded.",
                )
            except Exception:
                pass
        return {"success": True, "intent": "certified_ack", "confirmed": result["success"]}

    # Prediction acknowledgement button (✅ Acknowledge from prediction Telegram message)
    if payload.data.startswith("pred_ack:"):
        from app.services.notification_service import notification_service

        result = await notification_service.handle_prediction_acknowledge(
            callback_data=payload.data,
            acknowledged_by_telegram_id=payload.user_id,
        )
        if result["success"]:
            try:
                sender = get_telegram_sender()
                await sender.send_text(
                    chat_id=payload.chat_id,
                    text="✅ Prediction acknowledged.",
                )
            except Exception:
                pass
        return {"success": True, "intent": "prediction_ack", "confirmed": result["success"]}

    # Prediction Create Work Order button (🛠 Create Work Order from prediction Telegram message)
    if payload.data.startswith("pred_wo:"):
        from app.services.notification_service import notification_service

        parts = payload.data.split(":", 1)
        if len(parts) == 2:
            prediction_id = parts[1]
            result = await notification_service.handle_prediction_work_order_request(
                callback_data=payload.data,
                prediction_id=prediction_id,
                requested_by_telegram_id=payload.user_id,
            )
        else:
            result = {"success": False, "error": "invalid_callback_data"}

        try:
            sender = get_telegram_sender()
            if result["success"]:
                work_order = result.get("work_order") or {}
                text = f"🛠 Work order created: {work_order.get('code', 'created')}."
            else:
                text = f"Could not create work order: {result.get('error', 'unknown_error')}"
            await sender.send_text(chat_id=payload.chat_id, text=text)
        except Exception:
            pass
        return {"success": True, "intent": "prediction_work_order", "confirmed": result["success"], "result": result}

    if payload.data.startswith("wo:"):
        from app.services.notification_service import notification_service

        result = await notification_service.handle_work_order_request(
            callback_data=payload.data,
            requested_by_telegram_id=payload.user_id,
        )
        try:
            sender = get_telegram_sender()
            if result["success"]:
                action = result.get("action")
                work_order = result.get("work_order") or {}
                if action in ("open_work_order_exists", "duplicate_work_order_exists"):
                    wo_code = work_order.get("code", "unknown")
                    if action == "duplicate_work_order_exists":
                        text = f"🛠 Duplicate work order blocked: WO {wo_code} already covers this exact action."
                    else:
                        text = f"🛠 Open work order already exists: {wo_code}."
                else:
                    wo_code = work_order.get("code", "created")
                    assigned = work_order.get("assigned_to") or "Pending"
                    priority = (work_order.get("priority") or "medium").upper()
                    text = f"Work Order Created #{wo_code}\nAssigned: {assigned}\nPriority: {priority}"
            else:
                text = f"Could not create work order: {result.get('error', 'unknown_error')}"
            await sender.send_text(chat_id=payload.chat_id, text=text)
        except Exception:
            pass
        return {"success": True, "intent": "create_work_order", "confirmed": result["success"], "result": result}

    if payload.data.startswith("docintake:"):
        from app.services.telegram_document_intake_service import get_telegram_document_intake_service

        intake_service = get_telegram_document_intake_service()
        handled = await intake_service.handle_callback(
            chat_id=payload.chat_id,
            telegram_user_id=payload.user_id,
            callback_data=payload.data,
        )
        if handled:
            return {
                "success": True,
                "intent": "document_intake",
                "confidence": 1.0,
            }

    # Residential onboarding — platform selection buttons (platform:solarman, platform:victron, etc.)
    if payload.data.startswith("platform:"):
        from app.services.sentry.residential_onboard_service import ResidentialOnboardService

        platform = payload.data.split(":", 1)[1] if ":" in payload.data else ""
        service = ResidentialOnboardService()
        service.handle_platform_callback(
            chat_id=int(payload.chat_id),
            callback_query_id=payload.callback_query_id,
            platform=platform,
        )
        return {"success": True, "intent": "residential_onboarding", "confidence": 1.0}

    # Recommendation acknowledgement from morning digest inline buttons
    if payload.data.startswith("rec:accept:") or payload.data.startswith("rec:dismiss:"):
        from app.services.recommendation_service import get_recommendation_service

        parts = payload.data.split(":")
        if len(parts) >= 3:
            rec_id = parts[2]
            acknowledgement_type = "accepted" if parts[1] == "accept" else "dismissed"
            svc = get_recommendation_service()
            await svc.acknowledge_recommendation(rec_id, acknowledgement_type)
            sender = get_telegram_sender()
            action = "Accepted" if parts[1] == "accept" else "Dismissed"
            await sender.send_text(chat_id=payload.chat_id, text=f"✅ Recommendation {action}.")
            return {"success": True, "intent": "rec_ack", "confirmed": True}
        return {"success": False, "error": "invalid_rec_callback"}

    # Classify and route
    from app.services.telegram_conversation_manager import get_conversation_manager
    from app.services.telegram_flow_handlers import route_to_handler
    from app.services.telegram_intent_classifier import classify_intent

    mgr = get_conversation_manager()
    session = mgr.get_session(payload.chat_id)
    has_session = session is not None

    intent, confidence = classify_intent("", has_session, callback_data=payload.data)

    try:
        await route_to_handler(
            intent,
            payload.chat_id,
            "",
            callback_data=payload.data,
            message_id=payload.message_id,
        )
    except Exception as e:
        logger.error("Telegram callback handler error: %s", e, exc_info=True)
        return {"success": False, "error": "Internal flow error"}

    return {
        "success": True,
        "intent": intent.value,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Gateway observability — tool-level activity log
# ---------------------------------------------------------------------------


class GatewayLogEntry(BaseModel):
    """A single gateway tool invocation record."""

    tool: str = Field(..., description="Tool name (bms_query, bms_wo, bms_inspect, bms_reset, bms_note)")
    command: str = Field(..., description="Command or action (info, summary, create_wo, reset, etc.)")
    equipment_code: str | None = Field(None, description="Equipment code if applicable")
    telegram_user_id: str = Field("unknown", description="Telegram user who triggered the action")
    success: bool = Field(True, description="Whether the tool invocation succeeded")
    error: str | None = Field(None, description="Error message if failed")
    duration_ms: int | None = Field(None, description="Tool execution time in ms")
    result_summary: str | None = Field(None, description="Short result (e.g. WO code created)")
    metadata: dict[str, Any] | None = Field(None, description="Additional context")


# In-memory ring buffer for gateway logs (last 1000 entries)
_gateway_log: list = []
_GATEWAY_LOG_MAX = 1000


@router.post("/gateway-log")
async def log_gateway_activity(
    entry: GatewayLogEntry,
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
) -> dict:
    """Record a gateway tool invocation for observability.

    Called by Sentry tool scripts (bms_query.py, bms_wo.py, etc.)
    after each command execution.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="gateway_log", allow_public_in_simulation=True)

    record = {
        "id": len(_gateway_log) + 1,
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": entry.tool,
        "command": entry.command,
        "equipment_code": entry.equipment_code,
        "telegram_user_id": entry.telegram_user_id,
        "success": entry.success,
        "error": entry.error,
        "duration_ms": entry.duration_ms,
        "result_summary": entry.result_summary,
        "metadata": entry.metadata or {},
    }

    _gateway_log.append(record)
    if len(_gateway_log) > _GATEWAY_LOG_MAX:
        _gateway_log[:] = _gateway_log[-_GATEWAY_LOG_MAX:]

    logger.info(
        "GATEWAY %s/%s equipment=%s user=%s success=%s%s",
        entry.tool,
        entry.command,
        entry.equipment_code or "-",
        entry.telegram_user_id,
        entry.success,
        f" result={entry.result_summary}" if entry.result_summary else "",
    )

    return {"logged": True}


@router.get("/gateway-log")
async def get_gateway_log(
    limit: int = Query(50, ge=1, le=500),
    tool: str | None = Query(None),
    equipment_code: str | None = Query(None),
    telegram_user_id: str | None = Query(None),
    success_only: bool | None = Query(None),
) -> dict:
    """Query recent gateway activity log entries."""
    entries = list(reversed(_gateway_log))

    if tool:
        entries = [e for e in entries if e["tool"] == tool]
    if equipment_code:
        entries = [e for e in entries if e.get("equipment_code") == equipment_code]
    if telegram_user_id:
        entries = [e for e in entries if e.get("telegram_user_id") == telegram_user_id]
    if success_only is not None:
        entries = [e for e in entries if e["success"] == success_only]

    return {
        "entries": entries[:limit],
        "total_in_buffer": len(_gateway_log),
        "showing": min(limit, len(entries)),
    }


@router.get("/rooms")
async def list_rooms(site_id: str = Query("site-002")):
    """List meeting rooms for a site."""
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return {"rooms": [], "source": "unavailable"}
        result = (
            sb.table("meeting_rooms")
            .select("*")
            .eq("site_id", site_id)
            .neq("room_type", "focus")
            .order("floor")
            .execute()
        )
        return {"rooms": result.data or [], "source": "supabase"}
    except Exception as e:
        logger.error(f"Failed to fetch rooms: {e}")
        return {"rooms": [], "source": "error"}


@router.get("/building-info")
async def get_building_info(site_id: str = Query("site-002")):
    """Get building info for a site."""
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return {"error": "unavailable"}
        result = sb.table("building_info").select("*").eq("site_id", site_id).single().execute()
        return result.data or {}
    except Exception as e:
        logger.error(f"Failed to fetch building info: {e}")
        return {}


@router.put("/building-info")
async def update_building_info(data: dict, x_sentry_secret: str | None = Header(None)):
    """Update building info for a site."""
    _require_sentry_secret(x_sentry_secret, endpoint_name="building_info")
    data.get("site_id", "site-002")
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return {"success": False, "error": "unavailable"}
        from datetime import datetime

        data["updated_at"] = datetime.now(UTC).isoformat()
        result = sb.table("building_info").upsert(data, on_conflict="site_id").execute()
        return {"success": True, "data": result.data[0] if result.data else data}
    except Exception as e:
        logger.error(f"Failed to update building info: {e}")
        return {"success": False, "error": str(e)}


@router.get("/focus-room/status")
async def focus_room_status(site_id: str = Query("site-002")):
    """Get focus room active sessions and recent history."""
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return {"error": "unavailable"}

        active = (
            sb.table("space_focus_room_sessions").select("*").is_("end_time", None).eq("site_id", site_id).execute()
        )
        recent = (
            sb.table("space_focus_room_sessions")
            .select("*")
            .eq("site_id", site_id)
            .not_.is_("end_time", None)
            .order("end_time", desc=True)
            .limit(20)
            .execute()
        )

        from datetime import datetime

        now = datetime.now(UTC)
        for s in active.data or []:
            start = s.get("start_time")
            if start:
                if isinstance(start, str):
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                else:
                    start_dt = start if start.tzinfo else start.replace(tzinfo=UTC)
                elapsed_min = (now - start_dt).total_seconds() / 60
                s["elapsed_minutes"] = round(elapsed_min, 1)
                s["nearing_limit"] = elapsed_min >= 90

        return {
            "site_id": site_id,
            "active_sessions": active.data or [],
            "recent_sessions": recent.data or [],
            "limit_minutes": 120,
        }
    except Exception as e:
        logger.error(f"Focus room status failed: {e}")
        return {"error": str(e)}


@router.get("/rooms/available")
async def available_rooms(
    site_id: str = Query("site-002"),
    date: str = Query(...),
    start_time: str = Query(...),
    end_time: str = Query(...),
    capacity: int = Query(1),
):
    """List meeting rooms available for a given date/time slot."""
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return {"error": "unavailable"}

        rooms = (
            sb.table("meeting_rooms")
            .select("*")
            .eq("site_id", site_id)
            .neq("room_type", "focus")
            .gte("capacity", capacity)
            .execute()
        )
        all_rooms = rooms.data or []

        bookings = (
            sb.table("room_bookings")
            .select("room_id,start_time,end_time")
            .eq("site_id", site_id)
            .eq("meeting_date", date)
            .execute()
        )

        booked_room_ids = set()
        for b in bookings.data or []:
            bs = b.get("start_time", "")
            be = b.get("end_time", "")
            if bs and be and start_time < be and end_time > bs:
                booked_room_ids.add(b["room_id"])

        available = [r for r in all_rooms if r.get("name") not in booked_room_ids]
        return {"available": available, "total": len(available), "booked": len(booked_room_ids)}
    except Exception as e:
        logger.error(f"Room availability failed: {e}")
        return {"error": str(e)}


@router.post("/rooms/book")
async def book_room(data: dict, x_sentry_secret: str | None = Header(None)):
    """Book a meeting room."""
    _require_sentry_secret(x_sentry_secret, endpoint_name="book_room")
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return {"success": False, "error": "unavailable"}
        result = (
            sb.table("room_bookings")
            .insert(
                {
                    "room_id": data.get("room_name"),
                    "site_id": data.get("site_id", "site-002"),
                    "booker_name": data.get("booker_name", ""),
                    "booker_email": data.get("booker_email", ""),
                    "meeting_title": data.get("meeting_title", ""),
                    "meeting_date": data.get("date"),
                    "start_time": data.get("start_time"),
                    "end_time": data.get("end_time"),
                    "attendees": data.get("attendees", 1),
                }
            )
            .execute()
        )
        return {"success": True, "booking_id": str(result.data[0]["id"])} if result.data else {"success": False}
    except Exception as e:
        logger.error(f"Room booking failed: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Residential onboarding — /connect, state check, message forwarding
# ---------------------------------------------------------------------------


@router.post("/telegram/connect")
async def handle_telegram_connect(
    payload: dict,
    x_sentry_secret: str | None = Header(None),
):
    """Initialize onboarding state machine when user sends /connect.

    Called by the gateway skill when user sends /connect.
    Creates Redis conversation state and sends platform selection keyboard.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="telegram_connect")

    from app.services.sentry.residential_onboard_service import ResidentialOnboardService

    chat_id = int(payload.get("chat_id", 0))
    if not chat_id:
        return {"success": False, "error": "chat_id required"}

    service = ResidentialOnboardService()
    result = service.handle_connect(chat_id)
    return {"success": True, "result": result}


@router.post("/telegram/check-onboarding")
async def check_onboarding_state(
    payload: dict,
    x_sentry_secret: str | None = Header(None),
):
    """Called by gateway extension before routing a text message to LLM."""
    _require_sentry_secret(x_sentry_secret, endpoint_name="check_onboarding")

    from app.services.sentry.residential_onboard_service import ResidentialOnboardService

    chat_id = int(payload.get("chat_id", 0))
    service = ResidentialOnboardService()
    state = service._state.get(chat_id)

    if state is None:
        return {"in_flow": False, "step": None}

    return {"in_flow": True, "step": state.step}


@router.post("/telegram/message")
async def handle_telegram_message(
    payload: dict,
    x_sentry_secret: str | None = Header(None),
):
    """Called by gateway extension when user is in a state machine flow."""
    _require_sentry_secret(x_sentry_secret, endpoint_name="telegram_message")

    from app.services.sentry.residential_onboard_service import ResidentialOnboardService

    chat_id = int(payload.get("chat_id", 0))
    text = payload.get("text", "").strip()
    user_id = payload.get("user_id", "")

    if not text:
        return {"handled": False}

    service = ResidentialOnboardService()
    handled = service.handle_message(chat_id, text, user_id)
    return {"handled": handled}


# ---------------------------------------------------------------------------
# Phase 220 — Telegram webhook for home bot (bypasses openclaw entirely)
# ---------------------------------------------------------------------------


@router.post("/telegram/webhook/home")
async def handle_home_bot_webhook(request: Request):
    return JSONResponse(content={"status": "ok"})
