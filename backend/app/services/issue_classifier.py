"""Shared Issue Classifier — Phase 131.2d.

Unified taxonomy for classifying facilities issues regardless of intake
channel (Telegram call-log, email, future WhatsApp).

Extracted from ``~/.sentry/legacy-bot/handlers/call_log_handler.py``.
The call-log handler will continue using its own copy for now; Phase 2
will refactor it to import from here.

47 sub-categories across 11 disciplines.  Classification is pure keyword
matching — no LLM, no ML, deterministic.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ===========================================================================
# FIXED TAXONOMY — No "Other", no free text categories
# ===========================================================================
# Each entry: discipline, sub_category, specialty, priority, keywords
# Keywords are matched against the user's message.  ALL matching is done
# in Python — the LLM never decides the category.
# ===========================================================================

CALL_LOG_TAXONOMY: List[Dict[str, Any]] = [
    # --- Plumbing ---
    {
        "discipline": "Plumbing",
        "sub_category": "Leaking tap",
        "specialty": "plumbing",
        "priority": "medium",
        "keywords": ["tap", "dripping tap", "faucet", "dripping faucet"],
    },
    {
        "discipline": "Plumbing",
        "sub_category": "Leaking pipe",
        "specialty": "plumbing",
        "priority": "high",
        "keywords": ["pipe", "leaking pipe", "ceiling leak", "leak from ceiling", "leak above"],
    },
    {
        "discipline": "Plumbing",
        "sub_category": "Blocked drain",
        "specialty": "plumbing",
        "priority": "medium",
        "keywords": ["drain", "blocked drain", "clogged drain", "slow drain"],
    },
    {
        "discipline": "Plumbing",
        "sub_category": "Blocked toilet",
        "specialty": "plumbing",
        "priority": "medium",
        "keywords": ["toilet", "blocked toilet", "toilet blocked", "toilet won't flush", "won't flush"],
    },
    {
        "discipline": "Plumbing",
        "sub_category": "No hot water",
        "specialty": "plumbing",
        "priority": "medium",
        "keywords": ["hot water", "no hot water", "geyser", "no water", "cold water only"],
    },
    {
        "discipline": "Plumbing",
        "sub_category": "Flooding",
        "specialty": "plumbing",
        "priority": "critical",
        "keywords": ["flood", "flooding", "burst pipe", "burst", "water everywhere", "water pouring"],
    },
    # --- Electrical ---
    {
        "discipline": "Electrical",
        "sub_category": "Power outlet not working",
        "specialty": "electrical",
        "priority": "high",
        "keywords": ["outlet", "socket", "plug", "no power", "power point", "wall socket"],
    },
    {
        "discipline": "Electrical",
        "sub_category": "Tripped breaker",
        "specialty": "electrical",
        "priority": "high",
        "keywords": ["tripped", "breaker", "db", "distribution board", "trip switch"],
    },
    {
        "discipline": "Electrical",
        "sub_category": "Sparking",
        "specialty": "electrical",
        "priority": "critical",
        "keywords": ["spark", "sparking", "burning smell", "electrical smell", "arcing"],
    },
    {
        "discipline": "Electrical",
        "sub_category": "Light flickering",
        "specialty": "electrical",
        "priority": "medium",
        "keywords": ["flickering", "flashing", "flicker", "strobe"],
    },
    {
        "discipline": "Electrical",
        "sub_category": "Light not working",
        "specialty": "electrical",
        "priority": "medium",
        "keywords": [
            "light out",
            "light off",
            "dark",
            "dim",
            "bulb",
            "lamp",
            "no light",
            "light not working",
            "light is out",
            "light broken",
        ],
    },
    {
        "discipline": "Electrical",
        "sub_category": "Emergency light fault",
        "specialty": "electrical",
        "priority": "high",
        "keywords": ["emergency light", "exit light", "emergency lamp"],
    },
    # --- HVAC ---
    {
        "discipline": "HVAC",
        "sub_category": "Too hot",
        "specialty": "hvac",
        "priority": "medium",
        "keywords": ["too hot", "hot", "warm", "baking", "boiling", "overheating", "sweltering"],
    },
    {
        "discipline": "HVAC",
        "sub_category": "Too cold",
        "specialty": "hvac",
        "priority": "medium",
        "keywords": ["too cold", "cold", "freezing", "chilly", "icy"],
    },
    {
        "discipline": "HVAC",
        "sub_category": "Noisy unit",
        "specialty": "hvac",
        "priority": "medium",
        "keywords": ["noisy", "noise", "rattling", "humming", "vibrating", "loud", "fan noise", "buzzing"],
    },
    {
        "discipline": "HVAC",
        "sub_category": "Stuffy air",
        "specialty": "hvac",
        "priority": "medium",
        "keywords": [
            "stuffy",
            "stale",
            "no air",
            "bad air",
            "ventilation",
            "no ventilation",
            "stuffy air",
            "can't breathe",
        ],
    },
    {
        "discipline": "HVAC",
        "sub_category": "Water dripping from AC unit",
        "specialty": "hvac",
        "priority": "high",
        "keywords": [
            "aircon leak",
            "ac leak",
            "unit leaking",
            "dripping from aircon",
            "aircon dripping",
            "ac dripping",
            "water from ac",
        ],
    },
    {
        "discipline": "HVAC",
        "sub_category": "AC unit not working",
        "specialty": "hvac",
        "priority": "medium",
        "keywords": [
            "aircon not working",
            "ac not working",
            "ac off",
            "aircon off",
            "air con off",
            "unit off",
            "aircon broken",
            "ac broken",
        ],
    },
    # --- Building Fabric ---
    {
        "discipline": "Building Fabric",
        "sub_category": "Carpet lifting",
        "specialty": "general",
        "priority": "high",
        "keywords": ["carpet", "carpet lifting", "carpet loose", "carpet peeling"],
    },
    {
        "discipline": "Building Fabric",
        "sub_category": "Damaged floor tile",
        "specialty": "general",
        "priority": "medium",
        "keywords": ["tile", "cracked tile", "loose tile", "broken tile", "floor tile"],
    },
    {
        "discipline": "Building Fabric",
        "sub_category": "Broken window",
        "specialty": "general",
        "priority": "high",
        "keywords": ["window", "glass", "broken glass", "smashed glass", "smashed window", "cracked window"],
    },
    {
        "discipline": "Building Fabric",
        "sub_category": "Ceiling tile damaged",
        "specialty": "general",
        "priority": "medium",
        "keywords": ["ceiling", "ceiling tile", "ceiling panel", "ceiling board", "ceiling damage"],
    },
    {
        "discipline": "Building Fabric",
        "sub_category": "Wall damage",
        "specialty": "general",
        "priority": "low",
        "keywords": ["wall", "hole in wall", "crack in wall", "wall damage", "drywall"],
    },
    {
        "discipline": "Building Fabric",
        "sub_category": "Paint peeling",
        "specialty": "general",
        "priority": "low",
        "keywords": ["paint", "peeling", "chipping", "paint peeling", "flaking"],
    },
    # --- Access & Security ---
    {
        "discipline": "Access & Security",
        "sub_category": "Door won't close",
        "specialty": "security",
        "priority": "medium",
        "keywords": ["door won't close", "door stuck", "door not closing", "door jammed"],
    },
    {
        "discipline": "Access & Security",
        "sub_category": "Door won't lock",
        "specialty": "security",
        "priority": "medium",
        "keywords": ["lock", "won't lock", "can't lock", "latch", "door lock"],
    },
    {
        "discipline": "Access & Security",
        "sub_category": "Badge reader not working",
        "specialty": "security",
        "priority": "medium",
        "keywords": ["badge", "reader", "access card", "tag", "swipe", "card reader", "badge reader"],
    },
    {
        "discipline": "Access & Security",
        "sub_category": "Boom gate fault",
        "specialty": "security",
        "priority": "medium",
        "keywords": ["boom", "boom gate", "parking gate", "gate stuck", "barrier"],
    },
    # --- Fire & Life Safety ---
    {
        "discipline": "Fire & Life Safety",
        "sub_category": "Fire alarm sounding",
        "specialty": "fire",
        "priority": "critical",
        "keywords": ["fire alarm", "alarm sounding", "alarm going off", "fire bell"],
    },
    {
        "discipline": "Fire & Life Safety",
        "sub_category": "Smoke detected",
        "specialty": "fire",
        "priority": "critical",
        "keywords": ["smoke", "smelling smoke", "smoke in"],
    },
    {
        "discipline": "Fire & Life Safety",
        "sub_category": "Gas smell",
        "specialty": "general",
        "priority": "critical",
        "keywords": ["gas", "gas smell", "smell gas", "gas leak"],
    },
    {
        "discipline": "Fire & Life Safety",
        "sub_category": "Sprinkler issue",
        "specialty": "fire",
        "priority": "critical",
        "keywords": ["sprinkler", "sprinkler leak", "sprinkler activated"],
    },
    {
        "discipline": "Fire & Life Safety",
        "sub_category": "Extinguisher missing",
        "specialty": "fire",
        "priority": "high",
        "keywords": ["extinguisher", "fire extinguisher", "missing extinguisher", "expired extinguisher"],
    },
    {
        "discipline": "Fire & Life Safety",
        "sub_category": "Emergency exit blocked",
        "specialty": "fire",
        "priority": "critical",
        "keywords": ["exit blocked", "fire exit", "emergency exit", "exit door", "blocked exit"],
    },
    # --- Furniture & Fittings ---
    {
        "discipline": "Furniture & Fittings",
        "sub_category": "Broken chair",
        "specialty": "general",
        "priority": "low",
        "keywords": ["chair", "broken chair", "chair broken", "office chair"],
    },
    {
        "discipline": "Furniture & Fittings",
        "sub_category": "Broken desk",
        "specialty": "general",
        "priority": "low",
        "keywords": ["desk broken", "desk damaged", "table broken", "broken table", "broken desk"],
    },
    {
        "discipline": "Furniture & Fittings",
        "sub_category": "Broken blind",
        "specialty": "general",
        "priority": "low",
        "keywords": ["blind", "blinds", "curtain", "broken blind", "blind broken"],
    },
    # --- Pest Control ---
    {
        "discipline": "Pest Control",
        "sub_category": "Insects",
        "specialty": "general",
        "priority": "low",
        "keywords": [
            "insect",
            "cockroach",
            "cockroaches",
            "ants",
            "ant",
            "spider",
            "spiders",
            "bug",
            "bugs",
            "flies",
            "fly",
        ],
    },
    {
        "discipline": "Pest Control",
        "sub_category": "Rodents",
        "specialty": "general",
        "priority": "medium",
        "keywords": ["rat", "rats", "mouse", "mice", "rodent", "rodents"],
    },
    {
        "discipline": "Pest Control",
        "sub_category": "Birds",
        "specialty": "general",
        "priority": "low",
        "keywords": ["bird", "birds", "pigeon", "pigeons", "bird droppings"],
    },
    # --- Cleaning ---
    {
        "discipline": "Cleaning",
        "sub_category": "Spill on floor",
        "specialty": "general",
        "priority": "medium",
        "keywords": ["spill", "mess", "wet floor", "slippery floor", "spilled"],
    },
    {
        "discipline": "Cleaning",
        "sub_category": "Bad odour",
        "specialty": "general",
        "priority": "medium",
        "keywords": ["odour", "odor", "stink", "stench", "bad smell", "smell bad", "smells bad", "smelly"],
    },
    {
        "discipline": "Cleaning",
        "sub_category": "Biohazard",
        "specialty": "general",
        "priority": "high",
        "keywords": ["blood", "vomit", "needle", "biohazard", "bodily fluid"],
    },
    # --- Grounds & Parking ---
    {
        "discipline": "Grounds & Parking",
        "sub_category": "Pothole",
        "specialty": "general",
        "priority": "medium",
        "keywords": ["pothole", "hole in road", "uneven road", "uneven surface", "dip in road"],
    },
    {
        "discipline": "Grounds & Parking",
        "sub_category": "Outdoor lighting",
        "specialty": "general",
        "priority": "medium",
        "keywords": [
            "parking light",
            "outdoor light",
            "dark parking",
            "outside light",
            "street light",
            "parking lot dark",
        ],
    },
    {
        "discipline": "Grounds & Parking",
        "sub_category": "Landscaping",
        "specialty": "general",
        "priority": "low",
        "keywords": ["tree", "branch", "grass", "overgrown", "hedge", "garden", "landscaping"],
    },
]

# Urgency escalators — bump priority based on context keywords
URGENCY_ESCALATORS: Dict[str, List[str]] = {
    "critical": [
        "fire",
        "smoke",
        "gas",
        "stuck in",
        "trapped",
        "flooding",
        "sparking",
        "danger",
        "unsafe",
        "emergency",
    ],
    "high": [
        "trip",
        "tripping",
        "someone could",
        "hurt",
        "injury",
        "burst",
        "pouring",
        "no power",
        "safety",
        "urgent",
        "immediately",
        "hazard",
    ],
}

# Priority ranking for comparisons
PRIORITY_RANK: Dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# Discipline → email-category mapping (backward compat with n8n 8-category classifier)
DISCIPLINE_TO_CATEGORY: Dict[str, str] = {
    "Electrical": "electrical",
    "HVAC": "hvac",
    "Plumbing": "plumbing",
    "Fire & Life Safety": "fire",
    "Access & Security": "access",
    "Building Fabric": "general",
    "Furniture & Fittings": "general",
    "Pest Control": "pest",
    "Cleaning": "general",
    "Grounds & Parking": "general",
}


# ===========================================================================
# Classification — strict taxonomy matching
# ===========================================================================


def classify_issue(text: str) -> Optional[Dict[str, str]]:
    """Classify user text against the FIXED taxonomy.

    Returns the best matching entry or None if no match.
    Result includes: discipline, sub_category, specialty, priority.
    """
    text_lower = text.lower().strip()

    best_match = None
    best_score = 0

    for entry in CALL_LOG_TAXONOMY:
        score = 0
        for kw in entry["keywords"]:
            if kw in text_lower:
                # Longer keyword matches are worth more (multi-word = more specific)
                score += len(kw.split())
        if score > best_score:
            best_score = score
            best_match = entry

    if best_match and best_score > 0:
        result = {
            "discipline": best_match["discipline"],
            "sub_category": best_match["sub_category"],
            "specialty": best_match["specialty"],
            "priority": best_match["priority"],
        }

        # Apply urgency escalation
        for urg_level, keywords in URGENCY_ESCALATORS.items():
            if any(kw in text_lower for kw in keywords):
                if PRIORITY_RANK.get(urg_level, 0) > PRIORITY_RANK.get(result["priority"], 0):
                    result["priority"] = urg_level
                break

        return result

    return None  # NO MATCH


def classify_email_subject(subject: str, body_snippet: str = "") -> Optional[Dict[str, str]]:
    """Classify email using subject line (primary) + first 200 chars of body (secondary).

    Runs subject-only first for tighter matching.
    If no match, retries with subject + body snippet (wider net, may have false positives).
    """
    result = classify_issue(subject)
    if result:
        return result
    if body_snippet:
        return classify_issue(f"{subject} {body_snippet[:200]}")
    return None


# ===========================================================================
# Location extraction helpers
# ===========================================================================


def extract_desk_from_message(text: str) -> Optional[str]:
    """Try to extract a desk number from the message text."""
    patterns = [
        r"desk\s*(\d{1,3})",
        r"near\s+desk\s*(\d{1,3})",
        r"my\s+desk\s+(?:is\s+)?(\d{1,3})",
    ]
    text_lower = text.lower()
    for p in patterns:
        m = re.search(p, text_lower)
        if m:
            return m.group(1).zfill(3)
    return None


def extract_floor_from_message(text: str) -> Optional[str]:
    """Try to extract a floor reference from the message."""
    patterns = [
        (r"level\s*(\d+)", lambda m: f"L{m.group(1)}"),
        (r"floor\s*(\d+)", lambda m: f"L{m.group(1)}"),
        (r"\bl(\d)\b", lambda m: f"L{m.group(1)}"),
        (r"ground\s*floor", lambda _: "L0"),
        (r"basement", lambda _: "B1"),
    ]
    text_lower = text.lower()
    for pattern, formatter in patterns:
        m = re.search(pattern, text_lower)
        if m:
            return formatter(m)
    return None


def extract_area_from_message(text: str) -> Optional[str]:
    """Try to extract a named area from the message."""
    areas = [
        "kitchen",
        "bathroom",
        "ladies bathroom",
        "mens bathroom",
        "ladies toilet",
        "mens toilet",
        "restroom",
        "toilet",
        "reception",
        "lobby",
        "foyer",
        "canteen",
        "cafeteria",
        "boardroom",
        "meeting room",
        "conference room",
        "server room",
        "stairwell",
        "passage",
        "corridor",
        "hallway",
        "lift lobby",
        "parking",
        "basement parking",
        "loading bay",
        "store room",
        "break room",
        "tea kitchen",
    ]
    text_lower = text.lower()
    # Match longest first
    for area in sorted(areas, key=len, reverse=True):
        if area in text_lower:
            return area.title()
    return None


def desk_to_zone(desk_id: str) -> Dict[str, str]:
    """Map desk number to zone and floor.

    Convention: 001-099=L0, 100-199=L1, 200-299=L2
    """
    try:
        num = int(desk_id)
    except (ValueError, TypeError):
        return {"zone_id": "unknown", "floor": "unknown"}

    if num < 100:
        return {"zone_id": f"Zone-{desk_id}", "floor": "L0"}
    elif num < 200:
        return {"zone_id": f"Zone-{desk_id}", "floor": "L1"}
    elif num < 300:
        return {"zone_id": f"Zone-{desk_id}", "floor": "L2"}
    else:
        return {"zone_id": f"Zone-{desk_id}", "floor": "unknown"}
