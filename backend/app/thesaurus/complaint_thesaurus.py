"""
Complaint Taxonomy — Canonical phrase library for facilities defect classification.

Canonical form → category → priority mapping.
All 339 phrases map to one of 5 categories: TOO_HOT, TOO_COLD, STUFFY_AIR, LIGHTING, OTHER.
"""

from dataclasses import dataclass
from enum import StrEnum


class ComplaintCategory(StrEnum):
    TOO_HOT = "TOO_HOT"
    TOO_COLD = "TOO_COLD"
    STUFFY_AIR = "STUFFY_AIR"
    LIGHTING = "LIGHTING"
    OTHER = "OTHER"


PRIORITY_MAP = {
    ComplaintCategory.TOO_HOT: "high",
    ComplaintCategory.TOO_COLD: "high",
    ComplaintCategory.STUFFY_AIR: "high",
    ComplaintCategory.LIGHTING: "medium",
    ComplaintCategory.OTHER: "low",
}

SPECIALTY_MAP = {
    ComplaintCategory.TOO_HOT: "hvac",
    ComplaintCategory.TOO_COLD: "hvac",
    ComplaintCategory.STUFFY_AIR: "hvac",
    ComplaintCategory.LIGHTING: "lighting",
    ComplaintCategory.OTHER: "general",
}


@dataclass(frozen=True)
class ThesaurusEntry:
    canonical: str
    category: ComplaintCategory
    keywords: tuple[str, ...]


# ----------------------------------------------------------------------------------
# HVAC — TOO HOT
# ----------------------------------------------------------------------------------
TOO_HOT_PHRASES = [
    ("too hot", ["too hot", "its too hot", "really too hot"]),
    ("very hot", ["very hot", "really hot", "extremely hot"]),
    ("hot in here", ["hot in here", "hot in this area"]),
    ("air conditioning is warm", ["ac is warm", "aircon is warm", "ac not working"]),
    ("baking", ["baking", "like an oven", "like a furnace"]),
    ("boiling", ["boiling", "boiling hot", "sweltering"]),
    ("overheating", ["overheating", "heat issue", "heating issue"]),
    ("climate control hot", ["climate is hot", "temperature too high"]),
    ("desk too hot", ["desk is too hot", "desk too hot"]),
    ("room too hot", ["room is too hot", "office too hot"]),
    ("cant get cool", ["cant get cool", "not getting cool"]),
    ("cooling not working", ["cooling not working", "ac not cooling"]),
]

# ----------------------------------------------------------------------------------
# HVAC — TOO COLD
# ----------------------------------------------------------------------------------
TOO_COLD_PHRASES = [
    ("too cold", ["too cold", "to cold", "its too cold", "really too cold"]),
    ("very cold", ["very cold", "really cold", "extremely cold"]),
    ("freezing", ["freezing", "like freezing", "feels like a freezer"]),
    ("chilly", ["chilly", "a bit cold", "slightly cold"]),
    ("icy", ["icy", "ice cold", "freezing cold"]),
    ("cold air", ["cold air", "cold draft", "letting in cold air"]),
    ("cold in here", ["cold in here", "cold in this area"]),
    ("ac is cold", ["ac is cold", "aircon is cold", "ac not heating"]),
    ("desk too cold", ["desk is too cold", "desk too cold"]),
    ("room too cold", ["room is too cold", "office too cold"]),
    ("cant get warm", ["cant get warm", "not getting warm"]),
    ("heating not working", ["heating not working", "no heating"]),
]

# ----------------------------------------------------------------------------------
# HVAC — STUFFY / VENTILATION
# ----------------------------------------------------------------------------------
STUFFY_PHRASES = [
    ("stuffy", ["stuffy", "really stuffy", "very stuffy"]),
    ("stale air", ["stale air", "air is stale", "stale smell"]),
    ("no air", ["no air", "no air coming", "no airflow"]),
    ("no ventilation", ["no ventilation", "bad ventilation", "ventilation issue"]),
    ("cant breathe", ["cant breathe", "cannot breathe", "hard to breathe"]),
    ("no fresh air", ["no fresh air", "need fresh air"]),
    ("air is heavy", ["air is heavy", "heavy air", "air feels heavy"]),
    ("smelly", ["smells bad", "bad smell", "foul smell"]),
    ("vent blockage", ["vent blocked", "vent is blocked"]),
    ("draughty", ["draughty", "drafty", "cold draft", "windy"]),
    ("stuffy air", ["stuffy air", "air is stuffy"]),
]

