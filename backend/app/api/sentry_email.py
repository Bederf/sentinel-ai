"""Sentry Email Intake API — Phase 131.

Receives AI-classified FM emails from n8n, enriches with BMS context,
detects duplicates/follow-ups, and returns auto-reply templates.

Auth chain:
  1. Middleware: ``X-Sentry-API-Key`` (required, matches ``sentry_bot_api_key``)
  2. Endpoint: ``X-Sentry-Secret`` (required in live mode, matches ``sentry_webhook_secret``)
  3. Feature flag: ``email_intake_enabled`` must be True
"""

from __future__ import annotations

import hmac
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config.settings import settings
from app.database.repositories.email_intake_repository import get_email_intake_repository
from app.models.email_intake import (
    EmailIntakeHealthResponse,
    EmailIntakeRequest,
    EmailIntakeResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sentry/email", tags=["sentry-email"])

# ---------------------------------------------------------------------------
# Confidence thresholds for routing
# ---------------------------------------------------------------------------
AUTO_SUBMIT_THRESHOLD = 0.85
REQUEST_INFO_THRESHOLD = 0.60

# Urgency string → numeric (for priority comparisons)
URGENCY_RANK = {"low": 1, "normal": 2, "high": 3, "critical": 4}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _verify_webhook_secret(provided: Optional[str]) -> None:
    """Validate ``X-Sentry-Secret`` against ``sentry_webhook_secret``."""
    configured = (settings.sentry_webhook_secret or "").strip()

    # Backward-compat: check env var in simulation mode
    if not configured and not settings.is_live_mode:
        configured = (os.getenv("SENTRY_WEBHOOK_SECRET", "") or "").strip()

    if not configured:
        if settings.is_live_mode:
            raise HTTPException(status_code=503, detail="Email intake misconfigured: missing webhook secret")
        # In simulation / demo, allow unauthenticated
        return

    if not provided or not hmac.compare_digest(provided, configured):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def _build_reply_template(action: str, intake: dict[str, Any]) -> str:
    """Build a human-readable auto-reply body for n8n to send."""
    ref = intake.get("concept_ref") or intake.get("id", "")[:8]
    category = intake.get("issue_category", "general")
    summary = intake.get("issue_summary", "your request")

    if action == "linked_existing":
        return (
            f"Thank you for your follow-up regarding {summary}.\n\n"
            f"This has been linked to existing reference {intake.get('existing_reference', ref)}. "
            "Our team is already working on it and will provide an update shortly."
        )
    if action == "duplicate":
        return (
            f"Thank you for your message regarding {summary}.\n\n"
            "We already have a record of this issue and our team is working on it. "
            "You will receive an update once there is progress."
        )
    if action == "request_info":
        return (
            f"Thank you for reporting a {category} issue.\n\n"
            f"Reference: {ref}\n\n"
            "To help us route this efficiently, could you please provide:\n"
            "- The specific location (floor/wing/room number)\n"
            "- When the issue started\n"
            "- Any additional details\n\n"
            "Our team will begin investigating in the meantime."
        )
    # new_intake / auto_submit / manual_review
    return (
        f"Thank you for your {category} request.\n\n"
        f"Reference: {ref}\n\n"
        f"Issue: {summary}\n\n"
        "This has been logged and assigned for action. "
        "You will receive updates as the work progresses."
    )


async def _enrich_with_bms(site_id: Optional[str], issue_category: Optional[str]) -> dict[str, Any]:
    """Gather BMS context for the intake.

    Enrichment layers:
      1. Building name (from building code)
      2. Active alerts for the building
      3. Recent open work orders
      4. Equipment health summary (at-risk count)
      5. Agent memory notes
    """
    context: dict[str, Any] = {}
    if not site_id:
        return context

    building_uuid: Optional[str] = None

    # 1. Building lookup (also resolves UUID for subsequent queries)
    try:
        from app.database.repositories import BuildingRepository

        building_repo = BuildingRepository()
        building = building_repo.get_by_id(site_id)
        if building:
            context["building_name"] = building.get("name", site_id)
            building_uuid = building.get("id")
    except Exception as exc:
        logger.debug("BMS enrichment: building lookup failed: %s", exc)

    # 2. Active alerts for the building
    if building_uuid:
        try:
            from app.database.repositories.alert_repository import AlertRepository

            alert_repo = AlertRepository()
            alerts = alert_repo.get_alerts(building_id=building_uuid, status="active")
            if alerts:
                context["active_alerts"] = [
                    {
                        "code": a.get("equipment_code"),
                        "severity": a.get("severity"),
                        "message": a.get("title", a.get("message")),
                    }
                    for a in alerts[:5]
                ]
        except Exception as exc:
            logger.debug("BMS enrichment: alerts lookup failed: %s", exc)

    # 3. Recent open work orders
    if building_uuid:
        try:
            from app.database.repositories.work_order_repository import (
                WorkOrderRepository,
            )

            wo_repo = WorkOrderRepository()
            open_wos = await wo_repo.get_all_work_orders(limit=5, status="scheduled")
            # Filter to this building (get_all doesn't filter by building)
            site_wos = [w for w in (open_wos or []) if w.get("building_id") == building_uuid][:3]
            if site_wos:
                context["recent_work_orders"] = [
                    {
                        "code": w.get("code"),
                        "title": w.get("title"),
                        "priority": w.get("priority"),
                        "status": w.get("status"),
                    }
                    for w in site_wos
                ]
        except Exception as exc:
            logger.debug("BMS enrichment: work orders lookup failed: %s", exc)

    # 4. Equipment health summary
    if building_uuid:
        try:
            from app.database.repositories import BuildingRepository as BR

            br = BR()
            at_risk_count = br.get_at_risk_equipment_count(building_uuid)
            if at_risk_count > 0:
                context["equipment_health"] = {
                    "at_risk_count": at_risk_count,
                }
        except Exception as exc:
            logger.debug("BMS enrichment: equipment health lookup failed: %s", exc)

    # 5. Agent memory notes for site
    try:
        from app.database.repositories.agent_memory_repository import (
            get_agent_memory_repository,
        )

        mem_repo = get_agent_memory_repository()
        memories = mem_repo.get_by_site(site_id, limit=3)
        if memories:
            context["agent_notes"] = [{"key": m.get("key"), "value": m.get("value")} for m in memories]
    except Exception as exc:
        logger.debug("BMS enrichment: agent memory lookup failed: %s", exc)

    return context


def _score_completeness(req: EmailIntakeRequest) -> float:
    """Score 0.0-1.0 based on how complete the extraction is."""
    score = req.extraction_confidence
    # Boost if we have structured location info
    if req.site_id:
        score = min(1.0, score + 0.05)
    if req.zone_hint or req.floor_hint:
        score = min(1.0, score + 0.05)
    if req.issue_category and req.issue_category != "general":
        score = min(1.0, score + 0.05)
    return round(score, 3)


def _determine_route(completeness: float) -> str:
    """Route: auto_submit | request_info | manual_review."""
    if completeness >= AUTO_SUBMIT_THRESHOLD:
        return "auto_submit"
    if completeness >= REQUEST_INFO_THRESHOLD:
        return "request_info"
    return "manual_review"


def _apply_urgency_escalation(
    req: EmailIntakeRequest,
    bms_context: dict[str, Any],
) -> str:
    """Escalate urgency if BMS shows active alerts or n8n flagged boost."""
    urgency = req.urgency or "normal"

    # n8n urgency boost (e.g. URGENT in subject, manager CC)
    if req.urgency_boost and URGENCY_RANK.get(urgency, 2) < 3:
        urgency = "high"

    if req.has_manager_cc and URGENCY_RANK.get(urgency, 2) < 3:
        urgency = "high"

    # BMS alert escalation
    active_alerts = bms_context.get("active_alerts", [])
    if active_alerts:
        critical_alerts = [a for a in active_alerts if a.get("severity") in ("critical", "emergency")]
        if critical_alerts and URGENCY_RANK.get(urgency, 2) < 4:
            urgency = "critical"
        elif active_alerts and URGENCY_RANK.get(urgency, 2) < 3:
            urgency = "high"

    return urgency


# ---------------------------------------------------------------------------
# Stub: Concept WO creation (v1 — logs only)
# ---------------------------------------------------------------------------


async def _create_concept_work_order(intake: dict[str, Any]) -> Optional[str]:
    """Stub: create a Concept WO. Returns ref or None."""
    logger.info(
        "Concept WO creation stub: would create WO for intake %s (category=%s, site=%s)",
        intake.get("id"),
        intake.get("issue_category"),
        intake.get("site_id"),
    )
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=EmailIntakeHealthResponse)
async def email_intake_health():
    """Health check for the email intake pipeline."""
    return EmailIntakeHealthResponse(
        status="ok",
        enabled=settings.email_intake_enabled,
    )


