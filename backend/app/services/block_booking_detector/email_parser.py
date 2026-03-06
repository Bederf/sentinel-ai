"""Parse Outlook room booking confirmation emails into BookingRecord objects.

Handles standard Outlook resource booking confirmations. Extracts organiser,
room, date, start/end time from labelled fields. Detects cancellations by
subject line and returns None (caller should remove the corresponding record).
"""

from __future__ import annotations

import email
import hashlib
import logging
import re
from datetime import datetime
from email.utils import parseaddr
from typing import Optional

from app.models.booking_record import BookingRecord

logger = logging.getLogger(__name__)

# Subject patterns indicating a cancellation (not a new booking)
_CANCEL_PATTERNS = re.compile(
    r"cancel|declined|removed|withdrawn",
    re.IGNORECASE,
)

# Common datetime formats in Outlook confirmation bodies
_DATETIME_FORMATS = [
    "%A, %d %B %Y %H:%M",  # Monday, 03 March 2026 14:00
    "%d %B %Y %H:%M",  # 03 March 2026 14:00
    "%Y-%m-%dT%H:%M:%S",  # 2026-03-03T14:00:00
    "%Y-%m-%d %H:%M:%S",  # 2026-03-03 14:00:00
    "%Y-%m-%d %H:%M",  # 2026-03-03 14:00
    "%d/%m/%Y %H:%M",  # 03/03/2026 14:00
    "%m/%d/%Y %I:%M %p",  # 03/03/2026 2:00 PM
    "%A, %B %d, %Y %I:%M %p",  # Monday, March 03, 2026 2:00 PM
    "%B %d, %Y %I:%M %p",  # March 03, 2026 2:00 PM
]


def _hash_email(raw: str) -> str:
    """SHA-256 hash of the raw email for deduplication."""
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _parse_datetime(value: str) -> Optional[datetime]:
    """Try multiple datetime formats to parse a value string."""
    value = value.strip().rstrip(".")
    # Remove timezone abbreviations like (UTC), (SAST)
    value = re.sub(r"\s*\([A-Z]+\)\s*$", "", value)
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.debug("Could not parse datetime: %s", value)
    return None


def _extract_field(body: str, label: str) -> Optional[str]:
    """Extract a labelled field value from the email body.

    Matches patterns like:
        Start: Monday, 03 March 2026 14:00
        Location: Boardroom 1
    """
    pattern = rf"(?:^|\n)\s*{re.escape(label)}\s*:\s*(.+)"
    match = re.search(pattern, body, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def is_cancellation(raw_email: str) -> bool:
    """Return True if the email represents a booking cancellation."""
    try:
        msg = email.message_from_string(raw_email)
        subject = msg.get("Subject", "")
    except Exception:
        subject = raw_email[:500]
    return bool(_CANCEL_PATTERNS.search(subject))


def extract_cancelled_room(raw_email: str, site_id: str) -> Optional[dict]:
    """Extract organiser + room from a cancellation email for removal lookup.

    Returns dict with organiser_email, room_name, start_time (if parseable),
    or None if unparseable.
    """
    try:
        msg = email.message_from_string(raw_email)
    except Exception:
        return None

    from_header = msg.get("From", "")
    _, from_email = parseaddr(from_header)
    if not from_email:
        return None

    body = _get_body(msg)
    location = _extract_field(body, "Location")
    start_str = _extract_field(body, "Start")
    start_dt = _parse_datetime(start_str) if start_str else None

    return {
        "organiser_email": from_email.lower(),
        "room_name": location or "",
        "start_time": start_dt,
    }


def _get_body(msg: email.message.Message) -> str:
    """Extract plain-text body from a parsed email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
        # Fallback: try HTML stripped of tags
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    text = payload.decode("utf-8", errors="replace")
                    return re.sub(r"<[^>]+>", " ", text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
    return ""


def parse_booking_confirmation(
    raw_email: str,
    site_id: str,
) -> Optional[BookingRecord]:
    """Parse an Outlook room booking confirmation email.

    Returns a BookingRecord if the email is a valid booking confirmation.
    Returns None for cancellations, updates, or unparseable emails.
    """
    if is_cancellation(raw_email):
        return None

    try:
        msg = email.message_from_string(raw_email)
    except Exception:
        logger.warning("Failed to parse email message")
        return None

    # --- Organiser ---
    from_header = msg.get("From", "")
    organiser_name, organiser_email = parseaddr(from_header)
    if not organiser_email:
        # Try Organizer: field in body
        body = _get_body(msg)
        org_field = _extract_field(body, "Organizer") or _extract_field(body, "Organiser")
        if org_field:
            organiser_name, organiser_email = parseaddr(org_field)
    if not organiser_email:
        logger.debug("No organiser email found")
        return None

    body = _get_body(msg)

    # --- Location / Room ---
    location = _extract_field(body, "Location") or msg.get("X-Microsoft-Exchange-Organization-CalendarLocation", "")
    room_name = location.strip() if location else ""
    # Use the To: resource mailbox as room_id if available
    to_header = msg.get("To", "")
    _, to_email = parseaddr(to_header)
    room_id = to_email if to_email else room_name

    if not room_name and not room_id:
        logger.debug("No room/location found")
        return None

    # --- Start / End ---
    start_str = _extract_field(body, "Start")
    end_str = _extract_field(body, "End")
    if not start_str or not end_str:
        # Try When: field (some Outlook versions)
        when = _extract_field(body, "When")
        if when and " - " in when:
            parts = when.split(" - ", 1)
            start_str = start_str or parts[0].strip()
            end_str = end_str or parts[1].strip()

    start_time = _parse_datetime(start_str) if start_str else None
    end_time = _parse_datetime(end_str) if end_str else None

    if not start_time or not end_time:
        logger.debug(
            "Could not parse start/end times: start=%s end=%s",
            start_str,
            end_str,
        )
        return None

    return BookingRecord(
        site_id=site_id,
        organiser_email=organiser_email.lower(),
        organiser_name=organiser_name or organiser_email.split("@")[0],
        room_id=room_id,
        room_name=room_name or room_id,
        booking_date=start_time.date(),
        start_time=start_time,
        end_time=end_time,
        raw_email_hash=_hash_email(raw_email),
        ingested_at=datetime.utcnow(),
    )
