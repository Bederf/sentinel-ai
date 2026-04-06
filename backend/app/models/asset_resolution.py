"""
Phase 180: Asset ID Resolver — core models.

ResolutionMethod  — how the asset was resolved (EXACT, FUZZY, LLM_ASSISTED, UNRESOLVED)
ResolutionConfidence — band derived from the raw score (HIGH > 0.85, MEDIUM 0.60-0.85, LOW < 0.60)
ResolutionResult  — immutable result dataclass returned by AssetIDResolver.resolve()
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ResolutionMethod(str, Enum):
    """
    How the asset ID was matched.

    EXACT       — alias or code matched exactly (case-insensitive, normalised).
    FUZZY       — rapidfuzz token_set_ratio score >= 0.60.
    LLM_ASSISTED — Stage 4 (Wave 2), not yet implemented.
    UNRESOLVED  — no match found at any stage.
    """

    EXACT = "exact"
    FUZZY = "fuzzy"
    LLM_ASSISTED = "llm_assisted"
    UNRESOLVED = "unresolved"


class ResolutionConfidence(str, Enum):
    """
    Confidence band derived from the raw fuzzy score.

    HIGH   — score >= 0.85  (exact match falls here too)
    MEDIUM — 0.60 <= score < 0.85
    LOW    — score < 0.60   (or unresolvable)
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """
    Immutable result of AssetIDResolver.resolve().

    Attributes
    ----------
    asset_id : str | None
        Resolved SENTINEL equipment code (e.g. "S002-CHILLER-B1-001").
        None when method is UNRESOLVED.
    confidence : float
        Raw score 0.0-1.0.  1.0 for EXACT matches.  None for UNRESOLVED.
    confidence_band : ResolutionConfidence
        HIGH / MEDIUM / LOW derived from confidence.
    method : ResolutionMethod
        Which stage produced the match.
    matched_on : str | None
        Which field triggered the match (e.g. "code", "display_name", "alias").
        None when UNRESOLVED.
    needs_review : bool
        True when confidence_band is MEDIUM or LOW — human review required.
    review_reason : str | None
        Human-readable reason for review flag, or None.
    """

    asset_id: Optional[str]
    confidence: float
    confidence_band: ResolutionConfidence
    method: ResolutionMethod
    matched_on: Optional[str]
    needs_review: bool
    review_reason: Optional[str]