@router.post("/intake", response_model=EmailIntakeResponse)
async def email_intake(
    req: EmailIntakeRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    x_sentry_secret: Optional[str] = Header(None, alias="X-Sentry-Secret"),
):
    """Process an inbound FM email from n8n.

    Processing order:
    1. Feature flag + webhook secret check
    2. Duplicate / follow-up detection
    3. BMS enrichment
    4. Urgency escalation
    5. Completeness scoring + route decision
    6. Persist + return response
    """
    # 1. Feature flag
    if not settings.email_intake_enabled:
        raise HTTPException(status_code=503, detail="Email intake pipeline is disabled")

    # 2. Webhook secret
    _verify_webhook_secret(x_sentry_secret)

    repo = get_email_intake_repository()
    intake_id = str(uuid.uuid4())
    now_iso = datetime.utcnow().isoformat()

    # ------------------------------------------------------------------
    # 3. Duplicate / follow-up checks
    # ------------------------------------------------------------------

    # 3a. Existing reference match (e.g. FNBFW:12345)
    if req.existing_reference:
        existing = repo.get_latest_by_reference(req.existing_reference)
        if existing:
            # Link as follow-up
            follow_up_record = {
                "id": intake_id,
                "from_email": req.from_email,
                "from_name": req.from_name,
                "subject": req.subject,
                "body_plain": req.body_plain,
                "message_id": req.message_id,
                "received_at": req.received_at or now_iso,
                "site_id": req.site_id or existing.get("site_id"),
                "issue_category": req.issue_category or existing.get("issue_category"),
                "issue_summary": req.issue_summary,
                "urgency": req.urgency,
                "existing_reference": req.existing_reference,
                "parent_intake_id": existing.get("id"),
                "pipeline_status": "routed",
                "action_taken": "linked_existing",
                "routing_reason": f"Matched existing_reference={req.existing_reference}",
                "extraction_confidence": req.extraction_confidence,
                "extraction_model": req.extraction_model,
            }
            repo.create(follow_up_record)

            # Bump follow_up_count on parent
            parent_count = (existing.get("follow_up_count") or 0) + 1
            repo.update_status(existing["id"], existing.get("pipeline_status", "routed"), follow_up_count=parent_count)

            return EmailIntakeResponse(
                success=True,
                intake_id=intake_id,
                action_taken="linked_existing",
                concept_ref=existing.get("concept_ref"),
                message=f"Linked to existing reference {req.existing_reference}",
                reply_template=_build_reply_template("linked_existing", {**follow_up_record, **existing}),
                urgency=req.urgency,
            )

    # 3b. Exact message_id dedup
    if req.message_id:
        dup = repo.get_by_message_id(req.message_id)
        if dup:
            return EmailIntakeResponse(
                success=True,
                intake_id=dup["id"],
                action_taken="duplicate",
                concept_ref=dup.get("concept_ref"),
                message="Duplicate message_id — already processed",
                reply_template=_build_reply_template("duplicate", dup),
                urgency=dup.get("urgency", "normal"),
            )

    # 3c. Heuristic recent-window dedup
    recent = repo.find_recent(
        from_email=req.from_email,
        site_id=req.site_id,
        issue_category=req.issue_category,
        hours=settings.email_intake_duplicate_window_hours,
    )
    if recent:
        # Link as follow-up rather than creating a duplicate WO
        follow_up_record = {
            "id": intake_id,
            "from_email": req.from_email,
            "from_name": req.from_name,
            "subject": req.subject,
            "body_plain": req.body_plain,
            "message_id": req.message_id,
            "received_at": req.received_at or now_iso,
            "site_id": req.site_id,
            "issue_category": req.issue_category,
            "issue_summary": req.issue_summary,
            "urgency": req.urgency,
            "parent_intake_id": recent.get("id"),
            "pipeline_status": "routed",
            "action_taken": "linked_existing",
            "routing_reason": (
                f"Recent-window match: same sender+site+category within {settings.email_intake_duplicate_window_hours}h"
            ),
            "extraction_confidence": req.extraction_confidence,
            "extraction_model": req.extraction_model,
        }
        repo.create(follow_up_record)

        parent_count = (recent.get("follow_up_count") or 0) + 1
        repo.update_status(recent["id"], recent.get("pipeline_status", "routed"), follow_up_count=parent_count)

        return EmailIntakeResponse(
            success=True,
            intake_id=intake_id,
            action_taken="linked_existing",
            concept_ref=recent.get("concept_ref"),
            message="Linked to recent intake from same sender",
            reply_template=_build_reply_template("linked_existing", {**follow_up_record, **recent}),
            urgency=req.urgency,
        )

    # ------------------------------------------------------------------
    # 4. BMS enrichment
    # ------------------------------------------------------------------
    bms_context = await _enrich_with_bms(req.site_id, req.issue_category)

    # 5. Urgency escalation
    final_urgency = _apply_urgency_escalation(req, bms_context)

    # 6. Completeness scoring + route
    completeness = _score_completeness(req)
    route = _determine_route(completeness)

    # Map route to action_taken
    action_taken = route  # auto_submit | request_info | manual_review
    if route == "auto_submit" and not settings.email_intake_auto_wo_enabled:
        action_taken = "new_intake"  # downgrade if auto-WO is off

    # ------------------------------------------------------------------
    # 7. Persist record
    # ------------------------------------------------------------------
    record = {
        "id": intake_id,
        "from_email": req.from_email,
        "from_name": req.from_name,
        "from_phone": req.from_phone,
        "from_department": req.from_department,
        "subject": req.subject,
        "body_plain": req.body_plain,
        "message_id": req.message_id,
        "in_reply_to": req.in_reply_to,
        "received_at": req.received_at or now_iso,
        "site_id": req.site_id,
        "zone_hint": req.zone_hint,
        "floor_hint": req.floor_hint,
        "issue_category": req.issue_category,
        "issue_summary": req.issue_summary,
        "urgency": final_urgency,
        "extraction_confidence": req.extraction_confidence,
        "extraction_model": req.extraction_model,
        "extraction_raw": req.extraction_raw,
        "bms_context": bms_context if bms_context else None,
        "enrichment_ts": now_iso if bms_context else None,
        "pipeline_status": "routed",
        "action_taken": action_taken,
        "routing_reason": f"completeness={completeness}, route={route}",
        "existing_reference": req.existing_reference,
        "attachment_count": req.attachment_count,
        "attachment_refs": req.attachment_refs,
        "processed_by": "sentinel",
    }

    repo.create(record)

    # Concept WO stub (background, non-blocking)
    if action_taken == "auto_submit":
        background_tasks.add_task(_create_concept_work_order, record)

    # 8. Build response
    return EmailIntakeResponse(
        success=True,
        intake_id=intake_id,
        action_taken=action_taken,
        bms_context=bms_context if bms_context else None,
        message=f"Email intake processed: {action_taken}",
        reply_template=_build_reply_template(action_taken, record),
        urgency=final_urgency,
    )
