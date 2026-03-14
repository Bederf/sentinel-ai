"""
Weighted scoring formula for signal correlation (Phase 156-02).

Computes a 5-component weighted score to determine whether two signals
are correlated. Pure logic module — no DB writes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORRELATION_THRESHOLD = 0.55

WEIGHTS = {
    "location": 0.30,
    "entity": 0.25,
    "time": 0.20,
    "type": 0.15,
    "severity": 0.10,
}

# Mapping of location segment match counts to similarity scores
LOCATION_MATCH_SCORES = {
    4: 1.0,  # exact room
    3: 0.85,  # same floor+quadrant
    2: 0.65,  # same building
    1: 0.40,  # same campus
    0: 0.0,  # no match
}

# Bidirectional type compatibility map
TYPE_COMPATIBILITY: dict[tuple[str, str], float] = {
    # Same type = high compatibility
    ("complaint_email", "complaint_email"): 0.90,
    # Complaint + escalation = natural progression
    ("complaint_email", "escalation_email"): 0.95,
    ("complaint_email", "observation_email"): 0.85,
    ("complaint_email", "action_request_email"): 0.90,
    ("complaint_email", "intake_email"): 0.80,
    ("escalation_email", "escalation_email"): 0.85,
    ("escalation_email", "action_request_email"): 0.90,
    ("escalation_email", "intake_email"): 0.85,
    ("escalation_email", "observation_email"): 0.80,
    ("observation_email", "observation_email"): 0.85,
    ("observation_email", "action_request_email"): 0.80,
    ("observation_email", "intake_email"): 0.75,
    ("intake_email", "intake_email"): 0.70,
    ("intake_email", "action_request_email"): 0.80,
    ("action_request_email", "action_request_email"): 0.85,
    # Booking signals
    ("booking_conflict", "booking_no_show"): 0.90,
    ("booking_conflict", "no_show_pattern"): 0.90,
    ("booking_conflict", "complaint_email"): 0.85,
    ("booking_no_show", "no_show_pattern"): 0.95,
    # Resolution contradicts complaint (low — handled by contradiction detector)
    ("resolution_email", "complaint_email"): 0.30,
}

DEFAULT_TYPE_COMPATIBILITY = 0.40

SEVERITY_MAP = {"low": 1, "medium": 2, "high": 3, "critical": 4}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class ScoringResult:
    """Result of scoring a pair of signals for correlation."""

    score: float  # combined weighted score [0.0, 1.0]
    evidence_basis: str  # human-readable explanation of score components
    components: dict  # individual component scores for debugging
    above_threshold: bool  # score >= CORRELATION_THRESHOLD


# ---------------------------------------------------------------------------
# Component scoring functions
# ---------------------------------------------------------------------------


def _location_similarity(loc_a: str, loc_b: str) -> tuple[float, str]:
    """
    Compare two location_ref strings segment by segment.

    Wildcard segments ('*') always match their counterpart.
    Returns (score, label) where label describes the match level.
    """
    segments_a = loc_a.split("/")
    segments_b = loc_b.split("/")

    # Pad shorter list with empty strings
    max_len = max(len(segments_a), len(segments_b), 4)
    while len(segments_a) < max_len:
        segments_a.append("")
    while len(segments_b) < max_len:
        segments_b.append("")

    # Count matching segments (only compare first 4)
    matches = 0
    for i in range(min(4, max_len)):
        sa = segments_a[i].strip()
        sb = segments_b[i].strip()
        if sa == "*" or sb == "*" or sa == sb:
            matches += 1

    labels = {4: "exact", 3: "floor", 2: "building", 1: "campus", 0: "none"}
    score = LOCATION_MATCH_SCORES.get(matches, 0.0)
    label = labels.get(matches, "none")
    return score, label


def _shared_entity_ratio(
    shared_entities: list[str],
    anchor_entity_count: int,
    candidate_entity_count: int,
) -> float:
    """
    Compute ratio of shared entities to max entity count.

    shared_entities is deduplicated by value (case-insensitive).
    """
    if anchor_entity_count == 0 and candidate_entity_count == 0:
        return 0.0

    # Deduplicate case-insensitive
    seen: set[str] = set()
    distinct: list[str] = []
    for e in shared_entities:
        key = e.lower()
        if key not in seen:
            seen.add(key)
            distinct.append(e)

    denominator = max(anchor_entity_count, candidate_entity_count, 1)
    return len(distinct) / denominator


def _time_proximity_score(days_between: float) -> float:
    """Linear decay: 0 days = 1.0, 60+ days = 0.0."""
    return max(0.0, 1.0 - (days_between / 60.0))


def _type_compatibility_score(type_a: str, type_b: str) -> float:
    """Lookup bidirectional type compatibility. Default 0.40 for unlisted pairs."""
    score = TYPE_COMPATIBILITY.get((type_a, type_b))
    if score is not None:
        return score
    score = TYPE_COMPATIBILITY.get((type_b, type_a))
    if score is not None:
        return score
    return DEFAULT_TYPE_COMPATIBILITY


def _severity_alignment_score(sev_a: str, sev_b: str) -> float:
    """Score based on severity distance: same = 1.0, each level apart = -0.25."""
    val_a = SEVERITY_MAP.get(sev_a, 2)
    val_b = SEVERITY_MAP.get(sev_b, 2)
    diff = abs(val_a - val_b)
    return 1.0 - (diff * 0.25)


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def score_signal_pair(
    anchor: dict,
    candidate: dict,
    shared_entities: list[str],
    days_between: float,
    anchor_entity_count: int = 0,
    candidate_entity_count: int = 0,
) -> ScoringResult:
    """
    Score a pair of signals for correlation.

    Parameters
    ----------
    anchor : dict
        Signal dict with keys: id, signal_type, severity, location_ref, etc.
    candidate : dict
        Signal dict with same keys.
    shared_entities : list[str]
        Entity values present in both signals (case-insensitive deduplicated by caller
        or deduplicated internally).
    days_between : float
        Absolute days between the two signals.
    anchor_entity_count : int
        Total entity count for anchor signal.
    candidate_entity_count : int
        Total entity count for candidate signal.

    Returns
    -------
    ScoringResult
    """
    # Component 1: Location similarity
    loc_score, loc_label = _location_similarity(
        anchor.get("location_ref", ""),
        candidate.get("location_ref", ""),
    )

    # Component 2: Shared entity ratio
    entity_score = _shared_entity_ratio(shared_entities, anchor_entity_count, candidate_entity_count)
    # Build entity label
    # Deduplicate for display count
    distinct_count = len({e.lower() for e in shared_entities})
    max_count = max(anchor_entity_count, candidate_entity_count, 1)
    entity_label = f"{distinct_count}/{max_count}"

    # Component 3: Time proximity
    time_score = _time_proximity_score(days_between)

    # Component 4: Type compatibility
    type_score = _type_compatibility_score(
        anchor.get("signal_type", ""),
        candidate.get("signal_type", ""),
    )
    type_label = f"{anchor.get('signal_type', '')}+{candidate.get('signal_type', '')}"

    # Component 5: Severity alignment
    sev_score = _severity_alignment_score(
        anchor.get("severity", "medium"),
        candidate.get("severity", "medium"),
    )
    sev_label = f"{anchor.get('severity', '')}+{candidate.get('severity', '')}"

    components = {
        "location": loc_score,
        "entity": entity_score,
        "time": time_score,
        "type": type_score,
        "severity": sev_score,
    }

    # Final weighted score
    score = sum(WEIGHTS[k] * components[k] for k in WEIGHTS)

    # Evidence basis string
    evidence_basis = (
        f"location={loc_score:.2f}({loc_label}) "
        f"entity={entity_score:.2f}({entity_label}) "
        f"time={time_score:.2f}({days_between:.0f}d) "
        f"type={type_score:.2f}({type_label}) "
        f"severity={sev_score:.2f}({sev_label})"
    )

    return ScoringResult(
        score=round(score, 4),
        evidence_basis=evidence_basis,
        components=components,
        above_threshold=score >= CORRELATION_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# DB helper functions
# ---------------------------------------------------------------------------


def get_shared_entities(conn, signal_a_id: uuid.UUID, signal_b_id: uuid.UUID) -> list[str]:
    """
    Query entity table for entity_value strings present in both signals.

    Returns deduplicated list (case-insensitive matching).
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT lower(e1.entity_value) AS entity_value
            FROM entity e1
            JOIN entity e2 ON lower(e1.entity_value) = lower(e2.entity_value)
            WHERE e1.signal_id = %s AND e2.signal_id = %s
            """,
            (str(signal_a_id), str(signal_b_id)),
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()


def get_entity_count(conn, signal_id: uuid.UUID) -> int:
    """Return count of entities for a signal."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT count(*) FROM entity WHERE signal_id = %s",
            (str(signal_id),),
        )
        row = cur.fetchone()
        return row[0] if row else 0
    finally:
        cur.close()
