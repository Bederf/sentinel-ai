"""
Classification service for the correlation engine (Phase 156-04).

Maps signal types to classification domains via a vote aggregation system.
Each signal type votes for one or more domains with weighted confidence.
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Domain Vote Map — signal types vote for classification domains
# ---------------------------------------------------------------------------

DOMAIN_VOTE_MAP: dict[str, list[tuple[str, float]]] = {
    # Email signal types
    "complaint_email": [
        ("space_optimisation", 0.90),
        ("workplace_experience", 0.80),
    ],
    "escalation_email": [
        ("space_optimisation", 0.95),
        ("workplace_experience", 0.75),
    ],
    "observation_email": [
        ("space_optimisation", 0.95),
        ("workplace_experience", 0.70),
    ],
    "intake_email": [
        ("space_optimisation", 0.80),
        ("workplace_experience", 0.60),
    ],
    "action_request_email": [
        ("space_optimisation", 0.98),
        ("workplace_experience", 0.70),
    ],
    "resolution_email": [
        ("space_optimisation", 0.40),
        ("workplace_experience", 0.50),
    ],
    # Booking signal types
    "booking_conflict": [
        ("space_optimisation", 0.95),
        ("workplace_experience", 0.60),
    ],
    "booking_no_show": [
        ("space_optimisation", 0.90),
        ("workplace_experience", 0.50),
    ],
    "booking_saturation": [
        ("space_optimisation", 0.95),
        ("workplace_experience", 0.70),
    ],
    "booking_underutilisation": [
        ("space_optimisation", 0.90),
        ("workplace_experience", 0.40),
    ],
    "no_show_pattern": [
        ("space_optimisation", 0.90),
        ("workplace_experience", 0.50),
    ],
    "fragmented_usage": [
        ("space_optimisation", 0.85),
        ("workplace_experience", 0.40),
    ],
    "shadow_scheduling": [
        ("space_optimisation", 0.95),
        ("workplace_experience", 0.50),
    ],
    # HVAC signal types
    "hvac_fault": [
        ("hvac", 0.95),
        ("maintenance", 0.80),
    ],
    "hvac_setpoint_deviation": [
        ("hvac", 0.90),
        ("workplace_experience", 0.60),
    ],
    "hvac_efficiency_drop": [
        ("hvac", 0.85),
        ("energy", 0.70),
    ],
    # Maintenance signal types
    "maintenance_request": [
        ("maintenance", 0.95),
        ("workplace_experience", 0.50),
    ],
    "maintenance_completed": [
        ("maintenance", 0.90),
    ],
    "maintenance_overdue": [
        ("maintenance", 0.95),
        ("compliance", 0.60),
    ],
    # Energy signal types
    "energy_spike": [
        ("energy", 0.90),
    ],
    "energy_anomaly": [
        ("energy", 0.95),
    ],
    # Security signal types
    "security_alert": [
        ("security", 0.95),
        ("compliance", 0.50),
    ],
    "security_resolved": [
        ("security", 0.80),
    ],
    # Occupancy signal types
    "occupancy_anomaly": [
        ("space_optimisation", 0.80),
        ("workplace_experience", 0.60),
    ],
    "occupancy_normal": [],  # No domain vote
    "occupancy_trend": [
        ("space_optimisation", 0.70),
    ],
    # Misc signal types
    "manual_observation": [
        ("workplace_experience", 0.50),
    ],
    "external_event": [],  # No domain vote
    "information_email": [
        ("workplace_experience", 0.50),
    ],
}

NOISE_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_cluster(conn, cluster_id: uuid.UUID) -> list[dict]:
    """
    Classify a cluster by aggregating domain votes from its signals.

    For each signal in the cluster, looks up its signal_type in DOMAIN_VOTE_MAP
    and tallies votes per domain. Computes confidence as:
        confidence = (vote_count / max_possible_votes) * avg_weight

    Upserts results into issue_classification table.

    Returns list of {"domain": str, "confidence": float} sorted by confidence DESC.
    """
    cur = conn.cursor()
    try:
        # 1. Fetch all signal types in the cluster
        cur.execute(
            "SELECT signal_type FROM signal WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        signal_types = [row[0] for row in cur.fetchall()]

        if not signal_types:
            return []

        max_possible_votes = len(signal_types)

        # 2. Aggregate votes per domain
        domain_votes: dict[str, list[float]] = {}
        for sig_type in signal_types:
            votes = DOMAIN_VOTE_MAP.get(sig_type, [])
            for domain, weight in votes:
                domain_votes.setdefault(domain, []).append(weight)

        # 3. Compute confidence per domain
        results: list[dict] = []
        for domain, weights in domain_votes.items():
            vote_count = len(weights)
            total_weight = sum(weights)
            avg_weight = total_weight / vote_count
            confidence = (vote_count / max_possible_votes) * avg_weight
            confidence = max(0.0, min(confidence, 0.99))  # clamp

            if confidence < NOISE_THRESHOLD:
                continue

            results.append({"domain": domain, "confidence": round(confidence, 2)})

        # Sort by confidence descending
        results.sort(key=lambda x: x["confidence"], reverse=True)

        # 4. Upsert into issue_classification
        for item in results:
            cur.execute(
                """
                INSERT INTO issue_classification (issue_cluster_id, domain, confidence)
                VALUES (%s, %s, %s)
                ON CONFLICT (issue_cluster_id, domain)
                DO UPDATE SET confidence = EXCLUDED.confidence, classified_at = now()
                """,
                (str(cluster_id), item["domain"], item["confidence"]),
            )

        conn.commit()
        return results

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
