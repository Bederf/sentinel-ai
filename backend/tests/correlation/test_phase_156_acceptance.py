"""
Phase 156 acceptance tests — comprehensive validation of all BRIEF.md criteria.

Tests both chronological and reverse-chronological signal insertion orders.
"""

from __future__ import annotations

import json
import os
import uuid

import psycopg2
import psycopg2.extras
import pytest

from app.services.correlation.graph import get_cluster_graph
from app.services.correlation.runner import run_all_fixture_signals, run_correlation_for_signal

DB_DSN = os.environ.get(
    "CORRELATION_TEST_DSN",
    "postgresql://postgres:postgres@localhost:55322/postgres",
)

THANDI_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
KERYN_ID = uuid.UUID("10000000-0000-0000-0000-000000000002")
SIGNAL_IDS = [uuid.UUID(f"f1000000-0000-0000-0000-00000000000{i}") for i in range(1, 10)]


def _cleanup(conn):
    """Remove all correlation artifacts from previous test runs."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM dashboard_card WHERE issue_cluster_id IN "
        "(SELECT id FROM issue_cluster WHERE title LIKE 'Fairlands%%')"
    )
    cur.execute(
        "DELETE FROM issue_classification WHERE issue_cluster_id IN "
        "(SELECT id FROM issue_cluster WHERE title LIKE 'Fairlands%%')"
    )
    cur.execute(
        "DELETE FROM relationship WHERE source_id IN "
        "(SELECT id FROM issue_cluster WHERE title LIKE 'Fairlands%%') "
        "OR target_id IN "
        "(SELECT id FROM issue_cluster WHERE title LIKE 'Fairlands%%')"
    )
    cur.execute(
        "DELETE FROM relationship WHERE source_id::text LIKE 'f1000000%%' "
        "OR target_id::text LIKE 'f1000000%%' "
        "OR source_id::text LIKE 'e1000000%%' "
        "OR target_id::text LIKE 'e1000000%%'"
    )
    cur.execute(
        "DELETE FROM issue_evidence WHERE issue_cluster_id IN "
        "(SELECT id FROM issue_cluster WHERE title LIKE 'Fairlands%%')"
    )
    cur.execute(
        "UPDATE entity SET issue_cluster_id = NULL WHERE issue_cluster_id IN "
        "(SELECT id FROM issue_cluster WHERE title LIKE 'Fairlands%%')"
    )
    cur.execute("UPDATE signal SET issue_cluster_id = NULL WHERE id::text LIKE 'f1000000%%'")
    cur.execute("DELETE FROM issue_cluster WHERE title LIKE 'Fairlands%%'")
    cur.close()


@pytest.fixture(scope="module")
def conn():
    connection = psycopg2.connect(DB_DSN)
    connection.autocommit = True
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def cluster_id(conn):
    """Run all 9 fixture signals in chronological order and return the cluster ID."""
    _cleanup(conn)
    results = run_all_fixture_signals(conn)

    # Find the cluster ID from results
    cluster_ids = {r["cluster_id"] for r in results if r["cluster_id"]}
    assert len(cluster_ids) >= 1, "No cluster created"
    cid = cluster_ids.pop()
    return uuid.UUID(cid) if isinstance(cid, str) else cid


# ==========================================================================
# Criterion 1: 9 signals inserted
# ==========================================================================


def test_fixture_signals_exist(conn):
    """9 Fairlands signal fixtures exist in the database."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT count(*) AS cnt FROM signal WHERE id::text LIKE 'f1000000%%'")
    assert cur.fetchone()["cnt"] == 9
    cur.close()


# ==========================================================================
# Criterion 2: Runner completes without exception
# (Tested by cluster_id fixture -- if it fails, all tests fail)
# ==========================================================================


# ==========================================================================
# Criterion 3: Cluster state = escalated
# ==========================================================================


def test_cluster_state_escalated(conn, cluster_id):
    """Cluster reaches escalated state after processing all signals."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT cluster_state FROM issue_cluster WHERE id = %s", (str(cluster_id),))
    row = cur.fetchone()
    cur.close()
    assert row is not None, "Cluster not found"
    assert row["cluster_state"] == "escalated"


# ==========================================================================
# Criterion 4: Cluster severity = high or critical
# ==========================================================================


def test_cluster_severity(conn, cluster_id):
    """Cluster severity is high or critical."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT severity FROM issue_cluster WHERE id = %s", (str(cluster_id),))
    row = cur.fetchone()
    cur.close()
    assert row["severity"] in ("high", "critical")


