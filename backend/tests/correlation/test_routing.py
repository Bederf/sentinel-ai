"""
Tests for routing layer (Phase 156-04).

Verifies location scope matching and routing target resolution
against the Fairlands fixture dataset.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from app.services.correlation.classification import classify_cluster
from app.services.correlation.cluster_manager import (
    add_signal_to_cluster,
    create_cluster,
)
from app.services.correlation.routing import get_routing_targets, match_location_scope

DB_DSN = "postgresql://postgres:postgres@localhost:55322/postgres"

# Fixture signal IDs (from 156-01 migration)
SIG_IDS = [f"f1000000-0000-0000-0000-00000000000{i}" for i in range(1, 10)]

# Role assignment IDs (from 156-01 seed)
THANDI_ID = "10000000-0000-0000-0000-000000000001"
KERYN_ID = "10000000-0000-0000-0000-000000000002"
GREG_ID = "10000000-0000-0000-0000-000000000003"
FM_ID = "10000000-0000-0000-0000-000000000004"


@pytest.fixture()
def conn():
    """Provide a DB connection and clean up test clusters after each test."""
    c = psycopg2.connect(DB_DSN)
    created_cluster_ids: list[str] = []

    yield c, created_cluster_ids

    # Cleanup
    cur = c.cursor()
    try:
        for cid in created_cluster_ids:
            cur.execute(
                "DELETE FROM issue_classification WHERE issue_cluster_id = %s",
                (cid,),
            )
            cur.execute(
                "UPDATE signal SET issue_cluster_id = NULL WHERE issue_cluster_id = %s",
                (cid,),
            )
            cur.execute(
                "DELETE FROM relationship WHERE source_id = %s OR target_id = %s",
                (cid, cid),
            )
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


def _build_classified_fairlands_cluster(c, created_ids: list[str]) -> uuid.UUID:
    """Build a cluster with all 9 Fairlands signals, then classify it."""
    sig1 = _fetch_signal(c, SIG_IDS[0])
    cluster_id = create_cluster(c, "Fairlands meeting room issue", sig1)
    created_ids.append(str(cluster_id))

    for sig_id in SIG_IDS[1:]:
        sig = _fetch_signal(c, sig_id)
        add_signal_to_cluster(c, cluster_id, uuid.UUID(sig_id), sig, pairwise_score=0.75)

    classify_cluster(c, cluster_id)
    return cluster_id


# ---------------------------------------------------------------------------
# Unit tests for match_location_scope
# ---------------------------------------------------------------------------


class TestMatchLocationScope:
    def test_wildcard_campus_matches_specific_room(self):
        assert match_location_scope(["Fairlands/FA1/1Q4/MR10"], "Fairlands/*/*/*") is True

    def test_building_wildcard_matches_same_building(self):
        assert match_location_scope(["Fairlands/FA1/1Q4/MR10"], "Fairlands/FA1/*/*") is True

    def test_building_wildcard_does_not_match_different_building(self):
        assert match_location_scope(["Fairlands/FA2/2Q1/MR03"], "Fairlands/FA1/*/*") is False

    def test_global_wildcard_matches_anything(self):
        assert match_location_scope(["Fairlands/FA1/1Q4/MR10"], "*") is True

    def test_wildcard_ref_matches_wildcard_scope(self):
        assert match_location_scope(["Fairlands/*/*/*"], "Fairlands/*/*/*") is True

    def test_multiple_refs_one_match(self):
        """At least one location ref matching is sufficient."""
        assert (
            match_location_scope(
                ["Fairlands/FA2/2Q1/MR03", "Fairlands/FA1/1Q4/MR10"],
                "Fairlands/FA1/*/*",
            )
            is True
        )

    def test_no_match_at_all(self):
        assert match_location_scope(["Sandton/S1/1Q1/MR01"], "Fairlands/*/*/*") is False


# ---------------------------------------------------------------------------
# Integration tests for get_routing_targets
# ---------------------------------------------------------------------------


class TestGetRoutingTargets:
    def test_returns_three_targets_for_fairlands(self, conn):
        c, created = conn
        cluster_id = _build_classified_fairlands_cluster(c, created)

        targets = get_routing_targets(c, cluster_id)

        assert len(targets) == 3

    def test_thandi_is_routed(self, conn):
        c, created = conn
        cluster_id = _build_classified_fairlands_cluster(c, created)

        targets = get_routing_targets(c, cluster_id)
        target_ids = {str(t["id"]) for t in targets}

        assert THANDI_ID in target_ids

    def test_thandi_has_concierge_role(self, conn):
        c, created = conn
        cluster_id = _build_classified_fairlands_cluster(c, created)

        targets = get_routing_targets(c, cluster_id)
        thandi = next(t for t in targets if str(t["id"]) == THANDI_ID)

        assert thandi["role_type"] == "concierge"

    def test_keryn_is_routed(self, conn):
        c, created = conn
        cluster_id = _build_classified_fairlands_cluster(c, created)

        targets = get_routing_targets(c, cluster_id)
        target_ids = {str(t["id"]) for t in targets}

        assert KERYN_ID in target_ids

    def test_fm_excluded_no_domain_overlap(self, conn):
        """FM has hvac+maintenance+energy domains, but cluster has space_optimisation."""
        c, created = conn
        cluster_id = _build_classified_fairlands_cluster(c, created)

        targets = get_routing_targets(c, cluster_id)
        target_ids = {str(t["id"]) for t in targets}

        assert FM_ID not in target_ids

    def test_empty_cluster_no_targets(self, conn):
        """Cluster with no classifications produces no routing targets."""
        c, created = conn
        sig = _fetch_signal(c, SIG_IDS[0])
        cluster_id = create_cluster(c, "Empty cluster", sig)
        created.append(str(cluster_id))

        # Don't classify - no classifications exist
        targets = get_routing_targets(c, cluster_id)
        assert targets == []
