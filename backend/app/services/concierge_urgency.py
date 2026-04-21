"""
Concierge urgency scoring — Phase 161-03.

Computes per-room urgency scores based on signal count, severity,
unresolved duration, and repeat frequency. Scores are normalised
to 0.0–1.0 across all rooms for relative comparison.
"""

from __future__ import annotations

from datetime import UTC, datetime

SEVERITY_WEIGHTS: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def compute_urgency_score(
    signal_count: int,
    highest_severity: str,
    oldest_unresolved_at: datetime | None,
    repeat_count: int = 0,
) -> float:
    """Compute raw urgency score for a room based on its active signals.

    Formula::

        urgency = (signal_count * 0.3) + (severity_weight * 0.4)
                + (days_unresolved * 0.2) + (repeat_count * 0.1)

    Returns raw (un-normalised) score.
    """
    severity_weight = SEVERITY_WEIGHTS.get(highest_severity, 1)

    days_unresolved = (datetime.now(UTC) - oldest_unresolved_at).days if oldest_unresolved_at else 0

    raw = signal_count * 0.3 + severity_weight * 0.4 + days_unresolved * 0.2 + repeat_count * 0.1
    return raw


def normalise_urgency_scores(rooms: list[dict]) -> list[dict]:
    """Normalise ``urgency_score`` across all rooms to 0.0–1.0.

    The room with the highest raw score receives 1.0; the lowest
    approaches 0.0.  If all scores are zero the values remain at 0.0.
    """
    scores = [r.get("urgency_score", 0) for r in rooms]
    max_score = max(scores) if scores else 1.0
    if max_score == 0:
        max_score = 1.0
    for room in rooms:
        room["urgency_score"] = round(room.get("urgency_score", 0) / max_score, 3)
    return rooms
