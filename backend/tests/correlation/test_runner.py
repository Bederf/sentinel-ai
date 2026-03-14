"""
Tests for the correlation runner (Phase 156-05).

Validates basic runner behavior: processing signals, idempotency,
cluster creation, and the full pipeline wiring.
"""

from __future__ import annotations

import os

import psycopg2
import psycopg2.extras
import pytest

from app.services.correlation.runner import (
    FIXTURE_SIGNAL_IDS,
    run_all_fixture_signals,
    run_correlation_for_signal,
)

DB_DSN = os.environ.get(
    "CORRELATION_TEST_DSN",
    "postgresql://postgres:postgres@localhost:55322/postgres",
)


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
def run_results(conn):
    """Run all 9 fixture signals and return results list."""
    _cleanup(conn)
    results = run_all_fixture_signals(conn)
    yield results
    # Cleanup after all tests
    _cleanup(conn)


def test_run_all_completes(run_results):
    """run_all_fixture_signals completes without exception and returns 9 results."""
    assert len(run_results) == 9


def test_first_signal_action(run_results):
    """First signal either creates cluster or finds no correlation (no prior signals)."""
    assert run_results[0]["action"] in ("no_correlation", "created_cluster")


def test_later_signals_clustered(run_results):
    """Later signals either create or join a cluster."""
    # At least some of the later signals should be added_to_cluster or created_cluster
    clustered = [r for r in run_results if r["cluster_id"] is not None]
    assert len(clustered) >= 2, "At least 2 signals should be clustered"


def test_all_signals_same_cluster(conn, run_results):
    """All clustered fixture signals end up in the same cluster."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT DISTINCT issue_cluster_id FROM signal WHERE id::text LIKE 'f1000000%%' AND issue_cluster_id IS NOT NULL"
    )
    cluster_ids = [row["issue_cluster_id"] for row in cur.fetchall()]
    cur.close()
    assert len(cluster_ids) == 1, f"Expected 1 cluster, got {len(cluster_ids)}: {cluster_ids}"


def test_cluster_has_multiple_signals(conn, run_results):
    """The cluster should have multiple signals assigned to it."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT signal_count FROM issue_cluster WHERE title LIKE 'Fairlands%%' LIMIT 1")
    row = cur.fetchone()
    cur.close()
    assert row is not None, "No Fairlands cluster found"
    assert row["signal_count"] >= 2


def test_idempotency(conn, run_results):
    """Processing signal 1 again returns 'already_clustered'."""
    sig_1 = FIXTURE_SIGNAL_IDS[0]
    # Check if signal 1 was actually clustered
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT issue_cluster_id FROM signal WHERE id = %s",
        (str(sig_1),),
    )
    row = cur.fetchone()
    cur.close()

    if row and row["issue_cluster_id"] is not None:
        result = run_correlation_for_signal(conn, sig_1)
        assert result["action"] == "already_clustered"