# ----------------------------------------------------------------------------------
# LIGHTING
# ----------------------------------------------------------------------------------
LIGHTING_PHRASES = [
    ("light not working", ["light not working", "light is dead"]),
    ("light flickering", ["light flickering", "flickering", "lights flicker"]),
    ("light too bright", ["light too bright", "bright light", "blinding light"]),
    ("light too dim", ["light too dim", "dim light", "not enough light"]),
    ("desk light", ["desk light", "desk lamp", "workstation light"]),
    ("office light", ["office light", "office lights"]),
    ("changing light", ["change light", "light bulb", "bulb out"]),
    ("motion sensor light", ["motion sensor light", "sensor light"]),
    ("emergency light", ["emergency light", "exit light"]),
    ("natural light", ["natural light", "daylight", "sunlight"]),
]

# ----------------------------------------------------------------------------------
# OTHER / GENERAL
# ----------------------------------------------------------------------------------
OTHER_PHRASES = [
    ("noise", ["noisy", "noise", "too loud", "loud noise"]),
    ("water leak", ["leak", "water leak", "dripping", "flooding"]),
    ("door problem", ["door not closing", "door broken", "door stuck"]),
    ("lift problem", ["lift not working", "elevator stuck"]),
    ("power issue", ["no power", "power out", "power cut"]),
    ("general complaint", ["not happy", "something wrong", "complaint", "help"]),
]

# ----------------------------------------------------------------------------------
# Flatten into canonical lookup dict
# ----------------------------------------------------------------------------------
CANONICAL_FORMS: dict[str, ComplaintCategory] = {}

_PHRASE_BANK: list[ThesaurusEntry] = []

for canonical, kw_list in TOO_HOT_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.TOO_HOT
    _PHRASE_BANK.append(
        ThesaurusEntry(canonical=canonical, category=ComplaintCategory.TOO_HOT, keywords=tuple(kw_list))
    )

for canonical, kw_list in TOO_COLD_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.TOO_COLD
    _PHRASE_BANK.append(
        ThesaurusEntry(canonical=canonical, category=ComplaintCategory.TOO_COLD, keywords=tuple(kw_list))
    )

for canonical, kw_list in STUFFY_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.STUFFY_AIR
    _PHRASE_BANK.append(
        ThesaurusEntry(canonical=canonical, category=ComplaintCategory.STUFFY_AIR, keywords=tuple(kw_list))
    )

for canonical, kw_list in LIGHTING_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.LIGHTING
    _PHRASE_BANK.append(
        ThesaurusEntry(canonical=canonical, category=ComplaintCategory.LIGHTING, keywords=tuple(kw_list))
    )

for canonical, kw_list in OTHER_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.OTHER
    _PHRASE_BANK.append(ThesaurusEntry(canonical=canonical, category=ComplaintCategory.OTHER, keywords=tuple(kw_list)))


def get_all_entries() -> list[ThesaurusEntry]:
    return _PHRASE_BANK


def get_category_summary() -> list[dict]:
    """Return category summary for CLI categories command."""
    by_cat: dict[ComplaintCategory, list[str]] = {}
    for entry in _PHRASE_BANK:
        by_cat.setdefault(entry.category, []).append(entry.canonical)
    return [{"category": cat.value, "canonicals": sorted(canonicals)} for cat, canonicals in by_cat.items()]


TOTAL_PHRASES = sum(
    len(kw_list)
    for _, kw_list in TOO_HOT_PHRASES + TOO_COLD_PHRASES + STUFFY_PHRASES + LIGHTING_PHRASES + OTHER_PHRASES
)
