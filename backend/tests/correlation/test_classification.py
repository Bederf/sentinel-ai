"""
Tests for classification service (Phase 156-04).

Verifies domain vote aggregation against the Fairlands fixture dataset.
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

DB_DSN = "postgresql://postgres:postgres@localhost:55322/postgres"

# Fixture signal IDs (from 156-01 migration)
SIG_IDS = [f"f1000000-0000-0000-0000-00000000000{i}" for i in range(1, 10)]


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


def _build_fairlands_cluster(c, created_ids: list[str]) -> uuid.UUID:
    """Build a cluster with all 9 Fairlands signals."""
    sig1 = _fetch_signal(c, SIG_IDS[0])
    cluster_id = create_cluster(c, "Fairlands meeting room issue", sig1)
    created_ids.append(str(cluster_id))

    for sig_id in SIG_IDS[1:]:
        sig = _fetch_signal(c, sig_id)
        add_signal_to_cluster(c, cluster_id, uuid.UUID(sig_id), sig, pairwise_score=0.75)

    return cluster_id


class TestClassifyFairlandsCluster:
    def test_space_optimisation_confidence_gte_090(self, conn):
        c, created = conn
        cluster_id = _build_fairlands_cluster(c, created)

        results = classify_cluster(c, cluster_id)

        domains = {r["domain"]: r["confidence"] for r in results}
        assert "space_optimisation" in domains
        assert domains["space_optimisation"] >= 0.90

    def test_workplace_experience_present(self, conn):
        c, created = conn
        cluster_id = _build_fairlands_cluster(c, created)

        results = classify_cluster(c, cluster_id)

        domains = {r["domain"]: r["confidence"] for r in results}
        assert "workplace_experience" in domains
        assert domains["workplace_experience"] > 0.50

    def test_no_false_positive_domains(self, conn):
        c, created = conn
        cluster_id = _build_fairlands_cluster(c, created)

        results = classify_cluster(c, cluster_id)

        domain_names = {r["domain"] for r in results}
        for unwanted in ("hvac", "maintenance", "energy", "security", "compliance"):
            assert unwanted not in domain_names, f"Unexpected domain: {unwanted}"

    def test_space_optimisation_ranks_first(self, conn):
        c, created = conn
        cluster_id = _build_fairlands_cluster(c, created)

        results = classify_cluster(c, cluster_id)

        assert len(results) >= 2
        assert results[0]["domain"] == "space_optimisation"
        assert results[0]["confidence"] > results[1]["confidence"]


class TestClassifyHvacCluster:
    def test_hvac_cluster_has_hvac_domain(self, conn):
        """Classify a cluster with hvac_fault signals -> hvac domain present."""
        c, created = conn

        # Create a synthetic hvac signal
        cur = c.cursor()
        hvac_sig_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO signal (id, signal_type, severity, location_ref, confidence, source_module, created_at)
            VALUES (%s, 'hvac_fault', 'high', 'Fairlands/FA1/1Q4/AHU01', 0.90, 'hvac_telemetry', now())
            """,
            (hvac_sig_id,),
        )
        c.commit()
        cur.close()

        sig = _fetch_signal(c, hvac_sig_id)
        cluster_id = create_cluster(c, "HVAC fault cluster", sig)
        created.append(str(cluster_id))

        results = classify_cluster(c, cluster_id)
        domains = {r["domain"]: r["confidence"] for r in results}

        assert "hvac" in domains
        assert "space_optimisation" not in domains

        # Clean up synthetic signal
        cur = c.cursor()
        cur.execute("UPDATE signal SET issue_cluster_id = NULL WHERE id = %s", (hvac_sig_id,))
        cur.execute("DELETE FROM signal WHERE id = %s", (hvac_sig_id,))
        c.commit()
        cur.close()


class TestClassifySingleSignal:
    def test_single_signal_classification(self, conn):
        c, created = conn
        sig = _fetch_signal(c, SIG_IDS[0])  # complaint_email

        cluster_id = create_cluster(c, "Single signal cluster", sig)
        created.append(str(cluster_id))

        results = classify_cluster(c, cluster_id)
        domains = {r["domain"]: r["confidence"] for r in results}

        # Single complaint_email: space_optimisation = (1/1) * 0.90 = 0.90
        assert "space_optimisation" in domains
        assert domains["space_optimisation"] == 0.90

        # workplace_experience = (1/1) * 0.80 = 0.80
        assert "workplace_experience" in domains
        assert domains["workplace_experience"] == 0.80


class TestUpsertClassification:
    def test_reclassify_updates_no_duplicates(self, conn):
        c, created = conn
        cluster_id = _build_fairlands_cluster(c, created)

        # Classify twice
        results1 = classify_cluster(c, cluster_id)
        results2 = classify_cluster(c, cluster_id)

        # Same results
        assert len(results1) == len(results2)

        # No duplicate rows in DB
        cur = c.cursor()
        cur.execute(
            "SELECT count(*) FROM issue_classification WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        count = cur.fetchone()[0]
        cur.close()
        assert count == len(results1)
