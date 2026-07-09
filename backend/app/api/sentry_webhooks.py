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
import hashlib
import hmac
import html
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.middleware.auth_middleware import require_site_access
from app.security.prompt_guard import score_prompt
from app.services.equipment_reference_resolver import resolve_equipment_reference
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


def _derive_equipment_code_from_desk(desk_id: str, site_code: str = "site-002") -> str | None:
    """Derive serving FCU equipment code from a desk number using zone encoding.

    Zone encoding: asset IDs use format S{site_id}-FCU-{F}{ZZ} where
    F = floor digit (0=Ground, 1=L1, 2=L2)
    ZZ = zone number (01-05), derived from desk number range:
    00-19=Zone1, 20-39=Zone2, 40-59=Zone3, 60-79=Zone4, 80-99=Zone5.
    """
    if not desk_id or not desk_id.strip():
        return None
    desk_id = desk_id.strip()
    first_char = desk_id[0]
    if first_char.isdigit():
        floor_digit = int(first_char)
    elif first_char.upper() == "G":
        floor_digit = 0
    else:
        return None
    try:
        last_two = int(desk_id[-2:]) if len(desk_id) >= 2 else int(desk_id[-1])
    except ValueError:
        return None
    zone_number = (last_two // 20) + 1
    if zone_number < 1 or zone_number > 5:
        return None
    zone_code = f"{floor_digit}{zone_number:02d}"
    site_prefix = site_code.replace("-", "").upper()
    return f"{site_prefix}-FCU-{zone_code}"


def _normalise_dedupe_text(value: str | None) -> str:
    """Normalise user supplied text for short-window duplicate detection."""
    return " ".join((value or "").strip().lower().split())


def _call_log_dedupe_key(req: "CallLogRequest") -> str:
    """Stable key for the same reporter/location/issue within a short time window."""
    parts = [
        req.reporter_telegram_id or req.reported_by,
        req.site_id,
        req.desk_id or req.location_text,
        req.category,
        req.sub_category,
        _normalise_dedupe_text(req.original_message or req.description),
    ]
    material = "|".join(_normalise_dedupe_text(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _is_logical_work_order_target(target: str | None) -> bool:
    """Return true for logical advisory targets that are not physical equipment codes."""
    if not target:
        return False
    normalized = target.strip().upper().replace("_", "-")
    return normalized.startswith("SITE-") and any(
        marker in normalized
        for marker in (
            "HVAC-ZONE-SCOPE",
            "HVAC-SCHEDULE",
            "ZONE-SCOPE",
        )
    )


def _truncate_for_telegram(value: str | None, limit: int = 900) -> str:
    """Keep technician info replies inside Telegram's message size while preserving meaning."""
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _work_order_target_from_row(work_order: dict[str, Any]) -> str | None:
    """Best-effort target extraction for logical work orders."""
    for key in ("equipment_code", "equipment_id", "target_equipment"):
        value = work_order.get(key)
        if isinstance(value, str) and _is_logical_work_order_target(value):
            return value

    title = str(work_order.get("title") or "")
    match = re.search(r"(SITE-\d{3}-[A-Z0-9-]+)", title.upper())
    if match and _is_logical_work_order_target(match.group(1)):
        return match.group(1)
    return None


def _recommendation_action_text(recommendation: dict[str, Any] | None) -> str | None:
    if not recommendation:
        return None
    action = recommendation.get("action")
    if isinstance(action, dict):
        value = action.get("value")
        if value:
            return str(value)
    return None


def _format_logical_work_order_info(
    work_order: dict[str, Any],
    recommendation: dict[str, Any] | None = None,
) -> str:
    """Technician-facing action brief for logical advisory work orders."""
    wo_code = work_order.get("code") or "work order"
    rec_target = recommendation.get("target_equipment") if recommendation else None
    target = rec_target or _work_order_target_from_row(work_order) or "logical advisory target"
    action_text = (
        work_order.get("action_value")
        or _recommendation_action_text(recommendation)
        or work_order.get("description")
        or "Review the SENTINEL advisory and verify a safe scoped action."
    )
    reason = recommendation.get("reason") if recommendation else work_order.get("description")
    status = work_order.get("status") or "unknown"
    assigned_to = work_order.get("assigned_to") or "unassigned"
    assigned_team = work_order.get("assigned_team")
    assigned = f"{assigned_to} ({assigned_team})" if assigned_team else assigned_to

    lines = [
        f"<b>Work order info: {html.escape(str(wo_code))}</b>",
        "",
        "<b>Type:</b> Logical SENTINEL advisory scope, not a physical equipment lookup.",
        f"<b>Target:</b> {html.escape(str(target))}",
        f"<b>Status:</b> {html.escape(str(status))}",
        f"<b>Assigned:</b> {html.escape(str(assigned))}",
        "",
        "<b>What to do:</b>",
        html.escape(_truncate_for_telegram(str(action_text), 700)),
        "",
        "<b>Field checks:</b>",
        "1. Verify whether the building/floor/zone is actually occupied.",
        "2. Check PIR or lighting occupancy and badge/security context.",
        "3. Check CO2/IAQ before any setback decision.",
        "4. Identify only zones or floor AHUs that are verified empty.",
        "5. Do not perform a blanket HVAC shutdown while signals conflict or CO2 is high.",
        "",
        "<b>Closeout expected:</b>",
        "Record whether HVAC stayed active, or list the specific verified-empty zones/floors suitable for setback.",
    ]
    if reason:
        lines.extend(["", "<b>Why:</b>", html.escape(_truncate_for_telegram(str(reason), 900))])
    return "\n".join(lines)


async def _load_equipment_work_order_detail(
    wo_code: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    try:
        from app.database.repositories.service_record_repository import ServiceRecordRepository
        from app.database.repositories.work_order_repository import WorkOrderRepository
        from app.database.supabase_client import get_supabase_client
        from app.services.feedback_collection_service import get_feedback_collection_service
        from app.services.checklist_service import get_checklist_service

        wo_repo = WorkOrderRepository()
        work_order = await wo_repo.get_work_order_by_code(wo_code.strip().upper())
        if not work_order:
            return None, None, None, None

        equipment = None
        equipment_id = str(work_order.get("equipment_id") or "").strip()
        if equipment_id:
            sb = get_supabase_client()
            for field in ("id", "code"):
                try:
                    eq_result = (
                        sb.table("equipment")
                        .select("id, code, name, type, status")
                        .eq(field, equipment_id)
                        .limit(1)
                        .execute()
                    )
                    if eq_result.data:
                        equipment = eq_result.data[0]
                        break
                except Exception:
                    continue

        service_record = None
        try:
            sr_repo = ServiceRecordRepository()
            service_records = await sr_repo.list(filters={"work_order_id": work_order.get("id")})
            if service_records:
                service_record = next(
                    (
                        record
                        for record in service_records
                        if str(record.get("status") or "").strip().lower() != "closed"
                    ),
                    service_records[0],
                )
        except Exception as exc:
            logger.warning("Failed to load service record for WO %s: %s", wo_code, exc)

        equipment_type = str((equipment or {}).get("type") or "").strip().lower()
        checklist_template = None
        if equipment_type:
            try:
                service_type = str((service_record or {}).get("service_type") or "").strip().lower()
                if service_type:
                    feedback_template = get_feedback_collection_service().get_template(equipment_type, service_type)
                    if feedback_template:
                        checklist_template = {
                            "template_name": f"{equipment_type.title()} Service Closeout",
                            "required_items": feedback_template.required_items,
                            "optional_items": feedback_template.optional_items,
                            "prompts": feedback_template.prompts,
                        }
                if not checklist_template:
                    checklist_template = get_checklist_service().get_template_for_inspection(equipment_type, "routine")
            except Exception as exc:
                logger.warning("Failed to load checklist template for WO %s (%s): %s", wo_code, equipment_type, exc)

        return work_order, equipment, service_record, checklist_template
    except Exception as exc:
        logger.warning("Failed to load equipment work order detail for %s: %s", wo_code, exc)
        return None, None, None, None


def _format_equipment_work_order_info(
    work_order: dict[str, Any],
    equipment: dict[str, Any] | None = None,
    service_record: dict[str, Any] | None = None,
    checklist_template: dict[str, Any] | None = None,
) -> str:
    from app.services.work_order_info_renderer import build_work_order_info_text

    return build_work_order_info_text(work_order, equipment, service_record, checklist_template)


async def _load_recommendation_for_work_order(work_order: dict[str, Any]) -> dict[str, Any] | None:
    rec_id = work_order.get("recommendation_id")
    if not rec_id:
        return None
    try:
        from app.database.supabase_client import get_supabase_client

        result = (
            get_supabase_client()
            .table("recommendations")
            .select("id, target_equipment, action, reason, confidence_score, status")
            .eq("id", rec_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.warning("Failed to load recommendation %s for WO info callback: %s", rec_id, exc)
        return None


async def _find_latest_logical_work_order_code(target: str) -> str | None:
    """Resolve old /info-SITE-... buttons to the newest matching logical work order."""
    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

        normalized_target = target.upper().replace("_", "-")
        work_orders = await WorkOrderRepository().get_all_work_orders(limit=100)
        for work_order in work_orders:
            haystack = " ".join(
                str(work_order.get(key) or "")
                for key in ("code", "title", "description", "equipment_id", "action_value")
            ).upper()
            if normalized_target in haystack.replace("_", "-"):
                return str(work_order.get("code"))
    except Exception as exc:
        logger.warning("Failed to resolve logical work order for target %s: %s", target, exc)
    return None


async def _handle_work_order_info_callback(chat_id: str, wo_code: str, sender: Any) -> dict[str, Any]:
    work_order, equipment, service_record, checklist_template = await _load_equipment_work_order_detail(wo_code)
    if not work_order:
        if sender:
            await sender.send_text(chat_id=chat_id, text=f"Work order {html.escape(wo_code)} was not found.")
        return {"success": True, "intent": "work_order_info", "confirmed": False}

    recommendation = await _load_recommendation_for_work_order(work_order)
    target_equipment = recommendation.get("target_equipment") if recommendation else None
    if _is_logical_work_order_target(target_equipment or work_order.get("equipment_id") or wo_code):
        text = _format_logical_work_order_info(work_order, recommendation)
    else:
        text = _format_equipment_work_order_info(work_order, equipment, service_record, checklist_template)
    if sender:
        await sender.send_text(chat_id=chat_id, text=text)
    return {
        "success": True,
        "intent": "work_order_info",
        "confirmed": True,
        "wo_code": work_order.get("code"),
    }


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
        secret_ok = bool(secret and configured_secret and hmac.compare_digest(secret, configured_secret))
        key_ok = bool(api_key and configured_key and hmac.compare_digest(api_key, configured_key))
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


async def _require_sentry_or_site_access(
    request: Request,
    site_id: str,
    secret: str | None,
    api_key: str | None,
    *,
    endpoint_name: str,
) -> None:
    """Allow service callers by Sentry auth, and UI callers by JWT site access."""
    if secret or api_key:
        try:
            _require_sentry_secret_or_key(secret, api_key, endpoint_name=endpoint_name)
            return
        except HTTPException:
            if not request.headers.get("Authorization"):
                raise

    request.path_params["site_id"] = site_id
    await require_site_access("site_id")(request)


def _extract_supervised_approval_rec_id(text: str | None) -> str | None:
    """Extract supervised recommendation approval IDs from callback data or forwarded text."""
    raw = (text or "").strip()
    if not raw:
        return None
    exact_prefix = "approve:rec_id:"
    if raw.startswith(exact_prefix):
        return raw.split(":", 2)[-1].strip()
    match = re.search(
        r"\bapprove\b[\s:]+rec_id[\s:]+([0-9a-fA-F-]{32,36})\b",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status) or "").strip().lower()


def _format_telegram_time(value: Any) -> str:
    if not value:
        return "recorded earlier"
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def _closed_recommendation_approval_message(rec: Any) -> tuple[str, bool]:
    status_value = _status_value(getattr(rec, "status", ""))
    equipment = getattr(rec, "target_equipment", None) or "Equipment"
    action = getattr(rec, "action", None) or {}
    point = action.get("point") if isinstance(action, dict) else None
    value = action.get("value") if isinstance(action, dict) else None
    action_line = _approval_action_label(point, value) if point and value is not None else "Control action"

    if status_value in {"executed", "auto_executed"}:
        applied_at = getattr(rec, "executed_at", None) or getattr(rec, "approved_at", None)
        outcome_validated = getattr(rec, "outcome_validated", None)
        verification = (
            "Outcome verification is complete." if outcome_validated is True else "Outcome verification is pending."
        )
        return (
            f"✅ <b>Already actioned — {html.escape(str(equipment))}</b>\n"
            f"<b>Action:</b> {html.escape(action_line)}\n"
            f"<b>Applied:</b> {html.escape(_format_telegram_time(applied_at))}\n"
            f"{verification}\n"
            "No additional control action was applied.",
            True,
        )

    if status_value == "approved":
        return (
            f"✅ <b>Already approved — {html.escape(str(equipment))}</b>\n"
            f"<b>Action:</b> {html.escape(action_line)}\n"
            "The approval was already recorded. No duplicate control action was applied.",
            True,
        )

    if status_value == "expired":
        return (
            "Approval could not be completed.\n"
            "This recommendation was replaced by a newer recommendation before approval. "
            "No control action was applied from this button. Please use the latest SENTINEL recommendation.",
            False,
        )

    if status_value == "rejected":
        return (
            "Approval could not be completed.\n"
            "This recommendation was already rejected. No control action was applied.",
            False,
        )

    if status_value == "failed":
        return (
            "Approval could not be completed.\n"
            "This recommendation previously failed during execution. No duplicate control action was applied. "
            "Please log an issue for support if the action is still required.",
            False,
        )

    return (
        "Approval could not be completed.\n"
        "This recommendation is no longer pending. No control action was applied. "
        "Please use the latest SENTINEL recommendation.",
        False,
    )


def _is_no_write_control_gate_recommendation(rec: Any) -> bool:
    """Return True when approval records a safe no-write control-gate decision."""
    action = rec.action or {}
    metadata = rec.metadata or {}
    raw_source_metadata = metadata.get("source_metadata")
    source_metadata: dict[str, Any] = raw_source_metadata if isinstance(raw_source_metadata, dict) else {}
    advisory_type = action.get("advisory_type") or metadata.get("advisory_type")
    advisory_type = advisory_type or source_metadata.get("advisory_type")
    source_rule = (
        action.get("rule")
        or action.get("source_rule")
        or metadata.get("source_rule")
        or metadata.get("logical_family")
        or source_metadata.get("rule")
        or source_metadata.get("source_rule")
        or source_metadata.get("logical_family")
    )
    blocker_values = [
        action.get("blocker"),
        metadata.get("blocker"),
        source_metadata.get("blocker"),
        action.get("blockers") or action.get("blocking_reasons"),
        metadata.get("blockers") or metadata.get("blocking_reasons"),
        source_metadata.get("blockers") or source_metadata.get("blocking_reasons"),
    ]
    blockers = {
        str(blocker)
        for value in blocker_values
        for blocker in (value if isinstance(value, (list, tuple, set)) else [value])
        if blocker
    }
    return (
        advisory_type == "occupancy_conflict_control_gate"
        or source_rule == "occupancy_conflict_blocks_hvac_shutdown"
        or "occupancy_signal_conflict" in blockers
    )


async def _handle_supervised_recommendation_approval(
    *,
    chat_id: str,
    user_id: str,
    rec_uuid: str,
    sender: Any,
) -> dict[str, Any]:
    from app.database.repositories.recommendation_repository import RecommendationRepository
    from app.models.recommendation import RecommendationStatus
    from app.services.approval_service import get_approval_service
    from app.services.telegram_message_sender import InlineButton, InlineKeyboard

    async def _safe_send(
        *,
        text: str,
        keyboard: InlineKeyboard | None = None,
        parse_mode: str | None = None,
    ) -> None:
        if not sender:
            logger.warning("Telegram approval response not sent: no sender configured")
            return
        try:
            await sender.send_text(chat_id=chat_id, text=text, keyboard=keyboard, parse_mode=parse_mode)
        except Exception as exc:
            logger.warning("Telegram approval response send failed: %s", exc)

    repo = RecommendationRepository()
    rec = await repo.get_by_id(rec_uuid)
    if not rec:
        await _safe_send(
            text=(
                "Approval could not be completed.\n"
                "The recommendation is no longer available. No control action was applied."
            ),
        )
        return {"success": True, "intent": "approve_recommendation", "confirmed": False}

    if rec.status != RecommendationStatus.PENDING:
        message, confirmed = _closed_recommendation_approval_message(rec)
        await _safe_send(text=message, parse_mode="HTML")
        return {
            "success": True,
            "intent": "approve_recommendation",
            "confirmed": confirmed,
            "recommendation_id": rec_uuid,
            "status": _status_value(rec.status),
        }

    action = rec.action or {}
    if action.get("execution_blocked") or not action.get("point") or action.get("value") is None:
        if _is_no_write_control_gate_recommendation(rec):
            from app.services.recommendation_service import get_recommendation_service

            try:
                await get_recommendation_service().approve_no_write_recommendation(
                    rec_uuid,
                    f"telegram:{user_id}",
                    reason="Approved via SENTRY Telegram supervised no-write control-gate notification",
                )
            except Exception as exc:
                logger.exception(
                    "Telegram no-write recommendation approval failed: rec_id=%s user_id=%s",
                    rec_uuid,
                    user_id,
                )
                keyboard = InlineKeyboard(rows=[[InlineButton("Log issue", f"devissue:approval:{rec_uuid}")]])
                await _safe_send(
                    text=_approval_failed_message(rec.target_equipment or "Recommendation", type(exc).__name__),
                    keyboard=keyboard,
                    parse_mode="HTML",
                )
                return {
                    "success": True,
                    "intent": "approve_recommendation",
                    "confirmed": False,
                    "recommendation_id": rec_uuid,
                    "status": "error",
                    "error": type(exc).__name__,
                }

            await _safe_send(
                text=(
                    f"✅ <b>Approved — {html.escape(str(rec.target_equipment or 'Recommendation'))}</b>\n"
                    "Approved as a no-write control-gate action.\n"
                    "No BMS point was changed from Telegram."
                ),
                parse_mode="HTML",
            )
            return {
                "success": True,
                "intent": "approve_recommendation",
                "confirmed": True,
                "recommendation_id": rec_uuid,
                "status": "approved_no_write_control_gate",
            }

        keyboard = InlineKeyboard(
            rows=[
                [InlineButton("Create work order", f"wo:rec_id:{rec_uuid}")],
                [InlineButton("Log issue", f"devissue:approval:{rec_uuid}")],
            ]
        )
        await _safe_send(
            text=(
                "Approval could not be completed.\n"
                "This recommendation requires manual BMS action. No control action was applied from Telegram."
            ),
            keyboard=keyboard,
        )
        return {
            "success": True,
            "intent": "approve_recommendation",
            "confirmed": False,
            "recommendation_id": rec_uuid,
            "status": "manual_action_required",
        }

    try:
        if not _recommendation_has_verified_write_path(
            None,
            site_id=rec.site_id,
            equipment_id=rec.target_equipment,
            point_name=action.get("point"),
        ):
            logger.warning(
                "Telegram approval blocked because target write path is not verified: rec_id=%s site=%s equipment=%s point=%s",
                rec_uuid,
                rec.site_id,
                rec.target_equipment,
                action.get("point"),
            )
            keyboard = InlineKeyboard(
                rows=[
                    [InlineButton("Create work order", f"wo:rec_id:{rec_uuid}")],
                    [InlineButton("Log issue", f"devissue:approval:{rec_uuid}")],
                ]
            )
            await _safe_send(
                text=_approval_failed_message(
                    rec.target_equipment or "Equipment", "no verified writable control point"
                ),
                keyboard=keyboard,
                parse_mode="HTML",
            )
            return {
                "success": True,
                "intent": "approve_recommendation",
                "confirmed": False,
                "recommendation_id": rec_uuid,
                "status": "target_write_path_not_verified",
            }
    except Exception as readiness_err:
        logger.warning(
            "Telegram approval target write-path check failed closed: rec_id=%s site=%s error=%s",
            rec_uuid,
            rec.site_id,
            readiness_err,
        )
        keyboard = InlineKeyboard(
            rows=[
                [InlineButton("Create work order", f"wo:rec_id:{rec_uuid}")],
                [InlineButton("Log issue", f"devissue:approval:{rec_uuid}")],
            ]
        )
        await _safe_send(
            text=(
                "Approval could not be completed.\n"
                "The target control path could not be verified. No control action was applied from Telegram."
            ),
            keyboard=keyboard,
        )
        return {
            "success": True,
            "intent": "approve_recommendation",
            "confirmed": False,
            "recommendation_id": rec_uuid,
            "status": "target_write_path_check_failed",
        }

    approval_svc = get_approval_service()
    try:
        result = await approval_svc.execute_approval(
            recommendation_id=rec_uuid,
            approved_by=f"telegram:{user_id}",
            approval_notes="Approved via SENTRY Telegram supervised action notification",
        )
    except Exception as exc:
        logger.exception(
            "Telegram supervised recommendation approval crashed: rec_id=%s user_id=%s",
            rec_uuid,
            user_id,
        )
        keyboard = InlineKeyboard(rows=[[InlineButton("Log issue", f"devissue:approval:{rec_uuid}")]])
        await _safe_send(
            text=_approval_failed_message(rec.target_equipment or "Equipment"),
            keyboard=keyboard,
            parse_mode="HTML",
        )
        return {
            "success": True,
            "intent": "approve_recommendation",
            "confirmed": False,
            "recommendation_id": rec_uuid,
            "status": "error",
            "error": type(exc).__name__,
        }

    equip = rec.target_equipment or "Equipment"
    action = rec.action or {}
    point = action.get("point") or "point"
    value = action.get("value")
    if result.success:
        effect_text = _approval_effect_text(point)
        text = (
            f"✅ <b>Approved — {html.escape(str(equip))}</b>\n"
            f"<b>Action:</b> {html.escape(_approval_action_label(point, value))}\n"
            + (f"<b>Expected effect:</b> {html.escape(effect_text)}\n" if effect_text else "")
            + "Adjustment submitted via supervised control.\n"
            + "Outcome will be verified in ~30 minutes."
        )
        keyboard = None
    else:
        logger.warning(
            "Telegram supervised recommendation approval failed: rec_id=%s user_id=%s status=%s error=%s",
            rec_uuid,
            user_id,
            result.status,
            result.error_message,
        )
        text = _approval_failed_message(equip, result.error_message)
        if _is_control_path_not_ready_error(result.error_message):
            keyboard = InlineKeyboard(
                rows=[
                    [InlineButton("Create work order", f"wo:rec_id:{rec_uuid}")],
                    [InlineButton("Log issue", f"devissue:approval:{rec_uuid}")],
                ]
            )
        else:
            keyboard = InlineKeyboard(rows=[[InlineButton("Log issue", f"devissue:approval:{rec_uuid}")]])
    await _safe_send(text=text, keyboard=keyboard, parse_mode="HTML")
    return {
        "success": True,
        "intent": "approve_recommendation",
        "confirmed": result.success,
        "recommendation_id": rec_uuid,
        "status": result.status,
    }


async def _handle_supervised_recommendation_rejection(
    *,
    chat_id: str,
    user_id: str,
    rec_uuid: str,
    sender: Any,
) -> dict[str, Any]:
    from app.services.recommendation_service import get_recommendation_service

    try:
        await get_recommendation_service().reject_recommendation(
            rec_uuid,
            f"telegram:{user_id}",
            "Rejected via SENTRY Telegram supervised recommendation notification",
        )
        if sender:
            await sender.send_text(
                chat_id=chat_id,
                text="❌ Recommendation rejected. No control action was taken.",
            )
        return {
            "success": True,
            "intent": "reject_recommendation",
            "confirmed": True,
            "recommendation_id": rec_uuid,
            "status": "rejected",
        }
    except Exception as exc:
        logger.exception(
            "Telegram supervised recommendation rejection failed: rec_id=%s user_id=%s",
            rec_uuid,
            user_id,
        )
        if sender:
            await sender.send_text(
                chat_id=chat_id,
                text=f"Could not reject recommendation: {type(exc).__name__}",
            )
        return {
            "success": True,
            "intent": "reject_recommendation",
            "confirmed": False,
            "recommendation_id": rec_uuid,
            "status": "error",
            "error": type(exc).__name__,
        }


async def _handle_supervised_package_approval(
    *,
    chat_id: str,
    user_id: str,
    site_id: str,
    sender: Any,
) -> dict[str, Any]:
    from app.database.supabase_client import get_supabase_client
    from app.services.approval_service import get_approval_service
    from app.services.telegram_message_sender import InlineButton, InlineKeyboard

    client = get_supabase_client()
    rows = (
        client.table("recommendations")
        .select("id,site_id,target_equipment,action,status,timestamp")
        .eq("site_id", site_id)
        .eq("status", "pending")
        .order("timestamp", desc=True)
        .limit(8)
        .execute()
    )
    latest_ts = None
    for row in rows.data or []:
        row_ts = row.get("timestamp")
        if row_ts:
            try:
                parsed = datetime.fromisoformat(str(row_ts).replace("Z", "+00:00"))
                latest_ts = parsed if latest_ts is None or parsed > latest_ts else latest_ts
            except ValueError:
                continue
    candidates: list[dict[str, Any]] = []
    recent_since = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    for row in rows.data or []:
        if latest_ts is not None and row.get("timestamp"):
            try:
                row_ts = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
                if latest_ts - row_ts > timedelta(minutes=10):
                    continue
            except ValueError:
                pass
        action = row.get("action") or {}
        if not isinstance(action, dict):
            continue
        if action.get("execution_blocked") or not action.get("point") or action.get("value") is None:
            continue
        executed_match = (
            client.table("recommendations")
            .select("id,action")
            .eq("site_id", site_id)
            .eq("target_equipment", row.get("target_equipment"))
            .eq("status", "executed")
            .gte("timestamp", recent_since)
            .limit(20)
            .execute()
        )
        already_executed = False
        for executed_row in executed_match.data or []:
            executed_action = executed_row.get("action") or {}
            if (
                isinstance(executed_action, dict)
                and executed_action.get("point") == action.get("point")
                and str(executed_action.get("value")) == str(action.get("value"))
            ):
                already_executed = True
                break
        if already_executed:
            continue
        if not _recommendation_has_verified_write_path(
            None,
            site_id=site_id,
            equipment_id=row.get("target_equipment"),
            point_name=action.get("point"),
        ):
            continue
        candidates.append(row)

    if not candidates:
        await sender.send_text(
            chat_id=chat_id,
            text="Approval could not be completed.\nNo current executable supervised actions were ready for this site.",
        )
        return {"success": True, "intent": "approve_package", "confirmed": False, "site_id": site_id}

    approval_svc = get_approval_service()
    executed: list[str] = []
    failed: list[str] = []
    for row in candidates[:5]:
        rec_id = str(row.get("id"))
        action = row.get("action") or {}
        label = f"{row.get('target_equipment')}.{action.get('point')}"
        try:
            result = await approval_svc.execute_approval(
                recommendation_id=rec_id,
                approved_by=f"telegram:{user_id}",
                approval_notes="Approved via SENTRY Telegram supervised package approval",
            )
            if result.success:
                executed.append(label)
            else:
                failed.append(label)
        except Exception:
            logger.exception("Package approval failed for recommendation %s", rec_id)
            failed.append(label)

    text = (
        "✅ <b>Supervised package approved</b>\n"
        f"<b>Actions submitted:</b> {len(executed)}\n"
        "Expected effect: apply the coordinated sequence and verify building response on the next telemetry cycle."
    )
    if executed:
        text += "\n\nApplied:\n" + "\n".join(f"• {html.escape(item)}" for item in executed)
    if failed:
        text += "\n\nNot applied:\n" + "\n".join(f"• {html.escape(item)}" for item in failed)
        keyboard = InlineKeyboard(rows=[[InlineButton("Log issue", f"devissue:approval:{site_id}")]])
    else:
        keyboard = None
    await sender.send_text(chat_id=chat_id, text=text, keyboard=keyboard, parse_mode="HTML")
    return {
        "success": True,
        "intent": "approve_package",
        "confirmed": bool(executed) and not failed,
        "site_id": site_id,
        "executed": len(executed),
        "failed": len(failed),
    }


def _approval_failed_message(equipment: str, error_message: str | None = None) -> str:
    if _is_control_path_not_ready_error(error_message):
        return (
            "❌ <b>Approval could not be completed</b>\n"
            f"<b>Recommendation:</b> {html.escape(str(equipment or 'Equipment'))}\n"
            "This equipment is not ready for supervised control yet. "
            "No control action was applied. Create a work order for manual BMS action or log an issue for support."
        )
    return (
        "❌ <b>Approval could not be completed</b>\n"
        f"<b>Recommendation:</b> {html.escape(str(equipment or 'Equipment'))}\n"
        "The recommendation was not applied. Please try again in a moment or log an issue for support."
    )


def _parameter_type_is_writable(parameter_type: str | None) -> bool:
    text = (parameter_type or "").lower()
    if text in {"command", "setpoint", "writable"}:
        return True
    if text.startswith(("command:", "setpoint:", "writable:")):
        return True
    return any(token in text for token in ("analogoutput", "binaryoutput", "multistateoutput"))


def _approval_action_label(point: str | None, value: Any) -> str:
    point_key = str(point or "").strip().lower()
    labels = {
        "damper_position": "Open economiser damper",
        "sat_setpoint": "Set supply-air temperature setpoint",
        "chilled_water_setpoint": "Set chilled-water setpoint",
        "fan_speed": "Set fan speed",
        "setpoint": "Set temperature setpoint",
        "on_off": "Set on/off command",
    }
    label = labels.get(point_key, f"Set {str(point or 'control point').replace('_', ' ')}")
    return f"{label} to {value}"


def _approval_effect_text(point: str | None) -> str | None:
    point_key = str(point or "").strip().lower()
    if point_key == "damper_position":
        return "This brings in more cool outside air so the AHU can cool the building with less chiller load."
    if point_key == "sat_setpoint":
        return "This adjusts supply-air temperature so zones stay comfortable without unnecessary overcooling."
    if point_key == "chilled_water_setpoint":
        return "This makes chilled water warmer so the chiller compressor works less while cooling remains available."
    if point_key == "fan_speed":
        return "This changes airflow and fan energy; zone temperatures will be monitored for comfort drift."
    if point_key in {"setpoint", "temperature_setpoint", "zone_setpoint"}:
        return "This changes the zone target temperature and should reduce heating or cooling demand if comfort remains stable."
    return None


def _recommendation_has_verified_write_path(
    client: Any | None,
    *,
    site_id: str,
    equipment_id: str | None,
    point_name: str | None,
) -> bool:
    equipment_code = _clean_equipment_code(equipment_id)
    requested_point = str(point_name or "").strip().lower()
    if not equipment_code or not requested_point:
        return False

    if client is None:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()

    config_rows = (
        client.table("site_adapter_config")
        .select("protocol,connection_config")
        .eq("site_id", site_id)
        .eq("enabled", True)
        .execute()
    )
    has_write_adapter = False
    for row in config_rows.data or []:
        protocol = str(row.get("protocol") or "").strip().lower()
        config = row.get("connection_config") or {}
        if protocol in {"bacnet", "knx", "modbus", "obix"}:
            has_write_adapter = True
            break
        if protocol == "bridge" and config.get("supports_writes") is True and config.get("write_enabled") is True:
            has_write_adapter = True
            break
    if not has_write_adapter:
        return False

    site_row = client.table("sites").select("id").eq("code", site_id).limit(1).execute()
    if not site_row.data:
        return False

    mapping_rows = (
        client.table("point_asset_mappings")
        .select("bms_point_id,parameter_name,parameter_type")
        .eq("site_id", site_row.data[0]["id"])
        .eq("extracted_asset_id", equipment_code)
        .eq("is_verified", True)
        .execute()
    )
    for mapping in mapping_rows.data or []:
        if not _parameter_type_is_writable(mapping.get("parameter_type")):
            continue
        parameter_name = str(mapping.get("parameter_name") or "").strip().lower()
        bms_point_id = str(mapping.get("bms_point_id") or "").strip().lower()
        suffix = bms_point_id.rsplit(".", 1)[-1] if "." in bms_point_id else bms_point_id
        if requested_point in {parameter_name, suffix}:
            return True
    return False


def _clean_equipment_code(value: str | None) -> str:
    return str(value or "").strip().strip("*`").upper()


def _is_control_path_not_ready_error(error_message: str | None) -> bool:
    error_text = (error_message or "").lower()
    return (
        "no adapter registered" in error_text
        or "not found or not connected" in error_text
        or "no adapter for equipment" in error_text
        or "writable whitelist" in error_text
        or "not in the writable whitelist" in error_text
        or "bridge adapter write returned false" in error_text
        or "403 forbidden" in error_text
    )


def _developer_issue_recipient() -> str:
    for env_name in (
        "SENTRY_DEVELOPER_EMAIL",
        "SENTINEL_DEVELOPER_EMAIL",
        "DEVELOPER_ALERT_EMAIL",
        "SUPPORT_EMAIL",
    ):
        value = (os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return "support@sentinel-ai.co.za"


def _closeout_status_keyboard() -> Any:
    from app.services.telegram_message_sender import InlineButton, InlineKeyboard

    return InlineKeyboard(
        rows=[
            [
                InlineButton("OK", "closeout:item:ok"),
                InlineButton("Warning", "closeout:item:warning"),
                InlineButton("Critical", "closeout:item:critical"),
            ]
        ]
    )


def _closeout_notes_keyboard() -> Any:
    from app.services.telegram_message_sender import InlineButton, InlineKeyboard

    return InlineKeyboard(rows=[[InlineButton("Skip notes/photos", "closeout:notes:skip")]])


def _closeout_item_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("item_id") or item.get("id") or item.get("key") or f"item_{index + 1}")


def _closeout_item_question(item: dict[str, Any]) -> str:
    return str(item.get("question") or item.get("description") or item.get("label") or "Checklist item")


async def _find_active_closeout_session(telegram_user_id: str) -> dict[str, Any] | None:
    from app.database.supabase_client import get_supabase_client

    sb = get_supabase_client()
    result = (
        sb.table("sentry_inspection_sessions")
        .select("*")
        .eq("telegram_user_id", str(telegram_user_id))
        .in_("status", ["in_progress", "awaiting_notes"])
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def _update_closeout_session(session_id: str, updates: dict[str, Any]) -> None:
    from app.database.supabase_client import get_supabase_client

    sb = get_supabase_client()
    payload = {**updates, "updated_at": datetime.now(UTC).isoformat()}
    sb.table("sentry_inspection_sessions").update(payload).eq("id", session_id).execute()


async def _send_closeout_item_prompt(chat_id: str, session: dict[str, Any], sender: Any) -> None:
    items = session.get("checklist_items") or []
    index = int(session.get("current_index") or 0)
    if index >= len(items):
        await sender.send_text(
            chat_id=chat_id,
            text="All checklist items recorded. Any final notes or photos to add?",
            keyboard=_closeout_notes_keyboard(),
            parse_mode="HTML",
        )
        return

    item = items[index]
    total = len(items)
    question = _closeout_item_question(item)
    text = f"Item {index + 1}/{total}: {html.escape(question)}"
    await sender.send_text(chat_id=chat_id, text=text, keyboard=_closeout_status_keyboard(), parse_mode="HTML")


def _build_closeout_summary(
    session: dict[str, Any],
    *,
    final_notes: str = "",
    photo_refs: list[str] | None = None,
) -> tuple[list[Any], str, str, str]:
    items = session.get("checklist_items") or []
    responses = session.get("responses") or {}
    result_items: list[SentryInspectionItem] = []
    warnings: list[str] = []
    criticals: list[str] = []
    skipped: list[str] = []

    for index, item in enumerate(items):
        item_id = _closeout_item_id(item, index)
        question = _closeout_item_question(item)
        response = responses.get(item_id) or {}
        status_value = str(response.get("status") or "").lower()
        answer = str(response.get("answer") or status_value or "").strip()
        if status_value not in {"ok", "warning", "critical"}:
            status_value = "skipped"
            answer = "NOT INSPECTED [SKIPPED]"
            skipped.append(question)
        elif status_value == "warning":
            warnings.append(question)
        elif status_value == "critical":
            criticals.append(question)
        result_items.append(
            SentryInspectionItem(
                item_id=item_id,
                question=question,
                answer=answer,
                status=status_value,
            )
        )

    if criticals:
        outcome = "escalate"
        diagnosis = "Critical findings recorded: " + "; ".join(criticals)
        recommendations = (
            "Escalate for follow-up work and verify the affected equipment before returning it to normal service."
        )
    elif warnings:
        outcome = "parts_needed"
        diagnosis = "Warning findings recorded: " + "; ".join(warnings)
        recommendations = "Schedule follow-up maintenance for the warning items and monitor equipment operation."
    else:
        outcome = "fixed"
        diagnosis = "All inspected checklist items passed. No abnormal findings were recorded."
        recommendations = "No follow-up required from this closeout."

    if skipped:
        diagnosis += "\nSkipped/not inspected: " + "; ".join(skipped)
    if final_notes:
        diagnosis += f"\nTechnician notes: {final_notes}"
    if photo_refs:
        diagnosis += "\nPhoto/document references: " + ", ".join(photo_refs)

    return result_items, diagnosis, recommendations, outcome


async def _finalize_closeout_session(
    *,
    chat_id: str,
    telegram_user_id: str,
    sender: Any,
    final_notes: str = "",
    photo_refs: list[str] | None = None,
) -> dict[str, Any]:
    session = await _find_active_closeout_session(telegram_user_id)
    if not session:
        await sender.send_text(chat_id=chat_id, text="No active closeout session found.")
        return {"success": True, "intent": "closeout", "confirmed": False}

    items, diagnosis, recommendations, outcome = _build_closeout_summary(
        session,
        final_notes=final_notes,
        photo_refs=photo_refs,
    )
    equipment_code = session.get("equipment_code") or ""
    wo_code = session.get("wo_code") or ""

    tech = None
    try:
        from app.database.repositories.technician_repository import get_technician_repository

        tech = await get_technician_repository().get_technician_by_telegram_id(str(telegram_user_id))
    except Exception:
        logger.warning("Could not resolve technician for closeout finalisation: %s", telegram_user_id)
    technician_name = (tech or {}).get("name") or str(telegram_user_id)

    try:
        await sentry_submit_inspection_result(
            SentryInspectionResultRequest(
                equipment_code=equipment_code,
                work_order_code=wo_code,
                technician_name=technician_name,
                telegram_user_id=str(telegram_user_id),
                items=items,
                ai_diagnosis=diagnosis,
                recommendations=recommendations,
            ),
            x_sentry_secret=get_sentry_webhook_secret(),
        )
        await advance_wo_milestone(
            WoMilestoneRequest(
                wo_code=wo_code,
                milestone="resolved",
                notes=diagnosis,
                outcome=outcome,
                operator_password="",
            ),
            x_sentry_secret=get_sentry_webhook_secret(),
        )
        await _update_closeout_session(str(session["id"]), {"status": "completed", "current_index": len(items)})
    except Exception:
        logger.exception("Closeout finalisation failed for %s", wo_code)
        await sender.send_text(
            chat_id=chat_id,
            text="I couldn't complete the closeout sync right now. Please try again in a moment.",
        )
        return {"success": True, "intent": "closeout", "confirmed": False}

    await sender.send_text(
        chat_id=chat_id,
        text=f"Closeout completed for {html.escape(wo_code)}. Results saved and the work order was updated.",
        parse_mode="HTML",
    )
    return {"success": True, "intent": "closeout", "confirmed": True, "wo_code": wo_code}


async def _handle_closeout_callback(
    *,
    chat_id: str,
    telegram_user_id: str,
    callback_data: str,
    sender: Any,
) -> dict[str, Any]:
    parts = callback_data.split(":")
    if len(parts) < 3:
        await sender.send_text(chat_id=chat_id, text="Closeout action was not recognised.")
        return {"success": True, "intent": "closeout", "confirmed": False}

    action = parts[1]
    value = parts[2]

    if action == "notes" and value == "skip":
        return await _finalize_closeout_session(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            sender=sender,
        )

    if action != "item" or value not in {"ok", "warning", "critical"}:
        await sender.send_text(chat_id=chat_id, text="Closeout action was not recognised.")
        return {"success": True, "intent": "closeout", "confirmed": False}

    session = await _find_active_closeout_session(telegram_user_id)
    if not session:
        await sender.send_text(chat_id=chat_id, text="No active closeout session found.")
        return {"success": True, "intent": "closeout", "confirmed": False}
    if session.get("status") != "in_progress":
        await sender.send_text(
            chat_id=chat_id,
            text="All checklist items are recorded. Add final notes/photos, or tap Skip notes/photos.",
            keyboard=_closeout_notes_keyboard(),
        )
        return {"success": True, "intent": "closeout", "confirmed": False}

    items = session.get("checklist_items") or []
    index = int(session.get("current_index") or 0)
    if index >= len(items):
        await _update_closeout_session(str(session["id"]), {"status": "awaiting_notes"})
        await sender.send_text(
            chat_id=chat_id,
            text="All checklist items recorded. Any final notes or photos to add?",
            keyboard=_closeout_notes_keyboard(),
            parse_mode="HTML",
        )
        return {"success": True, "intent": "closeout", "confirmed": True}

    item = items[index]
    item_id = _closeout_item_id(item, index)
    responses = session.get("responses") or {}
    responses[item_id] = {
        "answer": value,
        "status": value,
        "source": "telegram_inline_button",
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    next_index = index + 1
    updates: dict[str, Any] = {"responses": responses, "current_index": next_index}
    if next_index >= len(items):
        updates["status"] = "awaiting_notes"
    await _update_closeout_session(str(session["id"]), updates)

    updated_session = {**session, **updates}
    if next_index >= len(items):
        await sender.send_text(
            chat_id=chat_id,
            text="All checklist items recorded. Any final notes or photos to add?",
            keyboard=_closeout_notes_keyboard(),
            parse_mode="HTML",
        )
    else:
        await _send_closeout_item_prompt(chat_id, updated_session, sender)
    return {"success": True, "intent": "closeout", "confirmed": True, "status": value}


def _extract_done_work_order_code(text: str | None) -> str | None:
    value = (text or "").strip()
    match = re.match(r"^/(?:done)[-_](WO-\d{4}-\d+)\b", value, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.match(r"^done\s+#?(WO-\d{4}-\d+)\b", value, re.IGNORECASE)
    return match.group(1).upper() if match else None


async def _start_closeout_session_from_done_command(
    *,
    chat_id: str,
    telegram_user_id: str,
    wo_code: str,
    sender: Any,
) -> dict[str, Any]:
    from app.database.supabase_client import get_supabase_client

    work_order, equipment, _service_record, _checklist_template = await _load_equipment_work_order_detail(wo_code)
    if not work_order:
        await sender.send_text(chat_id=chat_id, text=f"Work order {html.escape(wo_code)} was not found.")
        return {"success": True, "intent": "closeout_start", "confirmed": False}

    equipment_code = str((equipment or {}).get("code") or work_order.get("equipment_code") or "").strip()
    equipment_type = str((equipment or {}).get("type") or work_order.get("equipment_type") or "").strip().lower()
    if not equipment_type:
        await sender.send_text(
            chat_id=chat_id,
            text=f"I couldn't resolve the equipment type for {html.escape(wo_code)}. Please use /info-{html.escape(wo_code)}.",
        )
        return {"success": True, "intent": "closeout_start", "confirmed": False}

    checklist = await get_inspection_checklist_for_telegram(equipment_type)
    items = checklist.get("items") or []
    if not items:
        await sender.send_text(
            chat_id=chat_id,
            text=f"No closeout feedback template is configured for {html.escape(equipment_type)}.",
        )
        return {"success": True, "intent": "closeout_start", "confirmed": False}

    payload: dict[str, Any] = {
        "wo_code": wo_code,
        "telegram_user_id": str(telegram_user_id),
        "equipment_code": equipment_code,
        "equipment_type": equipment_type,
        "checklist_items": items,
        "responses": {},
        "current_index": 0,
        "status": "in_progress",
        "updated_at": datetime.now(UTC).isoformat(),
    }
    sb = get_supabase_client()
    sb.table("sentry_inspection_sessions").upsert(payload, on_conflict="wo_code, telegram_user_id").execute()

    equipment_label = equipment_code or "equipment"
    template_name = checklist.get("template_name") or f"{equipment_type.title()} Service Closeout"
    first_question = _closeout_item_question(items[0])
    text = (
        f"Starting closeout for {html.escape(wo_code)} "
        f"({html.escape(equipment_label)}, {html.escape(equipment_type.title())}).\n\n"
        f"{html.escape(str(template_name))} — {len(items)} items\n\n"
        f"Item 1/{len(items)}: {html.escape(first_question)}"
    )
    await sender.send_text(chat_id=chat_id, text=text, keyboard=_closeout_status_keyboard(), parse_mode="HTML")
    return {"success": True, "intent": "closeout_start", "confirmed": True, "wo_code": wo_code}


async def _handle_telegram_developer_issue(
    *,
    chat_id: str,
    user_id: str,
    rec_uuid: str,
    sender: Any,
) -> dict[str, Any]:
    from app.database.repositories.recommendation_repository import RecommendationRepository
    from app.services.email_reply_service import get_email_reply_service

    repo = RecommendationRepository()
    rec = None
    try:
        rec = await repo.get_by_id(rec_uuid)
    except Exception:
        logger.exception("Could not load recommendation while logging Telegram approval issue: %s", rec_uuid)

    recipient = _developer_issue_recipient()
    subject = f"[SENTINEL] Telegram approval issue {rec_uuid[:8]}"
    now = datetime.now(UTC).isoformat()
    equipment = getattr(rec, "target_equipment", None) or "unknown"
    site_id = getattr(rec, "site_id", None) or "unknown"
    action = getattr(rec, "action", None) or {}
    status_value = getattr(rec, "status", None) or "unknown"
    body_plain = (
        "A Telegram manager logged an approval issue.\n\n"
        f"Time: {now}\n"
        f"Recommendation ID: {rec_uuid}\n"
        f"Recommendation status: {status_value}\n"
        f"Site: {site_id}\n"
        f"Equipment: {equipment}\n"
        f"Action: {action}\n"
        f"Telegram chat ID: {chat_id}\n"
        f"Telegram user ID: {user_id}\n\n"
        "No control action was confirmed to the user."
    )

    email_sent = False
    try:
        email_service = get_email_reply_service()
        if email_service.is_configured():
            result = await email_service.send_reply(
                to_email=recipient,
                to_name="Sentinel Support",
                subject=subject,
                body_plain=body_plain,
                body_html=None,
            )
            email_sent = result.sent
            if not result.sent:
                logger.warning("Telegram approval issue email was not sent: %s", result.error)
        else:
            logger.warning(
                "Telegram approval issue logged but email service is not configured: rec_id=%s recipient=%s",
                rec_uuid,
                recipient,
            )
    except Exception:
        logger.exception("Failed to email Telegram approval issue: rec_id=%s recipient=%s", rec_uuid, recipient)

    logger.error(
        "Telegram approval issue logged: rec_id=%s user_id=%s chat_id=%s site_id=%s equipment=%s email_sent=%s",
        rec_uuid,
        user_id,
        chat_id,
        site_id,
        equipment,
        email_sent,
    )

    if email_sent:
        text = "Issue logged. Support has been notified. No control action was applied."
    else:
        text = "Issue logged for support review. No control action was applied."
    await sender.send_text(chat_id=chat_id, text=text, parse_mode="HTML")
    return {
        "success": True,
        "intent": "log_developer_issue",
        "recommendation_id": rec_uuid,
        "email_sent": email_sent,
    }


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
                "equipment_name": equipment_code,
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


def _is_technician_open_work_order(wo: dict[str, Any]) -> bool:
    """Technician-facing WO state is binary: open or closed."""
    status_value = str(wo.get("status") or "").strip().lower()
    milestone = str(wo.get("milestone_status") or "").strip().lower()
    if status_value in {"closed", "completed", "complete", "cancelled", "canceled"}:
        return False
    if milestone in {"resolved", "verified", "closed", "completed"}:
        return False
    if wo.get("closed_at") or wo.get("completed_at"):
        return False
    return True


def _classify_sentry_work_order(wo: dict[str, Any], equipment_code: str | None = None) -> dict[str, str]:
    """Return stable Sentry type/tier labels for bot detail and closeout routing."""
    created_by = str(wo.get("created_by") or "").lower()
    title = str(wo.get("title") or "").lower()
    description = str(wo.get("description") or "").lower()
    category = str(wo.get("category") or "").lower()
    service_type = str(wo.get("service_type") or "").lower()
    action_point = str(wo.get("action_point") or "").strip()

    if action_point:
        return {"work_order_type": "Advisory", "closeout_tier": "advisory"}

    is_staff = "sentry:call_log:" in created_by or service_type == "callout"
    comfort_terms = ("comfort", "too hot", "too cold", "aircon", "air con", "temperature", "hvac")
    is_comfort = category in {"hvac", "air conditioning", "comfort"} or any(
        term in title or term in description for term in comfort_terms
    )
    if is_staff and is_comfort:
        return {"work_order_type": "Staff comfort complaint", "closeout_tier": "comfort"}

    if is_staff:
        return {"work_order_type": "Staff reported issue", "closeout_tier": "general"}

    if equipment_code:
        return {"work_order_type": "Equipment fault", "closeout_tier": "equipment"}

    return {"work_order_type": "General task", "closeout_tier": "general"}


def _normalise_work_order_row(wo: dict[str, Any], equipment: dict[str, Any] | None = None) -> dict[str, Any]:
    equipment = equipment or {}
    equipment_code = equipment.get("code")
    labels = _classify_sentry_work_order(wo, equipment_code)
    return {
        **wo,
        "equipment_code": equipment_code,
        "equipment_name": equipment_code,
        "equipment_type": equipment.get("type"),
        "technician_status": "open" if _is_technician_open_work_order(wo) else "closed",
        **labels,
    }


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


@router.get("/work-order/open")
async def get_open_work_orders_for_technician(
    x_sentry_secret: str | None = Header(None),
    telegram_id: str | None = Query(None, description="Technician Telegram ID"),
    limit: int = Query(25, ge=1, le=100),
):
    """Return technician-visible open work orders.

    Unlike /work-order/pending, this is not notification polling. It is the
    Tech bot queue: open means actionable by the technician; closed/resolved
    work orders are excluded.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="work_order_open")

    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository
        from app.database.supabase_client import get_supabase_client

        wo_repo = WorkOrderRepository()
        query = (
            wo_repo.client.table("work_orders")
            .select(wo_repo._DETAIL_COLUMNS)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if telegram_id:
            try:
                query = query.eq("notified_technician_telegram_id", int(telegram_id))
            except ValueError:
                query = query.eq("notified_technician_telegram_id", telegram_id)
        result = query.execute()
        rows = [wo for wo in (result.data or []) if _is_technician_open_work_order(wo)]

        equipment_ids = [wo.get("equipment_id") for wo in rows if wo.get("equipment_id")]
        equipment_map: dict[str, dict[str, Any]] = {}
        if equipment_ids:
            sb = get_supabase_client()
            eq_result = (
                sb.table("equipment").select("id, code, name, type").in_("id", list(set(equipment_ids))).execute()
            )
            equipment_map = {row["id"]: row for row in (eq_result.data or [])}

        formatted = [_normalise_work_order_row(wo, equipment_map.get(wo.get("equipment_id"))) for wo in rows]
        return {"open_count": len(formatted), "work_orders": formatted}

    except Exception as e:
        logger.error(f"Error fetching open work orders: {e}")
        return {"open_count": 0, "work_orders": [], "error": str(e)}


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
    request: Request,
    site_id: str = Query(..., description="Site ID"),
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
):
    """Fetch the building handbook for a site.

    Reads from site_handbooks table. Falls back to filesystem
    BUILDING_HANDBOOK.md if not found in DB.

    Authentication: X-Sentry-API-Key/X-Sentry-Secret header or JWT with site access.
    """
    await _require_sentry_or_site_access(
        request,
        site_id,
        x_sentry_secret,
        x_sentry_api_key,
        endpoint_name="building-handbook",
    )

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
    request: Request,
    data: BuildingHandbookPost,
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
):
    """Save the building handbook for a site.

    Upserts into site_handbooks table.

    Authentication: X-Sentry-API-Key/X-Sentry-Secret header or JWT with site access.
    """
    await _require_sentry_or_site_access(
        request,
        data.site_id,
        x_sentry_secret,
        x_sentry_api_key,
        endpoint_name="building-handbook",
    )

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
    from app.services.feedback_collection_service import get_feedback_collection_service
    from app.services.work_order_info_renderer import render_service_feedback_checklist

    svc = get_checklist_service()

    if not isinstance(description, str):
        description = None
    if not isinstance(fault_code, str):
        fault_code = None

    description_l = (description or "").strip().lower()
    is_planned_or_service_closeout = any(
        term in description_l
        for term in (
            "maintenance",
            "maintenance work order",
            "planned maintenance",
            "preventive maintenance",
            "preventative maintenance",
            "ppm",
            "service sheet",
            "major service",
            "minor service",
        )
    )
    has_fault_context = bool(fault_code) or any(
        term in description_l
        for term in (
            "alarm",
            "breakdown",
            "fault",
            "failure",
            "failed",
            "leak",
            "trip",
            "tripped",
            "urgent",
        )
    )

    # Dynamic generation only for targeted fault descriptions. Generic
    # maintenance/service closeouts must use the service-feedback contract.
    if description and has_fault_context and not is_planned_or_service_closeout:
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

    # Static fallback: use service-closeout feedback for technician WO closeout.
    feedback_svc = get_feedback_collection_service()
    feedback_template = feedback_svc.get_template(equipment_type.lower(), "callout") or feedback_svc.get_template(
        equipment_type.lower(), "minor"
    )
    if feedback_template:
        items = []
        for item_key in feedback_template.required_items:
            items.append(
                {
                    "category": "Closeout feedback",
                    "item_id": item_key,
                    "question": feedback_template.prompts.get(item_key) or item_key.replace("_", " ").title(),
                    "item_type": "checklist",
                }
            )
        for item_key in feedback_template.optional_items:
            items.append(
                {
                    "category": "Closeout feedback",
                    "item_id": item_key,
                    "question": feedback_template.prompts.get(item_key) or item_key.replace("_", " ").title(),
                    "item_type": "checklist",
                    "optional": True,
                }
            )
        name = f"{equipment_type.title()} Service Closeout"
        duration = feedback_template.audio_duration_seconds or 30
        checklist_text = render_service_feedback_checklist(
            {
                "template_name": name,
                "required_items": feedback_template.required_items,
                "optional_items": feedback_template.optional_items,
                "prompts": feedback_template.prompts,
            }
        )
        return {
            "found": True,
            "equipment_type": equipment_type,
            "template_name": name,
            "estimated_minutes": duration,
            "checklist_text": checklist_text,
            "items": items,
        }

    template = svc.get_template_for_inspection(equipment_type.lower(), "routine")
    if not template:
        return {
            "found": False,
            "equipment_type": equipment_type,
            "checklist_text": f"No closeout feedback available for {equipment_type}.",
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
    from app.services.work_order_info_renderer import render_telegram_checklist

    checklist_text = render_telegram_checklist(
        {"template_name": name, "estimated_duration_minutes": duration, "checklist_items": items}, oem_contexts
    )

    for item in items:
        item_id = item.get("item_id", "")
        oem_spec = oem_contexts.get(item_id, "")
        if oem_spec:
            item["oem_spec"] = oem_spec[:300]

    return {
        "found": True,
        "equipment_type": equipment_type,
        "template_name": name,
        "estimated_minutes": duration,
        "checklist_text": checklist_text,
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


class SentryInspectionReading(BaseModel):
    """Structured numeric reading captured during a Sentry closeout."""

    item_id: str = Field(..., description="Checklist/measurement item ID")
    value: float = Field(..., description="Numeric reading value")
    unit: str | None = Field(None, description="Measurement unit")
    element_id: str | None = Field(None, description="Baseline element ID; defaults to item_id")
    raw_text: str | None = Field(None, description="Original technician/OCR text")
    attachment_id: str | None = Field(None, description="Optional service_attachments.id reference")
    captured_at: datetime | None = Field(None, description="Capture timestamp")
    source: str = Field("manual", description="manual, ocr, or sensor")
    confidence: float | None = Field(None, ge=0, le=1, description="Extraction confidence")


class SentryInspectionReadingsRequest(BaseModel):
    """Structured readings submission from Sentry bot after /done."""

    service_record_id: str | None = Field(None, description="Existing service_records.id")
    work_order_code: str | None = Field(None, description="WO code used to resolve service record")
    equipment_code: str | None = Field(None, description="Equipment code used to resolve latest service record")
    readings: list[SentryInspectionReading] = Field(..., min_length=1)


class SentryInspectionAttachment(BaseModel):
    """File reference captured during a Sentry closeout."""

    file_id: str | None = Field(None, description="Telegram file_id or document id")
    file_type: str | None = Field(None, description="Source file type")
    attachment_type: str | None = Field(None, description="service_sheet, issue_photo, thermal_image, etc.")
    file_path: str | None = Field(None, description="Stored path or Telegram path")
    file_name: str | None = Field(None, description="Original filename")
    file_size_bytes: int | None = Field(None, ge=0)
    mime_type: str | None = Field(None)
    ocr_processed: bool = Field(False)
    captured_at: datetime | None = Field(None)


class SentryInspectionAttachmentsRequest(BaseModel):
    """Attachment submission from Sentry bot after /done."""

    service_record_id: str | None = Field(None, description="Existing service_records.id")
    work_order_code: str | None = Field(None, description="WO code used to resolve service record")
    equipment_code: str | None = Field(None, description="Equipment code used to resolve latest service record")
    attachments: list[SentryInspectionAttachment] = Field(..., min_length=1)


async def _resolve_sentry_service_record(
    *,
    service_record_id: str | None,
    work_order_code: str | None,
    equipment_code: str | None,
) -> dict[str, Any]:
    """Resolve a service record for Sentry capture endpoints."""
    sr_repo = ServiceRecordRepository()
    if service_record_id:
        record = await sr_repo.get_by_id(service_record_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Service record not found: {service_record_id}")
        return record

    if work_order_code:
        from app.database.repositories.work_order_repository import get_work_order_repository

        wo_repo = get_work_order_repository()
        work_order = await wo_repo.get_work_order_by_code(work_order_code.strip().upper())
        if not work_order:
            raise HTTPException(status_code=404, detail=f"Work order not found: {work_order_code}")
        records = await sr_repo.list(filters={"work_order_id": work_order["id"]})
        if records:
            return next(
                (
                    record
                    for record in records
                    if str(record.get("status") or "").strip().lower() not in {"closed", "complete"}
                ),
                records[0],
            )

    if equipment_code:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        equipment_result = sb.table("equipment").select("id").eq("code", equipment_code).limit(1).execute()
        if not equipment_result.data:
            raise HTTPException(status_code=404, detail=f"Equipment not found: {equipment_code}")
        records = await sr_repo.list(filters={"equipment_id": equipment_result.data[0]["id"]})
        if records:
            return records[0]

    raise HTTPException(
        status_code=404,
        detail="Service record could not be resolved from service_record_id, work_order_code, or equipment_code",
    )


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


@router.post("/inspection-readings", status_code=status.HTTP_200_OK)
async def sentry_submit_inspection_readings(
    req: SentryInspectionReadingsRequest,
    x_sentry_secret: str | None = Header(None),
):
    """Persist structured closeout readings and roll them into a periodic baseline."""
    _require_sentry_secret(x_sentry_secret, endpoint_name="inspection_readings")

    try:
        service_record = await _resolve_sentry_service_record(
            service_record_id=req.service_record_id,
            work_order_code=req.work_order_code,
            equipment_code=req.equipment_code,
        )
        sr_repo = ServiceRecordRepository()
        persisted = []
        for reading in req.readings:
            captured_at = reading.captured_at or datetime.now(UTC)
            data = {
                "reading_type": reading.item_id,
                "element_id": reading.element_id or reading.item_id,
                "value": str(reading.value),
                "numeric_value": reading.value,
                "unit": reading.unit,
                "source": reading.source,
                "confidence": reading.confidence,
                "captured_at": captured_at.isoformat(),
                "raw_text": reading.raw_text,
                "attachment_id": reading.attachment_id,
            }
            data = {key: value for key, value in data.items() if value is not None}
            persisted.append(await sr_repo.add_reading(service_record["id"], data))

        from app.services.equipment_baseline_rollup_service import EquipmentBaselineRollupService

        rollup = await EquipmentBaselineRollupService().rollup_service_record(service_record["id"])
        return {
            "success": True,
            "service_record_id": service_record["id"],
            "readings_written": len(persisted),
            "reading_ids": [row.get("id") for row in persisted if row.get("id")],
            "rollup": rollup,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Sentry inspection readings submission failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inspection-attachments", status_code=status.HTTP_200_OK)
async def sentry_submit_inspection_attachments(
    req: SentryInspectionAttachmentsRequest,
    x_sentry_secret: str | None = Header(None),
):
    """Persist closeout file references without changing inspection-result contract."""
    _require_sentry_secret(x_sentry_secret, endpoint_name="inspection_attachments")

    try:
        service_record = await _resolve_sentry_service_record(
            service_record_id=req.service_record_id,
            work_order_code=req.work_order_code,
            equipment_code=req.equipment_code,
        )
        sr_repo = ServiceRecordRepository()
        persisted = []
        for attachment in req.attachments:
            if not attachment.file_id and not attachment.file_path:
                raise HTTPException(status_code=400, detail="Each attachment requires file_id or file_path")
            captured_at = attachment.captured_at or datetime.now(UTC)
            data = {
                "service_record_id": service_record["id"],
                "attachment_type": attachment.attachment_type,
                "file_path": attachment.file_path,
                "file_name": attachment.file_name,
                "file_size_bytes": attachment.file_size_bytes,
                "mime_type": attachment.mime_type,
                "file_id": attachment.file_id,
                "file_type": attachment.file_type,
                "captured_at": captured_at.isoformat(),
                "ocr_processed": attachment.ocr_processed,
            }
            data = {key: value for key, value in data.items() if value is not None}
            persisted.append(await sr_repo.add_attachment(data))

        return {
            "success": True,
            "service_record_id": service_record["id"],
            "attachments_written": len(persisted),
            "attachment_ids": [row.get("id") for row in persisted if row.get("id")],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Sentry inspection attachments submission failed: %s", e, exc_info=True)
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

        equipment = await resolve_equipment_reference(req.equipment_code)

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

        if equipment:
            wo_data["equipment_id"] = equipment["id"]
            wo_data["site_id"] = equipment.get("site_id")
            wo_data["equipment_code"] = equipment.get("code") or req.equipment_code

        if tech:
            wo_data["assigned_to"] = tech.get("name")
            wo_data["assigned_team"] = tech.get("specialty")
            if tech.get("telegram_id"):
                wo_data["notified_technician_telegram_id"] = int(tech["telegram_id"])  # type: ignore[assignment]

        created = await wo_repo.create_work_order(wo_data)

        if not created:
            raise HTTPException(status_code=500, detail="Failed to create work order")

        # Notify technician via Telegram (in-band, like /call-log)
        try:
            wo_notify_data: dict[str, Any] = {
                "work_order_id": created.get("id"),
                "work_order_code": created.get("code"),
                "equipment_id": equipment["id"] if equipment else "00000000-0000-0000-0000-000000000001",
                "site_id": equipment.get("site_id", "") if equipment else "",
                "zone_id": "",
                "equipment_code": equipment.get("code") if equipment else req.equipment_code,
                "equipment_name": equipment.get("name")
                if equipment and equipment.get("name")
                else (equipment.get("code") if equipment else req.equipment_code),
                "service_type": "callout",
                "criticality": req.priority.upper(),
                "problem_description": req.description,
                "original_message": req.description,
                "reported_by": req.created_by,
            }
            if tech:
                wo_notify_data["technician_id"] = tech.get("telegram_id")
                wo_notify_data["technician_name"] = tech.get("name", "Technician")
                wo_notify_data["technician_email"] = tech.get("email", "")
            notify_response = await work_order_notifier.notify_technician(wo_notify_data)
            technician_notified = (
                bool(notify_response.get("success")) if isinstance(notify_response, dict) else bool(notify_response)
            )
        except Exception as e:
            logger.warning(f"Technician notification failed for WO {created.get('code')}: {e}")
            technician_notified = False

        return {
            "success": True,
            "code": created.get("code"),
            "id": created.get("id"),
            "equipment_code": req.equipment_code,
            "equipment_name": req.equipment_code,
            "assigned_to": wo_data.get("assigned_to"),
            "technician_email": tech.get("email") if tech else None,
            "technician_telegram_id": tech.get("telegram_id") if tech else None,
            "technician_notified": technician_notified,
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
        dedupe_key = _call_log_dedupe_key(req)
        tech = None

        # Build location string for WO
        if req.desk_id:
            location = f"Desk {req.desk_id}, {req.floor}, {req.zone_id}"
        elif req.location_text:
            location = req.location_text
        else:
            location = "Location not specified"

        # Idempotency guard: staff bot conversations can occasionally repeat the
        # final confirmation/tool call. Reuse the recent WO instead of creating
        # and notifying a duplicate for the same reporter/location/issue.
        try:
            cutoff = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
            existing_result = (
                wo_repo.client.table("work_orders")
                .select("id, code, title, assigned_to, created_at, notes, status")
                .eq("created_by", who)
                .neq("status", "cancelled")
                .gte("created_at", cutoff)
                .execute()
            )
            for existing in existing_result.data or []:
                note_text = existing.get("notes") or ""
                if f"call_log_dedupe_key={dedupe_key}" in note_text:
                    logger.info(
                        "Duplicate call-log suppressed: reporter=%s existing_wo=%s",
                        req.reporter_telegram_id or req.reported_by,
                        existing.get("code"),
                    )
                    return {
                        "success": True,
                        "duplicate_suppressed": True,
                        "work_order_code": existing.get("code"),
                        "work_order_id": existing.get("id"),
                        "category": req.category,
                        "priority": req.priority,
                        "location": location,
                        "assigned_to": existing.get("assigned_to") or "maintenance team",
                        "technician_telegram_id": tech.get("telegram_id", "") if tech else "",
                        "technician_notified": False,
                        "location_memory_saved": False,
                    }
        except Exception as e:
            logger.warning("Call-log dedupe lookup failed; continuing with create: %s", e)

        # Resolve site code to UUID
        resolved_site_uuid = None
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
                            .eq("site_id", resolved_site_uuid)
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
                                .eq("site_id", resolved_site_uuid)
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
            "notes": f"{req.original_message}\ncall_log_dedupe_key={dedupe_key}",
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
            "equipment_name": req.site_id,
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
            "equipment_code": (_derive_equipment_code_from_desk(req.desk_id, req.site_id) or "")
            if req.specialty in ("hvac", "HVAC")
            or req.category in ("HVAC", "hvac", "Air Conditioning", "air conditioning")
            else "",
        }
        logger.info(f"Call-log invoking notify_technician with data={wo_notify_data}")
        try:
            notify_response = await work_order_notifier.notify_technician(wo_notify_data)
            is_success = notify_response.get("success") if isinstance(notify_response, dict) else bool(notify_response)
            notify_sent = bool(is_success and notify_response)
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
    display_status: str = ""
    staff_summary: str = ""
    priority: str = ""
    category: str = ""
    title: str = ""
    description: str = ""
    notes: str = ""
    assigned_to: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    resolved_at: str = ""
    closed_at: str = ""


def _staff_work_order_status(wo: dict[str, Any]) -> tuple[str, str]:
    """Return staff-safe status and summary."""
    status_value = str(wo.get("status") or "").strip().lower()
    milestone = str(wo.get("milestone_status") or "").strip().lower()

    if wo.get("closed_at") or wo.get("completed_at") or status_value in {"closed", "completed", "complete"}:
        return "Closed", "This work order has been formally closed."
    if milestone in {"resolved", "verified"} or wo.get("resolved_at"):
        return "Resolved", "The technician has resolved the issue. Manager closure is still pending."
    return "Open", "This work order is still being handled."


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
        display_status, staff_summary = _staff_work_order_status(wo)

        return WoStatusResponse(
            success=True,
            found=True,
            code=wo.get("code") or "",
            status=wo.get("status") or "",
            display_status=display_status,
            staff_summary=staff_summary,
            priority=wo.get("priority") or "",
            category=wo.get("category") or "",
            title=wo.get("title") or "",
            description=wo.get("description") or "",
            notes=notes,
            assigned_to=wo.get("assigned_to") or "",
            created_at=str(wo.get("created_at") or ""),
            updated_at=str(wo.get("updated_at") or ""),
            completed_at=str(wo.get("completed_at") or ""),
            resolved_at=str(wo.get("resolved_at") or ""),
            closed_at=str(wo.get("closed_at") or ""),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WO status lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/work-order/detail")
async def sentry_work_order_detail(
    code: str = Query(..., description="Work order code (e.g. WO-2026-0001)"),
    x_sentry_secret: str | None = Header(None),
):
    """Return full work order details including resolved equipment_code.

    Used by the technician closeout skill after `/done-WO-XXXX`.
    Joins equipment table to return equipment_code alongside WO fields.
    Sentry-authenticated (bot-level), no JWT required.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="work_order_detail")

    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

        wo_repo = WorkOrderRepository()
        wo = await wo_repo.get_work_order_by_code(code)

        if not wo:
            return {"success": False, "found": False, "error": "Work order not found"}

        equipment = None
        equipment_id = wo.get("equipment_id")
        if equipment_id:
            try:
                from app.database.supabase_client import get_supabase_client

                sb = get_supabase_client()
                if sb:
                    eq_result = (
                        sb.table("equipment").select("id, code, name, type").eq("id", equipment_id).limit(1).execute()
                    )
                    if eq_result.data:
                        equipment = eq_result.data[0]
            except Exception:
                pass

        enriched = _normalise_work_order_row(wo, equipment)

        return {
            "success": True,
            "found": True,
            "work_order": enriched,
            "equipment_code": enriched.get("equipment_code"),
            "equipment_name": enriched.get("equipment_name"),
            "equipment_type": enriched.get("equipment_type"),
            "work_order_type": enriched.get("work_order_type"),
            "closeout_tier": enriched.get("closeout_tier"),
            "technician_status": enriched.get("technician_status"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Work order detail lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Inspection Session Persistence (Tier 3 checklist state recovery)
# ---------------------------------------------------------------------------


class InspectionSessionRequest(BaseModel):
    """Upsert an in-progress inspection session for the closeout skill."""

    wo_code: str = Field(..., description="Work order code")
    telegram_user_id: str = Field(..., description="Technician Telegram user ID")
    equipment_code: str | None = Field(None, description="Equipment code")
    equipment_type: str | None = Field(None, description="Equipment type")
    checklist_items: list[dict[str, Any]] = Field(default_factory=list, description="Checklist items")
    responses: dict[str, Any] = Field(default_factory=dict, description="Per-item responses so far")
    current_index: int = Field(0, description="0-based index of next unanswered item")


class InspectionSessionResponse(BaseModel):
    """Inspection session lookup response."""

    success: bool
    found: bool = False
    session: dict[str, Any] | None = None


@router.post("/inspection-session", status_code=status.HTTP_200_OK)
async def upsert_inspection_session(
    req: InspectionSessionRequest,
    x_sentry_secret: str | None = Header(None),
):
    """Persist inspection session state so progress survives openclaw restart.

    Called after each answered checklist item. Upserts on (wo_code, telegram_user_id).
    The closeout skill checks for an existing session on startup to resume mid-checklist.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="inspection_session")

    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return {"success": False, "error": "Supabase unavailable"}

        payload = {
            "wo_code": req.wo_code,
            "telegram_user_id": req.telegram_user_id,
            "equipment_code": req.equipment_code,
            "equipment_type": req.equipment_type,
            "checklist_items": req.checklist_items,
            "responses": req.responses,
            "current_index": req.current_index,
            "status": "in_progress",
            "updated_at": datetime.now(UTC).isoformat(),
        }

        # Upsert on unique constraint (wo_code, telegram_user_id)
        result = (
            sb.table("sentry_inspection_sessions").upsert(payload, on_conflict="wo_code, telegram_user_id").execute()
        )

        return {"success": True, "session_id": result.data[0]["id"] if result.data else None}

    except Exception as e:
        logger.error(f"Inspection session upsert failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/inspection-session", response_model=InspectionSessionResponse)
async def get_inspection_session(
    wo_code: str = Query(..., description="Work order code"),
    telegram_user_id: str = Query(..., description="Technician Telegram user ID"),
    x_sentry_secret: str | None = Header(None),
):
    """Retrieve an existing inspection session for resume.

    Returns the session if it exists and is in_progress. Completed or abandoned
    sessions are returned with found=False so the closeout skill starts fresh.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="inspection_session")

    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return InspectionSessionResponse(success=False)

        result = (
            sb.table("sentry_inspection_sessions")
            .select("*")
            .eq("wo_code", wo_code)
            .eq("telegram_user_id", telegram_user_id)
            .execute()
        )

        if result.data and len(result.data) > 0:
            session = result.data[0]
            if session.get("status") == "in_progress":
                return InspectionSessionResponse(success=True, found=True, session=session)

        return InspectionSessionResponse(success=True, found=False)

    except Exception as e:
        logger.error(f"Inspection session lookup failed: {e}")
        return InspectionSessionResponse(success=False)


class WoMilestoneRequest(BaseModel):
    """Request to advance a work order SLA milestone."""

    wo_code: str = Field(..., description="Work order code (e.g., WO-2026-0001)")
    milestone: str = Field(..., description="Target milestone: assigned|in_progress|resolved|verified")
    notes: str = Field("", description="Technician notes / findings to append")
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


class TechnicianFollowUpRequest(BaseModel):
    """Manager-triggered follow-up message to a technician."""

    technician_telegram_id: str | None = Field(None, description="Technician Telegram chat ID")
    technician_name: str | None = Field(None, description="Technician name fallback")
    message: str = Field(..., min_length=1, description="Message to send to the technician")
    wo_code: str = Field("", description="Related work order code")
    source: str = Field("fm_agent", description="Source identifier for audit")


class WorkOrderReassignRequest(BaseModel):
    """Manager-triggered work-order reassignment."""

    wo_code: str = Field(..., description="Work order code, e.g. WO-2026-0012")
    technician_name: str = Field(..., description="Target active technician name")
    reason: str = Field("", description="Reason for reassignment")
    notify_technician: bool = Field(True, description="Send Telegram assignment notice when possible")
    source: str = Field("fm_agent", description="Source identifier for audit")


@router.get("/bot-state")
async def get_bot_state(
    key: str = Query(..., description="State key (e.g. 'optimization-check', 'health-alert')"),
    x_sentry_secret: str | None = Header(None),
) -> dict:
    """Fetch persisted bot tool state by key.

    Used by bms_optimization_check.py and sentinel_health_alert.py to restore
    deduplication state across restarts.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="bot_state_get")
    from app.database.supabase_client import get_async_supabase_client

    client = await get_async_supabase_client()
    result = await client.table("sentry_bot_state").select("value").eq("key", key).maybe_single().execute()
    if not result.data:
        return {"found": False, "key": key, "value": None}
    return {"found": True, "key": key, "value": result.data["value"]}


@router.post("/bot-state", status_code=200)
async def set_bot_state(
    request: Request,
    x_sentry_secret: str | None = Header(None),
) -> dict:
    """Upsert persisted bot tool state.

    Body: {"key": str, "value": any JSON-serialisable object}
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="bot_state_set")
    body = await request.json()
    key = body.get("key")
    value = body.get("value")
    if not key:
        raise HTTPException(status_code=422, detail="key is required")

    from app.database.supabase_client import get_async_supabase_client

    client = await get_async_supabase_client()
    await (
        client.table("sentry_bot_state")
        .upsert({"key": key, "value": value, "updated_at": "now()"}, on_conflict="key")
        .execute()
    )
    return {"status": "ok", "key": key}


@router.get("/technician")
async def get_technician_by_telegram(
    telegram_id: str = Query(..., description="Technician's Telegram user ID"),
    x_sentry_secret: str | None = Header(None),
) -> dict:
    """Look up a technician record by Telegram user ID.

    Used by Sentry bot during inspection closeout to resolve the display name
    of the person sending the message. Returns name or null — caller falls back
    to the raw telegram_id if no record is found.
    """
    _require_sentry_secret(x_sentry_secret, endpoint_name="technician_lookup")
    from app.database.repositories.technician_repository import get_technician_repository

    repo = get_technician_repository()
    tech = await repo.get_technician_by_telegram_id(telegram_id)
    if not tech:
        return {"found": False, "name": None, "telegram_id": telegram_id}
    return {"found": True, "name": tech.get("name"), "telegram_id": telegram_id}


@router.post("/send-technician-message", status_code=status.HTTP_200_OK)
async def send_technician_message(
    req: TechnicianFollowUpRequest,
    x_sentry_secret: str | None = Header(None),
    x_sentry_api_key: str | None = Header(None),
) -> dict:
    """Send a manager-approved follow-up message through the technician bot."""
    _require_sentry_secret_or_key(x_sentry_secret, x_sentry_api_key, endpoint_name="send_technician_message")

    from app.database.supabase_client import get_supabase_client
    from app.services.telegram_message_sender import TelegramMessageSender

    telegram_id = req.technician_telegram_id
    technician_name = req.technician_name or ""
    sb = get_supabase_client()

    if not telegram_id and technician_name:
        tech_result = (
            sb.table("technicians")
            .select("name, telegram_id")
            .ilike("name", technician_name)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        if tech_result.data:
            technician_name = tech_result.data[0].get("name") or technician_name
            telegram_id = tech_result.data[0].get("telegram_id")

    if not telegram_id:
        raise HTTPException(status_code=404, detail="Technician Telegram ID not found")
    if not settings.sentry_tech_bot_token:
        raise HTTPException(status_code=503, detail="Technician bot token is not configured")

    prefix = f"{req.wo_code} — " if req.wo_code else ""
    message = f"{prefix}{req.message}".strip()
    sender = TelegramMessageSender(settings.sentry_tech_bot_token)
    result = await sender.send_text(str(telegram_id), message, parse_mode=None)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=f"Telegram send failed: {result}")

    try:
        sb.table("notification_delivery_log").insert(
            {
                "notification_type": "technician_follow_up",
                "channel_type": "telegram",
                "recipient_identifier": str(telegram_id),
                "status": "sent",
                "provider": "telegram",
                "sent_at": datetime.now(UTC).isoformat(),
                "message_text": message,
                "delivery_status": "sent",
                "reference_type": "work_order",
                "reference_id": req.wo_code,
                "severity": "info",
            }
        ).execute()
    except Exception as exc:
        logger.warning("Technician follow-up audit write failed for %s: %s", req.wo_code, exc)

    return {
        "success": True,
        "sent": True,
        "technician_name": technician_name,
        "technician_telegram_id": str(telegram_id),
        "wo_code": req.wo_code,
    }


@router.patch("/work-order/reassign", status_code=status.HTTP_200_OK)
async def reassign_work_order(
    req: WorkOrderReassignRequest,
    x_sentry_secret: str | None = Header(None),
    x_sentry_api_key: str | None = Header(None),
) -> dict:
    """Reassign an existing work order to another active technician."""
    _require_sentry_secret_or_key(x_sentry_secret, x_sentry_api_key, endpoint_name="work_order_reassign")

    from app.database.repositories.work_order_repository import WorkOrderRepository
    from app.database.supabase_client import get_supabase_client
    from app.services.telegram_message_sender import TelegramMessageSender

    wo_repo = WorkOrderRepository()
    wo = await wo_repo.get_work_order_by_code(req.wo_code.strip().upper())
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    sb = get_supabase_client()
    tech_result = (
        sb.table("technicians")
        .select("id, name, specialty, telegram_id")
        .ilike("name", req.technician_name.strip())
        .eq("active", True)
        .limit(1)
        .execute()
    )
    if not tech_result.data:
        raise HTTPException(status_code=404, detail=f"Active technician not found: {req.technician_name}")

    technician = tech_result.data[0]
    now_iso = datetime.now(UTC).isoformat()
    previous = wo.get("assigned_to") or ""
    note_parts = []
    if wo.get("notes"):
        note_parts.append(str(wo["notes"]))
    reason = req.reason.strip() or "Manager reassignment"
    note_parts.append(f"{now_iso}: Reassigned from {previous or 'unassigned'} to {technician['name']} ({reason}).")

    updates: dict[str, Any] = {
        "assigned_to": technician["name"],
        "assigned_team": technician.get("specialty") or wo.get("assigned_team"),
        "status": "scheduled",
        "milestone_status": "assigned",
        "assigned_at": now_iso,
        "updated_at": now_iso,
        "notes": "\n".join(note_parts),
    }
    if technician.get("telegram_id"):
        try:
            updates["notified_technician_telegram_id"] = int(technician["telegram_id"])
        except (TypeError, ValueError):
            pass

    updated = await wo_repo.update_work_order(wo["id"], updates)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update work order assignment")

    notification_sent = False
    telegram_id = technician.get("telegram_id")
    if req.notify_technician and telegram_id and settings.sentry_tech_bot_token:
        message = (
            f"{updated.get('code') or req.wo_code} has been reassigned to you.\n"
            f"{updated.get('title') or 'Work order'}\n"
            f"Reason: {reason}"
        )
        result = await TelegramMessageSender(settings.sentry_tech_bot_token).send_text(
            str(telegram_id),
            message,
            parse_mode=None,
        )
        notification_sent = bool(result.get("ok"))

    return {
        "success": True,
        "wo_code": updated.get("code") or req.wo_code,
        "previous_assigned_to": previous,
        "assigned_to": technician["name"],
        "technician_telegram_id": telegram_id,
        "notification_sent": notification_sent,
    }


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
            # Extract reporter Telegram ID from created_by
            # Formats: sentry:call_log:{id}, sentry:telegram:{id}, telegram:{id}
            reporter_telegram_id = None
            if "sentry:call_log:" in created_by:
                reporter_telegram_id = created_by.split("sentry:call_log:")[-1].split(":")[0]
            elif "sentry:telegram:" in created_by:
                reporter_telegram_id = created_by.split("sentry:telegram:")[-1].split(":")[0]
            elif created_by.startswith("telegram:"):
                reporter_telegram_id = created_by.split("telegram:")[-1].split(":")[0]

            if reporter_telegram_id:
                try:
                    from app.services.telegram_message_sender import TelegramMessageSender
                    from app.config.settings import settings

                    # Route notification through the correct bot:
                    # - call-log WOs → staff bot (reporter is a staff member)
                    # - advisory/telegram WOs → manager bot (FM approved the rec)
                    if "sentry:call_log:" in created_by:
                        bot_token = settings.sentry_client_bot_token
                    else:
                        bot_token = settings.sentry_manager_bot_token or settings.sentry_client_bot_token

                    sender = TelegramMessageSender(bot_token) if bot_token else None
                    if not sender:
                        logger.warning("No bot token available for reporter notification")
                    else:
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
                    logger.warning(f"Reporter notification failed for WO {req.wo_code}: {notify_err}")

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

    approval_rec_id = _extract_supervised_approval_rec_id(payload.text)
    if approval_rec_id:
        from app.services.telegram_message_sender import get_telegram_sender

        sender = get_telegram_sender()
        return await _handle_supervised_recommendation_approval(
            chat_id=payload.chat_id,
            user_id=payload.user_id,
            rec_uuid=approval_rec_id,
            sender=sender,
        )

    done_wo_code = _extract_done_work_order_code(payload.text)
    if done_wo_code:
        from app.services.telegram_message_sender import TelegramMessageSender

        bot_token = settings.sentry_tech_bot_token or settings.telegram_bot_token
        if not bot_token:
            return {"success": False, "error": "Technician bot token is not configured"}
        sender = TelegramMessageSender(bot_token)
        return await _start_closeout_session_from_done_command(
            chat_id=payload.chat_id,
            telegram_user_id=payload.user_id,
            wo_code=done_wo_code,
            sender=sender,
        )

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

    try:
        closeout_session = await _find_active_closeout_session(payload.user_id)
    except Exception:
        logger.exception("Closeout session lookup failed for Telegram message: user=%s", payload.user_id)
        closeout_session = None
    if closeout_session and closeout_session.get("status") == "awaiting_notes":
        from app.services.telegram_message_sender import get_telegram_sender

        sender = get_telegram_sender()
        text_value = (payload.text or "").strip()
        if telegram_file_id:
            return await _finalize_closeout_session(
                chat_id=payload.chat_id,
                telegram_user_id=payload.user_id,
                sender=sender,
                final_notes=text_value,
                photo_refs=[telegram_file_id],
            )
        if text_value.lower() in {"skip", "no", "none", "done"}:
            text_value = ""
        return await _finalize_closeout_session(
            chat_id=payload.chat_id,
            telegram_user_id=payload.user_id,
            sender=sender,
            final_notes=text_value,
        )

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

    from app.services.telegram_message_sender import TelegramMessageSender

    bot_token = (
        getattr(settings, "sentry_manager_bot_token", None)
        or getattr(settings, "telegram_bot_token", None)
        or getattr(settings, "sentry_client_bot_token", None)
    )
    sender = TelegramMessageSender(bot_token) if bot_token else None

    # The gateway auto-acknowledges callbacks. This backend acknowledgement is
    # best-effort only and must not prevent the action handler from running.
    try:
        if sender:
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
                if sender:
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
                if sender:
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
            if result["success"]:
                work_order = result.get("work_order") or {}
                text = f"🛠 Work order created: {work_order.get('code', 'created')}."
            else:
                text = f"Could not create work order: {result.get('error', 'unknown_error')}"
            if sender:
                await sender.send_text(chat_id=payload.chat_id, text=text)
        except Exception:
            pass
        return {"success": True, "intent": "prediction_work_order", "confirmed": result["success"], "result": result}

    work_order_info_sender = (
        TelegramMessageSender(settings.sentry_tech_bot_token)
        if getattr(settings, "sentry_tech_bot_token", None)
        else sender
    )

    if payload.data.startswith("woinfo:"):
        wo_code = payload.data.split(":", 1)[1].strip()
        return await _handle_work_order_info_callback(payload.chat_id, wo_code, work_order_info_sender)

    if payload.data.startswith("/info-"):
        target = payload.data.removeprefix("/info-").strip()
        if _is_logical_work_order_target(target):
            wo_code = await _find_latest_logical_work_order_code(target)  # type: ignore[assignment]  # None handled by guard below
            if wo_code:
                return await _handle_work_order_info_callback(payload.chat_id, wo_code, work_order_info_sender)
            if work_order_info_sender:
                await work_order_info_sender.send_text(
                    chat_id=payload.chat_id,
                    text=f"No work order was found for logical target {html.escape(target)}.",
                )
            return {"success": True, "intent": "work_order_info", "confirmed": False}

    if payload.data.startswith("wo:"):
        from app.services.notification_service import notification_service

        result = await notification_service.handle_work_order_request(
            callback_data=payload.data,
            requested_by_telegram_id=payload.user_id,
        )
        try:
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
            if sender:
                await sender.send_text(chat_id=payload.chat_id, text=text)
        except Exception:
            pass
        return {"success": True, "intent": "create_work_order", "confirmed": result["success"], "result": result}

    # Supervised AI recommendation approval buttons from manager bot advisories.
    # These are direct control approvals, so handle them before generic conversation routing.
    if payload.data.startswith("devissue:approval:"):
        return await _handle_telegram_developer_issue(
            chat_id=payload.chat_id,
            user_id=payload.user_id,
            rec_uuid=payload.data.split(":")[-1],
            sender=sender,
        )

    if payload.data.startswith("approve:rec_id:"):
        return await _handle_supervised_recommendation_approval(
            chat_id=payload.chat_id,
            user_id=payload.user_id,
            rec_uuid=payload.data.split(":")[-1],
            sender=sender,
        )

    if payload.data.startswith("reject:rec_id:"):
        return await _handle_supervised_recommendation_rejection(
            chat_id=payload.chat_id,
            user_id=payload.user_id,
            rec_uuid=payload.data.split(":")[-1],
            sender=sender,
        )

    if payload.data.startswith("approvepkg:"):
        return await _handle_supervised_package_approval(
            chat_id=payload.chat_id,
            user_id=payload.user_id,
            site_id=payload.data.split(":", 1)[-1],
            sender=sender,
        )

    # Coordinated AI recommendation approve/reject buttons. These are supervised
    # control decisions, so do not route them through generic conversation flows.
    if payload.data.startswith("coord:approve:") or payload.data.startswith("coord:reject:"):
        parts = payload.data.split(":")
        decision = parts[1] if len(parts) > 2 else ""
        rec_uuid = parts[-1]
        from app.api.optimization import (
            _coordinated_bundle_from_record,
            _coordinated_draft_decision_update,
            _coordinated_execution_blocked_result,
            _coordinated_execution_blockers,
            _execute_coordinated_child_actions,
            _find_bundle_by_id,
            _load_coordinated_bundle_inputs,
            _validate_coordinated_draft_record,
            _validate_coordinated_execution_record,
        )
        from app.database.supabase_client import get_supabase_client
        from app.models.recommendation import RecommendationStatus

        supabase = get_supabase_client()
        result = supabase.table("recommendations").select("*").eq("id", rec_uuid).limit(1).execute()
        if not result.data:
            if sender:
                await sender.send_text(chat_id=payload.chat_id, text="Coordinated AI recommendation not found.")
            return {"success": True, "intent": "coordinated_optimization", "confirmed": False}

        record = result.data[0]
        site_id = record.get("site_id") or ""
        try:
            _validate_coordinated_draft_record(record, site_id)
            updates = _coordinated_draft_decision_update(
                record,
                decision="approved" if decision == "approve" else "rejected",
                user_id=f"telegram:{payload.user_id}",
                reason="Decision via SENTRY Telegram coordinated optimization notification",
            )
            update_result = supabase.table("recommendations").update(updates).eq("id", rec_uuid).execute()
            if not update_result.data:
                if sender:
                    await sender.send_text(
                        chat_id=payload.chat_id,
                        text="Could not update coordinated AI recommendation.",
                    )
                return {"success": True, "intent": "coordinated_optimization", "confirmed": False}

            updated = update_result.data[0]
            status_value = updated.get("approval_status")
            execution = updated.get("execution_result") or {}
            if status_value == "approved":
                _validate_coordinated_execution_record(updated, site_id)
                inputs = _load_coordinated_bundle_inputs(site_id)
                bundle = _coordinated_bundle_from_record(updated)
                bundle_id = bundle.get("bundle_id")
                live_bundle = _find_bundle_by_id(inputs["bundles"], bundle_id) if bundle_id else None
                user_id = f"telegram:{payload.user_id}"
                blockers = _coordinated_execution_blockers(
                    record=updated,
                    live_bundle=live_bundle,
                    site_phase=inputs["site_phase"],
                )
                if blockers:
                    execution_updates = _coordinated_execution_blocked_result(
                        record=updated,
                        blockers=blockers,
                        user_id=user_id,
                        reason="Approved via SENTRY Telegram coordinated optimization notification",
                    )
                    execution_update_result = (
                        supabase.table("recommendations").update(execution_updates).eq("id", rec_uuid).execute()
                    )
                    updated = (
                        execution_update_result.data[0]
                        if execution_update_result.data
                        else {**updated, **execution_updates}
                    )
                    execution = updated.get("execution_result") or execution_updates["execution_result"]
                    text = (
                        "✅ <b>AI recommendation approved</b>\n"
                        "Not applied to the BMS because execution is still blocked.\n"
                        f"<b>Blockers:</b> {', '.join(str(item) for item in blockers[:5])}\n"
                        f"<b>Device writes:</b> {execution.get('device_writes', 0)}"
                    )
                else:
                    execution = await _execute_coordinated_child_actions(
                        bundle=bundle,
                        user_id=user_id,
                        recommendation_id=rec_uuid,
                    )
                    executed = bool(execution.get("executed"))
                    execution_updates = {
                        "status": RecommendationStatus.EXECUTED.value
                        if executed
                        else RecommendationStatus.FAILED.value,
                        "execution_result": execution,
                    }
                    if executed:
                        from datetime import datetime

                        executed_at = datetime.utcnow().isoformat()
                        execution_updates["executed_at"] = executed_at
                        execution_updates["metadata"] = {
                            **(updated.get("metadata") or {}),
                            "lifecycle": "executed",
                            "executed_by": user_id,
                            "executed_at": executed_at,
                        }
                    supabase.table("recommendations").update(execution_updates).eq("id", rec_uuid).execute()
                    text = (
                        "✅ <b>AI recommendation approved and applied</b>\n"
                        if executed
                        else "❌ <b>AI recommendation approved but execution failed</b>\n"
                    )
                    text += f"<b>Device writes:</b> {execution.get('device_writes', 0)}"
            else:
                text = (
                    "❌ <b>AI recommendation rejected</b>\n"
                    "No control action was taken.\n"
                    f"Device writes: {execution.get('device_writes', 0)}"
                )
            if sender:
                await sender.send_text(chat_id=payload.chat_id, text=text, parse_mode="HTML")
            return {
                "success": True,
                "intent": "coordinated_optimization",
                "confirmed": True,
                "decision": decision,
                "device_writes": execution.get("device_writes", 0),
            }
        except Exception:
            from app.services.telegram_message_sender import InlineButton, InlineKeyboard

            logger.exception("SENTRY coordinated AI recommendation decision failed for %s", rec_uuid)
            keyboard = InlineKeyboard(rows=[[InlineButton("Log issue", f"devissue:approval:{rec_uuid}")]])
            if sender:
                await sender.send_text(
                    chat_id=payload.chat_id,
                    text=_approval_failed_message("Coordinated AI recommendation"),
                    keyboard=keyboard,
                    parse_mode="HTML",
                )
            return {"success": True, "intent": "coordinated_optimization", "confirmed": False}

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

    if payload.data.startswith("closeout:"):
        from app.services.telegram_message_sender import TelegramMessageSender

        closeout_sender = (
            TelegramMessageSender(settings.sentry_tech_bot_token or bot_token)
            if (settings.sentry_tech_bot_token or bot_token)
            else sender
        )
        return await _handle_closeout_callback(
            chat_id=payload.chat_id,
            telegram_user_id=payload.user_id,
            callback_data=payload.data,
            sender=closeout_sender,
        )

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

    # Recommendation acknowledgement from morning digest/advisory inline buttons
    if (
        payload.data.startswith("rec:accept:")
        or payload.data.startswith("rec:dismiss:")
        or payload.data.startswith("rec:review:")
    ):
        from app.services.recommendation_service import get_recommendation_service

        parts = payload.data.split(":")
        if len(parts) >= 3:
            rec_id = parts[2]
            acknowledgement_type = (
                "accepted" if parts[1] == "accept" else "reviewed" if parts[1] == "review" else "dismissed"
            )
            svc = get_recommendation_service()
            await svc.acknowledge_recommendation(rec_id, acknowledgement_type)
            action = "Accepted" if parts[1] == "accept" else "Acknowledged" if parts[1] == "review" else "Dismissed"
            if sender:
                await sender.send_text(chat_id=payload.chat_id, text=f"✅ Recommendation {action}.")
            return {"success": True, "intent": "rec_ack", "confirmed": True}
        return {"success": False, "error": "invalid_rec_callback"}

    # Inline "Done" button on WO notification card starts deterministic backend
    # closeout directly. Do not bounce back through the embedded agent.
    if payload.data.startswith("/done-") or payload.data.startswith("done #WO-") or payload.data.startswith("done #"):
        wo_code = _extract_done_work_order_code(payload.data)  # type: ignore[assignment]  # None handled by guard below
        if wo_code:
            from app.services.telegram_message_sender import TelegramMessageSender

            closeout_sender = (
                TelegramMessageSender(settings.sentry_tech_bot_token or bot_token)
                if (settings.sentry_tech_bot_token or bot_token)
                else sender
            )
            if not closeout_sender:
                return {"success": False, "error": "Technician bot token is not configured"}
            return await _start_closeout_session_from_done_command(
                chat_id=payload.chat_id,
                telegram_user_id=payload.user_id,
                wo_code=wo_code,
                sender=closeout_sender,
            )
        return {"success": True, "intent": "closeout", "confirmed": False, "method": "button_done"}

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


class FeedbackEventRequest(BaseModel):
    """Durable staff/tech feedback event for weekly Sentry digest."""

    batch_type: Literal["A", "B", "C"]
    bot_workspace: Literal["staff", "tech"]
    site_id: str
    occurred_at: datetime | None = None
    telegram_user_hash: str | None = None
    intent: str | None = None
    skill_name: str | None = None
    flow_name: str | None = None
    outcome: str | None = None
    failure_category: str | None = None
    feedback_category: str | None = None
    sanitised_message: str | None = None
    source_table: str | None = None
    source_id: str | None = None
    work_order_code: str | None = None
    detector: str | None = None
    classifier_confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/feedback-event")
async def log_feedback_event(
    event: FeedbackEventRequest,
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
) -> dict[str, str]:
    """Persist a feedback event. Insert failures are logged but never returned."""
    _require_sentry_secret_or_key(x_sentry_secret, x_sentry_api_key, endpoint_name="feedback_event")

    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            logger.warning("feedback_event skipped: Supabase client unavailable")
            return {"status": "ok"}

        payload = event.model_dump(exclude_none=True)
        payload.setdefault("occurred_at", datetime.now(UTC).isoformat())
        sb.table("sentry_feedback_events").insert(payload).execute()
    except Exception as e:
        logger.warning("feedback_event insert failed: %s", e)

    return {"status": "ok"}


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
async def handle_telegram_message_flow(
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


# ---------------------------------------------------------------------------
# Phase 227: SENTRY-MULTISITE — Site-scoped bot user provisioning
# ---------------------------------------------------------------------------


class BotUserCreate(BaseModel):
    telegram_id: int
    site_id: str
    bot_role: str = Field(..., pattern="^(manager|technician|staff)$")
    display_name: str | None = None
    email: str | None = None
    created_by: int | None = None


@router.get("/bot-users/{telegram_id}/sites")
async def get_bot_user_sites(
    telegram_id: int,
    bot_role: str = Query(..., pattern="^(manager|technician|staff)$"),
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
):
    """Return the list of sites this telegram user can access for the given role.

    Returns empty list on miss (fail-closed contract for downstream tools).
    """
    _require_sentry_secret_or_key(x_sentry_secret, x_sentry_api_key, endpoint_name="bot-users-sites")

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    result = (
        supabase.table("bot_users")
        .select("site_id, active")
        .eq("telegram_id", telegram_id)
        .eq("bot_role", bot_role)
        .eq("active", True)
        .execute()
    )
    sites = sorted({row["site_id"] for row in (result.data or []) if row.get("active")})
    return {
        "telegram_id": telegram_id,
        "bot_role": bot_role,
        "sites": sites,
        "active": bool(sites),
    }


@router.post("/bot-users", status_code=status.HTTP_201_CREATED)
async def create_bot_user(
    data: BotUserCreate,
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
):
    """Provision a new bot_user row. Idempotent via UNIQUE(telegram_id, site_id, bot_role)."""
    _require_sentry_secret_or_key(x_sentry_secret, x_sentry_api_key, endpoint_name="bot-users-create")

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    now = datetime.now(UTC).isoformat()
    payload = {
        "telegram_id": data.telegram_id,
        "site_id": data.site_id,
        "bot_role": data.bot_role,
        "display_name": data.display_name,
        "email": data.email,
        "active": True,
        "created_at": now,
        "created_by": data.created_by,
    }
    result = supabase.table("bot_users").upsert(payload, on_conflict="telegram_id,site_id,bot_role").execute()
    return {"success": True, "row": (result.data or [None])[0]}


@router.delete("/bot-users/{telegram_id}")
async def deactivate_bot_user(
    telegram_id: int,
    site_id: str = Query(...),
    bot_role: str = Query(..., pattern="^(manager|technician|staff)$"),
    x_sentry_api_key: str | None = Header(None),
    x_sentry_secret: str | None = Header(None),
):
    """Soft-delete a bot_user row — sets active=False. Never hard delete."""
    _require_sentry_secret_or_key(x_sentry_secret, x_sentry_api_key, endpoint_name="bot-users-delete")

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    result = (
        supabase.table("bot_users")
        .update({"active": False})
        .eq("telegram_id", telegram_id)
        .eq("site_id", site_id)
        .eq("bot_role", bot_role)
        .execute()
    )
    return {"success": True, "deactivated": len(result.data or [])}
