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


def format_ghost_email_message(finding: GhostBookingFinding, site_name: str = "", *, is_reminder: bool = False) -> str:
    site_label = site_name or finding.site_id
    prefix = "REMINDER — " if is_reminder else ""
    start_local = _to_sast(finding.booking_start)
    end_local = _to_sast(finding.booking_end)
    booking_date = start_local.strftime("%A %d %B %Y")
    start = start_local.strftime("%H:%M")
    end = end_local.strftime("%H:%M")
    duration_min = int((finding.booking_end - finding.booking_start).total_seconds() / 60)
    organiser_name = finding.organiser_name or "Unknown"
    organiser_email = finding.organiser_email or "Unknown"

    lines = [
        f"{prefix}GHOST BOOKING ALERT — {site_label}",
        "=" * 50,
        "",
        f"Room {finding.room_name or finding.room_code} has been booked but no presence",
        f"has been detected for {finding.grace_period_minutes} minutes after the start time.",
        "",
        "BOOKING DETAILS",
        "-" * 30,
        f"  Room:       {finding.room_name or finding.room_code}",
        f"  Room Code:  {finding.room_code}",
        f"  Date:       {booking_date}",
        f"  Time:       {start} – {end} ({duration_min} min)",
        "",
        "ORGANISER",
        "-" * 30,
        f"  Name:       {organiser_name}",
        f"  Email:      {organiser_email}",
        "",
        "ACTION REQUIRED",
        "-" * 30,
        f"  1. Physically inspect {finding.room_code}",
        "  2. If empty — the room can be released for other use",
        "  3. If occupied — no action needed (sensor may need recalibration)",
        "",
        "If the organiser needs to be contacted:",
        f"  → Email: {organiser_email}",
        "",
        f"Finding ID: {finding.id}",
        "",
        "—",
        f"SENTINEL Space Intelligence — {site_label}",
    ]
    return "\n".join(lines)


def _to_sast(dt):
    """Convert a datetime to SAST (UTC+2) for display."""
    from datetime import timezone, timedelta

    sast = timezone(timedelta(hours=2))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(sast)


def format_ghost_whatsapp_message(finding: GhostBookingFinding, *, is_reminder: bool = False) -> str:
    prefix = "REMINDER: " if is_reminder else ""
    start_local = _to_sast(finding.booking_start)
    end_local = _to_sast(finding.booking_end)
    return (
        f"{prefix}Ghost booking: *{finding.room_code}*\n"
        f"Organiser: {finding.organiser_name or finding.organiser_email}\n"
        f"Booked: {start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}\n"
        f"No movement detected for {finding.grace_period_minutes} min.\n\n"
        f"Swipe-reply on THIS message with *yes* or *no*."
    )


def _send_email_direct_smtp(to_email: str, subject: str, body: str) -> bool:
    """Send ghost alert email via SMTP using rooms@ mailbox (or fallback to notification SMTP)."""
    import smtplib
    from email.mime.text import MIMEText

    from app.config.settings import settings

    # Prefer rooms@ dedicated mailbox, fall back to notification SMTP
    host = settings.rooms_smtp_host or settings.notification_smtp_host
    port = settings.rooms_smtp_port or settings.notification_smtp_port
    username = settings.rooms_smtp_username or settings.notification_smtp_username
    password = settings.rooms_smtp_password or settings.notification_smtp_password
    from_name = settings.rooms_smtp_from_name or "SENTINEL Room Alerts"

    if not (host and username and password):
        logger.warning("No SMTP configured — cannot send ghost alert email")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{username}>"
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(host, port, timeout=10)
        server.starttls()
        server.login(username, password)
        server.sendmail(username, to_email, msg.as_string())
        server.quit()
        logger.info("Ghost alert email sent from %s to %s", username, to_email)
        return True
    except Exception as exc:
        logger.error("Direct SMTP send failed: %s", exc)
        return False


async def _send_email(
    finding: GhostBookingFinding,
    config: BlockBookingConfig,
    site_name: str,
    *,
    is_reminder: bool = False,
) -> bool:
    if not config.concierge_email:
        return False

    subject = f"{'REMINDER — ' if is_reminder else ''}Ghost booking alert: {finding.room_code}"
    body = format_ghost_email_message(finding, site_name, is_reminder=is_reminder)

    # Try n8n webhook first
    try:
        result = await get_n8n_service().trigger_webhook(
            webhook_path="space-ghost-room-alert",
            payload={
                "site_id": finding.site_id,
                "site_name": site_name or finding.site_id,
                "finding_id": finding.id,
                "room_code": finding.room_code,
                "room_name": finding.room_name,
                "to_email": config.concierge_email,
                "subject": subject,
                "message": body,
                "organiser_email": finding.organiser_email,
                "organiser_name": finding.organiser_name,
                "booking_start": finding.booking_start.isoformat(),
                "booking_end": finding.booking_end.isoformat(),
            },
        )
        if result.get("success"):
            return True
    except Exception as exc:
        logger.warning("n8n webhook failed, falling back to direct SMTP: %s", exc)

    # Fallback: send directly via SMTP
    return _send_email_direct_smtp(config.concierge_email, subject, body)


async def _send_whatsapp(
    finding: GhostBookingFinding,
    config: BlockBookingConfig,
    *,
    is_reminder: bool = False,
) -> dict[str, Any]:
    if not config.concierge_whatsapp:
        return {"success": False, "reason": "No concierge WhatsApp configured"}

    from app.integrations.whatsapp_service import get_whatsapp_service

    service = get_whatsapp_service()
    result = await service.send_text_message(
        config.concierge_whatsapp,
        format_ghost_whatsapp_message(finding, is_reminder=is_reminder),
    )
    return result


async def send_ghost_booking_alert(
    finding: GhostBookingFinding,
    config: BlockBookingConfig,
    site_name: str = "",
    *,
    is_reminder: bool = False,
) -> dict[str, Any]:
    """Dispatch email via n8n and WhatsApp via Twilio/Sentry."""
    email_sent = False
    whatsapp_sent = False
    whatsapp_message_id: str | None = None

    try:
        email_sent = await _send_email(finding, config, site_name, is_reminder=is_reminder)
    except Exception as exc:
        logger.error("Ghost booking email dispatch failed: %s", exc)

    try:
        whatsapp_result = await _send_whatsapp(finding, config, is_reminder=is_reminder)
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
        pending_count = len(occupancy_store.get_pending_ghost_findings_for_whatsapp(from_number))
        if pending_count > 0:
            return {
                "handled": True,
                "response_message": (
                    "Please *swipe-reply* on the specific ghost room message with yes or no to confirm."
                ),
            }
        return {
            "handled": True,
            "response_message": "No pending ghost booking found.",
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
