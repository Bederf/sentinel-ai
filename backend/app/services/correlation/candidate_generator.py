"""
Candidate generation service for the correlation engine.

Queries signals within the same campus and time window to produce
a list of candidates for pairwise scoring against an anchor signal.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

import psycopg2.extras

DEFAULT_TIME_WINDOW_DAYS = 30
EXCLUDED_STATES = ("resolved", "suppressed")


@dataclass
class CandidateSignal:
    """A signal retrieved as a candidate for correlation scoring."""

    id: uuid.UUID
    signal_type: str
    severity: str
    confidence: Decimal
    location_ref: str
    created_at: datetime
    metadata: dict
    raw_content: Optional[str] = None


def get_candidates(
    conn,
    anchor_signal_id: uuid.UUID,
    time_window_days: int = DEFAULT_TIME_WINDOW_DAYS,
) -> list[CandidateSignal]:
    """Return candidate signals for correlation with the anchor signal.

    Candidates are signals that:
    - Share the same campus prefix (first segment of location_ref)
    - Fall within ±time_window_days of the anchor signal's created_at
    - Are not in resolved or suppressed state
    - Are not the anchor signal itself

    Args:
        conn: psycopg2 connection object.
        anchor_signal_id: UUID of the anchor signal.
        time_window_days: Maximum age difference in days (default 30).

    Returns:
        List of CandidateSignal objects.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Step 1: Fetch anchor signal's location_ref and created_at
        cur.execute(
            "SELECT location_ref, created_at FROM signal WHERE id = %s",
            (str(anchor_signal_id),),
        )
        anchor = cur.fetchone()
        if anchor is None:
            return []

        # Step 2: Extract campus prefix (first segment before '/')
        location_ref = anchor["location_ref"]
        campus = location_ref.split("/")[0] if "/" in location_ref else location_ref
        campus_pattern = f"{campus}/%"

        anchor_created_at = anchor["created_at"]

        # Step 3: Query candidates
        cur.execute(
            """
            SELECT id, signal_type, severity, confidence, location_ref,
                   created_at, metadata, raw_content
            FROM signal
            WHERE location_ref LIKE %s
              AND created_at BETWEEN %s - make_interval(days := %s)
                                  AND %s + make_interval(days := %s)
              AND resolution_state NOT IN %s
              AND id != %s
            ORDER BY created_at ASC
            """,
            (
                campus_pattern,
                anchor_created_at,
                time_window_days,
                anchor_created_at,
                time_window_days,
                EXCLUDED_STATES,
                str(anchor_signal_id),
            ),
        )

        rows = cur.fetchall()

    return [
        CandidateSignal(
            id=uuid.UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
            signal_type=row["signal_type"],
            severity=row["severity"],
            confidence=row["confidence"],
            location_ref=row["location_ref"],
            created_at=row["created_at"],
            metadata=row["metadata"],
            raw_content=row["raw_content"],
        )
        for row in rows
    ]
