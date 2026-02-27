"""Pydantic models for SENTINEL Email Intake Pipeline (Phase 131).

EmailIntakeRequest matches the n8n merge-node output.
EmailIntakeResponse is returned to n8n for auto-reply templating.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    "hvac",
    "electrical",
    "plumbing",
    "fire",
    "access",
    "elevator",
    "pest",
    "general",
    "lighting",
    "structural",
}

VALID_URGENCIES = {"low", "normal", "high", "critical"}

VALID_ACTIONS = {
    "new_intake",
    "linked_existing",
    "duplicate",
    "request_info",
    "auto_submit",
    "manual_review",
}

VALID_PIPELINE_STATUSES = {
    "received",
    "enriched",
    "routed",
    "submitted",
    "closed",
}


# ---------------------------------------------------------------------------
# Request (n8n → SENTINEL)
# ---------------------------------------------------------------------------


class EmailIntakeRequest(BaseModel):
    """Payload POSTed by n8n after email parsing + AI classification."""

    # Requester identity
    from_email: str
    from_name: Optional[str] = None
    from_phone: Optional[str] = None
    from_department: Optional[str] = None

    # Email metadata
    subject: str
    body_plain: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    received_at: Optional[str] = None  # ISO timestamp

    # AI extraction (from n8n GPT-4.1 step)
    site_id: Optional[str] = None
    zone_hint: Optional[str] = None
    floor_hint: Optional[str] = None
    issue_category: Optional[str] = None
    issue_summary: Optional[str] = None
    urgency: str = "normal"
    extraction_confidence: float = 0.0
    extraction_model: Optional[str] = None
    extraction_raw: Optional[dict[str, Any]] = None

    # Follow-up / reference linking
    existing_reference: Optional[str] = None  # e.g. FNBFW:12345

    # Urgency signals from n8n parser
    urgency_boost: bool = False
    cc_count: int = 0
    has_manager_cc: bool = False

    # Attachments
    attachment_count: int = 0
    attachment_refs: Optional[list[dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Response (SENTINEL → n8n)
# ---------------------------------------------------------------------------


class EmailIntakeResponse(BaseModel):
    """Returned to n8n so it can send the auto-reply."""

    success: bool
    intake_id: Optional[str] = None
    action_taken: str  # new_intake | linked_existing | duplicate | ...
    concept_ref: Optional[str] = None
    bms_context: Optional[dict[str, Any]] = None
    message: str = ""
    reply_template: Optional[str] = None  # pre-built reply body for n8n
    urgency: str = "normal"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class EmailIntakeHealthResponse(BaseModel):
    """Health-check payload."""

    status: str = "ok"
    enabled: bool = False
    pipeline_version: str = "131.1"
