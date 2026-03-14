"""
Correlation runner — single entry point for the correlation pipeline (Phase 156-05).

Wires all components: candidates -> score -> cluster -> state machine ->
classify -> compute_confidence -> route -> cards.

CRITICAL ordering: classify BEFORE compute_confidence (classification_strength
component requires classifications to exist).
"""

from __future__ import annotations

import uuid

import psycopg2.extras

from app.services.correlation.candidate_generator import get_candidates
from app.services.correlation.card_generator import generate_cards
from app.services.correlation.classification import classify_cluster
from app.services.correlation.cluster_confidence import compute_cluster_confidence
from app.services.correlation.cluster_manager import (
    add_signal_to_cluster,
    create_cluster,
    find_existing_cluster,
    link_entities_to_cluster,
)
from app.services.correlation.contradiction_detector import (
    apply_contradiction_penalty,
    detect_contradiction,
)
from app.services.correlation.routing import get_routing_targets
from app.services.correlation.scoring import (
    CORRELATION_THRESHOLD,
    get_entity_count,
    get_shared_entities,
    score_signal_pair,
)
from app.services.correlation.state_machine import (
    evaluate_state_transition,
    update_escalation_level,
)
from app.services.correlation.time_decay import compute_days_elapsed

# ---------------------------------------------------------------------------
# Fixture signal IDs (for convenience testing)
# ---------------------------------------------------------------------------

FIXTURE_SIGNAL_IDS = [uuid.UUID(f"f1000000-0000-0000-0000-00000000000{i}") for i in range(1, 10)]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _fetch_signal(conn, signal_id: uuid.UUID) -> dict | None:
    """Fetch a signal row as a dict."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, signal_type, severity, confidence, location_ref,
                   created_at, metadata, raw_content, issue_cluster_id,
                   resolution_state
            FROM signal WHERE id = %s
            """,
            (str(signal_id),),
        )
        return cur.fetchone()
    finally:
        cur.close()


def _fetch_cluster_signals(conn, cluster_id: uuid.UUID) -> list[dict]:
    """Fetch all signals in a cluster."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, signal_type, severity, confidence, location_ref,
                   created_at, metadata
            FROM signal WHERE issue_cluster_id = %s
            ORDER BY created_at ASC
            """,
            (str(cluster_id),),
        )
        return cur.fetchall()
    finally:
        cur.close()


