"""
Signal Emitter Service — Email Bridge (Phase 159)
===================================================
Converts inbound emails into correlation signals. Writes to the ``signal``
table in Supabase. This is the email bridge — one of 3 bridges feeding the
correlation engine (email, booking, occupancy).

Uses shared utilities from ``signal_emitter_base`` for Supabase writes,
dedup, entity extraction, and signal row construction.
"""

import hashlib
import logging
import re
import uuid
from datetime import datetime
from email.utils import getaddresses, parsedate_to_datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.database.repositories.room_registry_repository import get_room_registry_repository
from app.services.room_signal_mapper import extract_room_id
from app.services.signal_emitter_base import (
    build_signal_row,
    check_dedup,
    extract_entities_from_text,
    write_entities,
    write_signal,
)

logger = logging.getLogger(__name__)

_FAIRLANDS_ROOM_PATTERN = re.compile(r"^(FA[12])-(\d+Q\d+)-(MR|PR)-(\d{2})$", re.IGNORECASE)
_LOCAL_TIMEZONE = ZoneInfo("Africa/Johannesburg")
_THREAD_HEADER_KEYS = ("from:", "sent:", "to:", "cc:", "subject:")
_MEETING_ROOM_KEYWORDS = (
    "meeting room",
    "meeting rooms",
    "boardroom",
    "board room",
    "conference room",
    "book a room",
    "book room",
    "room booking",
    "room bookings",
    "12-seater",
    "seater room",
    "war room",
    "springboks",
)


# ---------------------------------------------------------------------------
# Email-specific helpers
# ---------------------------------------------------------------------------


def _thread_id_from_references(message_id: str, in_reply_to: str, references: str) -> Optional[str]:
    """Derive a stable thread ID from email headers.

    Uses the earliest message-id in the References chain, or in_reply_to,
    or the message's own ID as fallback.
    """
    if references:
        # References header contains space-separated message-ids, oldest first
        refs = references.strip().split()
        if refs:
            return hashlib.sha256(refs[0].encode()).hexdigest()[:16]
    if in_reply_to:
        return hashlib.sha256(in_reply_to.strip().encode()).hexdigest()[:16]
    if message_id:
        return hashlib.sha256(message_id.strip().encode()).hexdigest()[:16]
    return None


def _normalise_received_at(received_at: str) -> tuple[str, str | None]:
    """Return received_at as Johannesburg-local ISO and preserve original if changed."""
    now_local = datetime.now(_LOCAL_TIMEZONE).isoformat()
    if not received_at:
        return now_local, None

    value = received_at.strip()
    if not value:
        return now_local, None

    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        parsed = None

    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value, None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_LOCAL_TIMEZONE)

    normalised = parsed.astimezone(_LOCAL_TIMEZONE).isoformat()
    if normalised == value:
        return normalised, None
    return normalised, value


def _normalise_signal_type_for_storage(signal_type: str) -> tuple[str, str | None]:
    """Translate app-level email signal types to schema-supported signal_type values."""
    mapping = {
        "observation_email": "information_email",
        "intake_email": "information_email",
        "action_request_email": "escalation_email",
    }
    stored = mapping.get(signal_type, signal_type)
    if stored == signal_type:
        return stored, None
    return stored, signal_type


def _coerce_site_uuid(site_id: str | None) -> tuple[str | None, str | None]:
    """Return a UUID site_id for persistence, preserving logical site codes separately."""
    if not site_id:
        return None, None

    value = site_id.strip()
    if not value:
        return None, None

    try:
        return str(uuid.UUID(value)), None
    except (ValueError, AttributeError):
        return None, value


def _looks_like_thread_header(lines: list[str], index: int) -> bool:
    """Return True when a line starts an embedded email header block."""
    if index >= len(lines):
        return False
    if not lines[index].strip().lower().startswith("from:"):
        return False

    window = [line.strip().lower() for line in lines[index + 1 : index + 6] if line.strip()]
    return any(line.startswith("sent:") for line in window) and any(line.startswith("subject:") for line in window)


