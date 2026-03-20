"""Send block booking alert notifications to the concierge."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from datetime import timedelta, timezone

from app.models.booking_record import BlockBookingAlert, BlockBookingConfig
from app.services.block_booking_detector.booking_store import (
    get_booking_store,
)
from app.config.settings import settings
from app.services.n8n_service import get_n8n_service

logger = logging.getLogger(__name__)
_SAST = timezone(timedelta(hours=2))


def _emit_block_booking_signals_background(alert: BlockBookingAlert) -> None:
    """Emit room-level concierge signals for each affected room without blocking notifications."""
    from app.services.booking_signal_emitter import emit_block_booking_signal

    async def _task() -> None:
        for room_code in alert.rooms:
            try:
                await emit_block_booking_signal(
                    {
                        "room_code": room_code,
                        "booked_by": alert.organiser_name or alert.organiser_email,
                        "booking_count": alert.room_count,
                        "pattern": "full_day_overlap",
                        "date_range": alert.overlap_window_start.date().isoformat(),
                        "alert_id": alert.id,
                        "booking_ids": alert.booking_ids,
                        "overlap_window_start": alert.overlap_window_start.isoformat(),
                        "overlap_window_end": alert.overlap_window_end.isoformat(),
                        "signal_stage": "planning",
                        "signal_lifecycle": "warn",
                        "site_id": alert.site_id,
                    }
                )
            except Exception as exc:
                logger.warning("Block booking signal emission failed for %s: %s", room_code, exc)

    try:
        asyncio.get_running_loop().create_task(_task())
    except RuntimeError:
        logger.debug("No running event loop — skipping block booking signal emission for %s", alert.id)


def format_alert_message(alert: BlockBookingAlert, site_name: str = "") -> str:
    """Format a block booking alert as a human-readable notification message."""
    start_local = _to_sast(alert.overlap_window_start)
    end_local = _to_sast(alert.overlap_window_end)
    anomaly_date = start_local.strftime("%A, %d %B %Y")
    flagged_at = alert.detected_at.strftime("%A, %d %B %Y %H:%M UTC")

    room_lines = []
    for room in alert.rooms:
        room_lines.append(f"  - {room}")
    rooms_text = "\n".join(room_lines)

    time_start = start_local.strftime("%H:%M")
    time_end = end_local.strftime("%H:%M")

    site_label = site_name or alert.site_id
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    msg = (
        f"Block Booking Detected — {site_label}\n\n"
        "Flagged anomaly details\n"
        f"  Date flagged: {flagged_at}\n"
        f"  Booking date: {anomaly_date}\n"
        f"  Organiser: {alert.organiser_name or 'Unknown'}\n"
        f"  Contact: {alert.organiser_email or 'Not available'}\n"
        f"  Rooms held: {alert.room_count}\n"
        f"  Window: {time_start} - {time_end}\n\n"
        f"{alert.organiser_name} ({alert.organiser_email}) "
        f"holds {alert.room_count} rooms for the same time slot on {anomaly_date}:\n"
        f"{rooms_text}\n"
        "\n"
        "Please contact the organiser to confirm which rooms are genuinely "
        "required. SENTINEL is flagging the anomaly only and is not cancelling "
        "or changing any bookings.\n\n"
        f"SENTINEL · {site_label} · {timestamp}"
    )
    return msg


def _to_sast(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_SAST)
    return dt.astimezone(_SAST)


async def _send_email_notification(
    alert: BlockBookingAlert,
    config: BlockBookingConfig,
    message: str,
    site_name: str,
) -> bool:
    """Send the block-booking alert to n8n for concierge email delivery."""
    if not config.concierge_email:
        return False

    site_label = site_name or alert.site_id
    subject = f"Block booking alert: {alert.room_count} rooms held by {alert.organiser_name or alert.organiser_email}"
    result = await get_n8n_service().trigger_webhook(
        webhook_path="space-block-booking-alert",
        payload={
            "site_id": alert.site_id,
            "site_name": site_label,
            "alert_id": alert.id,
            "to_email": config.concierge_email,
            "subject": subject,
            "message": message,
            "booking_date": alert.overlap_window_start.date().isoformat(),
            "flagged_at": alert.detected_at.isoformat(),
            "organiser_email": alert.organiser_email,
            "organiser_name": alert.organiser_name,
            "room_count": alert.room_count,
            "rooms": alert.rooms,
            "window_start": alert.overlap_window_start.isoformat(),
            "window_end": alert.overlap_window_end.isoformat(),
        },
    )
    if not result.get("success"):
        logger.warning(
            "Block booking alert n8n dispatch failed: organiser=%s reason=%s",
            alert.organiser_email,
            result.get("reason") or result.get("status_code"),
        )
        return False

    logger.info(
        "Block booking concierge email queued via n8n: site=%s organiser=%s to=%s",
        site_label,
        alert.organiser_email,
        config.concierge_email,
    )
    return True


def _send_email_direct_smtp(to_email: str, subject: str, body: str) -> bool:
    """Send block-booking alert email directly when n8n is unavailable."""
    host = settings.rooms_smtp_host or settings.notification_smtp_host
    port = settings.rooms_smtp_port or settings.notification_smtp_port
    username = settings.rooms_smtp_username or settings.notification_smtp_username
    password = settings.rooms_smtp_password or settings.notification_smtp_password
    from_name = settings.rooms_smtp_from_name or "SENTINEL Room Alerts"

    if not (host and username and password):
        logger.warning("No SMTP configured — cannot send block booking alert email")
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
        logger.info("Block booking alert email sent from %s to %s", username, to_email)
        return True
    except Exception as exc:
        logger.error("Direct SMTP block booking send failed: %s", exc)
        return False


async def send_block_booking_alert(
    alert: BlockBookingAlert,
    config: BlockBookingConfig,
    site_name: str = "",
) -> bool:
    """Send a notification to the concierge about a detected block booking.

    Sends the concierge email via n8n. Falls back to the event bus so existing
    notification plumbing still receives the event if n8n is unavailable.
    """
    message = format_alert_message(alert, site_name)
    store = get_booking_store()
    _emit_block_booking_signals_background(alert)
    subject = f"Block booking alert: {alert.room_count} rooms held by {alert.organiser_name or alert.organiser_email}"

    email_sent = False

    try:
        email_sent = await _send_email_notification(alert, config, message, site_name)
    except Exception as exc:
        logger.error("Failed to send block booking concierge email: %s", exc)

    if not email_sent and config.concierge_email:
        email_sent = _send_email_direct_smtp(config.concierge_email, subject, message)

    if email_sent:
        store.mark_alert_notified(alert.id)
        return True

    try:
        from app.services.event_bus import Importance, SentinelEvent, get_event_bus

        bus = get_event_bus()
        event = SentinelEvent(
            event_type="space.block_booking_detected",
            source="block_booking_detector",
            payload={
                "alert_id": alert.id,
                "organiser_email": alert.organiser_email,
                "organiser_name": alert.organiser_name,
                "room_count": alert.room_count,
                "rooms": alert.rooms,
                "date": alert.overlap_window_start.strftime("%Y-%m-%d"),
                "message": message,
            },
            importance=Importance.HIGH,
            site_id=alert.site_id,
            site_name=site_name,
        )
        await bus.emit(event)

        store.mark_alert_notified(alert.id)

        logger.info(
            "Block booking alert sent for %s (%d rooms)",
            alert.organiser_email,
            alert.room_count,
        )
        return True

    except Exception as exc:
        logger.error("Failed to send block booking alert: %s", exc)
        return False
