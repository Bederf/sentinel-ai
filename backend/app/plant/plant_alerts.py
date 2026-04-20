"""FastAPI router for Desigo plant-room alert ingestion and retrieval.

Endpoints:
- POST /api/plant/alerts/ingest  -- parse email, save alarm, send WhatsApp
- GET  /api/plant/alerts         -- recent alarms for a site
- GET  /api/plant/alerts/{id}    -- single alarm by ID
- POST /api/plant/alerts/{id}/acknowledge -- mark alarm as notified/acknowledged
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.plant import alarm_store, email_parser
from app.plant.notification_throttle import (
    ThrottleAction,
    format_flood_summary,
    get_throttle,
)
from app.plant.plant_notifier import send_plant_alert, send_raw_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plant/alerts", tags=["plant-alerts"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    """Payload sent by n8n when a Desigo email arrives."""

    from_address: str = Field(..., description="Sender email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(default="", description="Email body text")
    received_at: datetime | None = Field(default=None, description="When the email was received")
    site_id: str | None = Field(default=None, description="Override site ID (defaults to PLANT_SITE_ID)")


class IngestResponse(BaseModel):
    """Response returned after successful ingestion."""

    alarm_id: str
    severity: str
    equipment: str
    notified: bool
    cleared: bool


class AcknowledgeResponse(BaseModel):
    """Response returned after acknowledging an alarm."""

    alarm_id: str
    acknowledged: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse)
async def ingest_email(req: IngestRequest):
    """Parse a Desigo fault email, save the alarm, and trigger WhatsApp notification.

    Validates sender address against DESIGO_SENDER_EMAIL setting.
    Returns 403 if sender is not authorised.
    Returns 400 if subject is empty.
    Returns 409 if a duplicate alarm exists within the dedup window.
    """
    # 1. Validate sender
    allowed_sender = settings.desigo_sender_email.strip().lower()
    if req.from_address.strip().lower() != allowed_sender:
        raise HTTPException(
            status_code=403,
            detail=f"Sender '{req.from_address}' not authorised. Expected '{allowed_sender}'.",
        )

    # 2. Validate subject
    if not req.subject or not req.subject.strip():
        raise HTTPException(status_code=400, detail="Subject must not be empty.")

    # 3. Check duplicate
    is_dup = await alarm_store.check_duplicate(req.subject)
    if is_dup:
        raise HTTPException(status_code=409, detail="Duplicate alarm within dedup window.")

    # 4. Parse email
    site_id = req.site_id or settings.plant_site_id
    alarm = email_parser.parse_desigo_email(
        subject=req.subject,
        body=req.body,
        received_at=req.received_at,
        site_id=site_id,
    )
    alarm.building = settings.plant_building_name

    # 5. Save alarm
    saved = await alarm_store.save_alarm(alarm)
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to persist alarm.")

    # 6. Send WhatsApp notification (throttle-aware)
    notified = False
    try:
        throttle = get_throttle()
        decision = throttle.check_alarm(alarm)

        if decision.action == ThrottleAction.SEND:
            ok = await send_plant_alert(alarm)
            if ok:
                throttle.record_send()
                await alarm_store.mark_notified(alarm.id)
                notified = True
        elif decision.action == ThrottleAction.SEND_FLOOD_SUMMARY:
            flood_msg = format_flood_summary(
                decision.equipment,
                decision.flood_count,
                throttle.flood_window_minutes,
            )
            ok = await send_raw_message(flood_msg)
            if ok:
                throttle.record_send()
            logger.warning("Flood summary sent for %s: %s", decision.equipment, decision.reason)
        else:
            # SUPPRESS — alarm saved but no notification
            logger.info("Notification suppressed: %s", decision.reason)
    except Exception:
        logger.exception("WhatsApp notification failed for alarm %s", alarm.id)

    return IngestResponse(
        alarm_id=alarm.id,
        severity=alarm.severity.value,
        equipment=alarm.equipment_description,
        notified=notified,
        cleared=alarm.cleared,
    )


@router.get("/")
async def get_recent_alarms(site_id: str | None = None, limit: int = 50):
    """Return the most recent alarms for a site.

    Args:
        site_id: Site identifier. Defaults to PLANT_SITE_ID setting.
        limit: Maximum number of alarms to return. Defaults to 50.
    """
    resolved_site = site_id or settings.plant_site_id
    alarms = await alarm_store.get_recent_alarms(resolved_site, limit=limit)
    return [a.model_dump() for a in alarms]


@router.get("/throttle/status")
async def throttle_status():
    """Return current throttle state — flood detection and rate limit status."""
    throttle = get_throttle()
    return {
        "flood": throttle.get_flood_status(),
        "rate_limit": throttle.get_rate_status(),
    }


@router.get("/{alarm_id}")
async def get_alarm(alarm_id: str):
    """Return a single alarm by ID, or 404 if not found."""
    # Search across all alarms (site-agnostic lookup)
    alarms = await alarm_store.get_recent_alarms(settings.plant_site_id, limit=10000)
    for a in alarms:
        if a.id == alarm_id:
            return a.model_dump()
    raise HTTPException(status_code=404, detail=f"Alarm '{alarm_id}' not found.")


@router.post("/{alarm_id}/acknowledge", response_model=AcknowledgeResponse)
async def acknowledge_alarm(alarm_id: str):
    """Mark an alarm as acknowledged (notified)."""
    ok = await alarm_store.mark_notified(alarm_id)
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge alarm '{alarm_id}'.")
    return AcknowledgeResponse(alarm_id=alarm_id, acknowledged=True)