def _extract_email_thread_messages(body: str) -> list[dict[str, object]]:
    """Parse embedded forwarded/replied email blocks from plain-text email bodies."""
    if not body:
        return []

    text = body.replace("\r\n", "\n")
    lines = text.split("\n")
    messages: list[dict[str, object]] = []
    idx = 0

    while idx < len(lines):
        if not _looks_like_thread_header(lines, idx):
            idx += 1
            continue

        headers: dict[str, str] = {}
        j = idx
        while j < len(lines):
            stripped = lines[j].strip()
            if not stripped:
                j += 1
                break
            lowered = stripped.lower()
            if not any(lowered.startswith(key) for key in _THREAD_HEADER_KEYS):
                break
            key, _, value = stripped.partition(":")
            headers[key.strip().lower()] = value.strip()
            j += 1

        body_start = j
        while body_start < len(lines) and not lines[body_start].strip():
            body_start += 1

        k = body_start
        while k < len(lines):
            if _looks_like_thread_header(lines, k):
                break
            k += 1

        sender_pairs = getaddresses([headers.get("from", "")])
        sender_name, sender_email = sender_pairs[-1] if sender_pairs else ("", "")
        msg_to = [addr.lower() for _, addr in getaddresses([headers.get("to", "")]) if addr]
        msg_cc = [addr.lower() for _, addr in getaddresses([headers.get("cc", "")]) if addr]
        message_body = "\n".join(lines[body_start:k]).strip()

        messages.append(
            {
                "from_name": sender_name.strip(),
                "from_email": sender_email.strip().lower(),
                "sent_at": headers.get("sent", ""),
                "to": msg_to,
                "cc": msg_cc,
                "subject": headers.get("subject", ""),
                "body_plain": message_body,
            }
        )
        idx = k

    return messages


def _build_thread_context(body_plain: str, thread_messages: list[dict[str, object]]) -> str:
    """Build text context across the reconstructed email thread for extraction."""
    if not thread_messages:
        return body_plain

    parts: list[str] = []
    for message in thread_messages:
        subject = str(message.get("subject", "")).strip()
        body = str(message.get("body_plain", "")).strip()
        sender = str(message.get("from_email", "")).strip()
        sent_at = str(message.get("sent_at", "")).strip()
        header = " | ".join(part for part in [sender, sent_at, subject] if part)
        if header:
            parts.append(header)
        if body:
            parts.append(body)
    return "\n\n".join(parts).strip() or body_plain


def _is_meeting_room_email(subject: str, body: str) -> bool:
    """Return True only for meeting-room-related intelligence emails."""
    text = f"{subject}\n{body}"
    text_lower = text.lower()

    if extract_room_id(text):
        return True

    return any(keyword in text_lower for keyword in _MEETING_ROOM_KEYWORDS)


def _classify_email(subject: str, body: str) -> tuple[str, str, str]:
    """Simple rule-based email classification.

    Returns (source_module, signal_type, severity).
    """
    text = f"{subject} {body}".lower()
    room_id = extract_room_id(f"{subject}\n{body}")

    if room_id and any(
        w in text
        for w in [
            "not working",
            "not wroking",
            "broken",
            "faulty",
            "please fix",
            "does not work",
            "doesn't work",
        ]
    ):
        return "email_helpdesk", "observation_email", "low"

    # Escalation patterns
    if any(w in text for w in ["exco", "escalat", "executive", "urgent action", "unacceptable"]):
        return "email_escalation", "escalation_email", "critical"

    # Action request patterns
    action_words = [
        "please release",
        "please cancel",
        "need the room",
        "cannot book",
        "requesting release",
    ]
    if any(w in text for w in action_words):
        return "email_escalation", "action_request_email", "high"

    # Complaint patterns (repeat/frustration)
    if any(
        w in text
        for w in [
            "no progress",
            "still the same",
            "nothing has changed",
            "frustrated",
            "again",
        ]
    ):
        return "email_helpdesk", "complaint_email", "high"

    # Observation patterns (ground truth)
    if any(
        w in text
        for w in [
            "confirmed",
            "observed",
            "schedule full",
            "rooms cancelled",
            "pre-preparation",
        ]
    ):
        return "email_helpdesk", "observation_email", "medium"

    # Initial complaint
    if any(w in text for w in ["complaint", "issue", "problem", "block book", "not available"]):
        return "email_helpdesk", "complaint_email", "medium"

    # Intake / forwarding
    if any(w in text for w in ["forwarded", "helpdesk", "please attend", "logged"]):
        return "email_helpdesk", "intake_email", "medium"

    # Default
    return "email_helpdesk", "observation_email", "low"


