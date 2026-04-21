"""
Tests for cluster manager (Phase 156-03).

Each test creates and cleans up its own clusters to avoid fixture pollution.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from app.services.correlation.cluster_manager import (
    add_signal_to_cluster,
    create_cluster,
    find_existing_cluster,
    link_entities_to_cluster,
)

DB_DSN = "postgresql://postgres:postgres@localhost:55322/postgres"

# Fixture signal IDs (from 156-01 migration)
SIG_1 = "f1000000-0000-0000-0000-000000000001"
SIG_2 = "f1000000-0000-0000-0000-000000000002"
SIG_3 = "f1000000-0000-0000-0000-000000000003"


@pytest.fixture()
def conn():
    """Provide a DB connection and clean up test clusters after each test."""
    c = psycopg2.connect(DB_DSN)
    created_cluster_ids: list[str] = []

    yield c, created_cluster_ids

    # Cleanup: unassign signals, delete clusters
    cur = c.cursor()
    try:
        for cid in created_cluster_ids:
            cur.execute(
                "UPDATE signal SET issue_cluster_id = NULL WHERE issue_cluster_id = %s",
                (cid,),
            )
            cur.execute(
                "UPDATE entity SET issue_cluster_id = NULL WHERE issue_cluster_id = %s",
                (cid,),
            )
            cur.execute(
                "DELETE FROM relationship WHERE source_id = %s OR target_id = %s",
                (cid, cid),
            )
            # Also delete signal→entity involves edges we created
        # Delete involves edges for fixture signals
        for sig_id in [SIG_1, SIG_2, SIG_3]:
            cur.execute(
                "DELETE FROM relationship WHERE source_id = %s AND edge_type = 'involves'",
                (sig_id,),
            )
        for cid in created_cluster_ids:
            cur.execute("DELETE FROM issue_cluster WHERE id = %s", (cid,))
        c.commit()
    except Exception:
        c.rollback()
    finally:
        cur.close()
        c.close()


def _fetch_signal(c, sig_id: str) -> dict:
    """Helper to fetch a signal row as dict."""
    cur = c.cursor()
    cur.execute(
        "SELECT id, signal_type, severity, location_ref, confidence, created_at FROM signal WHERE id = %s",
        (sig_id,),
    )
    row = cur.fetchone()
    cur.close()
    return {
        "id": row[0],
        "signal_type": row[1],
        "severity": row[2],
        "location_ref": row[3],
        "confidence": float(row[4]),
        "created_at": row[5],
    }


def _fetch_cluster(c, cluster_id) -> dict:
    """Helper to fetch cluster row as dict."""
    cur = c.cursor()
    cur.execute(
        "SELECT id, cluster_state, severity, escalation_level, confidence_score, "
        "signal_count, entity_count, first_seen_at, last_seen_at "
        "FROM issue_cluster WHERE id = %s",
        (str(cluster_id),),
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return {}
    return {
        "id": row[0],
        "cluster_state": row[1],
        "severity": row[2],
        "escalation_level": row[3],
        "confidence_score": float(row[4]),
        "signal_count": row[5],
        "entity_count": row[6],
        "first_seen_at": row[7],
        "last_seen_at": row[8],
    }


class TestCreateCluster:
    def test_creates_emerging_cluster(self, conn):
        c, created = conn
        sig = _fetch_signal(c, SIG_1)

        cluster_id = create_cluster(c, "Test cluster", sig)
        created.append(str(cluster_id))

        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["cluster_state"] == "emerging"
        assert cluster["signal_count"] == 1
        assert cluster["severity"] == "medium"
        assert cluster["escalation_level"] == "operational"
        assert cluster["confidence_score"] == 0.50

    def test_signal_assigned_to_cluster(self, conn):
        c, created = conn
        sig = _fetch_signal(c, SIG_1)

        cluster_id = create_cluster(c, "Test cluster", sig)
        created.append(str(cluster_id))

        cur = c.cursor()
        cur.execute("SELECT issue_cluster_id FROM signal WHERE id = %s", (SIG_1,))
        row = cur.fetchone()
        cur.close()
        assert str(row[0]) == str(cluster_id)

    def test_evidenced_by_edge_created(self, conn):
        c, created = conn
        sig = _fetch_signal(c, SIG_1)

        cluster_id = create_cluster(c, "Test cluster", sig)
        created.append(str(cluster_id))

        cur = c.cursor()
        cur.execute(
            "SELECT edge_type, confidence FROM relationship WHERE source_id = %s AND target_id = %s",
            (str(cluster_id), SIG_1),
        )
        row = cur.fetchone()
        cur.close()
        assert row is not None
        assert row[0] == "evidenced_by"
        assert float(row[1]) == 0.85  # signal 1 confidence


class TestAddSignalToCluster:
    def test_signal_count_incremented(self, conn):
        c, created = conn
        sig1 = _fetch_signal(c, SIG_1)
        sig2 = _fetch_signal(c, SIG_2)

        cluster_id = create_cluster(c, "Test cluster", sig1)
        created.append(str(cluster_id))

        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIG_2), sig2, pairwise_score=0.72)

        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["signal_count"] == 2

    def test_last_seen_at_updated(self, conn):
        c, created = conn
        sig1 = _fetch_signal(c, SIG_1)
        sig2 = _fetch_signal(c, SIG_2)

        cluster_id = create_cluster(c, "Test cluster", sig1)
        created.append(str(cluster_id))

        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIG_2), sig2, pairwise_score=0.72)

        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["last_seen_at"] >= sig2["created_at"]

    def test_severity_upgraded_on_higher_signal(self, conn):
        c, created = conn
        sig1 = _fetch_signal(c, SIG_1)  # medium

        cluster_id = create_cluster(c, "Test cluster", sig1)
        created.append(str(cluster_id))

        # Signal 5 is high severity
        sig5_id = "f1000000-0000-0000-0000-000000000005"
        sig5 = _fetch_signal(c, sig5_id)

        add_signal_to_cluster(c, cluster_id, uuid.UUID(sig5_id), sig5, pairwise_score=0.80)

        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["severity"] == "high"


class TestLinkEntitiesToCluster:
    def test_entities_linked_and_counted(self, conn):
        c, created = conn
        sig1 = _fetch_signal(c, SIG_1)

        cluster_id = create_cluster(c, "Test cluster", sig1)
        created.append(str(cluster_id))

        entity_count = link_entities_to_cluster(c, cluster_id)

        # Signal 1 should have entities (Shaun Grose, FA1-1Q4-MR10, Fairlands 1)
        assert entity_count >= 1

        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["entity_count"] == entity_count

    def test_involves_edges_created(self, conn):
        c, created = conn
        sig1 = _fetch_signal(c, SIG_1)

        cluster_id = create_cluster(c, "Test cluster", sig1)
        created.append(str(cluster_id))

        link_entities_to_cluster(c, cluster_id)

        cur = c.cursor()
        cur.execute(
            "SELECT count(*) FROM relationship WHERE source_id = %s AND edge_type = 'involves'",
            (SIG_1,),
        )
        count = cur.fetchone()[0]
        cur.close()
        assert count >= 1


class TestFindExistingCluster:
    def test_returns_cluster_when_candidate_clustered(self, conn):
        c, created = conn
        sig1 = _fetch_signal(c, SIG_1)

        cluster_id = create_cluster(c, "Test cluster", sig1)
        created.append(str(cluster_id))

        # SIG_1 is now clustered; search with SIG_2 as anchor
        result = find_existing_cluster(
            c,
            uuid.UUID(SIG_2),
            [(uuid.UUID(SIG_1), 0.75)],
        )
        assert result is not None
        assert str(result) == str(cluster_id)

    def test_returns_none_when_no_candidates_clustered(self, conn):
        c, _created = conn

        result = find_existing_cluster(
            c,
            uuid.UUID(SIG_1),
            [(uuid.UUID(SIG_2), 0.75), (uuid.UUID(SIG_3), 0.60)],
        )
        assert result is None

    def test_returns_highest_scoring_cluster(self, conn):
        c, created = conn
        sig1 = _fetch_signal(c, SIG_1)
        sig2 = _fetch_signal(c, SIG_2)

        cluster_a = create_cluster(c, "Cluster A", sig1)
        created.append(str(cluster_a))
        cluster_b = create_cluster(c, "Cluster B", sig2)
        created.append(str(cluster_b))

        # SIG_1 (score 0.60) and SIG_2 (score 0.80) both clustered
        result = find_existing_cluster(
            c,
            uuid.UUID(SIG_3),
            [(uuid.UUID(SIG_2), 0.80), (uuid.UUID(SIG_1), 0.60)],
        )
        assert str(result) == str(cluster_b)
