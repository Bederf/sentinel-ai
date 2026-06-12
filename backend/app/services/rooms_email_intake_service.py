"""Rooms Email Intake IMAP Poller.

Polls rooms@sentinel-ai.co.za every 5 minutes via APScheduler.
Routes emails to the correct pipeline:
  - Booking confirmations  → block booking ingest
  - Room issues/complaints → emit_email_signal() (concierge dashboard)
"""

from __future__ import annotations

import email as email_lib
import hashlib
import imaplib
import logging
from email.message import Message
from pathlib import Path
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)

_BOOKING_KEYWORDS = (
    "new resource use notification",
    "cancelled reservation",
    "accepted",
    "invitation",
    "meeting",
)


def _is_booking_email(subject: str) -> bool:
    s = subject.lower()
    return any(kw in s for kw in _BOOKING_KEYWORDS)


class RoomsEmailIntakeService:
    """IMAP poller for the rooms@ mailbox."""

    def __init__(self) -> None:
        self._last_uid_file = Path(__file__).parent.parent / "data" / "rooms_email_last_uid.txt"

    def _is_configured(self) -> bool:
        return bool(settings.rooms_imap_host)

    def poll(self) -> list[dict[str, Any]]:
        if not self._is_configured():
            logger.debug("[RoomsEmail] IMAP not configured — skipping poll")
            return []

        try:
            return self._poll_impl()
        except Exception as e:
            logger.error("[RoomsEmail] Poll failed: %s", e)
            return []

    def _poll_impl(self) -> list[dict[str, Any]]:
        mail = imaplib.IMAP4_SSL(
            host=settings.rooms_imap_host,
            port=settings.rooms_imap_port or 993,
        )
        mail.login(settings.rooms_imap_username, settings.rooms_imap_password)
        mail.select(settings.rooms_imap_folder or "INBOX")

        last_uid = self._read_last_uid()
        status, messages = mail.search(None, f"UID {last_uid + 1}:*")
        if status != "OK":
            mail.logout()
            return []

        email_ids = messages[0].split()
        if not email_ids:
            mail.logout()
            return []

        results: list[dict[str, Any]] = []
        for email_id in email_ids:
            uid = self._extract_uid(email_id)
            try:
                result = self._process_email(mail, email_id)
                if result:
                    results.append(result)
                if uid:
                    self._write_last_uid(uid)
            except Exception as e:
                logger.warning("[RoomsEmail] Failed to process email %s: %s", email_id, e)
                if uid:
                    self._write_last_uid(uid)

        mail.logout()
        return results

    def _process_email(self, mail: imaplib.IMAP4_SSL, email_id: bytes) -> dict[str, Any] | None:
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            return None

        raw_bytes = msg_data[0][1]
        msg = email_lib.message_from_bytes(raw_bytes)

        message_id = msg.get("Message-ID", "")
        subject = msg.get("Subject", "(no subject)")
        msg_hash = hashlib.sha256((message_id or "").encode()).hexdigest()

        if _is_booking_email(subject):
            return self._route_booking(raw_bytes)
        else:
            return self._route_room_issue(msg, subject, msg_hash)

    def _route_booking(self, raw_bytes: bytes) -> dict[str, Any]:
        raw_str = raw_bytes.decode("utf-8", errors="replace")
        ics_data = self._extract_ics(raw_bytes)

        try:
            from app.api.block_bookings import BookingEmailRequest
            from app.models.booking_record import BlockBookingConfig
            from app.services.block_booking_detector.booking_store import get_booking_store
            from app.services.block_booking_detector.email_parser import (
                extract_cancelled_room,
                is_cancellation,
                parse_booking_confirmation,
                parse_ics_booking,
            )
            from app.services.block_booking_detector.notifier import send_block_booking_alert
            from app.services.block_booking_detector.overlap_detector import detect_overlaps

            request = BookingEmailRequest(raw_email=raw_str, ics_data=ics_data)
            store = get_booking_store()

            if request.raw_email and is_cancellation(request.raw_email):
                info = extract_cancelled_room(request.raw_email, request.site_id)
                if info:
                    store.remove_booking(
                        site_id=info.get("site_id", "site-002"),
                        organiser_email=info["organiser_email"],
                        room_name=info["room_name"],
                        start_time=info.get("start_time"),
                    )
                return {"action": "cancellation", "subject": "(booking cancellation)"}

            record = None
            if request.ics_data:
                record = parse_ics_booking(request.ics_data, request.site_id)
            if not record and request.raw_email:
                record = parse_booking_confirmation(request.raw_email, request.site_id)

            if record:
                store.save_booking(record)
                config = BlockBookingConfig(site_id=request.site_id)
                alerts = detect_overlaps(request.site_id, [record], config, store)
                for alert in alerts:
                    notify_result = send_block_booking_alert(alert, store)
                    store.save_block_booking_alert(alert, notify_result)
                return {
                    "action": "booking_ingested",
                    "room": record.room_name or record.room_id,
                }

            return {"action": "unparseable", "subject": subject}

        except Exception as e:
            logger.warning("[RoomsEmail] Block booking ingest failed: %s", e)
            return {"action": "error", "error": str(e)}

    def _route_room_issue(self, msg: Message, subject: str, msg_hash: str) -> dict[str, Any]:
        body = self._extract_body(msg)
        from_addr = msg.get("From", "")
        from_name, from_email = self._parse_from(from_addr)
        message_id = msg.get("Message-ID", "")
        in_reply_to = msg.get("In-Reply-To", "")
        references = msg.get("References", "")
        date_str = msg.get("Date", "")

        try:
            import asyncio

            from app.services.signal_emitter import emit_email_signal

            result = asyncio.run(
                emit_email_signal(
                    from_email=from_email,
                    from_name=from_name,
                    subject=subject,
                    body_plain=body,
                    message_id=message_id or "",
                    in_reply_to=in_reply_to or "",
                    references=references or "",
                    received_at=date_str or "",
                )
            )
            return result

        except Exception as e:
            logger.warning("[RoomsEmail] Signal emission failed: %s", e)
            return {"action": "error", "error": str(e)}

    def _extract_body(self, msg: Message) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(errors="replace")
        return ""

    def _extract_ics(self, raw_bytes: bytes) -> str | None:
        msg = email_lib.message_from_bytes(raw_bytes)
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ("text/calendar", "application/ics"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        decoded = payload.decode("utf-8", errors="replace")
                        if decoded.strip().startswith("BEGIN:VCALENDAR"):
                            return decoded
                filename = part.get_filename() or ""
                if filename.endswith(".ics"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        decoded = payload.decode("utf-8", errors="replace")
                        if decoded.strip().startswith("BEGIN:VCALENDAR"):
                            return decoded
        return None

    def _parse_from(self, from_header: str) -> tuple[str, str]:
        import email.utils

        name, addr = email.utils.parseaddr(from_header)
        return name or addr, addr.lower() if addr else ""

    def _extract_uid(self, email_id: bytes) -> int | None:
        try:
            return int(email_id)
        except (ValueError, TypeError):
            return None

    def _read_last_uid(self) -> int:
        try:
            return int(self._last_uid_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _write_last_uid(self, uid: int) -> None:
        self._last_uid_file.parent.mkdir(parents=True, exist_ok=True)
        self._last_uid_file.write_text(str(uid))
