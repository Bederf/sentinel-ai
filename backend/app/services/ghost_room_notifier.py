"""Ghost-room notification and concierge reply handling."""

from __future__ import annotations

import logging
from typing import Any

from app.models.booking_record import BlockBookingConfig
from app.models.space_occupancy import GhostBookingFinding
from app.services import occupancy_store
from app.services.ghost_booking_detector import concierge_confirm_empty, concierge_confirm_occupied
from app.services.n8n_service import get_n8n_service

logger = logging.getLogger(__name__)


def format_ghost_email_message(finding: GhostBookingFinding, site_name: str = "") -> str:
    site_label = site_name or finding.site_id
    return (
        f"Ghost booking reported for {finding.room_code}\n\n"
        f"Site: {site_label}\n"
        f"Room: {finding.room_name or finding.room_code}\n"
        f"Organiser: {finding.organiser_name or finding.organiser_email}\n"
        f"Booking: {finding.booking_start.strftime('%H:%M')} - {finding.booking_end.strftime('%H:%M')}\n"
        f"No presence detected for {finding.grace_period_minutes} minutes after the booking start time.\n\n"
        "Please inspect the room and confirm whether it is occupied or empty."
    )


def format_ghost_whatsapp_message(finding: GhostBookingFinding) -> str:
    return f"Ghost booking reported for {finding.room_code} please confirm if room is occupied reply yes/no"


async def _send_email_via_n8n(
    finding: GhostBookingFinding,
    config: BlockBookingConfig,
    site_name: str,
) -> bool:
    if not config.concierge_email:
        return False

    result = await get_n8n_service().trigger_webhook(
        webhook_path="space-ghost-room-alert",
        payload={
            "site_id": finding.site_id,
            "site_name": site_name or finding.site_id,
            "finding_id": finding.id,
            "room_code": finding.room_code,
            "room_name": finding.room_name,
            "to_email": config.concierge_email,
            "subject": f"Ghost booking alert: {finding.room_code}",
            "message": format_ghost_email_message(finding, site_name),
            "organiser_email": finding.organiser_email,
            "organiser_name": finding.organiser_name,
            "booking_start": finding.booking_start.isoformat(),
            "booking_end": finding.booking_end.isoformat(),
        },
    )
    return bool(result.get("success"))


async def _send_whatsapp(
    finding: GhostBookingFinding,
    config: BlockBookingConfig,
) -> dict[str, Any]:
    if not config.concierge_whatsapp:
        return {"success": False, "reason": "No concierge WhatsApp configured"}

    from app.integrations.whatsapp_service import get_whatsapp_service

    service = get_whatsapp_service()
    result = await service.send_text_message(
        config.concierge_whatsapp,
        format_ghost_whatsapp_message(finding),
    )
    return result


async def send_ghost_booking_alert(
    finding: GhostBookingFinding,
    config: BlockBookingConfig,
    site_name: str = "",
) -> dict[str, Any]:
    """Dispatch email via n8n and WhatsApp via Twilio/Sentry."""
    email_sent = False
    whatsapp_sent = False
    whatsapp_message_id: str | None = None

    try:
        email_sent = await _send_email_via_n8n(finding, config, site_name)
    except Exception as exc:
        logger.error("Ghost booking email dispatch failed: %s", exc)

    try:
        whatsapp_result = await _send_whatsapp(finding, config)
        whatsapp_sent = bool(whatsapp_result.get("success"))
        whatsapp_message_id = whatsapp_result.get("message_id")
    except Exception as exc:
        logger.error("Ghost booking WhatsApp dispatch failed: %s", exc)

    if email_sent or whatsapp_sent:
        occupancy_store.mark_ghost_finding_notified(
            finding.id,
            concierge_email=config.concierge_email,
            concierge_whatsapp=config.concierge_whatsapp,
            email_sent=email_sent,
            whatsapp_sent=whatsapp_sent,
            whatsapp_message_id=whatsapp_message_id,
        )

    return {
        "success": email_sent or whatsapp_sent,
        "email_sent": email_sent,
        "whatsapp_sent": whatsapp_sent,
        "whatsapp_message_id": whatsapp_message_id,
    }


async def process_concierge_whatsapp_reply(
    from_number: str,
    content: str,
    *,
    reply_to_message_id: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Handle a yes/no concierge reply for a pending ghost-room finding."""
    reply = (content or "").strip().lower()
    if reply not in {"yes", "no"}:
        return {"handled": False}

    finding = occupancy_store.find_pending_ghost_for_whatsapp(
        from_number,
        reply_to_message_id=reply_to_message_id,
    )
    if not finding:
        return {
            "handled": True,
            "response_message": "No pending ghost booking matched this reply.",
        }

    confirmed_by = f"whatsapp:{from_number}"
    if reply == "yes":
        updated = concierge_confirm_occupied(
            finding.id,
            confirmed_by,
            response_message_id=message_id,
            response_text=content,
        )
        status_text = "occupied"
    else:
        updated = occupancy_store.update_ghost_finding_status(
            finding.id,
            "confirmed_empty",
            inspected_by=confirmed_by,
            response_message_id=message_id,
            response_text=content,
        )
        if updated is None:
            updated = concierge_confirm_empty(
                finding.id,
                confirmed_by,
            )
        status_text = "empty"

    if updated is None:
        return {
            "handled": True,
            "response_message": f"{finding.room_code} was already resolved.",
        }

    return {
        "handled": True,
        "finding_id": finding.id,
        "status": updated.status,
        "response_message": f"Recorded: {finding.room_code} marked {status_text}.",
    }
