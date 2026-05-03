"""
ThesaurusService — Facilities complaint classification service.

Uses keyword substring matching against the canonical phrase library.
No LLM. Returns structured classification result.
"""

from dataclasses import dataclass
from typing import Optional

import rapidfuzz.fuzz as fuzz

from complaint_thesaurus import (
    ComplaintCategory,
    PRIORITY_MAP,
    SPECIALTY_MAP,
    _PHRASE_BANK,
    ThesaurusEntry,
    get_category_summary,
    TOTAL_PHRASES,
)

# Threshold for fuzzy match (0–100 score from rapidfuzz)
MATCH_THRESHOLD = 75


@dataclass
class ClassificationResult:
    discipline: str
    sub_category: str
    specialty: str
    priority: str
    matched_phrase: str
    match_score: int
    category: ComplaintCategory

    def to_dict(self) -> dict:
        return {
            "discipline": self.discipline,
            "sub_category": self.sub_category,
            "specialty": self.specialty,
            "priority": self.priority,
            "matched_phrase": self.matched_phrase,
            "match_score": self.match_score,
        }


def _map_category_to_sub_category(cat: ComplaintCategory) -> str:
    return {
        ComplaintCategory.TOO_HOT: "Too hot",
        ComplaintCategory.TOO_COLD: "Too cold",
        ComplaintCategory.STUFFY_AIR: "Stuffy air",
        ComplaintCategory.LIGHTING: "Lighting issue",
        ComplaintCategory.OTHER: "Other facilities issue",
    }[cat]


def _build_result(entry: ThesaurusEntry, matched_phrase: str, score: int) -> ClassificationResult:
    cat = entry.category
    sub_cat = _map_category_to_sub_category(cat)
    return ClassificationResult(
        discipline="HVAC" if cat in (ComplaintCategory.TOO_HOT, ComplaintCategory.TOO_COLD, ComplaintCategory.STUFFY_AIR) else cat.value.title(),
        sub_category=sub_cat,
        specialty=SPECIALTY_MAP[cat],
        priority=PRIORITY_MAP[cat],
        matched_phrase=matched_phrase,
        match_score=score,
        category=cat,
    )


class ThesaurusService:
    """
    Stateless complaint classifier.

    Match strategy:
    1. Exact substring match against all keywords (fast path)
    2. Fuzzy token-set match against canonical forms (fallback)
    """

    def __init__(self):
        self._keyword_index: dict[str, ThesaurusEntry] = {}
        for entry in _PHRASE_BANK:
            for kw in entry.keywords:
                self._keyword_index[kw.lower()] = entry

    def classify(self, text: str) -> Optional[ClassificationResult]:
        """Classify a complaint string."""
        if not text:
            return None

        text_lower = text.lower().strip()

        # --- Fast path: exact keyword substring match ---
        for kw, entry in self._keyword_index.items():
            if kw in text_lower:
                return _build_result(entry, kw, 100)

        # --- Fallback: fuzzy match on canonical forms ---
        # partial_token_set_ratio gives 100 when ANY query token appears
        # in the canonical (false-positive risk). Require minimum token overlap
        # of 2 content words to be confident it's a real match.
        best_score = 0
        best_entry: Optional[ThesaurusEntry] = None
        best_canonical: str = ""

        src_tokens = set(text_lower.split())
        MIN_TOKEN_OVERLAP = 2

        for entry in _PHRASE_BANK:
            can_tokens = set(entry.canonical.lower().split())
            overlap = src_tokens & can_tokens
            if len(overlap) < MIN_TOKEN_OVERLAP:
                continue
            score = fuzz.partial_token_set_ratio(text_lower, entry.canonical)
            if score > best_score:
                best_score = score
                best_entry = entry
                best_canonical = entry.canonical

        if best_score >= MATCH_THRESHOLD and best_entry:
            return _build_result(best_entry, best_canonical, best_score)

        return None

    def is_facilities_complaint(self, text: str) -> bool:
        """Return True if text matches any known facilities complaint."""
        return self.classify(text) is not None

    def get_stats(self) -> dict:
        return {
            "total_entries": len(_PHRASE_BANK),
            "total_keywords": TOTAL_PHRASES,
            "categories": len(ComplaintCategory),
            "match_threshold": MATCH_THRESHOLD,
        }


# ----------------------------------------------------------------------------------
# Module-level singleton for use by call_log_handler.py
# ----------------------------------------------------------------------------------
_service: Optional[ThesaurusService] = None


def get_thesaurus() -> ThesaurusService:
    global _service
    if _service is None:
        _service = ThesaurusService()
    return _service


def classify_complaint(text: str) -> Optional[dict]:
    """Convenience wrapper — returns dict or None."""
    result = get_thesaurus().classify(text)
    return result.to_dict() if result else None


def is_facilities(text: str) -> bool:
    """Convenience wrapper — returns bool."""
    return get_thesaurus().is_facilities_complaint(text)
