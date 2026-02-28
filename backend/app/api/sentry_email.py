"""Sentry Email Intake API — Phase 134.

Receives FM emails from n8n, enriches with BMS context, detects
duplicates/follow-ups, and uses an AI agent (Phase 134) for classification
+ natural reply generation.  Falls back to keyword pipeline if agent fails.

Auth chain:
  1. Middleware: ``X-Sentry-API-Key`` (required, matches ``sentry_bot_api_key``)
  2. Endpoint: ``X-Sentry-Secret`` (required in live mode, matches ``sentry_webhook_secret``)
  3. Feature flag: ``email_intake_enabled`` must be True
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config.settings import settings
from app.database.repositories.email_intake_repository import get_email_intake_repository
from app.security.webhook_auth import (
    check_attachment_type_allowed,
    check_email_domain_allowed,
    check_email_sender_rate_limit,
    is_known_sender,
)
from app.models.email_intake import (
    EmailIntakeHealthResponse,
    EmailIntakeRequest,
    EmailIntakeResponse,
)
from app.security.prompt_guard import score_prompt
from app.services.email_reply_service import get_email_reply_service
from app.services.issue_classifier import (
    classify_email_subject,
    DISCIPLINE_TO_CATEGORY,
    extract_desk_from_message,
    extract_floor_from_message,
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


def _subjects_similar(subject_a: str, subject_b: str, threshold: float = 0.3) -> bool:
    """Check if two email subjects share enough keywords to be the same issue.

    Used to prevent heuristic dedup from linking unrelated emails that happen
    to come from the same sender within the duplicate window.
    """

    def _keywords(s: str) -> set[str]:
        stop = {
            "the",
            "a",
            "an",
            "is",
            "at",
            "in",
            "on",
            "for",
            "to",
            "and",
            "or",
            "my",
            "our",
            "please",
            "hi",
            "hello",
            "dear",
            "regards",
            "thanks",
            "thank",
            "you",
            "good",
            "day",
            "morning",
            "afternoon",
            "fwd",
            "re",
        }
        return {w.lower() for w in re.findall(r"\w{3,}", s)} - stop

    words_a = _keywords(subject_a)
    words_b = _keywords(subject_b)
    if not words_a or not words_b:
        return False
    overlap = words_a & words_b
    smaller = min(len(words_a), len(words_b))
    return (len(overlap) / smaller) >= threshold if smaller > 0 else False


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


def _article(word: str) -> str:
    """Return 'an' for vowel-starting words, 'a' otherwise."""
    return "an" if word and word[0].lower() in "aeiou" else "a"


def _build_reply_template(action: str, intake: dict[str, Any]) -> str:
    """Build a plain-text auto-reply body for n8n to send."""
    ref = intake.get("concept_ref") or intake.get("id", "")[:8]
    category = intake.get("issue_category", "general")
    summary = intake.get("issue_summary", "your request")
    from_name = intake.get("from_name", "")

    # Greeting
    greeting = f"Dear {from_name}," if from_name else "Dear Tenant,"

    if action == "linked_existing":
        body = (
            f"{greeting}\n\n"
            f"Thank you for your follow-up regarding {summary}.\n\n"
            f"This has been linked to existing reference {intake.get('existing_reference', ref)}. "
            "Our team is already working on it and will provide an update shortly.\n\n"
            "NEXT STEPS:\n"
            "- A technician has been assigned and will attend to the issue\n"
            "- You will receive a status update once work is completed\n"
            "- Reply to this email if the situation has changed\n"
        )
    elif action == "duplicate":
        body = (
            f"{greeting}\n\n"
            f"Thank you for your message regarding {summary}.\n\n"
            "We already have a record of this issue and our team is working on it. "
            "You will receive an update once there is progress.\n"
        )
    elif action == "request_info":
        body = (
            f"{greeting}\n\n"
            f"Thank you for reporting {_article(category)} {category} issue.\n\n"
            f"Reference: {ref}\n\n"
            "To help us route this efficiently, could you please reply with:\n"
            "- The specific location (floor/wing/room number)\n"
            "- When the issue started\n"
            "- Any additional details\n\n"
            "Our team will begin investigating in the meantime.\n"
        )
    else:
        # new_intake / auto_submit / manual_review
        body = (
            f"{greeting}\n\n"
            f"Thank you for your {category} request.\n\n"
            f"Reference: {ref}\n\n"
            f"Issue: {summary}\n\n"
            "This has been logged and assigned for action.\n\n"
            "NEXT STEPS:\n"
            "- Your request has been assigned to the facilities team\n"
            "- A technician will be dispatched based on priority\n"
            "- You will receive updates as the work progresses\n"
        )

    # Contact info
    body += (
        "\nFor urgent issues, please contact the facilities help desk directly.\n\n"
        "Kind regards,\n"
        "SENTINEL Building Management\n"
    )

    # Quoted original email
    original_body = intake.get("body_plain", "")
    original_from = intake.get("from_name") or intake.get("from_email", "")
    original_date = intake.get("received_at", "")
    original_subject = intake.get("subject", "")
    if original_body or original_subject:
        body += "\n--- Original Message ---\n"
        if original_date or original_from:
            body += f"On {original_date}, {original_from} wrote:\n"
        if original_subject:
            body += f"Subject: {original_subject}\n\n"
        if original_body:
            # Prefix each line with > for quoting
            for line in original_body.splitlines()[:30]:
                body += f"> {line}\n"

    return body


def _build_reply_html(action: str, intake: dict[str, Any]) -> str:
    """Build a branded HTML auto-reply for n8n to send."""
    ref = intake.get("concept_ref") or intake.get("id", "")[:8]
    category = intake.get("issue_category", "general")
    summary = intake.get("issue_summary", "your request")
    from_name = intake.get("from_name", "")
    bms_ctx = intake.get("bms_context") or {}

    # Category badge colour
    cat_colours = {
        "hvac": "#2563eb",
        "electrical": "#d97706",
        "plumbing": "#0891b2",
        "fire": "#dc2626",
        "lighting": "#7c3aed",
        "access": "#059669",
        "elevator": "#6366f1",
        "pest": "#84cc16",
        "structural": "#78716c",
        "general": "#6b7280",
    }
    badge_colour = cat_colours.get(category, "#6b7280")

    # Action-specific body section
    if action == "linked_existing":
        existing_ref = intake.get("existing_reference", ref)
        body_section = (
            f"<p>Thank you for your follow-up regarding <strong>{_esc(summary)}</strong>.</p>"
            f"<p>This has been linked to existing reference <strong>{_esc(existing_ref)}</strong>. "
            "Our team is already working on it and will provide an update shortly.</p>"
        )
    elif action == "duplicate":
        body_section = (
            f"<p>Thank you for your message regarding <strong>{_esc(summary)}</strong>.</p>"
            "<p>We already have a record of this issue and our team is working on it. "
            "You will receive an update once there is progress.</p>"
        )
    elif action == "request_info":
        body_section = (
            f"<p>Thank you for reporting {_article(category)} <strong>{_esc(category)}</strong> issue.</p>"
            "<p>To help us route this efficiently, could you please reply with:</p>"
            "<ul>"
            "<li>The specific location (floor / wing / room number)</li>"
            "<li>When the issue started</li>"
            "<li>Any additional details or photos</li>"
            "</ul>"
            "<p>Our team will begin investigating in the meantime.</p>"
        )
    else:
        # new_intake / auto_submit / manual_review
        body_section = (
            f"<p>Your <strong>{_esc(category)}</strong> request has been logged and assigned for action.</p>"
            f"<p><strong>Issue:</strong> {_esc(summary)}</p>"
            "<p>You will receive updates as the work progresses.</p>"
        )

    # BMS context section (active alerts)
    bms_section = ""
    active_alerts = bms_ctx.get("active_alerts", [])
    if active_alerts:
        alert_rows = ""
        for a in active_alerts[:3]:
            sev = a.get("severity", "info")
            sev_colour = "#dc2626" if sev == "critical" else "#d97706" if sev == "warning" else "#6b7280"
            alert_rows += (
                f'<tr><td style="padding:4px 8px;color:{sev_colour};font-weight:600;">'
                f"{_esc(sev.upper())}</td>"
                f'<td style="padding:4px 8px;">{_esc(a.get("message", ""))}</td></tr>'
            )
        bms_section = (
            '<div style="margin-top:20px;padding:12px 16px;background:#fef3c7;'
            'border-left:4px solid #d97706;border-radius:4px;">'
            '<p style="margin:0 0 8px;font-weight:600;color:#92400e;">'
            "Active Building Alerts</p>"
            f'<table style="width:100%;font-size:13px;">{alert_rows}</table>'
            "</div>"
        )

    # Greeting
    greeting = f"Dear {_esc(from_name)}," if from_name else "Dear Tenant,"

    # Next steps section (for new intakes and linked_existing)
    next_steps = ""
    if action in ("auto_submit", "new_intake", "manual_review", "linked_existing"):
        next_steps = (
            '<div style="margin-top:16px;padding:12px 16px;background:#f0fdf4;'
            'border-left:4px solid #16a34a;border-radius:4px;">'
            '<p style="margin:0 0 8px;font-weight:600;color:#166534;">Next Steps</p>'
            '<ul style="margin:0;padding-left:20px;color:#374151;font-size:13px;">'
            "<li>Your request has been assigned to the facilities team</li>"
            "<li>A technician will be dispatched based on priority</li>"
            "<li>You will receive updates as the work progresses</li>"
            "</ul></div>"
        )

    # Contact escalation
    contact_section = (
        '<p style="margin-top:16px;font-size:13px;color:#6b7280;">'
        "For urgent issues, please contact the facilities help desk directly.</p>"
    )

    # Quoted original email
    original_quote = ""
    original_body = intake.get("body_plain", "")
    original_from = intake.get("from_name") or intake.get("from_email", "")
    original_date = intake.get("received_at", "")
    original_subject = intake.get("subject", "")
    if original_body or original_subject:
        quote_header = ""
        if original_date or original_from:
            quote_header = (
                f'<p style="margin:0 0 8px;font-size:12px;color:#6b7280;">'
                f"On {_esc(original_date)}, {_esc(original_from)} wrote:</p>"
            )
        # Truncate to first 30 lines
        truncated = "\n".join(original_body.splitlines()[:30]) if original_body else ""
        original_quote = (
            '<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;">'
            f"{quote_header}"
            '<div style="margin:0;padding:8px 12px;border-left:3px solid #d1d5db;'
            'color:#6b7280;font-size:12px;line-height:1.5;white-space:pre-wrap;">'
            f"{_esc(truncated)}</div></div>"
        )

    return (
        "<!DOCTYPE html>"
        '<html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '</head><body style="margin:0;padding:0;font-family:Arial,Helvetica,sans-serif;'
        'background:#f3f4f6;">'
        '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">'
        '<tr><td align="center" style="padding:24px 16px;">'
        '<table width="600" cellpadding="0" cellspacing="0" '
        'style="background:#ffffff;border-radius:8px;overflow:hidden;'
        'box-shadow:0 1px 3px rgba(0,0,0,0.1);">'
        # Header bar
        '<tr><td style="background:#1e3a5f;padding:20px 24px;">'
        '<table width="100%" cellpadding="0" cellspacing="0"><tr>'
        '<td style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:1px;">'
        "SENTINEL</td>"
        '<td align="right" style="color:#94a3b8;font-size:12px;">'
        "Building Intelligence</td>"
        "</tr></table></td></tr>"
        # Reference banner
        '<tr><td style="background:#f0f9ff;padding:14px 24px;'
        'border-bottom:1px solid #e0f2fe;">'
        '<table width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="font-size:14px;color:#1e3a5f;font-weight:600;">'
        f"Reference: {_esc(ref)}</td>"
        f'<td align="right"><span style="display:inline-block;padding:3px 10px;'
        f"background:{badge_colour};color:#ffffff;border-radius:12px;"
        f'font-size:11px;font-weight:600;text-transform:uppercase;">'
        f"{_esc(category)}</span></td>"
        "</tr></table></td></tr>"
        # Body
        '<tr><td style="padding:24px;color:#374151;font-size:14px;line-height:1.6;">'
        f'<p style="margin-top:0;">{greeting}</p>'
        f"{body_section}"
        f"{bms_section}"
        f"{next_steps}"
        f"{contact_section}"
        f"{original_quote}"
        "</td></tr>"
        # Footer with SENTINEL branding
        '<tr><td style="background:#f9fafb;padding:16px 24px;'
        "border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280;"
        'line-height:1.5;">'
        '<p style="margin:0 0 4px;font-weight:600;color:#1e3a5f;">SENTINEL Building Management</p>'
        '<p style="margin:0;">This is an automated message from the SENTINEL '
        "building management system. Please reply to this email if you have "
        "additional information to share.</p>"
        "</td></tr>"
        "</table></td></tr></table></body></html>"
    )


def _esc(text: str) -> str:
    """Minimal HTML escaping for user-provided content."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


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
            alerts = alert_repo.get_active_by_building(building_uuid)
            if alerts:
                context["active_alerts"] = [
                    {
                        "equipment_id": a.get("equipment_id"),
                        "severity": a.get("severity"),
                        "message": a.get("title") or a.get("message"),
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
        # Desk number is more specific than a vague zone/floor hint
        has_desk = req.zone_hint and req.zone_hint.lower().startswith("desk")
        score = min(1.0, score + (0.10 if has_desk else 0.05))
    if req.issue_category and req.issue_category != "general":
        score = min(1.0, score + 0.05)
    if req.from_name:
        score = min(1.0, score + 0.03)
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
# Work order creation from email intake
# ---------------------------------------------------------------------------

# Category → WO specialty mapping
_CATEGORY_SPECIALTY: dict[str, str] = {
    "hvac": "hvac",
    "electrical": "electrical",
    "plumbing": "plumbing",
    "fire": "fire",
    "lighting": "dali",
    "access": "general",
    "elevator": "general",
    "pest": "general",
    "structural": "general",
    "general": "general",
}

# Urgency → WO priority mapping (DB allows: low, medium, high, urgent)
_URGENCY_PRIORITY: dict[str, str] = {
    "low": "low",
    "normal": "medium",
    "high": "high",
    "critical": "urgent",
}

# WO priority rank for comparisons
_WO_PRIORITY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3, "urgent": 4}


def _priority_rank(priority: str) -> int:
    """Return numeric rank for a WO priority string."""
    return _WO_PRIORITY_RANK.get(priority, 0)


async def _create_concept_work_order(intake: dict[str, Any]) -> Optional[str]:
    """Create a real work order from an auto-submitted email intake.

    Returns the WO code (e.g. ``WO-2026-0042``) or ``None`` on failure.
    """
    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

        wo_repo = WorkOrderRepository()

        specialty = _CATEGORY_SPECIALTY.get(intake.get("issue_category", "general"), "general")
        priority = _URGENCY_PRIORITY.get(intake.get("urgency", "normal"), "medium")

        # --- Attempt technician auto-assignment (same pattern as call-log) ---
        tech: Optional[dict[str, Any]] = None
        site_id = intake.get("site_id")
        if site_id:
            try:
                from app.database.supabase_client import get_supabase_client

                sb = get_supabase_client()
                if sb:
                    bld = sb.table("buildings").select("id").eq("code", site_id).execute()
                    if bld.data:
                        building_id = bld.data[0]["id"]
                        tech_result = (
                            sb.table("site_technicians")
                            .select("specialty, technicians(id, name, email, phone, telegram_id)")
                            .eq("building_id", building_id)
                            .eq("specialty", specialty)
                            .eq("is_primary", True)
                            .execute()
                        )
                        if tech_result.data:
                            tech = tech_result.data[0].get("technicians", {})
                        elif specialty != "general":
                            # Fallback to general-specialty primary tech
                            tech_result = (
                                sb.table("site_technicians")
                                .select("specialty, technicians(id, name, email, phone, telegram_id)")
                                .eq("building_id", building_id)
                                .eq("specialty", "general")
                                .eq("is_primary", True)
                                .execute()
                            )
                            if tech_result.data:
                                tech = tech_result.data[0].get("technicians", {})
            except Exception as e:
                logger.warning("WO technician lookup failed: %s", e)

        # --- Build WO payload ---
        location_hint = intake.get("zone_hint") or intake.get("floor_hint") or "Not specified"

        # Use taxonomy fields for structured WO title (matches Telegram call-log format)
        tax_discipline = intake.get("taxonomy_discipline")
        tax_sub_category = intake.get("taxonomy_sub_category")
        tax_specialty = intake.get("taxonomy_specialty")

        if tax_discipline and tax_sub_category:
            wo_title = f"{tax_discipline}: {tax_sub_category}"
            # Use taxonomy specialty for tech routing if available
            if tax_specialty:
                specialty = tax_specialty
            # Escalate priority if taxonomy says higher
            tax_priority = _URGENCY_PRIORITY.get(intake.get("taxonomy_priority") or "", "")
            if tax_priority and _priority_rank(tax_priority) > _priority_rank(priority):
                priority = tax_priority
        else:
            wo_title = intake.get("issue_summary") or intake.get("subject", "Email reported issue")

        wo_data: dict[str, Any] = {
            "title": wo_title,
            "description": (
                f"Reported by: {intake.get('from_name', '')} <{intake.get('from_email', '')}>\n"
                f"Subject: {intake.get('subject', '')}\n"
                f"Category: {intake.get('issue_category', 'general')}\n"
                f"Location hint: {location_hint}\n\n"
                f"{(intake.get('body_plain') or '')[:2000]}"
            ),
            "priority": priority,
            "status": "scheduled",
            "created_by": f"email_intake:{intake.get('id', 'unknown')}",
        }
        if tech:
            wo_data["assigned_to"] = tech.get("name")
            wo_data["assigned_team"] = specialty

        created = await wo_repo.create_work_order(wo_data)
        if not created:
            logger.warning("WO creation returned None for intake %s", intake.get("id"))
            return None

        wo_code = created.get("code", "")

        # Link WO back to email intake record
        repo = get_email_intake_repository()
        repo.update_status(
            intake["id"],
            "submitted",
            local_wo_id=created.get("id"),
            concept_ref=wo_code,
        )

        logger.info("Created WO %s for email intake %s", wo_code, intake.get("id"))
        return wo_code

    except Exception as e:
        logger.error("Failed to create WO for intake %s: %s", intake.get("id"), e)
        return None


# ---------------------------------------------------------------------------
# Threaded reply helper (Phase 131.2b)
# ---------------------------------------------------------------------------


async def _send_reply_and_respond(
    *,
    action_taken: str,
    intake_id: str,
    record: dict[str, Any],
    bms_context: Optional[dict[str, Any]],
    concept_ref: Optional[str],
    message: str,
    urgency: str,
    req: EmailIntakeRequest,
) -> EmailIntakeResponse:
    """Build reply templates, optionally send via backend SMTP, return response.

    If ``email_reply_enabled`` is True and SMTP is configured, the backend
    sends a threaded reply directly (with correct In-Reply-To / References).
    The response includes ``reply_sent=True`` so n8n can skip its own SMTP node.

    If disabled or sending fails, ``reply_sent=False`` and n8n falls back to
    its own emailSend node (without threading).
    """
    # Phase 134: Use agent-generated reply if available, else template
    if record.get("_agent_reply_text"):
        reply_template = record["_agent_reply_text"]
        reply_html = record["_agent_reply_html"]
    else:
        reply_template = _build_reply_template(action_taken, record)
        reply_html = _build_reply_html(action_taken, record)

    reply_sent = False
    reply_message_id: Optional[str] = None
    reply_error: Optional[str] = None

    svc = get_email_reply_service()
    if svc.is_configured():
        # Build subject with Re: prefix + WO code suffix for Outlook threading
        original_subject = req.subject or ""
        reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
        # Only append local WO-... codes to subject (not FNBFW or other external refs)
        if concept_ref and concept_ref.startswith("WO-") and concept_ref not in reply_subject:
            reply_subject = f"{reply_subject} [{concept_ref}]"

        result = await svc.send_reply(
            to_email=req.from_email,
            to_name=req.from_name,
            subject=reply_subject,
            body_plain=reply_template,
            body_html=reply_html,
            in_reply_to=req.message_id,
            references=req.references,
        )

        reply_sent = result.sent
        reply_message_id = result.message_id
        reply_error = result.error

        # Persist threading fields on the intake record
        repo = get_email_intake_repository()
        update_fields: dict[str, Any] = {
            "reply_sent": reply_sent,
        }
        if reply_message_id:
            update_fields["outbound_message_id"] = reply_message_id
        if result.references:
            update_fields["outbound_references"] = result.references
        if reply_sent:
            update_fields["outbound_sent_at"] = datetime.utcnow().isoformat()
        if req.references:
            update_fields["references_header"] = req.references

        repo.update_status(intake_id, record.get("pipeline_status", "routed"), **update_fields)

        if reply_error:
            logger.warning("Backend reply failed for %s: %s (n8n fallback)", intake_id, reply_error)

    return EmailIntakeResponse(
        success=True,
        intake_id=intake_id,
        action_taken=action_taken,
        concept_ref=concept_ref,
        bms_context=bms_context,
        message=message,
        reply_template=reply_template,
        reply_html=reply_html,
        urgency=urgency,
        reply_sent=reply_sent,
        reply_message_id=reply_message_id,
        reply_error=reply_error,
        agent_model=record.get("extraction_model"),
    )


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


@router.post("/intake", response_model=EmailIntakeResponse, tags=["llm_touching"])
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

    # 2a. Phase 137-04: Email intake hardening
    # Domain allowlist
    if not check_email_domain_allowed(req.from_email):
        logger.warning(
            "Email intake blocked: domain not allowed sender=%s",
            req.from_email,
        )
        raise HTTPException(
            status_code=403,
            detail="Sender domain not in allowlist",
        )

    # Per-sender rate limit
    if not check_email_sender_rate_limit(req.from_email):
        logger.warning(
            "Email intake rate limited: sender=%s",
            req.from_email,
        )
        raise HTTPException(
            status_code=429,
            detail="Sender rate limit exceeded. Try again later.",
        )

    # Attachment file type allowlist
    if hasattr(req, "attachments") and req.attachments:
        for attachment in req.attachments:
            filename = (
                attachment.get("filename", "") if isinstance(attachment, dict) else getattr(attachment, "filename", "")
            )
            if filename and not check_attachment_type_allowed(filename):
                logger.warning(
                    "Email intake blocked attachment: filename=%s sender=%s",
                    filename,
                    req.from_email,
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Attachment type not allowed: {filename}. Allowed: .pdf, .jpg, .jpeg, .png",
                )

    # Unknown sender quarantine
    if not is_known_sender(req.from_email):
        logger.info(
            "Email intake quarantined: unknown sender=%s subject=%s",
            req.from_email,
            req.subject,
        )
        # Return a quarantine response instead of processing via LLM
        return EmailIntakeResponse(
            success=True,
            intake_id=str(uuid.uuid4()),
            action_taken="quarantined",
            concept_ref=None,
            reply_template="Your message has been received and is pending review by an administrator.",
            reply_html="",
            message="Unknown sender — quarantined for admin review",
        )

    # --- Prompt guard: score email body as webhook source ---
    email_text = f"{req.subject or ''}\n{req.body_plain or ''}"
    guard_result = score_prompt(email_text, "webhook")
    if not guard_result.allow:
        logger.warning(
            "Email intake prompt guard BLOCKED: sender=%s score=%.2f",
            req.from_email,
            guard_result.score,
        )
        raise HTTPException(
            status_code=400,
            detail="Email content blocked by prompt injection guard",
        )

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

            # Current email fields win, but preserve parent's WO ref
            merged = {**existing, **follow_up_record}
            if existing.get("concept_ref"):
                merged["concept_ref"] = existing["concept_ref"]
            return await _send_reply_and_respond(
                action_taken="linked_existing",
                intake_id=intake_id,
                record=merged,
                bms_context=None,
                concept_ref=existing.get("concept_ref"),
                message=f"Linked to existing reference {req.existing_reference}",
                urgency=req.urgency,
                req=req,
            )

    # 3b. Exact message_id dedup
    if req.message_id:
        dup = repo.get_by_message_id(req.message_id)
        if dup:
            return await _send_reply_and_respond(
                action_taken="duplicate",
                intake_id=dup["id"],
                record=dup,
                bms_context=None,
                concept_ref=dup.get("concept_ref"),
                message="Duplicate message_id — already processed",
                urgency=dup.get("urgency", "normal"),
                req=req,
            )

    # 3c. Heuristic recent-window dedup (with subject similarity gate)
    recent = repo.find_recent(
        from_email=req.from_email,
        site_id=req.site_id,
        issue_category=req.issue_category,
        hours=settings.email_intake_duplicate_window_hours,
    )
    if recent and not _subjects_similar(req.subject or "", recent.get("subject", "")):
        logger.info(
            "Dedup skip: subjects too different — %r vs %r",
            req.subject,
            recent.get("subject", ""),
        )
        recent = None  # subjects too different — treat as new intake
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

        # Current email fields win, but preserve parent's WO ref
        merged_recent = {**recent, **follow_up_record}
        if recent.get("concept_ref"):
            merged_recent["concept_ref"] = recent["concept_ref"]
        return await _send_reply_and_respond(
            action_taken="linked_existing",
            intake_id=intake_id,
            record=merged_recent,
            bms_context=None,
            concept_ref=recent.get("concept_ref"),
            message="Linked to recent intake from same sender",
            urgency=req.urgency,
            req=req,
        )

    # ------------------------------------------------------------------
    # 3d. BMS enrichment (moved before agent — feeds into agent prompt)
    # ------------------------------------------------------------------
    req_category = req.issue_category or "general"
    bms_context = await _enrich_with_bms(req.site_id, req_category)

    # ------------------------------------------------------------------
    # 4. AI Agent classification + reply (Phase 134)
    # ------------------------------------------------------------------
    agent_result = None
    taxonomy_result = None

    if settings.email_intake_agent_enabled:
        try:
            from app.services.email_intake_agent import get_email_intake_agent

            agent = get_email_intake_agent()
            agent_result = await agent.classify_and_reply(
                from_name=req.from_name,
                from_email=req.from_email,
                subject=req.subject or "",
                body_plain=req.body_plain,
                site_id=req.site_id,
                bms_context=bms_context,
            )
            logger.info(
                "Agent result: %s/%s, action=%s, model=%s, latency=%dms",
                agent_result.discipline,
                agent_result.sub_category,
                agent_result.action,
                agent_result.agent_model,
                agent_result.agent_latency_ms,
            )

            # Map agent result to request fields
            req_category = DISCIPLINE_TO_CATEGORY.get(agent_result.discipline, req_category)
            req.issue_category = req_category
            req.zone_hint = req.zone_hint or (
                f"Desk {agent_result.location_desk}" if agent_result.location_desk else None
            )
            req.floor_hint = req.floor_hint or agent_result.location_floor
            req.from_phone = req.from_phone or agent_result.phone

            # Use agent's classification as taxonomy result
            taxonomy_result = {
                "discipline": agent_result.discipline,
                "sub_category": agent_result.sub_category,
                "specialty": agent_result.specialty,
                "priority": agent_result.priority,
            }

        except Exception as exc:
            logger.warning("Agent call failed, falling back to keyword pipeline: %s", exc)
            agent_result = None

    # ------------------------------------------------------------------
    # 4b. Keyword fallback (if agent disabled or failed)
    # ------------------------------------------------------------------
    if agent_result is None:
        taxonomy_result = classify_email_subject(req.subject or "", req.body_plain or "")
        if taxonomy_result:
            req_category = DISCIPLINE_TO_CATEGORY.get(taxonomy_result["discipline"], req.issue_category)
            if req_category != req.issue_category:
                logger.info(
                    "Taxonomy override: %s -> %s (sub: %s)",
                    req.issue_category,
                    req_category,
                    taxonomy_result["sub_category"],
                )
                req.issue_category = req_category
        else:
            req_category = req.issue_category  # keep n8n's classification

        # Location extraction from email text (fills gaps n8n missed)
        if not req.zone_hint and (req.subject or req.body_plain):
            combined = f"{req.subject or ''} {req.body_plain or ''}"
            desk = extract_desk_from_message(combined)
            if desk:
                req.zone_hint = f"Desk {desk}"
            floor = extract_floor_from_message(combined)
            if floor and not req.floor_hint:
                req.floor_hint = floor

        # Phone number extraction from email body (SA mobile format)
        if not req.from_phone and req.body_plain:
            phone_match = re.search(r"\b(0\d{9})\b", req.body_plain)
            if not phone_match:
                phone_match = re.search(r"\b(\+27\d{9})\b", req.body_plain)
            if phone_match:
                req.from_phone = phone_match.group(1)

    # ------------------------------------------------------------------
    # 5. Urgency escalation
    # ------------------------------------------------------------------
    if agent_result is not None:
        # Use agent priority, but still apply BMS alert escalation
        _PRIORITY_TO_URGENCY = {"critical": "critical", "high": "high", "medium": "normal", "low": "low"}
        final_urgency = _PRIORITY_TO_URGENCY.get(agent_result.priority, "normal")
        # BMS alert escalation on top
        active_alerts = bms_context.get("active_alerts", [])
        if active_alerts:
            critical_alerts = [a for a in active_alerts if a.get("severity") in ("critical", "emergency")]
            if critical_alerts and URGENCY_RANK.get(final_urgency, 2) < 4:
                final_urgency = "critical"
            elif active_alerts and URGENCY_RANK.get(final_urgency, 2) < 3:
                final_urgency = "high"
    else:
        final_urgency = _apply_urgency_escalation(req, bms_context)
        if taxonomy_result:
            _TAX_TO_URGENCY = {"critical": "critical", "high": "high", "medium": "normal", "low": "low"}
            tax_urgency = _TAX_TO_URGENCY.get(taxonomy_result["priority"], "normal")
            if URGENCY_RANK.get(tax_urgency, 2) > URGENCY_RANK.get(final_urgency, 2):
                logger.info("Taxonomy priority escalation: %s -> %s", final_urgency, tax_urgency)
                final_urgency = tax_urgency

    # ------------------------------------------------------------------
    # 6. Completeness scoring + route
    # ------------------------------------------------------------------
    if agent_result is not None:
        completeness = agent_result.completeness
        route = agent_result.action
    else:
        completeness = _score_completeness(req)
        if taxonomy_result:
            completeness = min(1.0, completeness + 0.10)
            completeness = round(completeness, 3)
        route = _determine_route(completeness)

    # Map route to action_taken (WO always created, action reflects routing)
    action_taken = route  # auto_submit | request_info | manual_review

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
        "issue_category": req_category,
        "issue_summary": (agent_result.issue_summary if agent_result else None) or req.issue_summary,
        "urgency": final_urgency,
        "taxonomy_discipline": taxonomy_result["discipline"] if taxonomy_result else None,
        "taxonomy_sub_category": taxonomy_result["sub_category"] if taxonomy_result else None,
        "taxonomy_specialty": taxonomy_result["specialty"] if taxonomy_result else None,
        "taxonomy_priority": taxonomy_result["priority"] if taxonomy_result else None,
        "extraction_confidence": completeness,
        "extraction_model": (agent_result.agent_model if agent_result else None) or req.extraction_model,
        "extraction_raw": req.extraction_raw,
        "bms_context": bms_context if bms_context else None,
        "enrichment_ts": now_iso if bms_context else None,
        "pipeline_status": "routed",
        "action_taken": action_taken,
        "routing_reason": (
            f"completeness={completeness}, route={route}, "
            f"agent={agent_result.agent_model if agent_result else 'keyword'}"
        ),
        "existing_reference": req.existing_reference,
        "attachment_count": req.attachment_count,
        "attachment_refs": req.attachment_refs,
        "processed_by": "sentinel",
    }

    repo.create(record)

    # ------------------------------------------------------------------
    # 7b. Work order creation — always create so WO number is in reply
    # ------------------------------------------------------------------
    concept_ref: Optional[str] = None
    concept_ref = await _create_concept_work_order(record)
    if concept_ref:
        record["concept_ref"] = concept_ref

    # ------------------------------------------------------------------
    # 7c. Replace {ref} placeholder in agent reply with actual WO code
    # ------------------------------------------------------------------
    if agent_result is not None:
        ref_value = concept_ref or record.get("id", "")[:8]
        agent_reply_text = agent_result.reply_text.replace("{ref}", ref_value)
        agent_reply_html = agent_result.reply_html.replace("{ref}", ref_value)
        # Override the template reply functions with agent-generated reply
        record["_agent_reply_text"] = agent_reply_text
        record["_agent_reply_html"] = agent_reply_html

    # 8. Store inbound references header for thread chain tracking
    if req.references:
        record["references_header"] = req.references

    # 9. Build response + send threaded reply if backend SMTP enabled
    return await _send_reply_and_respond(
        action_taken=action_taken,
        intake_id=intake_id,
        record=record,
        bms_context=bms_context if bms_context else None,
        concept_ref=concept_ref,
        message=f"Email intake processed: {action_taken}",
        urgency=final_urgency,
        req=req,
    )
