"""
Cluster management for the correlation engine (Phase 156-03).

Creates, updates, and merges issue clusters. Tracks signal counts,
entity counts, severity, and relationship edges.
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
SEVERITY_REVERSE = {v: k for k, v in SEVERITY_ORDER.items()}


# ---------------------------------------------------------------------------
# Cluster creation
# ---------------------------------------------------------------------------


def create_cluster(
    conn,
    title: str,
    first_signal: dict,
    severity: str = "medium",
) -> uuid.UUID:
    """
    Create a new issue cluster from the first signal.

    Inserts the cluster, assigns the signal, and creates an evidenced_by
    relationship edge.

    Returns the new cluster UUID.
    """
    sig_severity = first_signal.get("severity", severity)
    sig_id = first_signal["id"]
    sig_created_at = first_signal["created_at"]
    sig_confidence = float(first_signal.get("confidence", 0.50))

    cur = conn.cursor()
    try:
        # 1. Insert cluster
        cur.execute(
            """
            INSERT INTO issue_cluster (
                title, cluster_state, severity, escalation_level,
                confidence_score, first_seen_at, last_seen_at,
                signal_count, entity_count, is_managed
            ) VALUES (
                %s, 'emerging', %s, 'operational',
                0.50, %s, %s,
                1, 0, false
            )
            RETURNING id
            """,
            (title, sig_severity, sig_created_at, sig_created_at),
        )
        cluster_id = cur.fetchone()[0]

        # 2. Assign signal to cluster
        cur.execute(
            "UPDATE signal SET issue_cluster_id = %s WHERE id = %s",
            (str(cluster_id), str(sig_id)),
        )

        # 3. Create evidenced_by relationship edge
        cur.execute(
            """
            INSERT INTO relationship (
                source_id, target_id, source_type, target_type,
                edge_type, confidence, evidence_basis
            ) VALUES (
                %s, %s, 'cluster', 'signal',
                'evidenced_by', %s, %s
            )
            """,
            (
                str(cluster_id),
                str(sig_id),
                min(sig_confidence, 0.99),
                f"first_signal confidence={sig_confidence:.2f}",
            ),
        )

        conn.commit()
        return cluster_id

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Add signal to existing cluster
# ---------------------------------------------------------------------------


def add_signal_to_cluster(
    conn,
    cluster_id: uuid.UUID,
    signal_id: uuid.UUID,
    signal_data: dict,
    pairwise_score: float,
) -> None:
    """
    Add a signal to an existing cluster.

    Updates signal assignment, creates evidenced_by edge, updates cluster
    counts and timestamps, and upgrades severity if needed.
    """
    cur = conn.cursor()
    try:
        # 1. Assign signal to cluster
        cur.execute(
            "UPDATE signal SET issue_cluster_id = %s WHERE id = %s",
            (str(cluster_id), str(signal_id)),
        )

        # 2. Create evidenced_by relationship edge
        cur.execute(
            """
            INSERT INTO relationship (
                source_id, target_id, source_type, target_type,
                edge_type, confidence, evidence_basis
            ) VALUES (
                %s, %s, 'cluster', 'signal',
                'evidenced_by', %s, %s
            )
            """,
            (
                str(cluster_id),
                str(signal_id),
                min(pairwise_score, 0.99),
                f"pairwise_score={pairwise_score:.2f}",
            ),
        )

        # 3. Update cluster counts and timestamps
        sig_created_at = signal_data.get("created_at")
        cur.execute(
            """
            UPDATE issue_cluster SET
                signal_count = signal_count + 1,
                last_seen_at = GREATEST(last_seen_at, %s),
                first_seen_at = LEAST(first_seen_at, %s),
                updated_at = now()
            WHERE id = %s
            """,
            (sig_created_at, sig_created_at, str(cluster_id)),
        )

        # 4. Upgrade severity if new signal is higher
        new_severity = signal_data.get("severity", "medium")
        new_sev_order = SEVERITY_ORDER.get(new_severity, 1)

        cur.execute(
            "SELECT severity FROM issue_cluster WHERE id = %s",
            (str(cluster_id),),
        )
        row = cur.fetchone()
        if row:
            current_sev_order = SEVERITY_ORDER.get(row[0], 1)
            if new_sev_order > current_sev_order:
                cur.execute(
                    "UPDATE issue_cluster SET severity = %s WHERE id = %s",
                    (new_severity, str(cluster_id)),
                )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Link entities to cluster
# ---------------------------------------------------------------------------


def link_entities_to_cluster(conn, cluster_id: uuid.UUID) -> int:
    """
    Link all entities from signals in a cluster to that cluster.

    Creates involves relationship edges and updates entity_count.
    Returns the entity count.
    """
    cur = conn.cursor()
    try:
        # 1. Get all signal IDs in the cluster
        cur.execute(
            "SELECT id FROM signal WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        signal_ids = [row[0] for row in cur.fetchall()]
        if not signal_ids:
            return 0

        # 2. Get all entities for those signals
        placeholders = ",".join(["%s"] * len(signal_ids))
        cur.execute(
            f"SELECT id, signal_id FROM entity WHERE signal_id IN ({placeholders})",
            [str(sid) for sid in signal_ids],
        )
        entities = cur.fetchall()

        # 3. Update entities to point to the cluster
        if entities:
            entity_ids = [str(e[0]) for e in entities]
            e_placeholders = ",".join(["%s"] * len(entity_ids))
            cur.execute(
                f"""
                UPDATE entity SET issue_cluster_id = %s
                WHERE id IN ({e_placeholders})
                  AND (issue_cluster_id IS NULL OR issue_cluster_id != %s)
                """,
                [str(cluster_id)] + entity_ids + [str(cluster_id)],
            )

        # 4. Create involves edges (signal → entity), skip duplicates
        for entity_id, signal_id in entities:
            # Check if edge already exists
            cur.execute(
                """
                SELECT 1 FROM relationship
                WHERE source_id = %s AND target_id = %s AND edge_type = 'involves'
                LIMIT 1
                """,
                (str(signal_id), str(entity_id)),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO relationship (
                        source_id, target_id, source_type, target_type,
                        edge_type, confidence
                    ) VALUES (
                        %s, %s, 'signal', 'entity',
                        'involves', 0.90
                    )
                    """,
                    (str(signal_id), str(entity_id)),
                )

        # 5. Update entity_count on cluster
        cur.execute(
            """
            SELECT count(DISTINCT id) FROM entity
            WHERE issue_cluster_id = %s
            """,
            (str(cluster_id),),
        )
        entity_count = cur.fetchone()[0]
        cur.execute(
            "UPDATE issue_cluster SET entity_count = %s WHERE id = %s",
            (entity_count, str(cluster_id)),
        )

        conn.commit()
        return entity_count

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Find existing cluster for a signal
# ---------------------------------------------------------------------------


