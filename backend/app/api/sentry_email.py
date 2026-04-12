"""
SENTINEL Email Intake API — Advisor Strategy Classification

The n8n workflow handles layers 1-3 only (headers, signature, filtering).
Classification moves to Python backend using Haiku executor + Opus advisor.

This replaces the GPT-4.1 OpenAI node in n8n with a smarter, cheaper alternative.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4
import hmac
import logging
import os

from app.config.settings import settings
from app.services.sentry_email import get_email_classifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sentry-email", tags=["sentry-email"])


# ── Auth (mirrors sentry_webhooks.py pattern) ────────────────────


def _require_sentry_email_secret(
    provided_secret: Optional[str],
    endpoint_name: str = "email_intake",
) -> None:
    """Validate webhook secret with fail-closed behaviour in live mode."""
    configured_secret = (
        os.getenv("SENTRY_EMAIL_WEBHOOK_SECRET", "") or os.getenv("SENTRY_WEBHOOK_SECRET", "") or ""
    ).strip()

    if not configured_secret:
        if getattr(settings, "is_live_mode", False):
            logger.error("Missing SENTRY_EMAIL_WEBHOOK_SECRET in live mode for %s", endpoint_name)
            raise HTTPException(status_code=503, detail="Email intake misconfigured")
        return  # Allow in simulation mode

    if not provided_secret or not hmac.compare_digest(provided_secret, configured_secret):
        raise HTTPException(status_code=403, detail="Unauthorized")


# ── Request Model (from n8n layers 1-3 only) ─────────────────────


class EmailIntakeRequest(BaseModel):
    """
    Payload from n8n after header extraction + signature parsing.
    NO AI classification — that happens here in the backend.
    """

    # Requester (Layer 1: headers)
    from_email: str
    from_name: Optional[str] = None
    to_email: Optional[str] = None
    subject: str
    body_text: str
    body_html: Optional[str] = None
    message_id: Optional[str] = None
    received_at: Optional[str] = None
    importance: str = "normal"
    has_attachments: bool = False
    attachment_count: int = 0
    attachment_names: List[str] = []
    is_internal: bool = False

    # Threading (Layer 1: headers)
    is_reply: bool = False
    in_reply_to: Optional[str] = None

    # Signature extractions (Layer 3: regex)
    sig_cost_center: Optional[str] = None
    sig_building: Optional[str] = None
    sig_floor: Optional[str] = None
    sig_phone: Optional[str] = None
    sig_f_number: Optional[str] = None
    sig_department: Optional[str] = None
    sig_specific_location: Optional[str] = None

    # Derived by n8n
    existing_reference: Optional[str] = None
    site_id: Optional[str] = None
    urgency_boost: bool = False
    has_manager_cc: bool = False
    cc_count: int = 0


class EmailIntakeResponse(BaseModel):
    success: bool
    intake_id: str
    action_taken: str
    concept_ref: Optional[str] = None
    classification: Optional[Dict[str, Any]] = None
    advisor_consulted: bool = False
    message: str


# ── Main Endpoint ────────────────────────────────────────────────


@router.post("/intake", response_model=EmailIntakeResponse)
async def process_email_intake(
    intake: EmailIntakeRequest,
    background_tasks: BackgroundTasks,
    x_sentry_api_key: Optional[str] = Header(None),
):
    """
    Main intake endpoint called by n8n workflow.

    Flow:
    1. Validate auth
    2. Check for duplicate/follow-up (existing_reference)
    3. Classify via Haiku + Opus advisor
    4. Enrich with BMS data
    5. Score completeness
    6. Route: auto_submit / request_info / manual_review
    7. Store audit record
    8. Queue reply email
    """
    _require_sentry_email_secret(x_sentry_api_key)

    intake_id = str(uuid4())

    logger.info(
        f"Email intake: from={intake.from_email}, "
        f"subject={intake.subject[:50]}, "
        f"site={intake.site_id}, "
        f"existing_ref={intake.existing_reference}"
    )

    # ── 1. Duplicate/Follow-up Check ──
    if intake.existing_reference:
        # Link to existing work order — don't classify or create new
        action_taken = "linked_existing"
        concept_ref = intake.existing_reference

        background_tasks.add_task(_store_intake, intake_id, intake, None, {}, action_taken, concept_ref)

        return EmailIntakeResponse(
            success=True,
            intake_id=intake_id,
            action_taken=action_taken,
            concept_ref=concept_ref,
            advisor_consulted=False,
            message=f"Linked to existing work order {concept_ref}",
        )

    # ── 2. Classify via Advisor Strategy ──
    classifier = get_email_classifier()
    classification = await classifier.classify_email(
        from_email=intake.from_email,
        from_name=intake.from_name or "",
        subject=intake.subject,
        body_text=intake.body_text,
        sig_building=intake.sig_building,
        sig_floor=intake.sig_floor,
        sig_cost_center=intake.sig_cost_center,
        sig_specific_location=intake.sig_specific_location,
        existing_reference=intake.existing_reference,
        is_reply=intake.is_reply,
        importance=intake.importance,
        urgency_boost=intake.urgency_boost,
        has_manager_cc=intake.has_manager_cc,
    )

    # ── 3. BMS Enrichment ──
    bms_context = await _enrich_with_bms(
        site_id=intake.site_id,
        floor=intake.sig_floor or classification.specific_location,
        equipment_mentioned=classification.equipment_mentioned,
    )

    # Escalate urgency if BMS shows active alerts
    if bms_context.get("active_alerts"):
        if classification.urgency == "low":
            classification.urgency = "medium"
        elif classification.urgency == "medium":
            classification.urgency = "high"
        logger.info(f"Urgency escalated due to BMS alerts at {intake.site_id}")

    # ── 4. Completeness Scoring ──
    field_weights = {
        "from_name": 0.10,
        "from_email": 0.10,
        "cost_center": 0.15,
        "site_id": 0.15,
        "floor": 0.10,
        "issue_description": 0.20,
        "issue_category": 0.10,
        "urgency": 0.10,
    }

    field_values = {
        "from_name": intake.from_name,
        "from_email": intake.from_email,
        "cost_center": intake.sig_cost_center,
        "site_id": intake.site_id,
        "floor": intake.sig_floor or classification.specific_location,
        "issue_description": classification.issue_description,
        "issue_category": classification.issue_category,
        "urgency": classification.urgency,
    }

    confidence = sum(weight for field, weight in field_weights.items() if field_values.get(field))
    confidence = round(confidence, 2)

    missing_fields = [f for f, v in field_values.items() if not v]

    # ── 5. Route ──
    concept_ref = None

    if confidence >= 0.85:
        concept_ref = await _create_concept_work_order(intake, classification, bms_context)
        action_taken = "created_wo"
        message = f"Work order created: {concept_ref}" if concept_ref else "Created in local pipeline"

    elif confidence >= 0.60:
        action_taken = "requested_info"
        message = f"Missing: {', '.join(missing_fields)}"

    else:
        action_taken = "flagged_review"
        message = "Flagged for manual helpdesk review"

    # ── 6. Store Audit Record ──
    classification_dict = classification.model_dump()
    classification_dict["confidence"] = confidence
    classification_dict["missing_fields"] = missing_fields

    background_tasks.add_task(
        _store_intake,
        intake_id,
        intake,
        classification_dict,
        bms_context,
        action_taken,
        concept_ref,
    )

    # ── 7. Queue Reply Email ──
    if action_taken in ("created_wo", "requested_info"):
        reply = _build_reply(intake, classification, concept_ref, bms_context, action_taken, missing_fields)
        background_tasks.add_task(_queue_reply, reply)

    return EmailIntakeResponse(
        success=True,
        intake_id=intake_id,
        action_taken=action_taken,
        concept_ref=concept_ref,
        classification=classification_dict,
        advisor_consulted=classification.advisor_consulted,
        message=message,
    )


# ── BMS Enrichment ───────────────────────────────────────────────


async def _enrich_with_bms(
    site_id: Optional[str],
    floor: Optional[str],
    equipment_mentioned: Optional[str],
) -> Dict[str, Any]:
    """Cross-reference with live BMS data."""
    bms_context = {
        "active_alerts": [],
        "recent_work_orders": [],
        "equipment_status": None,
        "known_issues": [],
        "enrichment_timestamp": datetime.utcnow().isoformat(),
    }

    if not site_id:
        return bms_context

    try:
        # TODO: Wire to existing alert_service, equipment_service, agent_memory_repo
        # alerts = await alert_service.get_active_alerts(site_id=site_id, floor=floor)
        # bms_context["active_alerts"] = [...]
        pass
    except Exception as e:
        logger.error(f"BMS enrichment failed: {e}")
        bms_context["enrichment_error"] = str(e)

    return bms_context


# ── Concept API Bridge ───────────────────────────────────────────


async def _create_concept_work_order(intake, classification, bms_context) -> Optional[str]:
    """Push work order to MRI Evolution (Concept)."""
    # TODO: Implement when Concept API credentials available
    logger.info(f"Concept WO placeholder: site={intake.site_id}, category={classification.issue_category}")
    return None


# ── Reply Builder ────────────────────────────────────────────────


def _build_reply(intake, classification, concept_ref, bms_context, action, missing_fields) -> Dict:
    """Build auto-reply email."""
    if action == "created_wo":
        bms_note = ""
        if bms_context.get("active_alerts"):
            bms_note = (
                "\n\nNote: Our building systems have detected an active alert "
                "in this area. This has been included in the technician's briefing."
            )

        return {
            "to": intake.from_email,
            "subject": f"RE: {intake.subject} — {'Logged as ' + concept_ref if concept_ref else 'Received'} [SENTINEL]",
            "body": f"""Hi {intake.from_name or "there"},