def _extract_location_ref(subject: str, body: str) -> Optional[str]:
    """Extract Fairlands location reference from email text."""
    text = f"{subject} {body}"

    room_id = extract_room_id(text)
    if room_id:
        return _room_id_to_location_ref(room_id)

    # Match FA1/FA2 building references
    fa_match = re.search(r"\b(FA[12])\b", text, re.IGNORECASE)
    if fa_match:
        building = fa_match.group(1).upper()
        # Try to find room code like FA1-1Q4-MR10 or FA1/1Q4/MR10
        room_match = re.search(
            rf"{building}(?:[-/\s])(\dQ\d)(?:[-/\s])([A-Z]{{2}})(?:[-/\s]?)(\d+)",
            text,
            re.IGNORECASE,
        )
        if room_match:
            fq = room_match.group(1).upper()
            rt = room_match.group(2).upper()
            num = room_match.group(3).zfill(2)
            return f"Fairlands/{building}/{fq}/{rt}{num}"
        return f"Fairlands/{building}"

    # Match Fairlands general
    if re.search(r"\bfairlands?\b", text, re.IGNORECASE):
        return "Fairlands"

    # Match Springboks room
    if re.search(r"\bspringbok", text, re.IGNORECASE):
        return "Fairlands/FA1/1Q4/Springboks"

    return None


def _room_id_to_location_ref(room_id: str) -> str:
    """Convert a canonical Fairlands room ID into a hierarchical location ref."""
    match = _FAIRLANDS_ROOM_PATTERN.match(room_id)
    if not match:
        return room_id
    building = match.group(1).upper()
    quadrant = match.group(2).upper()
    return f"Fairlands/{building}/{quadrant}/{room_id}"


