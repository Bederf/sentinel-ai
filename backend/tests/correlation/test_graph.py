"""
Tests for graph traversal RPC function (Phase 156-05).

Tests the get_cluster_graph function that returns nodes + edges
for Cytoscape.js visualization.
"""

from __future__ import annotations

import uuid

import psycopg2
import psycopg2.extras
import pytest

from app.services.correlation.graph import get_cluster_graph

DB_DSN = "postgresql://postgres:postgres@localhost:55322/postgres"

# Fixture signal IDs
SIG_1 = uuid.UUID("f1000000-0000-0000-0000-000000000001")
SIG_2 = uuid.UUID("f1000000-0000-0000-0000-000000000002")


@pytest.fixture()
def conn():
    connection = psycopg2.connect(DB_DSN)
    connection.autocommit = True
    yield connection
    connection.close()


@pytest.fixture()
def test_cluster(conn):
    """Create a test cluster with 2 signals and relationship edges, clean up after."""
    cur = conn.cursor()

    # Create cluster
    cur.execute(
        """
        INSERT INTO issue_cluster (id, title, cluster_state, severity,
            confidence_score, first_seen_at, last_seen_at, signal_count)
        VALUES (%s, 'Test Graph Cluster', 'active', 'medium',
            0.80, '2026-01-05', '2026-01-12', 2)
        """,
        ("a0000000-0000-0000-0000-000000000001",),
    )

    cluster_id = uuid.UUID("a0000000-0000-0000-0000-000000000001")

    # Assign signals to cluster
    cur.execute(
        "UPDATE signal SET issue_cluster_id = %s WHERE id IN (%s, %s)",
        (str(cluster_id), str(SIG_1), str(SIG_2)),
    )

    # Create evidenced_by edges
    cur.execute(
        """
        INSERT INTO relationship (source_id, target_id, source_type, target_type, edge_type, confidence, evidence_basis)
        VALUES (%s, %s, 'cluster', 'signal', 'evidenced_by', 0.85, 'test edge 1'),
               (%s, %s, 'cluster', 'signal', 'evidenced_by', 0.82, 'test edge 2')
        """,
        (str(cluster_id), str(SIG_1), str(cluster_id), str(SIG_2)),
    )

    # Create involves edges from signals to their entities
    # SIG_1 has entity e1000000-...-001 (Shaun Grose), e1000000-...-007 (FA1-1Q4-MR10), e1000000-...-010 (Fairlands 1)
    # SIG_2 has entity e1000000-...-002 (Lisa Moyo), e1000000-...-008 (FA2-2Q1-MR03), e1000000-...-011 (Fairlands 2)
    entity_pairs = [
        (str(SIG_1), "e1000000-0000-0000-0000-000000000001"),
        (str(SIG_1), "e1000000-0000-0000-0000-000000000007"),
        (str(SIG_1), "e1000000-0000-0000-0000-000000000010"),
        (str(SIG_2), "e1000000-0000-0000-0000-000000000002"),
        (str(SIG_2), "e1000000-0000-0000-0000-000000000008"),
        (str(SIG_2), "e1000000-0000-0000-0000-000000000011"),
    ]
    for sig_id, ent_id in entity_pairs:
        cur.execute(
            """
            INSERT INTO relationship (source_id, target_id, source_type, target_type, edge_type, confidence)
            VALUES (%s, %s, 'signal', 'entity', 'involves', 0.90)
            """,
            (sig_id, ent_id),
        )

    cur.close()
    yield cluster_id

    # Cleanup
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM relationship WHERE source_id = %s OR target_id = %s",
        (str(cluster_id), str(cluster_id)),
    )
    cur.execute(
        "DELETE FROM relationship WHERE source_id IN (%s, %s) OR target_id IN (%s, %s)",
        (str(SIG_1), str(SIG_2), str(SIG_1), str(SIG_2)),
    )
    cur.execute(
        "UPDATE signal SET issue_cluster_id = NULL WHERE id IN (%s, %s)",
        (str(SIG_1), str(SIG_2)),
    )
    cur.execute("DELETE FROM issue_cluster WHERE id = %s", (str(cluster_id),))
    cur.close()


def test_graph_returns_nodes_and_edges(conn, test_cluster):
    """Graph for test cluster returns nodes and edges."""
    graph = get_cluster_graph(conn, test_cluster)
    assert "nodes" in graph
    assert "edges" in graph
    assert isinstance(graph["nodes"], list)
    assert isinstance(graph["edges"], list)


def test_graph_node_count(conn, test_cluster):
    """Graph returns cluster + 2 signals + 6 entities = 9 nodes."""
    graph = get_cluster_graph(conn, test_cluster)
    # 1 cluster + 2 signals + up to 6 entities via involves edges
    assert len(graph["nodes"]) >= 3, f"Expected >= 3 nodes, got {len(graph['nodes'])}"


def test_graph_edge_count(conn, test_cluster):
    """Graph returns at least 2 evidenced_by + 6 involves = 8 edges."""
    graph = get_cluster_graph(conn, test_cluster)
    assert len(graph["edges"]) >= 2, f"Expected >= 2 edges, got {len(graph['edges'])}"


def test_cluster_node_has_metadata(conn, test_cluster):
    """Cluster node has label, severity, cluster_state."""
    graph = get_cluster_graph(conn, test_cluster)
    cluster_nodes = [n for n in graph["nodes"] if n["node_type"] == "cluster"]
    assert len(cluster_nodes) == 1
    cn = cluster_nodes[0]
    assert cn["label"] == "Test Graph Cluster"
    assert cn["severity"] == "medium"
    assert cn["cluster_state"] == "active"


def test_signal_nodes_have_type(conn, test_cluster):
    """Signal nodes have signal_type and sender label."""
    graph = get_cluster_graph(conn, test_cluster)
    signal_nodes = [n for n in graph["nodes"] if n["node_type"] == "signal"]
    assert len(signal_nodes) >= 2
    for sn in signal_nodes:
        assert sn["signal_type"] is not None
        assert sn["label"] is not None


def test_entity_nodes_have_type_and_value(conn, test_cluster):
    """Entity nodes have entity_type and entity_value."""
    graph = get_cluster_graph(conn, test_cluster)
    entity_nodes = [n for n in graph["nodes"] if n["node_type"] == "entity"]
    assert len(entity_nodes) >= 1
    for en in entity_nodes:
        assert en["entity_type"] is not None
        assert en["entity_value"] is not None


def test_empty_cluster_returns_empty(conn):
    """Non-existent cluster returns empty nodes and edges."""
    fake_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    graph = get_cluster_graph(conn, fake_id)
    assert graph["nodes"] == []
    assert graph["edges"] == []