def _generate_cluster_title(conn, signal_a_id: uuid.UUID, signal_b_id: uuid.UUID) -> str:
    """Generate a cluster title from the first two correlated signals."""
    a = _fetch_signal(conn, signal_a_id)
    b = _fetch_signal(conn, signal_b_id)
    if not a or not b:
        return "Untitled cluster"

    campus = a["location_ref"].split("/")[0]
    types = sorted({a["signal_type"], b["signal_type"]})
    if any("complaint" in t or "escalation" in t for t in types):
        return f"{campus} meeting room availability conflict"
    return f"{campus} issue cluster"


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_correlation_for_signal(conn, signal_id: uuid.UUID) -> dict:
    """
    Process a single signal through the entire correlation pipeline.

    Returns a summary dict with action taken and result details.
    """
    # 1. Fetch the anchor signal
    anchor = _fetch_signal(conn, signal_id)
    if anchor is None:
        raise ValueError(f"Signal {signal_id} not found")

    # 2. Idempotency: if signal already belongs to a cluster, skip
    if anchor["issue_cluster_id"] is not None:
        return {
            "signal_id": str(signal_id),
            "action": "already_clustered",
            "cluster_id": str(anchor["issue_cluster_id"]),
            "cluster_state": None,
            "classifications": None,
            "cards_generated": 0,
            "confidence": None,
        }

    # 3. Get candidates
    candidates = get_candidates(conn, signal_id)

    # 4. Score each candidate against the anchor
    scored_pairs: list[tuple[uuid.UUID, float]] = []
    for candidate in candidates:
        # Compute days between anchor and candidate
        anchor_created = anchor["created_at"]
        candidate_created = candidate.created_at
        days_between = abs(compute_days_elapsed(candidate_created, anchor_created))

        # Get shared entities
        shared = get_shared_entities(conn, signal_id, candidate.id)

        # Get entity counts
        anchor_entity_count = get_entity_count(conn, signal_id)
        candidate_entity_count = get_entity_count(conn, candidate.id)

        # Build dicts for scoring
        anchor_dict = {
            "id": anchor["id"],
            "signal_type": anchor["signal_type"],
            "severity": anchor["severity"],
            "location_ref": anchor["location_ref"],
            "created_at": anchor["created_at"],
            "metadata": anchor["metadata"],
        }
        candidate_dict = {
            "id": candidate.id,
            "signal_type": candidate.signal_type,
            "severity": candidate.severity,
            "location_ref": candidate.location_ref,
            "created_at": candidate.created_at,
            "metadata": candidate.metadata,
        }
        result = score_signal_pair(
            anchor_dict,
            candidate_dict,
            shared,
            days_between,
            anchor_entity_count,
            candidate_entity_count,
        )

        # Check for contradictions
        contradiction = detect_contradiction(anchor["signal_type"], candidate.signal_type)
        final_score = apply_contradiction_penalty(result.score, contradiction)

        if final_score >= CORRELATION_THRESHOLD:
            scored_pairs.append((candidate.id, final_score))

    # 5. If no correlations found, no clustering
    if not scored_pairs:
        return {
            "signal_id": str(signal_id),
            "action": "no_correlation",
            "cluster_id": None,
            "cluster_state": None,
            "classifications": None,
            "cards_generated": 0,
            "confidence": None,
        }

    # 6. Check if any candidate already belongs to a cluster
    existing_cluster_id = find_existing_cluster(conn, signal_id, scored_pairs)

    if existing_cluster_id:
        # Add to existing cluster
        best_score = max(s for _, s in scored_pairs)
        add_signal_to_cluster(conn, existing_cluster_id, signal_id, anchor, best_score)
        cluster_id = existing_cluster_id
        action = "added_to_cluster"
    else:
        # Create new cluster
        best_candidate_id, best_score = max(scored_pairs, key=lambda x: x[1])
        title = _generate_cluster_title(conn, signal_id, best_candidate_id)
        cluster_id = create_cluster(conn, title, anchor)
        # Add the best candidate too
        best_candidate_data = _fetch_signal(conn, best_candidate_id)
        if best_candidate_data:
            add_signal_to_cluster(conn, cluster_id, best_candidate_id, best_candidate_data, best_score)
        # Add remaining above-threshold candidates
        for cand_id, score in scored_pairs:
            if cand_id != best_candidate_id:
                cand_data = _fetch_signal(conn, cand_id)
                if cand_data and cand_data["issue_cluster_id"] is None:
                    add_signal_to_cluster(conn, cluster_id, cand_id, cand_data, score)
        action = "created_cluster"

    # 7. Link entities to cluster
    link_entities_to_cluster(conn, cluster_id)

    # 8. Evaluate state machine
    new_state, transition = evaluate_state_transition(conn, cluster_id)

    # 9. Update escalation level
    cluster_signals = _fetch_cluster_signals(conn, cluster_id)
    update_escalation_level(conn, cluster_id, cluster_signals)

    # 10. Classify cluster (MUST happen before confidence computation)
    classifications = classify_cluster(conn, cluster_id)

    # 11. Compute cluster confidence (MUST happen after classification)
    confidence = compute_cluster_confidence(conn, cluster_id)

    # 12. Route and generate cards
    targets = get_routing_targets(conn, cluster_id)
    card_ids = generate_cards(conn, cluster_id, targets)

    return {
        "signal_id": str(signal_id),
        "action": action,
        "cluster_id": str(cluster_id),
        "cluster_state": new_state,
        "classifications": classifications,
        "cards_generated": len(card_ids),
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Convenience: run all fixture signals
# ---------------------------------------------------------------------------


def run_all_fixture_signals(conn) -> list[dict]:
    """Process all 9 fixture signals in chronological order."""
    results = []
    for signal_id in FIXTURE_SIGNAL_IDS:
        result = run_correlation_for_signal(conn, signal_id)
        results.append(result)
    return results
