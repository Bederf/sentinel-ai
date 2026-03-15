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
from typing import Optional

from app.services.signal_emitter_base import (
    build_signal_row,
    check_dedup,
    extract_entities_from_text,
    write_entities,
    write_signal,
)

logger = logging.getLogger(__name__)


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


def _classify_email(subject: str, body: str) -> tuple[str, str, str]:
    """Simple rule-based email classification.

    Returns (source_module, signal_type, severity).
    """
    text = f"{subject} {body}".lower()

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

    # Match FA1/FA2 building references
    fa_match = re.search(r"\b(FA[12])\b", text, re.IGNORECASE)
    if fa_match:
        building = fa_match.group(1).upper()
        # Try to find room code like FA1-1Q4-MR10 or FA1/1Q4/MR10
        room_match = re.search(
            rf"{building}[-/](\dQ\d)[-/]([A-Z]{{2}})[-/]?(\d+)",
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
    from datetime import datetime, timezone

    source_module, signal_type, severity = _classify_email(subject, body_plain)
    location_ref = _extract_location_ref(subject, body_plain)
    thread_id = _thread_id_from_references(message_id, in_reply_to, references)

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

    now = datetime.now(timezone.utc).isoformat()

    metadata = {
        "from_email": from_email,
        "from_name": from_name,
        "to": to or [],
        "cc": cc or [],
        "subject": subject,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "thread_id": thread_id,
        "received_at": received_at or now,
        "source": "intelligence_intake",
    }

    signal_row = build_signal_row(
        source_module=source_module,
        signal_type=signal_type,
        severity=severity,
        confidence=0.80,
        location_ref=location_ref or "unknown",
        raw_content=f"Subject: {subject}\n\n{body_plain}",
        metadata=metadata,
    )

    # Write signal to Supabase
    row = await write_signal(signal_row)

    # Extract and write entities
    entities_raw = extract_entities_from_text(body_plain)
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
