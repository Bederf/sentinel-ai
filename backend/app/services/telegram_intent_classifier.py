"""Telegram Intent Classifier — synchronous, no I/O, no LLM.

Classifies incoming Telegram messages into conversation intents
based on text patterns, session state, and callback data.
"""

from __future__ import annotations

import re
from enum import Enum

from app.services.issue_classifier import classify_issue


class TelegramIntent(str, Enum):
    CLIENT_COMPLAINT = "client_complaint"
    TECHNICIAN_REPORT = "technician_report"
    WO_UPDATE = "wo_update"
    CHECKLIST_REPLY = "checklist_reply"
    AD_HOC_FAULT = "ad_hoc_fault"
    DOCUMENT_INTAKE = "document_intake"
    GHOST_ROOM = "ghost_room"
    UNKNOWN = "unknown"


# Equipment ID patterns
_EQUIPMENT_RE = re.compile(
    r"S00\d-|AHU|FCU|CHW|PUMP|UPS|GEN|CHILLER|VAV|SPLIT|CRAC|CT|ATS|MSB|TX",
    re.IGNORECASE,
)

# WO reference pattern
_WO_RE = re.compile(r"WO-\d{4}-\d{4}", re.IGNORECASE)

# Technical inspection vocabulary
_TECH_VOCAB = {
    "inspection",
    "checking",
    "at the unit",
    "vibration",
    "pressure drop",
    "belt",
    "filter",
    "coil",
    "damper",
    "actuator",
    "bearing",
    "compressor",
    "condenser",
    "evaporator",
    "refrigerant",
    "superheat",
    "subcooling",
}

# Ad-hoc fault keywords (non-technical, no equipment context)
_ADHOC_KEYWORDS = {
    "chair",
    "desk",
    "door",
    "window",
    "blind",
    "light bulb",
    "tap",
    "toilet",
    "leak",
    "broken",
    "damaged",
    "carpet",
    "ceiling tile",
    "paint",
}

# WO completion keywords
_WO_DONE_KEYWORDS = {"done", "completed", "closed", "finished", "complete"}

# Callback data flow prefixes -> intent mapping
_CALLBACK_FLOW_MAP = {
    "complaint": TelegramIntent.CLIENT_COMPLAINT,
    "menu:start:complaint": TelegramIntent.CLIENT_COMPLAINT,
    "menu:start:inspection": TelegramIntent.TECHNICIAN_REPORT,
    "menu:start:wo_check": TelegramIntent.WO_UPDATE,
    "wo": TelegramIntent.WO_UPDATE,
    "inspect": TelegramIntent.TECHNICIAN_REPORT,
    "adhoc": TelegramIntent.AD_HOC_FAULT,
    "ghost": TelegramIntent.GHOST_ROOM,
}


def classify_intent(
    message_text: str,
    has_active_session: bool,
    callback_data: str | None = None,
) -> tuple[TelegramIntent, float]:
    """Classify a Telegram message into a conversation intent.

    Returns (intent, confidence 0.0-1.0).
    """
    text = (message_text or "").strip()
    text_lower = text.lower()

    # Rule 1: callback_data present + active session -> CHECKLIST_REPLY
    if callback_data and has_active_session:
        return TelegramIntent.CHECKLIST_REPLY, 1.0

    # Rule 2: callback_data present, no session -> parse flow prefix
    if callback_data:
        # Check exact match first (e.g. "menu:start:complaint")
        if callback_data in _CALLBACK_FLOW_MAP:
            return _CALLBACK_FLOW_MAP[callback_data], 0.95

        # Check flow prefix (e.g. "complaint:category:hvac" -> "complaint")
        prefix = callback_data.split(":")[0]
        if prefix in _CALLBACK_FLOW_MAP:
            return _CALLBACK_FLOW_MAP[prefix], 0.95

        return TelegramIntent.UNKNOWN, 0.5

    # Rule 3: active session + free text -> CHECKLIST_REPLY
    if has_active_session and text:
        return TelegramIntent.CHECKLIST_REPLY, 0.9

    # No text to classify
    if not text:
        return TelegramIntent.UNKNOWN, 0.0

    # Rule 4: WO pattern + done/completed keywords
    has_wo_ref = bool(_WO_RE.search(text))
    has_done = any(kw in text_lower for kw in _WO_DONE_KEYWORDS)
    if has_wo_ref or has_done:
        if has_wo_ref and has_done:
            return TelegramIntent.WO_UPDATE, 0.95
        if has_wo_ref:
            return TelegramIntent.WO_UPDATE, 0.85
        # "done" alone without WO ref — could be checklist or WO
        # Let session context decide; if no session, it's ambiguous
        # Fall through to other rules

    # Rule 5: Equipment ID pattern
    has_equipment = bool(_EQUIPMENT_RE.search(text))
    if has_equipment:
        return TelegramIntent.TECHNICIAN_REPORT, 0.85

    # Rule 6: Technical inspection vocabulary
    if any(term in text_lower for term in _TECH_VOCAB):
        return TelegramIntent.TECHNICIAN_REPORT, 0.75

    # Rule 7: Issue classifier match (client complaint)
    classification = classify_issue(text)
    if classification and not has_equipment:
        # Has a discipline match — treat as client complaint
        return TelegramIntent.CLIENT_COMPLAINT, 0.7

    # Rule 8: Ad-hoc fault keywords (without HVAC/equipment context)
    if any(kw in text_lower for kw in _ADHOC_KEYWORDS) and not has_equipment:
        return TelegramIntent.AD_HOC_FAULT, 0.7

    # Rule 9: Unknown
    return TelegramIntent.UNKNOWN, 0.0
