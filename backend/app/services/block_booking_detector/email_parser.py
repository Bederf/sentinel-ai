"""Parse room booking confirmation emails into BookingRecord objects.

Supports three formats:
  1. iCalendar (.ics) attachments — structured VEVENT data (preferred)
  2. Resource Scheduler (resourcescheduler.com) — FNB/WesBank production format
  3. Outlook calendar confirmations — fallback for standard Exchange environments

Resource Scheduler format:
  - Sender: noreply@resourcescheduler.com
  - Meeting Contact: Name, email, phone (in body)
  - Location: "Fairland 1(WB); GR Floor Meeting Rooms; FA1-GRQ1-TR-01"
  - Date/time: "Friday, 27 March 2026 from 8:00 AM until 5:00 PM South Africa"
  - New booking subject: "New Resource Use Notification - ..."
  - Cancellation subject: "Cancelled Reservation - ..."
"""

from __future__ import annotations

import email
import hashlib
import logging
import re
from datetime import datetime
from email.utils import parseaddr

from app.models.booking_record import BookingRecord
from app.services.block_booking_detector.site_resolver import resolve_site_id_for_room

logger = logging.getLogger(__name__)

# Subject patterns indicating a cancellation (not a new booking)
_CANCEL_PATTERNS = re.compile(
    r"cancel|declined|removed|withdrawn",
    re.IGNORECASE,
)

# Resource Scheduler: "Friday, 27 March 2026 from 8:00 AM until 5:00 PM South Africa"
_RS_DATETIME_RE = re.compile(
    r"(\w+,\s+\d{1,2}\s+\w+\s+\d{4})\s+from\s+(\d{1,2}:\d{2}\s*[AP]M)\s+until\s+(\d{1,2}:\d{2}\s*[AP]M)",
    re.IGNORECASE,
)

# Fallback datetime formats for Outlook-style emails
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

# Resource Scheduler room code: FA1-GRQ1-TR-01
_ROOM_CODE_RE = re.compile(r"(FA\d+)-(\w+)-(\w+)-(\d+)", re.IGNORECASE)


def _hash_email(raw: str) -> str:
    """SHA-256 hash of the raw email for deduplication."""
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _parse_datetime(value: str) -> datetime | None:
    """Try multiple datetime formats to parse a value string."""
    value = value.strip().rstrip(".")
    # Remove timezone names like "South Africa", "(UTC)", "(SAST)"
    value = re.sub(r"\s*\([A-Z]+\)\s*$", "", value)
    value = re.sub(r"\s+South Africa\s*$", "", value, flags=re.IGNORECASE)
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.debug("Could not parse datetime: %s", value)
    return None


def _parse_rs_datetime(body: str) -> tuple[datetime | None, datetime | None]:
    """Parse Resource Scheduler date/time format.

    "Friday, 27 March 2026 from 8:00 AM until 5:00 PM South Africa"
    """
    match = _RS_DATETIME_RE.search(body)
    if not match:
        return None, None

    date_str = match.group(1).strip()  # "Friday, 27 March 2026"
    start_str = match.group(2).strip()  # "8:00 AM"
    end_str = match.group(3).strip()  # "5:00 PM"

    # Parse date
    date_dt = None
    for fmt in ["%A, %d %B %Y", "%d %B %Y"]:
        try:
            date_dt = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue
    if not date_dt:
        return None, None

    # Parse times
    try:
        start_t = datetime.strptime(start_str, "%I:%M %p")
        end_t = datetime.strptime(end_str, "%I:%M %p")
    except ValueError:
        return None, None

    start_dt = date_dt.replace(hour=start_t.hour, minute=start_t.minute)
    end_dt = date_dt.replace(hour=end_t.hour, minute=end_t.minute)
    return start_dt, end_dt


