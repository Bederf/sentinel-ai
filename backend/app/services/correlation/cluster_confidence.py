"""
Cluster confidence computation (Phase 156-03).

5-component weighted formula:
- signal_agreement (0.30): avg pairwise score
- temporal_density (0.25): signals per 7-day window
- entity_connectivity (0.20): unique entities / signal count
- severity_consensus (0.15): inverted std dev of severity
- classification_strength (0.10): top domain confidence
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEIGHTS = {
    "signal_agreement": 0.30,
    "temporal_density": 0.25,
    "entity_connectivity": 0.20,
    "severity_consensus": 0.15,
    "classification_strength": 0.10,
}

SEVERITY_MAP = {"low": 1, "medium": 2, "high": 3, "critical": 4}


# ---------------------------------------------------------------------------
# Component functions
# ---------------------------------------------------------------------------


def _temporal_density(timestamps: list[datetime]) -> float:
    """
    Compute temporal density: fraction of signals with a temporal neighbor
    within 7 days.

    All signals within 7 days -> 1.0.
    Spread evenly over 60 days with no neighbors -> 0.0.
    Signals arriving in bursts (typical of real issues) -> high score.
    """
    if len(timestamps) <= 1:
        return 1.0
    sorted_ts = sorted(timestamps)
    n = len(sorted_ts)
    has_neighbor = 0
    for i, t in enumerate(sorted_ts):
        for j, t2 in enumerate(sorted_ts):
            if i != j:
                diff = abs((t2 - t).total_seconds()) / 86400.0
                if diff <= 7.0:
                    has_neighbor += 1
                    break
    return has_neighbor / n


def _severity_consensus(severities: list[str]) -> float:
    """
    Compute severity consensus: 1.0 - (std_dev / 1.5), clamped to [0, 1].

    All same severity -> 1.0.
    Mixed low+critical -> ~0.0.
    """
    if len(severities) <= 1:
        return 1.0

    values = [SEVERITY_MAP.get(s, 2) for s in severities]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std_dev = math.sqrt(variance)

    return max(0.0, min(1.0, 1.0 - (std_dev / 1.5)))


# ---------------------------------------------------------------------------
# Main confidence function
# ---------------------------------------------------------------------------


def compute_cluster_confidence(
    conn,
    cluster_id: uuid.UUID,
) -> float:
    """
    Compute 5-component cluster confidence and update the cluster.

    Returns the computed confidence score.
    """
    cur = conn.cursor()
    try:
        # ---- Component 1: signal_agreement ----
        # Average confidence from evidenced_by edges
        cur.execute(
            """
            SELECT confidence FROM relationship
            WHERE source_id = %s AND source_type = 'cluster'
              AND edge_type = 'evidenced_by'
            """,
            (str(cluster_id),),
        )
        edge_confidences = [float(row[0]) for row in cur.fetchall()]
        if len(edge_confidences) == 0:
            signal_agreement = 0.50
        elif len(edge_confidences) == 1:
            signal_agreement = edge_confidences[0]
        else:
            signal_agreement = sum(edge_confidences) / len(edge_confidences)

        # ---- Component 2: temporal_density ----
        cur.execute(
            "SELECT created_at FROM signal WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        timestamps = [row[0] for row in cur.fetchall()]
        temporal_density = _temporal_density(timestamps)

        # ---- Component 3: entity_connectivity ----
        cur.execute(
            "SELECT signal_count, entity_count FROM issue_cluster WHERE id = %s",
            (str(cluster_id),),
        )
        row = cur.fetchone()
        signal_count = row[0] if row else 1
        entity_count = row[1] if row else 0

        entity_connectivity = min(entity_count / signal_count, 1.0) if signal_count > 0 else 0.0

        # ---- Component 4: severity_consensus ----
        cur.execute(
            "SELECT severity FROM signal WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        severities = [row[0] for row in cur.fetchall()]
        severity_consensus = _severity_consensus(severities)

        # ---- Component 5: classification_strength ----
        cur.execute(
            "SELECT max(confidence) FROM issue_classification WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        row = cur.fetchone()
        classification_strength = float(row[0]) if row and row[0] is not None else 0.50

        # ---- Final computation ----
        confidence = (
            WEIGHTS["signal_agreement"] * signal_agreement
            + WEIGHTS["temporal_density"] * temporal_density
            + WEIGHTS["entity_connectivity"] * entity_connectivity
            + WEIGHTS["severity_consensus"] * severity_consensus
            + WEIGHTS["classification_strength"] * classification_strength
        )

        # Clamp to [0.0, 0.99]
        confidence = max(0.0, min(0.99, confidence))

        # Round to 2 decimal places for numeric(3,2)
        confidence = round(confidence, 2)

        # Update cluster
        cur.execute(
            "UPDATE issue_cluster SET confidence_score = %s WHERE id = %s",
            (confidence, str(cluster_id)),
        )
        conn.commit()

        return confidence

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