# ==========================================================================
# Criterion 5: space_optimisation >= 0.90
# ==========================================================================


def test_space_optimisation_classification(conn, cluster_id):
    """space_optimisation classification confidence >= 0.90."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT confidence FROM issue_classification WHERE issue_cluster_id = %s AND domain = 'space_optimisation'",
        (str(cluster_id),),
    )
    row = cur.fetchone()
    cur.close()
    assert row is not None, "space_optimisation classification not found"
    assert float(row["confidence"]) >= 0.90


# ==========================================================================
# Criterion 6: workplace_experience present
# ==========================================================================


def test_workplace_experience_classification(conn, cluster_id):
    """workplace_experience classification is present."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT confidence FROM issue_classification WHERE issue_cluster_id = %s AND domain = 'workplace_experience'",
        (str(cluster_id),),
    )
    row = cur.fetchone()
    cur.close()
    assert row is not None, "workplace_experience classification not found"


# ==========================================================================
# Criterion 7: No hvac or maintenance classifications
# ==========================================================================


def test_no_false_positive_classifications(conn, cluster_id):
    """No hvac or maintenance classifications exist."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT domain FROM issue_classification WHERE issue_cluster_id = %s AND domain IN ('hvac', 'maintenance')",
        (str(cluster_id),),
    )
    row = cur.fetchone()
    cur.close()
    assert row is None, "hvac or maintenance classification should not exist"


# ==========================================================================
# Criterion 8: confidence_score >= 0.75
# ==========================================================================


def test_cluster_confidence(conn, cluster_id):
    """Cluster confidence_score >= 0.75."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT confidence_score FROM issue_cluster WHERE id = %s", (str(cluster_id),))
    row = cur.fetchone()
    cur.close()
    assert float(row["confidence_score"]) >= 0.75


# ==========================================================================
# Criterion 9: 9 evidenced_by edges
# ==========================================================================


def test_evidenced_by_edges(conn, cluster_id):
    """At least 9 evidenced_by relationship edges exist."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT count(*) AS cnt FROM relationship WHERE source_id = %s AND edge_type = 'evidenced_by'",
        (str(cluster_id),),
    )
    row = cur.fetchone()
    cur.close()
    assert row["cnt"] >= 9, f"Expected >= 9 evidenced_by edges, got {row['cnt']}"


# ==========================================================================
# Criterion 10: Entity involves edges for all 13 entities
# ==========================================================================


def test_entity_involves_edges(conn, cluster_id):
    """At least 13 entities are linked to the cluster."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT count(*) AS cnt FROM entity WHERE issue_cluster_id = %s",
        (str(cluster_id),),
    )
    row = cur.fetchone()
    cur.close()
    assert row["cnt"] >= 13, f"Expected >= 13 entities, got {row['cnt']}"


# ==========================================================================
# Criterion 11: Thandi card with concierge role
# ==========================================================================


def test_thandi_card_exists(conn, cluster_id):
    """Thandi receives a dashboard card via concierge role."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT dc.id, dc.card_content FROM dashboard_card dc "
        "WHERE dc.issue_cluster_id = %s AND dc.recipient_role_assignment_id = %s",
        (str(cluster_id), str(THANDI_ID)),
    )
    row = cur.fetchone()
    cur.close()
    assert row is not None, "Thandi dashboard card not found"


# ==========================================================================
# Criterion 12: Thandi NOT in signal recipients
# ==========================================================================


def test_thandi_not_in_signal_recipients(conn):
    """Thandi Dineka is NOT in the recipients of signals 1-7."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, metadata FROM signal WHERE id::text LIKE 'f1000000%%'")
    for row in cur.fetchall():
        metadata = row["metadata"] or {}
        recipients = metadata.get("recipients", [])
        assert "Thandi Dineka" not in recipients, (
            f"Thandi should NOT be in signal {row['id']} recipients but found in {recipients}"
        )
    cur.close()


# ==========================================================================
# Criterion 13: Keryn card with management role
# ==========================================================================


