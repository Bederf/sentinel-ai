"""
Tests for dashboard card generator (Phase 156-04).

Verifies card generation, role-appropriate content, idempotency,
and the critical acceptance test: Thandi receives a card without
being in any signal's recipient list.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from app.services.correlation.card_generator import (
    generate_cards,
    get_cards_for_person,
)
from app.services.correlation.classification import classify_cluster
from app.services.correlation.cluster_manager import (
    add_signal_to_cluster,
    create_cluster,
    link_entities_to_cluster,
)
from app.services.correlation.routing import get_routing_targets

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
    """Provide a DB connection and clean up test artifacts after each test."""
    c = psycopg2.connect(DB_DSN)
    created_cluster_ids: list[str] = []

    yield c, created_cluster_ids

    # Cleanup
    cur = c.cursor()
    try:
        for cid in created_cluster_ids:
            cur.execute(
                "DELETE FROM dashboard_card WHERE issue_cluster_id = %s",
                (cid,),
            )
            cur.execute(
                "DELETE FROM issue_classification WHERE issue_cluster_id = %s",
                (cid,),
            )
            cur.execute(
                "UPDATE entity SET issue_cluster_id = NULL WHERE issue_cluster_id = %s",
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
            # Delete involves edges for fixture signals
            for sig_id in SIG_IDS:
                cur.execute(
                    "DELETE FROM relationship WHERE source_id = %s AND edge_type = 'involves'",
                    (sig_id,),
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


def _build_full_pipeline(c, created_ids: list[str]) -> tuple[uuid.UUID, list[dict]]:
    """
    Build a cluster with all 9 Fairlands signals, link entities,
    classify, and route. Returns (cluster_id, routing_targets).
    """
    sig1 = _fetch_signal(c, SIG_IDS[0])
    cluster_id = create_cluster(c, "Fairlands meeting room issue", sig1)
    created_ids.append(str(cluster_id))

    for sig_id in SIG_IDS[1:]:
        sig = _fetch_signal(c, sig_id)
        add_signal_to_cluster(c, cluster_id, uuid.UUID(sig_id), sig, pairwise_score=0.75)

    link_entities_to_cluster(c, cluster_id)
    classify_cluster(c, cluster_id)
    targets = get_routing_targets(c, cluster_id)

    return cluster_id, targets


class TestGenerateCards:
    def test_three_cards_created(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        card_ids = generate_cards(c, cluster_id, targets)

        assert len(card_ids) == 3

    def test_thandi_card_has_concierge_actions(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        generate_cards(c, cluster_id, targets)

        cards = get_cards_for_person(c, uuid.UUID(THANDI_ID))
        assert len(cards) == 1
        content = cards[0]["card_content"]
        assert "Cancel confirmed unoccupied slots" in content["recommended_actions"]
        assert "Monitor no-show patterns this week" in content["recommended_actions"]

    def test_thandi_card_has_affected_rooms(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        generate_cards(c, cluster_id, targets)

        cards = get_cards_for_person(c, uuid.UUID(THANDI_ID))
        content = cards[0]["card_content"]
        rooms = set(content["affected_rooms"])
        assert "FA1-1Q4-MR10" in rooms
        assert "FA2-2Q1-MR03" in rooms
        assert "FA1-1Q2-TR01" in rooms

    def test_thandi_card_has_people_involved(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        generate_cards(c, cluster_id, targets)

        cards = get_cards_for_person(c, uuid.UUID(THANDI_ID))
        content = cards[0]["card_content"]
        assert len(content["people_involved"]) >= 1

    def test_thandi_card_has_classifications(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        generate_cards(c, cluster_id, targets)

        cards = get_cards_for_person(c, uuid.UUID(THANDI_ID))
        content = cards[0]["card_content"]
        domain_names = {c["domain"] for c in content["classifications"]}
        assert "space_optimisation" in domain_names

    def test_thandi_card_has_advisory_label(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        generate_cards(c, cluster_id, targets)

        cards = get_cards_for_person(c, uuid.UUID(THANDI_ID))
        assert "suggestions" in cards[0]["advisory_label"].lower()

    def test_card_has_confidence_and_state(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        generate_cards(c, cluster_id, targets)

        cards = get_cards_for_person(c, uuid.UUID(THANDI_ID))
        content = cards[0]["card_content"]
        assert "confidence_score" in content
        assert "cluster_state" in content
        assert "severity" in content
        assert "signal_count" in content
        assert content["signal_count"] == 9

    def test_keryn_card_has_management_actions(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        generate_cards(c, cluster_id, targets)

        cards = get_cards_for_person(c, uuid.UUID(KERYN_ID))
        assert len(cards) == 1
        content = cards[0]["card_content"]
        assert "Review booking policy for affected areas" in content["recommended_actions"]


class TestCardIdempotency:
    def test_duplicate_generation_updates_not_creates(self, conn):
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        card_ids_1 = generate_cards(c, cluster_id, targets)
        card_ids_2 = generate_cards(c, cluster_id, targets)

        # Same card IDs returned (updated, not new)
        assert set(str(cid) for cid in card_ids_1) == set(str(cid) for cid in card_ids_2)

        # Total card count unchanged
        cur = c.cursor()
        cur.execute(
            "SELECT count(*) FROM dashboard_card WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        count = cur.fetchone()[0]
        cur.close()
        assert count == 3


class TestThandiNotInRecipients:
    def test_thandi_card_exists_and_not_in_signal_recipients(self, conn):
        """
        CRITICAL ACCEPTANCE TEST:
        Thandi receives a card as concierge even though she is NOT in any
        signal's recipient list. She appears only as sender in signals 3 and 7.
        """
        c, created = conn
        cluster_id, targets = _build_full_pipeline(c, created)

        generate_cards(c, cluster_id, targets)

        # Verify Thandi has a card
        cards = get_cards_for_person(c, uuid.UUID(THANDI_ID))
        assert len(cards) == 1, "Thandi should have exactly 1 card"

        # Verify Thandi is NOT in any signal's recipients metadata
        cur = c.cursor()
        cur.execute(
            """
            SELECT id, metadata FROM signal
            WHERE issue_cluster_id = %s
            """,
            (str(cluster_id),),
        )
        signal_rows = cur.fetchall()
        cur.close()

        for sig_id, metadata in signal_rows:
            if metadata:
                recipients = metadata.get("recipients", [])
                for recipient in recipients:
                    assert recipient.lower() != "thandi dineka", (
                        f"Thandi should NOT be in signal {sig_id} recipients, but found in: {recipients}"
                    )
