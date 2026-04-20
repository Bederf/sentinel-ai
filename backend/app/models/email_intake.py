"""Pydantic models for SENTINEL Email Intake Pipeline (Phase 134).

EmailIntakeRequest matches the n8n merge-node output.
Fields that were previously classified by n8n are now optional (backward compat)
since Phase 134 moves classification to the backend AI agent.
EmailIntakeResponse is returned to n8n for auto-reply templating.
"""

from __future__ import annotations

from typing import Any

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
    from_name: str | None = None
    from_phone: str | None = None
    from_department: str | None = None

    # Email metadata
    subject: str
    body_plain: str | None = None
    body_html: str | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    received_at: str | None = None  # ISO timestamp
    to: list[str] | None = None
    cc: list[str] | None = None
    source: str | None = None

    # AI extraction (optional — Phase 134 moves classification to backend agent)
    site_id: str | None = None
    zone_hint: str | None = None
    floor_hint: str | None = None
    issue_category: str | None = "general"
    issue_summary: str | None = None
    urgency: str = "normal"
    extraction_confidence: float = 0.70
    extraction_model: str | None = None
    extraction_raw: dict[str, Any] | None = None

    # Email threading (RFC 822)
    references: str | None = None  # References header from inbound email

    # Follow-up / reference linking
    existing_reference: str | None = None  # e.g. FNBFW:12345

    # Urgency signals from n8n parser (optional — Phase 134)
    urgency_boost: bool = False
    cc_count: int = 0
    has_manager_cc: bool = False

    # Attachments
    attachment_count: int = 0
    attachment_refs: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Response (SENTINEL → n8n)
# ---------------------------------------------------------------------------


class EmailIntakeResponse(BaseModel):
    """Returned to n8n so it can send the auto-reply."""

    success: bool
    intake_id: str | None = None
    action_taken: str  # new_intake | linked_existing | duplicate | ...
    concept_ref: str | None = None
    bms_context: dict[str, Any] | None = None
    message: str = ""
    reply_template: str | None = None  # plain-text reply body for n8n
    reply_html: str | None = None  # branded HTML reply for n8n
    urgency: str = "normal"

    # Backend SMTP reply status (Phase 131.2b)
    reply_sent: bool = False  # True if backend sent threaded reply via SMTP
    reply_message_id: str | None = None  # Outbound Message-ID header
    reply_error: str | None = None  # Error message if backend reply failed

    # Phase 134: AI agent metadata
    agent_model: str | None = None  # e.g. "gpt-4.1-nano", "claude", "keyword_fallback"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class EmailIntakeHealthResponse(BaseModel):
    """Health-check payload."""

    status: str = "ok"
    enabled: bool = False
    pipeline_version: str = "134.0"