Your maintenance request has been logged:

Reference: {concept_ref or "Pending assignment"}
Category: {classification.issue_category}
Priority: {classification.urgency}
Location: {", ".join(filter(None, [intake.sig_building, intake.sig_floor, classification.specific_location]))}

A technician will be assigned shortly.{bms_note}

— SENTINEL Facilities Assistant""",
        }
    else:
        field_labels = {
            "cost_center": "Your cost center number",
            "site_id": "Which building you're in",
            "floor": "Which floor/level",
            "issue_description": "A description of the issue",
        }
        missing_list = "\n".join(f"  - {field_labels.get(f, f)}" for f in missing_fields if f in field_labels)
        return {
            "to": intake.from_email,
            "subject": f"RE: {intake.subject} — Info Needed [SENTINEL]",
            "body": f"""Hi {intake.from_name or "there"},

Thank you for reporting this. To log your request, I need:

{missing_list}

Please reply with the missing details.

— SENTINEL Facilities Assistant""",
        }


# ── Storage ──────────────────────────────────────────────────────


async def _store_intake(
    intake_id: str,
    intake: EmailIntakeRequest,
    classification: Optional[Dict],
    bms_context: Dict,
    action_taken: str,
    concept_ref: Optional[str],
):
    """Store email intake record in Supabase."""
    # TODO: Wire to Supabase email_intakes table
    logger.info(f"Stored intake {intake_id}: action={action_taken}, concept_ref={concept_ref}")


async def _queue_reply(reply: Dict):
    """Send reply via n8n outbound email workflow or direct SMTP."""
    # TODO: POST to n8n outbound webhook or use SMTP directly
    logger.info(f"Reply queued: to={reply['to']}, subject={reply['subject']}")


# ── Health ───────────────────────────────────────────────────────


@router.get("/health")
async def email_intake_health():
    return {
        "status": "ok",
        "module": "sentry-email",
        "strategy": "advisor",
        "executor": "claude-haiku-4-5",
        "advisor": "claude-opus-4-6",
        "timestamp": datetime.utcnow().isoformat(),
    }