def test_keryn_card_exists(conn, cluster_id):
    """Keryn Norman receives a dashboard card via management role."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT dc.id FROM dashboard_card dc WHERE dc.issue_cluster_id = %s AND dc.recipient_role_assignment_id = %s",
        (str(cluster_id), str(KERYN_ID)),
    )
    row = cur.fetchone()
    cur.close()
    assert row is not None, "Keryn dashboard card not found"


# ==========================================================================
# Criterion 14: Graph API returns >= 10 nodes and >= 9 edges
# ==========================================================================


def test_graph_traversal(conn, cluster_id):
    """Graph traversal returns >= 10 nodes and >= 9 edges."""
    graph = get_cluster_graph(conn, cluster_id)
    assert len(graph["nodes"]) >= 10, f"Expected >= 10 nodes, got {len(graph['nodes'])}"
    assert len(graph["edges"]) >= 9, f"Expected >= 9 edges, got {len(graph['edges'])}"


# ==========================================================================
# Criterion 15: Thandi card has affected_rooms and actions
# ==========================================================================


def test_thandi_card_content(conn, cluster_id):
    """Thandi card contains affected_rooms, recommended_actions, summary."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT dc.card_content FROM dashboard_card dc "
        "WHERE dc.issue_cluster_id = %s AND dc.recipient_role_assignment_id = %s",
        (str(cluster_id), str(THANDI_ID)),
    )
    row = cur.fetchone()
    cur.close()
    assert row is not None
    content = row["card_content"] if isinstance(row["card_content"], dict) else json.loads(row["card_content"])
    assert "affected_rooms" in content
    assert len(content["affected_rooms"]) >= 1
    assert "recommended_actions" in content
    assert len(content["recommended_actions"]) >= 1
    assert "summary" in content


# ==========================================================================
# Bonus: Signal count on cluster
# ==========================================================================


def test_cluster_signal_count(conn, cluster_id):
    """Cluster has >= 9 signals."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT signal_count FROM issue_cluster WHERE id = %s", (str(cluster_id),))
    row = cur.fetchone()
    cur.close()
    count = row["signal_count"]
    assert count >= 9, f"Expected >= 9 signals in cluster, got {count}"


# ==========================================================================
# REVERSE ORDER ACCEPTANCE TESTS
# ==========================================================================


class TestReverseOrderAcceptance:
    """Test that signals processed in reverse chronological order produce the same cluster."""

    @pytest.fixture(scope="class")
    def reverse_cluster_id(self, conn):
        """Process signals 9 down to 1 and return cluster ID."""
        _cleanup(conn)

        # Process in reverse order
        for i in range(9, 0, -1):
            signal_id = uuid.UUID(f"f1000000-0000-0000-0000-00000000000{i}")
            run_correlation_for_signal(conn, signal_id)

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT DISTINCT issue_cluster_id FROM signal "
            "WHERE id::text LIKE 'f1000000%%' AND issue_cluster_id IS NOT NULL"
        )
        rows = cur.fetchall()
        cur.close()
        assert len(rows) >= 1, "No cluster created in reverse order"
        cid = rows[0]["issue_cluster_id"]
        yield cid if isinstance(cid, uuid.UUID) else uuid.UUID(str(cid))
        _cleanup(conn)

    def test_reverse_cluster_state_escalated(self, conn, reverse_cluster_id):
        """Reverse-order cluster reaches escalated state."""
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT cluster_state FROM issue_cluster WHERE id = %s",
            (str(reverse_cluster_id),),
        )
        row = cur.fetchone()
        cur.close()
        assert row["cluster_state"] == "escalated"

    def test_reverse_cluster_signal_count(self, conn, reverse_cluster_id):
        """Reverse-order cluster has >= 9 signals."""
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT signal_count FROM issue_cluster WHERE id = %s",
            (str(reverse_cluster_id),),
        )
        row = cur.fetchone()
        cur.close()
        assert row["signal_count"] >= 9, f"Expected >= 9, got {row['signal_count']}"

    def test_reverse_thandi_card_exists(self, conn, reverse_cluster_id):
        """Reverse-order cluster generates Thandi card."""
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT 1 FROM dashboard_card WHERE issue_cluster_id = %s AND recipient_role_assignment_id = %s",
            (str(reverse_cluster_id), str(THANDI_ID)),
        )
        row = cur.fetchone()
        cur.close()
        assert row is not None, "Thandi card not found in reverse order"

    def test_reverse_space_optimisation(self, conn, reverse_cluster_id):
        """Reverse-order cluster has space_optimisation >= 0.90."""
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT confidence FROM issue_classification WHERE issue_cluster_id = %s AND domain = 'space_optimisation'",
            (str(reverse_cluster_id),),
        )
        row = cur.fetchone()
        cur.close()
        assert row is not None, "space_optimisation not found in reverse order"
        assert float(row["confidence"]) >= 0.90
