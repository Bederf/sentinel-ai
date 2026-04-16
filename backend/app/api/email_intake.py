"""Email Intake API — cluster emails into zone heatmap signals.

POST /api/emails/intake
  Called by n8n after parsing each incoming occupant email.
  Clusters by zone + complaint_type, with same-floor adjacency grouping.
  When count >= 3, surfaces in cockpit heatmap.

Auth: Bearer token (SENTINEL_API_KEY from settings).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.database.repositories.email_intake_repository import get_email_intake_repository
from app.services.email_cluster_service import get_email_cluster_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/emails", tags=["email-intake"])


def _check_api_key(authorization: str | None = Header(None)) -> str:
    """Validate Bearer token against configured sentry_bot_api_key."""
    if not settings.sentry_bot_api_key:
        raise HTTPException(status_code=503, detail="Email intake not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.sentry_bot_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return token


class EmailIntakeRequest(BaseModel):
    """Parsed email fields from n8n → SENTINEL."""

    from_email: str = Field(..., description="Sender email address")
    subject: str = Field(..., description="Email subject")
    body_plain: str = Field(default="", description="Plain text body")
    site_id: str = Field(..., description="Site code, e.g. site-002")
    desk_hint: str | None = Field(None, description="Desk number, e.g. 25")
    floor_hint: str | None = Field(None, description="Floor, e.g. L1")
    issue_category: str = Field(default="general", description="Taxonomy category from n8n")
    message_id: str | None = Field(None, description="RFC 822 Message-ID for dedup")


class EmailClusterResponse(BaseModel):
    """Cluster state returned to n8n for traceability."""

    cluster_id: str | None
    zone_id: str | None
    zone_name: str | None
    floor: str | None
    email_count: int
    complaint_type: str
    severity: str
    summary: str
    is_new: bool
    cockpit_visible: bool = Field(description="True when cluster count >= 3 and visible in cockpit heatmap")


@router.post("/intake", response_model=EmailClusterResponse)
async def intake_email(
    req: EmailIntakeRequest,
    _auth: Annotated[str, Depends(_check_api_key)],
) -> EmailClusterResponse:
    """
    Receive a parsed email from n8n, cluster it by zone, return cluster state.

    n8n should store the returned `cluster_id` on the email record for traceability.
    """
    intake_repo = get_email_intake_repository()
    cluster_service = get_email_cluster_service()

    # Dedupe on Message-ID
    if req.message_id:
        existing = intake_repo.get_by_message_id(req.message_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Duplicate message_id: {req.message_id} already processed as {existing['id']}",
            )

    # Store email intake
    intake_record = intake_repo.create(
        {
            "from_email": req.from_email,
            "subject": req.subject,
            "body_plain": req.body_plain,
            "site_id": req.site_id,
            "zone_hint": req.desk_hint,
            "floor_hint": req.floor_hint,
            "issue_category": req.issue_category,
            "message_id": req.message_id,
            "pipeline_status": "received",
        }
    )

    # Cluster
    cluster_state = cluster_service.intake_email(
        from_email=req.from_email,
        subject=req.subject,
        body_plain=req.body_plain,
        site_id=req.site_id,
        desk_hint=req.desk_hint,
        floor_hint=req.floor_hint,
        issue_category=req.issue_category,
        message_id=req.message_id,
    )

    # Link intake → cluster (idempotent)
    if cluster_state.get("cluster_id") and intake_record.get("id"):
        from app.database.repositories.email_cluster_repository import EmailClusterRepository

        cluster_repo = EmailClusterRepository()
        cluster_repo.link_intake_to_cluster(intake_record["id"], cluster_state["cluster_id"])

    cockpit_visible = cluster_state.get("email_count", 0) >= 3

    logger.info(
        "Email intake clustered: intake=%s cluster=%s zone=%s count=%d visible=%s",
        intake_record.get("id"),
        cluster_state.get("cluster_id"),
        cluster_state.get("zone_id"),
        cluster_state.get("email_count"),
        cockpit_visible,
    )

    return EmailClusterResponse(
        cluster_id=cluster_state.get("cluster_id"),
        zone_id=cluster_state.get("zone_id"),
        zone_name=cluster_state.get("zone_name"),
        floor=cluster_state.get("floor"),
        email_count=cluster_state.get("email_count", 0),
        complaint_type=cluster_state.get("complaint_type", "general"),
        severity=cluster_state.get("severity", "low"),
        summary=cluster_state.get("summary", ""),
        is_new=cluster_state.get("is_new", False),
        cockpit_visible=cockpit_visible,
    )
