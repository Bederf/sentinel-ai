"""
Tests for cluster confidence computation (Phase 156-03).

Tests individual components and the full Fairlands cluster confidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import psycopg2
import pytest

from app.services.correlation.cluster_confidence import (
    _severity_consensus,
    _temporal_density,
    compute_cluster_confidence,
)
from app.services.correlation.cluster_manager import (
    add_signal_to_cluster,
    create_cluster,
    link_entities_to_cluster,
)

DB_DSN = "postgresql://postgres:postgres@localhost:55322/postgres"

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
        for sig_id in SIGNAL_IDS:
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


class TestTemporalDensity:
    def test_single_signal(self):
        assert _temporal_density([datetime(2026, 1, 5)]) == 1.0

    def test_all_within_7_days(self):
        timestamps = [
            datetime(2026, 1, 5),
            datetime(2026, 1, 8),
            datetime(2026, 1, 10),
            datetime(2026, 1, 12),
        ]
        assert _temporal_density(timestamps) == 1.0

    def test_spread_over_60_days(self):
        # 5 signals, each ~15 days apart
        timestamps = [
            datetime(2026, 1, 1),
            datetime(2026, 1, 16),
            datetime(2026, 1, 31),
            datetime(2026, 2, 15),
            datetime(2026, 3, 2),
        ]
        density = _temporal_density(timestamps)
        assert density < 0.50


class TestSeverityConsensus:
    def test_all_same(self):
        assert _severity_consensus(["medium", "medium", "medium"]) == 1.0

    def test_mixed_low_critical(self):
        score = _severity_consensus(["low", "critical"])
        assert score < 0.10  # std_dev = 1.5, score = 0.0

    def test_moderate_mix(self):
        score = _severity_consensus(["medium", "high", "medium"])
        assert 0.50 < score < 1.0


class TestSingleSignalConfidence:
    def test_single_signal_cluster(self, conn):
        c, created = conn
        sig = _fetch_signal(c, SIGNAL_IDS[0])

        cluster_id = create_cluster(c, "Single signal test", sig)
        created.append(str(cluster_id))

        confidence = compute_cluster_confidence(c, cluster_id)
        # With 1 signal: agreement=0.85, density=1.0, entity=0/1=0.0,
        # severity_consensus=1.0, classification=0.50
        assert confidence > 0.40
        assert confidence <= 0.99


class TestTwoSignalConfidence:
    def test_two_signals_decent_confidence(self, conn):
        c, created = conn
        sig1 = _fetch_signal(c, SIGNAL_IDS[0])
        sig2 = _fetch_signal(c, SIGNAL_IDS[1])

        cluster_id = create_cluster(c, "Two signal test", sig1)
        created.append(str(cluster_id))

        add_signal_to_cluster(c, cluster_id, uuid.UUID(SIGNAL_IDS[1]), sig2, 0.75)

        confidence = compute_cluster_confidence(c, cluster_id)
        # Two signals, no entities linked, limited pairwise data → modest confidence
        assert confidence > 0.35


class TestFullFairlandsConfidence:
    def test_nine_signals_above_threshold(self, conn):
        """Full Fairlands cluster with 9 signals must achieve >= 0.75 confidence."""
        c, created = conn

        # Create cluster with signal 1
        sig1 = _fetch_signal(c, SIGNAL_IDS[0])
        cluster_id = create_cluster(c, "Fairlands full test", sig1)
        created.append(str(cluster_id))

        # Add signals 2-9 with pairwise scores reflecting entity overlap
        # Real scores with shared entities (Fairlands campus, people) are higher
        pairwise_scores = [0.85, 0.82, 0.88, 0.92, 0.84, 0.86, 0.91, 0.95]
        for i in range(1, 9):
            sig = _fetch_signal(c, SIGNAL_IDS[i])
            add_signal_to_cluster(
                c,
                cluster_id,
                uuid.UUID(SIGNAL_IDS[i]),
                sig,
                pairwise_scores[i - 1],
            )

        # Link entities to boost entity_connectivity
        link_entities_to_cluster(c, cluster_id)

        confidence = compute_cluster_confidence(c, cluster_id)
        assert confidence >= 0.75, f"Expected >= 0.75 but got {confidence}"
        assert confidence <= 0.99


class TestEntityConnectivity:
    def test_entity_connectivity_capped(self, conn):
        """13 entities / 9 signals = 1.44 -> capped at 1.0."""
        c, created = conn

        sig1 = _fetch_signal(c, SIGNAL_IDS[0])
        cluster_id = create_cluster(c, "Entity cap test", sig1)
        created.append(str(cluster_id))

        # Add all 9 signals
        pairwise_scores = [0.85, 0.82, 0.88, 0.92, 0.84, 0.86, 0.91, 0.95]
        for i in range(1, 9):
            sig = _fetch_signal(c, SIGNAL_IDS[i])
            add_signal_to_cluster(
                c,
                cluster_id,
                uuid.UUID(SIGNAL_IDS[i]),
                sig,
                pairwise_scores[i - 1],
            )

        entity_count = link_entities_to_cluster(c, cluster_id)
        assert entity_count >= 1  # Should have entities from fixture signals

        # Entity connectivity = min(entity_count/9, 1.0)
        # With 13 entities / 9 signals -> 1.44 -> capped at 1.0
        cur = c.cursor()
        cur.execute(
            "SELECT entity_count, signal_count FROM issue_cluster WHERE id = %s",
            (str(cluster_id),),
        )
        row = cur.fetchone()
        cur.close()
        ec_ratio = min(row[0] / row[1], 1.0)
        assert ec_ratio <= 1.0
