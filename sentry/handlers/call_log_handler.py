"""
Call Log Handler — Integration layer between call_log CLI and ThesaurusService.

classify_issue() always returns a dict; check is_facilities_issue to branch.
"""

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SENTRY_ROOT = os.path.join(_HERE, "..")
_THESAURUS_DIR = os.path.join(_SENTRY_ROOT, "thesaurus")
for _p in (_THESAURUS_DIR, _SENTRY_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from complaint_thesaurus import ComplaintCategory, PRIORITY_MAP, SPECIALTY_MAP
from thesaurus_service import get_thesaurus

# ---------------------------------------------------------------------------
# Taxonomy constants
# ---------------------------------------------------------------------------
CALL_LOG_TAXONOMY = {
    "HVAC": ["Too hot", "Too cold", "Stuffy air"],
    "Lighting": ["Lighting issue"],
    "General": ["Other facilities issue"],
}

_DISCIPLINE_MAP: dict[ComplaintCategory, str] = {
    ComplaintCategory.TOO_HOT: "HVAC",
    ComplaintCategory.TOO_COLD: "HVAC",
    ComplaintCategory.STUFFY_AIR: "HVAC",
    ComplaintCategory.LIGHTING: "Lighting",
    ComplaintCategory.OTHER: "General",
}

_SUB_CATEGORY_MAP: dict[ComplaintCategory, str] = {
    ComplaintCategory.TOO_HOT: "Too hot",
    ComplaintCategory.TOO_COLD: "Too cold",
    ComplaintCategory.STUFFY_AIR: "Stuffy air",
    ComplaintCategory.LIGHTING: "Lighting issue",
    ComplaintCategory.OTHER: "Other facilities issue",
}

# ---------------------------------------------------------------------------
# Desk → zone mapping (site-002 floor plan, prefix-based fallback)
# ---------------------------------------------------------------------------
_DESK_ZONE_OVERRIDES: dict[str, dict] = {
    "208": {"zone_id": "zone-004", "floor": "First Floor"},
    "209": {"zone_id": "zone-004", "floor": "First Floor"},
}

_FLOOR_BY_PREFIX = {
    "1": "Ground Floor",
    "2": "First Floor",
    "3": "Second Floor",
    "4": "Third Floor",
}

_ZONE_BY_PREFIX = {
    "1": "zone-001",
    "2": "zone-003",
    "3": "zone-005",
    "4": "zone-007",
}


def desk_to_zone(desk_id: str) -> dict:
    """Map a desk ID string to zone_id and floor."""
    key = str(desk_id).strip()
    if key in _DESK_ZONE_OVERRIDES:
        return _DESK_ZONE_OVERRIDES[key]
    prefix = key[0] if key else "1"
    return {
        "zone_id": _ZONE_BY_PREFIX.get(prefix, "zone-001"),
        "floor": _FLOOR_BY_PREFIX.get(prefix, "Unknown floor"),
    }


# ---------------------------------------------------------------------------
# Desk extraction
# ---------------------------------------------------------------------------
_DESK_PATTERNS = [
    re.compile(r"\bdesk\s*(\d{2,4})\b", re.IGNORECASE),
    re.compile(r"\bstation\s*(\d{2,4})\b", re.IGNORECASE),
    re.compile(r"\bd(\d{3,4})\b", re.IGNORECASE),
]


def extract_desk_from_message(text: str) -> str | None:
    """Return the first desk number found in text, or None."""
    if not text:
        return None
    for pat in _DESK_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_issue(text: str, user_id=None) -> dict:
    """
    Classify a facilities complaint.

    Always returns a dict:
      - is_facilities_issue=True  → matched, includes discipline/category/etc.
      - is_facilities_issue=False → no match, includes escalate=True and reason.

    user_id is accepted for audit purposes but does not affect classification.
    """
    if not text or not text.strip():
        return {
            "is_facilities_issue": False,
            "escalate": True,
            "reason": "Empty complaint text",
        }

    result = get_thesaurus().classify(text)

    if result is None:
        return {
            "is_facilities_issue": False,
            "escalate": True,
            "reason": "No matching facilities category found",
        }

    cat = result.category
    return {
        "is_facilities_issue": True,
        "category": cat.value,
        "discipline": _DISCIPLINE_MAP[cat],
        "sub_category": _SUB_CATEGORY_MAP[cat],
        "specialty": SPECIALTY_MAP[cat],
        "priority": PRIORITY_MAP[cat],
        "matched_phrase": result.matched_phrase,
        "match_score": result.match_score,
    }


def is_facilities_complaint(text: str) -> bool:
    """Return True if text matches a known facilities complaint."""
    return get_thesaurus().is_facilities_complaint(text)


def get_taxonomy_summary() -> list[dict]:
    """Return taxonomy rows for CLI display."""
    return [
        {
            "discipline": _DISCIPLINE_MAP[cat],
            "sub_category": _SUB_CATEGORY_MAP[cat],
            "specialty": SPECIALTY_MAP[cat],
            "priority": PRIORITY_MAP[cat],
        }
        for cat in ComplaintCategory
    ]