async def _resolve_room_context(subject: str, body: str) -> tuple[str | None, str | None, str | None]:
    """Resolve canonical room_id, location_ref, and site_id from email content."""
    text = f"{subject}\n{body}"
    room_id = extract_room_id(text)
    if not room_id:
        location_ref = _extract_location_ref(subject, body)
        return None, location_ref, "S001" if location_ref == "Fairlands" else None

    repo = get_room_registry_repository()
    room = await repo.get_room(room_id)
    if room:
        return room_id, _room_id_to_location_ref(room_id), room.get("site_id")

    return room_id, _room_id_to_location_ref(room_id), "S001"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def emit_email_signal(
    from_email: str,
    from_name: str,
    subject: str,
    body_plain: str,
    message_id: str = "",
    in_reply_to: str = "",
    references: str = "",
    to: list[str] | None = None,
    cc: list[str] | None = None,
    received_at: str = "",
) -> dict:
    """Convert an inbound email into one or more correlation signals.

    Uses shared base utilities for dedup, signal construction, and Supabase
    writes. Extracts entities from the email body and persists them.

    Returns the created signal summary dict.
    """
    thread_messages = _extract_email_thread_messages(body_plain)
    thread_context = _build_thread_context(body_plain, thread_messages)

    if not _is_meeting_room_email(subject, thread_context):
        logger.info("Ignoring non-meeting-room intelligence email: subject=%s", subject)
        return {
            "signal_id": None,
            "source_module": None,
            "signal_type": None,
            "severity": None,
            "location_ref": None,
            "thread_id": _thread_id_from_references(message_id, in_reply_to, references),
            "status": "ignored",
            "reason": "non_meeting_room_email",
        }

    source_module, signal_type, severity = _classify_email(subject, thread_context)
    room_id, location_ref, site_id = await _resolve_room_context(subject, thread_context)

    # Phase gate: shadow sites must not emit advisory signals
    from app.models.onboarding_phase import get_site_phase, phase_allows

    _site_phase = await get_site_phase(site_id or "")
    if not phase_allows(_site_phase, "emit_signal"):
        logger.debug(
            "emit_email_signal: site %s in phase %s — skipped",
            site_id,
            _site_phase,
        )
        return {
            "signal_id": None,
            "source_module": source_module,
            "signal_type": signal_type,
            "severity": severity,
            "location_ref": location_ref,
            "thread_id": _thread_id_from_references(message_id, in_reply_to, references),
            "status": "phase_gate_skipped",
            "reason": f"site in phase {_site_phase}",
        }

    thread_id = _thread_id_from_references(message_id, in_reply_to, references)
    stored_signal_type, signal_type_variant = _normalise_signal_type_for_storage(signal_type)
    persisted_site_id, logical_site_id = _coerce_site_uuid(site_id)

    # Dedup: skip if same signal within 5-minute window
    if check_dedup(source_module, signal_type, location_ref or "unknown"):
        logger.info(
            "Signal deduplicated: %s/%s at %s",
            source_module,
            signal_type,
            location_ref,
        )
        return {
            "signal_id": None,
            "source_module": source_module,
            "signal_type": signal_type,
            "severity": severity,
            "location_ref": location_ref,
            "thread_id": thread_id,
            "status": "deduplicated",
        }

    local_received_at, original_received_at = _normalise_received_at(received_at)

    metadata = {
        "from_email": from_email,
        "from_name": from_name,
        "to": to or [],
        "cc": cc or [],
        "subject": subject,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "thread_id": thread_id,
        "received_at": local_received_at,
        "source": "intelligence_intake",
    }
    if thread_messages:
        metadata["thread_messages"] = thread_messages
        metadata["thread_message_count"] = len(thread_messages)
        metadata["thread_participants"] = sorted(
            {
                email_addr
                for message in thread_messages
                for email_addr in [
                    str(message.get("from_email", "")).strip().lower(),
                    *[addr.strip().lower() for addr in message.get("to", []) if addr],
                    *[addr.strip().lower() for addr in message.get("cc", []) if addr],
                ]
                if email_addr
            }
        )
    if signal_type_variant:
        metadata["email_signal_variant"] = signal_type_variant
    if original_received_at:
        metadata["received_at_original"] = original_received_at
    if not received_at:
        metadata["received_at_fallback"] = "signal_emitter_local_clock"
    if logical_site_id:
        metadata["logical_site_id"] = logical_site_id
    if room_id:
        metadata["room_id"] = room_id

    signal_row = build_signal_row(
        source_module=source_module,
        signal_type=stored_signal_type,
        severity=severity,
        confidence=0.80,
        location_ref=location_ref or "unknown",
        raw_content=f"Subject: {subject}\n\n{thread_context}",
        metadata=metadata,
        site_id=persisted_site_id,
    )

    # Write signal to Supabase
    row = await write_signal(signal_row)

    # Extract and write entities
    entities_raw = extract_entities_from_text(thread_context)
    if entities_raw:
        import uuid

        entity_rows = []
        for ent in entities_raw:
            entity_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "signal_id": signal_row["id"],
                    "entity_type": ent["entity_type"],
                    "name": ent["name"],
                    "metadata": ent.get("metadata", {}),
                }
            )
        try:
            await write_entities(entity_rows)
        except Exception as exc:
            logger.warning("Failed to write entities for signal %s: %s", signal_row["id"], exc)

    # Track cost (free but audit)
    try:
        from app.services.ai_usage_tracker import usage_tracker

        usage_tracker.record_message("telegram", source="signal_emitter")
    except Exception:
        pass

    return {
        "signal_id": row["id"],
        "source_module": row["source_module"],
        "signal_type": row["signal_type"],
        "severity": row["severity"],
        "location_ref": row["location_ref"],
        "thread_id": thread_id,
        "status": "created",
    }
