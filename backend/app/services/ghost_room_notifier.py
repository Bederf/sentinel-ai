"""Ghost-room notification and concierge reply handling."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timezone
from typing import Any

from app.models.booking_record import BlockBookingConfig
from app.models.space_occupancy import GhostBookingFinding
from app.services import occupancy_store
from app.services.ghost_booking_detector import concierge_confirm_empty, concierge_confirm_occupied
from app.services.telegram_message_sender import InlineButton, InlineKeyboard, get_telegram_sender

logger = logging.getLogger(__name__)


def _resolve_related_ghost_signal(finding: GhostBookingFinding, *, resolution_state: str) -> None:
    """Mark the active concierge signal for this ghost finding as resolved/acknowledged."""
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    if not client:
        return

    try:
        result = (
            client.table("signal")
            .select("id, metadata")
            .eq("signal_type", "no_show_pattern")
            .eq("resolution_state", "active")
            .filter("metadata->>booking_id", "eq", finding.booking_id)
            .filter("metadata->>room_id", "eq", finding.room_code)
            .execute()
        )
    except Exception as exc:
        logger.warning("Failed to look up related ghost signal for %s: %s", finding.id, exc)
        return

    for row in result.data or []:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        try:
            client.table("signal").update(
                {
                    "resolution_state": resolution_state,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "metadata": {
                        **metadata,
                        "concierge_outcome": {
                            "finding_id": finding.id,
                            "status": finding.status,
                            "inspected_by": finding.inspected_by,
                            "inspected_at": finding.inspected_at.isoformat() if finding.inspected_at else None,
                            "response_text": finding.response_text,
                        },
                    },
                }
            ).eq("id", row["id"]).execute()
        except Exception as exc:
            logger.warning("Failed to resolve related ghost signal %s: %s", row.get("id"), exc)


def format_ghost_email_message(finding: GhostBookingFinding, site_name: str = "", *, is_reminder: bool = False) -> str:
    site_label = site_name or finding.site_id
    prefix = "REMINDER — " if is_reminder else ""
    start_local = _to_sast(finding.booking_start, assume_utc_if_naive=False)
    end_local = _to_sast(finding.booking_end, assume_utc_if_naive=False)
    booking_date = start_local.strftime("%A %d %B %Y")
    flagged_at = _to_sast(finding.detected_at).strftime("%A %d %B %Y %H:%M SAST")
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
        f"  Date Flagged: {flagged_at}",
        f"  Room:       {finding.room_name or finding.room_code}",
        f"  Room Code:  {finding.room_code}",
        f"  Date:       {booking_date}",
        f"  Time:       {start} - {end} ({duration_min} min)",
        "",
        "ORGANISER",
        "-" * 30,
        f"  Name:       {organiser_name}",
        f"  Email:      {organiser_email}",
        "",
    ]

    if finding.source_booking_flagged:
        lines.extend(
            [
                "RELATED ANOMALY",
                "-" * 30,
                "  This booking was already flagged as a block-booking anomaly.",
                "",
            ]
        )

    lines.extend(
        [
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
    )
    return "\n".join(lines)


def _to_sast(dt, *, assume_utc_if_naive: bool = True):
    """Convert a datetime to SAST for display.

    Booking timestamps are often already parsed as local SAST naive datetimes,
    while detection timestamps are usually stored as naive UTC.
    """
    from datetime import timedelta

    sast = timezone(timedelta(hours=2))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC if assume_utc_if_naive else sast)
    return dt.astimezone(sast)


def format_ghost_whatsapp_message(finding: GhostBookingFinding, *, is_reminder: bool = False) -> str:
    prefix = "REMINDER: " if is_reminder else ""
    start_local = _to_sast(finding.booking_start, assume_utc_if_naive=False)
    end_local = _to_sast(finding.booking_end, assume_utc_if_naive=False)
    message = (
        f"{prefix}Ghost booking: *{finding.room_code}*\n"
        f"Organiser: {finding.organiser_name or finding.organiser_email}\n"
        f"Date: {start_local.strftime('%d %b %Y')}\n"
        f"Booked: {start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}\n"
        f"No movement detected for {finding.grace_period_minutes} min.\n\n"
        "Swipe-reply on THIS message with:\n"
        "*yes* = room in use\n"
        "*no* = room empty"
    )
    if finding.source_booking_flagged:
        message = f"{message}\nPreviously flagged: block booking."
    return message


def format_ghost_email_html(finding: GhostBookingFinding, site_name: str = "", *, is_reminder: bool = False) -> str:
    """Build an HTML ghost booking alert email matching the visitor confirmation style."""
    site_label = site_name or finding.site_id
    prefix = "REMINDER — " if is_reminder else ""
    start_local = _to_sast(finding.booking_start, assume_utc_if_naive=False)
    end_local = _to_sast(finding.booking_end, assume_utc_if_naive=False)
    booking_date = start_local.strftime("%A %d %B %Y")
    flagged_at = _to_sast(finding.detected_at).strftime("%d %b %Y %H:%M SAST")
    start = start_local.strftime("%H:%M")
    end = end_local.strftime("%H:%M")
    duration_min = int((finding.booking_end - finding.booking_start).total_seconds() / 60)
    organiser_name = finding.organiser_name or "Unknown"
    organiser_email = finding.organiser_email or "Unknown"
    header_color = "#c0392b" if not is_reminder else "#e67e22"
    header_label = f"{prefix}GHOST BOOKING ALERT"

    anomaly_row = ""
    if finding.source_booking_flagged:
        anomaly_row = (
            "<tr>"
            '<td colspan="2" style="padding:8px 0;color:#c0392b;font-size:13px">'
            "&#9888; This booking was already flagged as a block-booking anomaly."
            "</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{header_label}</title>
</head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#222">
  <div style="background:{header_color};padding:24px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:20px">&#128680; {header_label}</h1>
    <p style="color:#fdd;margin:6px 0 0;font-size:14px">{site_label}</p>
  </div>

  <div style="background:#f8f9fa;padding:24px;border:1px solid #e0e0e0;border-top:none">
    <p style="margin:0 0 16px;font-size:14px;color:#555">
      <strong>{finding.room_name or finding.room_code}</strong> has been booked but no presence
      was detected for <strong>{finding.grace_period_minutes} minutes</strong> after the start time.
    </p>

    <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
      <tr style="background:#fff2f2">
        <td style="padding:8px;color:#555;font-size:13px;width:120px">Room</td>
        <td style="padding:8px;font-weight:600">{
        finding.room_name or finding.room_code
    } <span style="color:#999;font-weight:400">({finding.room_code})</span></td>
      </tr>
      <tr>
        <td style="padding:8px;color:#555;font-size:13px">Date</td>
        <td style="padding:8px;font-weight:600">{booking_date}</td>
      </tr>
      <tr style="background:#fafafa">
        <td style="padding:8px;color:#555;font-size:13px">Time</td>
        <td style="padding:8px;font-weight:600">{start} - {end} ({duration_min} min)</td>
      </tr>
      <tr>
        <td style="padding:8px;color:#555;font-size:13px">Flagged at</td>
        <td style="padding:8px">{flagged_at}</td>
      </tr>
      <tr style="background:#fafafa">
        <td style="padding:8px;color:#555;font-size:13px">Organiser</td>
        <td style="padding:8px">
          {organiser_name}<br/>
          <a href="mailto:{organiser_email}" style="color:#1a73e8;font-size:13px">{organiser_email}</a>
        </td>
      </tr>
      {anomaly_row}
    </table>

    <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:14px 16px;margin-bottom:16px">
      <strong style="font-size:13px">Action Required</strong>
      <ol style="margin:8px 0 0;padding-left:18px;font-size:13px;color:#555">
        <li>Physically inspect <strong>{finding.room_code}</strong></li>
        <li>If empty — the room can be released for other use</li>
        <li>If occupied — no action needed (sensor may need recalibration)</li>
      </ol>
    </div>

    <p style="font-size:12px;color:#999;margin:0">
      Finding ID: {finding.id} &nbsp;|&nbsp; SENTINEL Space Intelligence — {site_label}
    </p>
  </div>
</body>
</html>"""


