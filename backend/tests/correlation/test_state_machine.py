"""
Tests for state machine (Phase 156-03).

Tests the Fairlands progression by adding signals one by one and
verifying state transitions after each addition.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from app.services.correlation.cluster_manager import (
    add_signal_to_cluster,
    create_cluster,
)
from app.services.correlation.state_machine import (
    evaluate_state_transition,
)

DB_DSN = "postgresql://postgres:postgres@localhost:55322/postgres"

# Fixture signal IDs
SIGNAL_IDS = [f"f1000000-0000-0000-0000-00000000000{i}" for i in range(1, 10)]


@pytest.fixture()
def conn():
    """Provide a DB connection and clean up test clusters after each test."""
    c = psycopg2.connect(DB_DSN)
    created_cluster_ids: list[str] = []

    yield c, created_cluster_ids

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
        "SELECT id, signal_type, severity, location_ref, confidence, created_at, metadata FROM signal WHERE id = %s",
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
        "metadata": row[6] or {},
    }


def _fetch_cluster(c, cluster_id) -> dict:
    """Helper to fetch cluster row as dict."""
    cur = c.cursor()
    cur.execute(
        "SELECT id, cluster_state, severity, escalation_level, signal_count FROM issue_cluster WHERE id = %s",
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
        "signal_count": row[4],
    }


class TestFairlandsProgression:
    """Test the full Fairlands signal progression through state machine."""

    def test_full_progression(self, conn):
        """
        Add signals 1-9 one by one, verify state after each.

        Expected:
        - Signal 1: emerging (count=1)
        - Signal 2: emerging (count=2)
        - Signal 3: active (count=3, threshold met)
        - Signal 4: active (stays)
        - Signal 5: escalated (escalation_email, management)
        - Signal 6: escalated (stays)
        - Signal 7: escalated (stays)
        - Signal 8: escalated (stays)
        - Signal 9: escalated (critical severity -> executive)
        """
        c, created = conn

        # Signal 1: create cluster
        sig1 = _fetch_signal(c, SIGNAL_IDS[0])
        cluster_id = create_cluster(c, "Fairlands progression test", sig1)
        created.append(str(cluster_id))

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "emerging"
        assert transition is None

        # Signal 2: still emerging
        sig2 = _fetch_signal(c, SIGNAL_IDS[1])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[1]), sig2, 0.72)

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "emerging"
        assert transition is None

        # Signal 3: transition to active (count >= 3)
        sig3 = _fetch_signal(c, SIGNAL_IDS[2])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[2]), sig3, 0.68)

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "active"
        assert transition == "emerging_to_active"

        # Signal 4: stays active
        sig4 = _fetch_signal(c, SIGNAL_IDS[3])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[3]), sig4, 0.75)

        state, transition = evaluate_state_transition(c, cluster_id)
        # Now active with escalation signals present? No - signal 4 is complaint
        # But wait - no escalation signals yet, stays active
        assert state == "active"
        assert transition is None

        # Signal 5: escalation_email -> escalated, management
        sig5 = _fetch_signal(c, SIGNAL_IDS[4])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[4]), sig5, 0.80)

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "escalated"
        assert transition == "active_to_escalated"

        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["escalation_level"] == "management"

        # Signal 6: stays escalated
        sig6 = _fetch_signal(c, SIGNAL_IDS[5])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[5]), sig6, 0.70)

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "escalated"
        assert transition is None

        # Signal 7: stays escalated
        sig7 = _fetch_signal(c, SIGNAL_IDS[6])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[6]), sig7, 0.73)

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "escalated"
        assert transition is None

        # Signal 8: stays escalated
        sig8 = _fetch_signal(c, SIGNAL_IDS[7])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[7]), sig8, 0.82)

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "escalated"
        assert transition is None

        # Signal 9: critical severity -> executive
        sig9 = _fetch_signal(c, SIGNAL_IDS[8])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[8]), sig9, 0.90)

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "escalated"
        assert transition is None  # Already escalated, but escalation level updated

        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["escalation_level"] == "executive"
        assert cluster["signal_count"] == 9


class TestReopen:
    """Test resolved -> active reopen."""

    def test_reopen_on_active_signal(self, conn):
        c, created = conn

        # Create cluster, add 3 signals to make it active
        sig1 = _fetch_signal(c, SIGNAL_IDS[0])
        cluster_id = create_cluster(c, "Reopen test", sig1)
        created.append(str(cluster_id))

        sig2 = _fetch_signal(c, SIGNAL_IDS[1])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[1]), sig2, 0.72)
        sig3 = _fetch_signal(c, SIGNAL_IDS[2])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[2]), sig3, 0.68)

        # Transition to active
        evaluate_state_transition(c, cluster_id)

        # Manually set to resolved
        cur = c.cursor()
        cur.execute(
            "UPDATE issue_cluster SET cluster_state = 'resolved', resolved_at = now() WHERE id = %s",
            (str(cluster_id),),
        )
        c.commit()
        cur.close()

        # Verify it's resolved
        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["cluster_state"] == "resolved"

        # Evaluate should reopen (has complaint_email = active signal type)
        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "active"
        assert transition == "resolved_to_active"


class TestNoSpuriousTransitions:
    """Test that emerging with < 3 signals stays emerging."""

    def test_emerging_stays_with_two_signals(self, conn):
        c, created = conn

        sig1 = _fetch_signal(c, SIGNAL_IDS[0])
        cluster_id = create_cluster(c, "No-transition test", sig1)
        created.append(str(cluster_id))

        sig2 = _fetch_signal(c, SIGNAL_IDS[1])
        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[1]), sig2, 0.72)

        state, transition = evaluate_state_transition(c, cluster_id)
        assert state == "emerging"
        assert transition is None

        cluster = _fetch_cluster(c, cluster_id)
        assert cluster["signal_count"] == 2