def find_existing_cluster(
    conn,
    signal_id: uuid.UUID,
    scored_pairs: list[tuple[uuid.UUID, float]],
) -> uuid.UUID | None:
    """
    Check if any scored candidate signals already belong to a cluster.

    Returns the cluster_id of the best-scoring candidate that is already
    clustered, or None if no candidates are clustered.
    """
    if not scored_pairs:
        return None

    # Sort by score descending
    sorted_pairs = sorted(scored_pairs, key=lambda x: x[1], reverse=True)

    cur = conn.cursor()
    try:
        for candidate_id, _score in sorted_pairs:
            cur.execute(
                "SELECT issue_cluster_id FROM signal WHERE id = %s AND issue_cluster_id IS NOT NULL",
                (str(candidate_id),),
            )
            row = cur.fetchone()
            if row:
                return row[0]
        return None
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Merge clusters
# ---------------------------------------------------------------------------


def merge_clusters(
    conn,
    keep_id: uuid.UUID,
    absorb_id: uuid.UUID,
) -> None:
    """
    Merge absorb_id cluster into keep_id cluster.

    Moves signals, entities, evidence, and relationship edges.
    Deletes the absorbed cluster.
    """
    cur = conn.cursor()
    try:
        # 1. Move all signals
        cur.execute(
            "UPDATE signal SET issue_cluster_id = %s WHERE issue_cluster_id = %s",
            (str(keep_id), str(absorb_id)),
        )

        # 2. Move all entities
        cur.execute(
            "UPDATE entity SET issue_cluster_id = %s WHERE issue_cluster_id = %s",
            (str(keep_id), str(absorb_id)),
        )

        # 3. Move issue_evidence
        cur.execute(
            "UPDATE issue_evidence SET issue_cluster_id = %s WHERE issue_cluster_id = %s",
            (str(keep_id), str(absorb_id)),
        )

        # 4. Move relationship edges: update source_id references
        cur.execute(
            """
            UPDATE relationship SET source_id = %s
            WHERE source_id = %s AND source_type = 'cluster'
            """,
            (str(keep_id), str(absorb_id)),
        )
        cur.execute(
            """
            UPDATE relationship SET target_id = %s
            WHERE target_id = %s AND target_type = 'cluster'
            """,
            (str(keep_id), str(absorb_id)),
        )

        # 5. Recalculate counts on keep cluster
        cur.execute(
            """
            UPDATE issue_cluster SET
                signal_count = (SELECT count(*) FROM signal WHERE issue_cluster_id = %s),
                entity_count = (SELECT count(DISTINCT id) FROM entity WHERE issue_cluster_id = %s),
                first_seen_at = COALESCE(
                    (SELECT min(created_at) FROM signal WHERE issue_cluster_id = %s),
                    first_seen_at
                ),
                last_seen_at = COALESCE(
                    (SELECT max(created_at) FROM signal WHERE issue_cluster_id = %s),
                    last_seen_at
                ),
                updated_at = now()
            WHERE id = %s
            """,
            (str(keep_id), str(keep_id), str(keep_id), str(keep_id), str(keep_id)),
        )

        # 6. Upgrade severity of keep cluster if absorb was higher
        cur.execute(
            "SELECT severity FROM issue_cluster WHERE id = %s",
            (str(absorb_id),),
        )
        absorb_row = cur.fetchone()
        if absorb_row:
            absorb_sev = SEVERITY_ORDER.get(absorb_row[0], 1)
            cur.execute(
                "SELECT severity FROM issue_cluster WHERE id = %s",
                (str(keep_id),),
            )
            keep_row = cur.fetchone()
            if keep_row:
                keep_sev = SEVERITY_ORDER.get(keep_row[0], 1)
                if absorb_sev > keep_sev:
                    cur.execute(
                        "UPDATE issue_cluster SET severity = %s WHERE id = %s",
                        (absorb_row[0], str(keep_id)),
                    )

        # 7. Delete absorbed cluster (CASCADE handles classifications, dashboard_cards)
        cur.execute(
            "DELETE FROM issue_cluster WHERE id = %s",
            (str(absorb_id),),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