def _send_email_direct_smtp(to_email: str, subject: str, body: str, body_html: str | None = None) -> bool:
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

    if body_html:
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{username}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(body_html, "html"))
    else:
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


async def send_ghost_booking_alert(
    finding: GhostBookingFinding,
    config: BlockBookingConfig,
    site_name: str = "",
    *,
    is_reminder: bool = False,
) -> dict[str, Any]:
    """Dispatch WhatsApp + email alerts for ghost bookings.

    WhatsApp via sentry/OpenClaw CLI (same as focus room notifier).
    Email via direct SMTP as fallback.
    """
    whatsapp_sent = False
    whatsapp_message_id: str | None = None

    wa_number = (config.concierge_whatsapp or "").strip().replace("whatsapp:", "")
    if wa_number:
        try:
            import subprocess

            msg = format_ghost_whatsapp_message(finding, is_reminder=is_reminder)
            result = subprocess.run(
                ["sentry", "message", "send", "--channel", "whatsapp", "--target", wa_number, "--message", msg],
                capture_output=True,
                text=True,
                timeout=30,
            )
            whatsapp_sent = result.returncode == 0
            whatsapp_message_id = result.stdout.strip() or None
            if not whatsapp_sent:
                logger.warning("Ghost booking WhatsApp send failed: %s", result.stderr)
        except Exception as exc:
            logger.error("Ghost booking WhatsApp dispatch failed: %s", exc)
    else:
        logger.warning("Ghost booking alert skipped: no WhatsApp number configured")

    if whatsapp_sent:
        occupancy_store.mark_ghost_finding_notified(
            finding.id,
            concierge_email=config.concierge_email,
            concierge_whatsapp=config.concierge_whatsapp,
            email_sent=False,
            whatsapp_sent=whatsapp_sent,
            whatsapp_message_id=whatsapp_message_id,
            telegram_sent=False,
            telegram_message_id=None,
            reset_reminder_cycle=not is_reminder,
        )

    # Email fallback — direct SMTP, no n8n
    if config.concierge_email and config.concierge_email.strip():
        to_email = config.concierge_email.strip()
        subject = f"{'REMINDER — ' if is_reminder else ''}Ghost booking alert: {finding.room_code}"
        email_body = format_ghost_email_message(finding, site_name, is_reminder=is_reminder)
        email_html = format_ghost_email_html(finding, site_name, is_reminder=is_reminder)
        _send_email_direct_smtp(to_email, subject, email_body, email_html)

    return {
        "success": whatsapp_sent,
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

    # Only create a concierge dashboard "Ghost" signal once concierge confirmed the room is empty.
    if updated.status == "confirmed_empty":
        try:
            from app.services.ghost_booking_signal_emitter import emit_ghost_booking_signal

            await emit_ghost_booking_signal(updated.room_code, updated)
        except Exception as exc:
            logger.warning("Failed to emit confirmed ghost booking signal for %s: %s", updated.id, exc)

    # If a legacy signal exists (older runs), mark it resolved.
    _resolve_related_ghost_signal(updated, resolution_state="resolved")

    return {
        "handled": True,
        "finding_id": finding.id,
        "status": updated.status,
        "response_message": f"Recorded: {finding.room_code} marked {status_text}.",
    }