def _extract_field(body: str, label: str) -> str | None:
    """Extract a labelled field value from the email body.

    Matches patterns like:
        Location:    Fairland 1(WB); GR Floor Meeting Rooms; FA1-GRQ1-TR-01
        Meeting Contact:    Lemond Luxman, Lemond.Luxman@wesbank.co.za, 0681227791
    """
    pattern = rf"(?:^|\n)\s*{re.escape(label)}\s*:\s*(.+)"
    match = re.search(pattern, body, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_room_code(location: str) -> str | None:
    """Extract room code from Resource Scheduler location string.

    "Fairland 1(WB); GR Floor Meeting Rooms; FA1-GRQ1-TR-01" -> "FA1-GRQ1-TR-01"
    """
    match = _ROOM_CODE_RE.search(location)
    if match:
        return match.group(0).upper()
    # Fallback: last semicolon-delimited segment
    parts = [p.strip() for p in location.split(";")]
    if parts:
        return parts[-1]
    return None


def _extract_site_from_room_code(room_code: str) -> str | None:
    """Extract site prefix from room code: FA1-GRQ1-TR-01 -> FA1."""
    match = re.match(r"(FA\d+)", room_code, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _is_resource_scheduler(body: str, from_email: str) -> bool:
    """Detect if email is from Resource Scheduler."""
    return (
        "resourcescheduler" in from_email.lower()
        or "Resource Scheduler Notification" in body
        or "Action Performed By:" in body
    )


def _parse_rs_meeting_contact(body: str) -> tuple[str, str]:
    """Parse Meeting Contact field from Resource Scheduler body.

    "Meeting Contact:    Lemond Luxman, Lemond.Luxman@wesbank.co.za, 0681227791"
    Returns (name, email).
    """
    field = _extract_field(body, "Meeting Contact")
    if not field:
        return "", ""

    # Split by comma: "Name, email@domain, phone"
    parts = [p.strip() for p in field.split(",")]
    name = parts[0] if parts else ""
    contact_email = ""
    for part in parts[1:]:
        if "@" in part:
            contact_email = part.strip().lower()
            # Strip Outlook mailto: artifacts e.g. "user@domain<mailto:user@domain>"
            contact_email = re.sub(r"<mailto:[^>]*>", "", contact_email).strip()
            break
    return name, contact_email


def is_cancellation(raw_email: str) -> bool:
    """Return True if the email represents a booking cancellation."""
    try:
        msg = email.message_from_string(raw_email)
        subject = msg.get("Subject", "")
    except Exception:
        subject = raw_email[:500]
    return bool(_CANCEL_PATTERNS.search(subject))


def extract_cancelled_room(raw_email: str, site_id: str) -> dict | None:
    """Extract organiser + room from a cancellation email for removal lookup."""
    try:
        msg = email.message_from_string(raw_email)
    except Exception:
        return None

    body = _get_body(msg)
    from_header = msg.get("From", "")
    _, from_email = parseaddr(from_header)

    # Resource Scheduler: organiser is in Meeting Contact, not From
    if _is_resource_scheduler(body, from_email):
        contact_name, contact_email = _parse_rs_meeting_contact(body)
        if not contact_email:
            # Fallback: use "Action Performed By" name
            performed_by = _extract_field(body, "Action Performed By")
            contact_name = performed_by or ""
            # No email available — use name-based lookup
            contact_email = ""

        location = _extract_field(body, "Location") or ""
        room_code = _extract_room_code(location)
        start_dt, _ = _parse_rs_datetime(body)

        return {
            "organiser_email": contact_email,
            "organiser_name": contact_name,
            "room_name": room_code or location,
            "start_time": start_dt,
        }

    # Outlook fallback
    if not from_email:
        return None

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
    site_id: str = "",
) -> BookingRecord | None:
    """Parse a room booking confirmation email.

    Supports Resource Scheduler (FNB) and Outlook formats.
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

    body = _get_body(msg)
    from_header = msg.get("From", "")
    _, from_email = parseaddr(from_header)

    # ---- Resource Scheduler path ----
    if _is_resource_scheduler(body, from_email):
        return _parse_resource_scheduler(raw_email, body, site_id)

    # ---- Outlook fallback path ----
    return _parse_outlook(raw_email, msg, body, site_id)


def _parse_resource_scheduler(
    raw_email: str,
    body: str,
    site_id: str,
) -> BookingRecord | None:
    """Parse Resource Scheduler booking notification."""

    # Organiser from Meeting Contact field
    organiser_name, organiser_email = _parse_rs_meeting_contact(body)
    if not organiser_email:
        # Use "Action Performed By" as fallback name
        performed_by = _extract_field(body, "Action Performed By") or ""
        organiser_name = organiser_name or performed_by
        if not organiser_name:
            logger.debug("No organiser found in Resource Scheduler email")
            return None

    # Location / Room
    location = _extract_field(body, "Location") or ""
    room_code = _extract_room_code(location)
    if not room_code:
        logger.debug("No room code found in location: %s", location)
        return None

    # Extract site from room code if not provided
    site_id = resolve_site_id_for_room(
        room_code,
        location,
        fallback_site_id=_extract_site_from_room_code(room_code) or site_id,
    )

    # Date and time
    start_time, end_time = _parse_rs_datetime(body)
    if not start_time or not end_time:
        logger.debug("Could not parse Resource Scheduler date/time")
        return None

    return BookingRecord(
        site_id=site_id,
        organiser_email=organiser_email or f"{organiser_name.lower().replace(' ', '.')}@unknown",
        organiser_name=organiser_name or (organiser_email.split("@")[0] if organiser_email else "Unknown"),
        room_id=room_code,
        room_name=room_code,
        booking_date=start_time.date(),
        start_time=start_time,
        end_time=end_time,
        raw_email_hash=_hash_email(raw_email),
        ingested_at=datetime.utcnow(),
    )


def parse_ics_booking(
    ics_data: str,
    site_id: str = "",
) -> BookingRecord | None:
    """Parse an iCalendar (.ics) VEVENT into a BookingRecord.

    Extracts ORGANIZER, LOCATION, DTSTART, DTEND, SUMMARY from the first VEVENT.
    Returns None if required fields are missing or the event is a cancellation.
    """
    try:
        from icalendar import Calendar
    except ImportError:
        logger.warning("icalendar package not installed — cannot parse .ics")
        return None

    try:
        cal = Calendar.from_ical(ics_data)
    except Exception as exc:
        logger.warning("Failed to parse .ics data: %s", exc)
        return None

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        # Check for cancellation (METHOD:CANCEL or STATUS:CANCELLED)
        method = str(cal.get("METHOD", "")).upper()
        status = str(component.get("STATUS", "")).upper()
        if method == "CANCEL" or status == "CANCELLED":
            return None

        # ORGANIZER — "mailto:user@example.com" or "CN=Name:mailto:..."
        organiser_email = ""
        organiser_name = ""
        organiser = component.get("ORGANIZER")
        if organiser:
            org_str = str(organiser)
            if "mailto:" in org_str.lower():
                organiser_email = org_str.lower().split("mailto:")[-1].strip()
            organiser_name = str(organiser.params.get("CN", "")) if hasattr(organiser, "params") else ""

        # ATTENDEES — if no organiser, try first attendee
        if not organiser_email:
            attendees = component.get("ATTENDEE")
            if attendees:
                if not isinstance(attendees, list):
                    attendees = [attendees]
                for att in attendees:
                    att_str = str(att)
                    if "mailto:" in att_str.lower():
                        organiser_email = att_str.lower().split("mailto:")[-1].strip()
                        organiser_name = str(att.params.get("CN", "")) if hasattr(att, "params") else ""
                        break

        if not organiser_email:
            logger.debug("No organiser email in .ics VEVENT")
            return None

        # LOCATION
        location = str(component.get("LOCATION", ""))
        room_code = _extract_room_code(location) if location else None
        room_name = room_code or location or ""

        if not room_name:
            logger.debug("No location in .ics VEVENT")
            return None

        # Extract site from room code if not provided
        site_id = resolve_site_id_for_room(
            room_code,
            location,
            fallback_site_id=_extract_site_from_room_code(room_code) or site_id,
        )

        # DTSTART / DTEND
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        if not dtstart or not dtend:
            logger.debug("No DTSTART/DTEND in .ics VEVENT")
            return None

        start_dt = dtstart.dt
        end_dt = dtend.dt

        # Convert date to datetime if needed (all-day events)
        if not isinstance(start_dt, datetime):
            start_dt = datetime.combine(start_dt, datetime.min.time())
        if not isinstance(end_dt, datetime):
            end_dt = datetime.combine(end_dt, datetime.min.time())

        # Strip timezone info for naive datetime consistency
        if start_dt.tzinfo is not None:
            start_dt = start_dt.replace(tzinfo=None)
        if end_dt.tzinfo is not None:
            end_dt = end_dt.replace(tzinfo=None)

        return BookingRecord(
            site_id=site_id or "UNKNOWN",
            organiser_email=organiser_email,
            organiser_name=organiser_name or organiser_email.split("@")[0],
            room_id=room_code or room_name,
            room_name=room_name,
            booking_date=start_dt.date(),
            start_time=start_dt,
            end_time=end_dt,
            raw_email_hash=_hash_email(ics_data),
            ingested_at=datetime.utcnow(),
        )

    logger.debug("No VEVENT found in .ics data")
    return None


def _parse_outlook(
    raw_email: str,
    msg: email.message.Message,
    body: str,
    site_id: str,
) -> BookingRecord | None:
    """Parse Outlook calendar booking confirmation (legacy path)."""

    # Organiser from From: header
    from_header = msg.get("From", "")
    organiser_name, organiser_email = parseaddr(from_header)
    if not organiser_email:
        org_field = _extract_field(body, "Organizer") or _extract_field(body, "Organiser")
        if org_field:
            organiser_name, organiser_email = parseaddr(org_field)
    if not organiser_email:
        logger.debug("No organiser email found")
        return None

    # Location / Room
    location = _extract_field(body, "Location") or msg.get("X-Microsoft-Exchange-Organization-CalendarLocation", "")
    room_name = location.strip() if location else ""
    to_header = msg.get("To", "")
    _, to_email = parseaddr(to_header)
    room_id = to_email if to_email else room_name

    if not room_name and not room_id:
        logger.debug("No room/location found")
        return None

    # Start / End
    start_str = _extract_field(body, "Start")
    end_str = _extract_field(body, "End")
    if not start_str or not end_str:
        when = _extract_field(body, "When")
        if when and " - " in when:
            parts = when.split(" - ", 1)
            start_str = start_str or parts[0].strip()
            end_str = end_str or parts[1].strip()

    start_time = _parse_datetime(start_str) if start_str else None
    end_time = _parse_datetime(end_str) if end_str else None

    if not start_time or not end_time:
        logger.debug("Could not parse start/end times: start=%s end=%s", start_str, end_str)
        return None

    resolved_site_id = resolve_site_id_for_room(room_name, room_id, fallback_site_id=site_id)

    return BookingRecord(
        site_id=resolved_site_id,
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
