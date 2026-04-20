"""
Comfort Complaint NLP Extraction
=================================
Pure Python text extraction for comfort complaints.
Zero LLM dependency - uses regex and keyword matching.

Extracts structured info from free-text messages like:
  "it's freezing at desk 25" -> desk_id="25", types=["too_cold"]
"""

import re

# --- Complaint type detection ---

# Keywords mapped to complaint types (order matters for compound detection)
_COMPLAINT_PATTERNS: dict[str, list[str]] = {
    "too_hot": [
        r"\bhot\b",
        r"\bwarm\b",
        r"\bheat(?:ing)?\b",
        r"\bboiling\b",
        r"\bsweat(?:ing|y)?\b",
        r"\bburning\b",
        r"\boven\b",
        r"\bstifling\b",
        r"\broasting\b",
    ],
    "too_cold": [
        r"\bcold\b",
        r"\bfreez(?:ing|e)?\b",
        r"\bchilly?\b",
        r"\bfrost(?:y)?\b",
        r"\bicy?\b",
        r"\bcool\b",
    ],
    "stuffy": [
        r"\bstuff(?:y|iness)\b",
        r"\bstale\b",
        r"\bairless\b",
        r"\bstuffy?\b",
        r"\bno\s+(?:fresh\s+)?air\b",
        r"\bhard\s+to\s+breathe\b",
        r"\bcan'?t\s+breathe\b",
        r"\bco2\b",
        r"\bhumid(?:ity)?\b",
        r"\bmuggy\b",
    ],
    "drafty": [
        r"\bdraft(?:y|s)?\b",
        r"\bdraught(?:y|s)?\b",
        r"\bwindy?\b",
        r"\bblowing\b",
        r"\bbreezy?\b",
    ],
    "noise": [
        r"\bnois(?:e|y)\b",
        r"\bloud\b",
        r"\bbuzz(?:ing)?\b",
        r"\bhum(?:ming)?\b",
        r"\brattl(?:e|ing)\b",
        r"\bfcu\s+noise\b",
        r"\bvibrat(?:e|ing|ion)\b",
    ],
    "too_dark": [
        r"\bdark\b",
        r"\bdim\b",
        r"\bcan'?t\s+see\b",
        r"\blow\s+light\b",
        r"\bneed\s+(?:more\s+)?light\b",
    ],
    "too_bright": [
        r"\bbright\b",
        r"\bglare?\b",
        r"\bblind(?:ing)?\b",
        r"\btoo\s+much\s+light\b",
    ],
}

# Phrases that indicate a comfort complaint (broad detection)
_COMFORT_INDICATORS = [
    r"\b(?:too\s+)?(?:hot|cold|warm|chilly?|freez(?:ing|e)?)\b",
    r"\b(?:stuff(?:y|iness)|stale|airless|muggy|humid)\b",
    r"\b(?:draft(?:y|s)?|draught(?:y|s)?)\b",
    r"\b(?:nois(?:e|y)|loud|buzz(?:ing)?|hum(?:ming)?)\b",
    r"\b(?:dark|dim|bright|glare?)\b",
    r"\bcomfort\s+(?:complaint|issue|problem)\b",
    r"\buncomfortable\b",
    r"\btemperature\s+(?:issue|problem|complaint)\b",
    r"\bmy\s+desk\b.*\b(?:hot|cold|warm|freez)\b",
    r"\bit'?s\s+(?:really\s+)?(?:hot|cold|warm|freez)\b",
]

# Desk ID extraction patterns (ordered by specificity)
_DESK_PATTERNS = [
    # "desk L12-25" or "desk L2-D025"
    r"desk\s+([A-Za-z]\d{1,2}-?[A-Za-z]?\d{1,4})",
    # "desk 25" or "desk 203"
    r"desk\s+(\d{1,4})",
    # "at L12-25" or "at L2-D025"
    r"at\s+([A-Za-z]\d{1,2}-?[A-Za-z]?\d{1,4})\b",
    # "at 25" or "at desk 203"
    r"at\s+(?:desk\s+)?(\d{1,4})\b",
    # Standalone desk reference with prefix: "L12-25", "L2-D025"
    r"\b([A-Za-z]\d{1,2}-[A-Za-z]?\d{1,4})\b",
]


def detect_comfort_complaint(text: str) -> bool:
    """
    Detect whether a message is a comfort complaint.

    Uses broad keyword matching to catch natural language complaints.
    Returns True for messages like:
      - "it's freezing at my desk"
      - "too hot here"
      - "the FCU is making noise"
      - "can't see, too dark"

    Returns False for non-comfort messages like:
      - "WO-2026-0042"
      - "status"
      - "help"
    """
    lower = text.lower().strip()

    # Quick exclusions: known command patterns
    if lower.startswith(("wo-", "/", "status", "help", "alert", "?")):
        return False

    # Check broad indicators first
    for pattern in _COMFORT_INDICATORS:
        if re.search(pattern, lower):
            return True

    # Also check specific complaint type patterns
    for patterns in _COMPLAINT_PATTERNS.values():
        for pattern in patterns:
            if re.search(pattern, lower):
                return True

    return False


def extract_desk_id(text: str, bare_number_ok: bool = False) -> str | None:
    """
    Extract desk ID from free-text message.

    Handles various formats:
      "desk 203 is too hot"  -> "203"
      "at L12-25"            -> "L12-25"
      "too hot at 25"        -> "25"
      "desk L2-D025"         -> "L2-D025"

    Args:
        text: User message text.
        bare_number_ok: If True, accept a standalone number as desk ID.
            Used in multi-turn context when we've already asked "which desk?"

    Returns None if no desk ID found.
    """
    for pattern in _DESK_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Last resort: look for a bare number that could be a desk
    # Accept if message mentions desk/seat context, or if bare_number_ok (multi-turn)
    if bare_number_ok or re.search(r"\b(?:desk|seat|workstation|position)\b", text, re.IGNORECASE):
        match = re.search(r"\b(\d{1,4})\b", text)
        if match:
            return match.group(1)

    return None


def extract_complaint_types(text: str) -> list[str]:
    """
    Extract complaint type(s) from free-text message.

    Supports compound complaints:
      "cold and noisy"      -> ["too_cold", "noise"]
      "too hot"             -> ["too_hot"]
      "stuffy and dark"     -> ["stuffy", "too_dark"]

    Returns empty list if no complaint type detected.
    """
    lower = text.lower()
    found: list[str] = []

    for complaint_type, patterns in _COMPLAINT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lower):
                if complaint_type not in found:
                    found.append(complaint_type)
                break  # Found this type, move to next

    return found


def extract_duration(text: str) -> str | None:
    """
    Extract duration/timing context from complaint message.

    Captures phrases like:
      "since this morning"
      "for the past hour"
      "all day"
      "since 9am"

    Returns the duration phrase or None.
    """
    duration_patterns = [
        r"(since\s+(?:this\s+)?(?:morning|afternoon|yesterday|last\s+\w+|\d{1,2}(?::\d{2})?\s*(?:am|pm)?))",
        r"(for\s+(?:the\s+(?:past|last)\s+)?\d+\s*(?:hour|minute|min|hr|day)s?)",
        r"(all\s+(?:day|morning|afternoon|week))",
        r"(the\s+(?:whole|entire)\s+(?:day|morning|afternoon))",
    ]

    lower = text.lower()
    for pattern in duration_patterns:
        match = re.search(pattern, lower)
        if match:
            return match.group(1).strip()

    return None
