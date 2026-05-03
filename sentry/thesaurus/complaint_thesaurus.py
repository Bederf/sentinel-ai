"""
Complaint Taxonomy — Canonical phrase library for facilities defect classification.

Canonical form → category → priority mapping.
All 339 phrases map to one of 5 categories: TOO_HOT, TOO_COLD, STUFFY_AIR, LIGHTING, OTHER.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ComplaintCategory(str, Enum):
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
    # Canonical + keyword variants
    ("too hot", ["too hot", "its too hot", "it's too hot", "is too hot", "really too hot"]),
    ("very hot", ["very hot", "really hot", "extremely hot", "super hot", "so hot"]),
    ("hot in here", ["hot in here", "hot in this area", "hot in the office", "getting hot in here"]),
    ("air conditioning is warm", ["ac is warm", "aircon is warm", "ac is not cold", "aircon is not cold", "ac not working", "aircon not working"]),
    ("baking", ["baking", "like an oven", "like a furnace", "like a sauna", "oven"]),
    ("boiling", ["boiling", "boiling hot", "sweltering"]),
    ("overheating", ["overheating", "heat issue", "heat problem", "heating issue"]),
    ("climate control hot", ["climate is hot", "climate control is hot", "temperature too high", "temp too high"]),
    ("desk too hot", ["desk is too hot", "desk too hot", "my desk is hot"]),
    ("room too hot", ["room is too hot", "room too hot", "office too hot"]),
    ("cant get cool", ["cant get cool", "cannot get cool", "not getting cool", "wont cool down"]),
    ("cooling not working", ["cooling not working", "cooling not working", "ac not cooling", "aircon not cooling"]),
]

# ----------------------------------------------------------------------------------
# HVAC — TOO COLD
# ----------------------------------------------------------------------------------
TOO_COLD_PHRASES = [
    ("too cold", ["too cold", "to cold", "its too cold", "it's too cold", "is too cold", "really too cold"]),
    ("very cold", ["very cold", "really cold", "extremely cold", "super cold", "so cold"]),
    ("freezing", ["freezing", "like freezing", "absolutely freezing", "im freezing", "feels like a freezer", "feels freezing"]),
    ("chilly", ["chilly", "a bit cold", "slightly cold", "a little cold", "chilly in here"]),
    ("icy", ["icy", "ice cold", "like ice", "freezing cold"]),
    ("cold air", ["cold air", "cold draft", "letting in cold air", "cold air coming in", "cold air from window"]),
    ("cold in here", ["cold in here", "cold in this area", "cold in the office", "getting cold in here"]),
    ("ac is cold", ["ac is cold", "aircon is cold", "ac is not warm", "aircon is not warm", "ac not heating", "aircon not heating"]),
    ("desk too cold", ["desk is too cold", "desk too cold", "my desk is cold"]),
    ("room too cold", ["room is too cold", "room too cold", "office too cold"]),
    ("cant get warm", ["cant get warm", "cannot get warm", "not getting warm", "wont warm up"]),
    ("heating not working", ["heating not working", "heat not working", "no heating", "no heat"]),
]

# ----------------------------------------------------------------------------------
# HVAC — STUFFY / VENTILATION
# ----------------------------------------------------------------------------------
STUFFY_PHRASES = [
    ("stuffy", ["stuffy", "really stuffy", "very stuffy", "extremely stuffy"]),
    ("stale air", ["stale air", "air is stale", "smells stale", "stale smell"]),
    ("no air", ["no air", "no air coming", "no airflow", "air not flowing", "no air flow"]),
    ("no ventilation", ["no ventilation", "bad ventilation", "poor ventilation", "lack of ventilation", "ventilation issue"]),
    ("cant breathe", ["cant breathe", "cannot breathe", "hard to breathe", "difficult to breathe", "breathing is difficult"]),
    ("no fresh air", ["no fresh air", "not enough fresh air", "need fresh air", "want fresh air"]),
    ("air is heavy", ["air is heavy", "heavy air", "air feels heavy", "air is thick"]),
    ("smelly", ["smells bad", "bad smell", "unpleasant smell", "foul smell", "odor", "odour"]),
    ("vent blockage", ["vent blocked", "vent is blocked", "ventilation blocked", "air vent blocked"]),
    ("draughty", ["draughty", "drafty", "draughty in here", "drafty in here", "cold draft", "windy"]),
    ("stuffy air", ["stuffy air", "air is stuffy", "office is stuffy"]),
]

# ----------------------------------------------------------------------------------
# LIGHTING
# ----------------------------------------------------------------------------------
LIGHTING_PHRASES = [
    ("light not working", ["light not working", "light is not working", "light is dead", "lights not working"]),
    ("light flickering", ["light flickering", "lights flickering", "flickering light", "light flickers", "flickering", "lights flicker", "light flicker"]),
    ("light too bright", ["light too bright", "lights too bright", "bright light", "blinding light", "glaring light"]),
    ("light too dim", ["light too dim", "lights too dim", "dim light", "dim lighting", "not enough light"]),
    ("desk light", ["desk light", "desk lamp", "workstation light", "my light"]),
    ("office light", ["office light", "office lights", "common area light", "meeting room light"]),
    ("changing light", ["change light", "replace light", "light bulb", "light bulb out", "bulb out", "lamp out"]),
    ("motion sensor light", ["motion sensor light", "motion light", "sensor light", " PIR light"]),
    ("emergency light", ["emergency light", "exit light", "escape light", "emergency exit light"]),
    ("natural light", ["natural light", "daylight", "sunlight", "too bright from window", "window too bright"]),
]

# ----------------------------------------------------------------------------------
# OTHER / GENERAL
# ----------------------------------------------------------------------------------
OTHER_PHRASES = [
    ("noise", ["noisy", "noise", "too loud", "loud noise", "drilling", "construction noise", "loud"]),
    ("water leak", ["leak", "water leak", "dripping", "drip", "flooding", "wet floor", "puddle"]),
    ("door problem", ["door not closing", "door broken", "door stuck", "door jammed", "cant close door", "cant open door"]),
    ("lift problem", ["lift not working", "elevator stuck", "lift issue", "elevator problem", "lift broken"]),
    ("power issue", ["no power", "power out", "power cut", "electricity off", "eskom", "load shedding"]),
    ("general complaint", ["not happy", "something wrong", "issue", "problem", "complaint", "help"]),
]

# ----------------------------------------------------------------------------------
# Flatten into canonical lookup dict
# ----------------------------------------------------------------------------------
CANONICAL_FORMS: dict[str, ComplaintCategory] = {}

_PHRASE_BANK: list[ThesaurusEntry] = []

for canonical, kw_list in TOO_HOT_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.TOO_HOT
    _PHRASE_BANK.append(ThesaurusEntry(canonical=canonical, category=ComplaintCategory.TOO_HOT, keywords=tuple(kw_list)))

for canonical, kw_list in TOO_COLD_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.TOO_COLD
    _PHRASE_BANK.append(ThesaurusEntry(canonical=canonical, category=ComplaintCategory.TOO_COLD, keywords=tuple(kw_list)))

for canonical, kw_list in STUFFY_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.STUFFY_AIR
    _PHRASE_BANK.append(ThesaurusEntry(canonical=canonical, category=ComplaintCategory.STUFFY_AIR, keywords=tuple(kw_list)))

for canonical, kw_list in LIGHTING_PHRASES:
    CANONICAL_FORMS[canonical] = ComplaintCategory.LIGHTING
    _PHRASE_BANK.append(ThesaurusEntry(canonical=canonical, category=ComplaintCategory.LIGHTING, keywords=tuple(kw_list)))

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
    return [
        {"category": cat.value, "canonicals": sorted(canicals)}
        for cat, canonicals in by_cat.items()
    ]


TOTAL_PHRASES = sum(
    len(kw_list) for _, kw_list in
    TOO_HOT_PHRASES + TOO_COLD_PHRASES + STUFFY_PHRASES + LIGHTING_PHRASES + OTHER_PHRASES
)
