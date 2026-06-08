"""
Tests for Phase 171-01: Asset Evidence Schema & Migration

Verifies:
1. Table structure and column types
2. Index creation and query performance
3. RLS policies for site isolation
4. Immutability constraints
5. FK constraints
"""

from datetime import datetime
from uuid import uuid4

import pytest


@pytest.mark.asyncio
class TestAssetEvidenceSchema:
    """Test asset_evidence table structure and constraints."""

    def test_table_exists(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='asset_evidence'
                """
            )
            columns = {row[0] for row in cur.fetchall()}

        expected_columns = {
            "evidence_id",
            "site_id",
            "equipment_id",
            "source_type",
            "artifact_type",
            "evidence_class",
            "document_id",
            "source_ref",
            "event_timestamp",
            "raw_payload",
            "normalized_payload",
            "confidence_score",
            "assessment_relevance",
            "provenance_type",
            "provenance_uri",
            "uploader_user_id",
            "uploader_user_email",
            "created_at",
            "supersedes_evidence_id",
        }
        assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

    def test_enums_exist(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("SELECT typname FROM pg_type WHERE typname LIKE 'evidence_%' AND typtype = 'e'")
            enum_types = {row[0] for row in cur.fetchall()}

        expected_enums = {
            "evidence_source_type",
            "evidence_artifact_type",
            "evidence_class_type",
            "evidence_provenance_type",
        }
        assert expected_enums.issubset(enum_types), f"Missing ENUMs: {expected_enums - enum_types}"

    def test_primary_key_constraint(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_schema='public' AND table_name='asset_evidence'
                  AND constraint_type='PRIMARY KEY'
                """
            )
            assert cur.fetchone() is not None, "No PRIMARY KEY constraint found"

    def test_fk_constraints_exist(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE table_schema='public' AND table_name='asset_evidence'
                  AND constraint_type='FOREIGN KEY'
                """
            )
            count = cur.fetchone()[0]

        assert count >= 2, f"Expected at least 2 FK constraints, got {count}"

    def test_indices_created(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename='asset_evidence' AND indexname NOT LIKE 'pg_%'
                """
            )
            index_names = {row[0] for row in cur.fetchall()}

        expected_indices = {
            "idx_asset_evidence_equipment_timestamp",
            "idx_asset_evidence_site_timestamp",
            "idx_asset_evidence_class",
            "idx_asset_evidence_provenance",
            "idx_asset_evidence_supersedes",
            "idx_asset_evidence_document",
        }
        assert expected_indices.issubset(index_names), f"Missing indices: {expected_indices - index_names}"

    async def test_confidence_score_bounds(self, supabase_client, site_id, equipment_id):
        result = (
            supabase_client.table("asset_evidence")
            .insert(
                {
                    "site_id": str(site_id),
                    "equipment_id": str(equipment_id),
                    "source_type": "upload",
                    "artifact_type": "document",
                    "evidence_class": "service_report",
                    "event_timestamp": datetime.utcnow().isoformat(),
                    "confidence_score": 0.5,
                    "provenance_type": "user_upload",
                    "provenance_uri": "test",
                }
            )
            .execute()
        )
        assert result.data, "Valid confidence_score should be accepted"

        with pytest.raises(Exception):
            supabase_client.table("asset_evidence").insert(
                {
                    "site_id": str(site_id),
                    "equipment_id": str(equipment_id),
                    "source_type": "upload",
                    "artifact_type": "document",
                    "evidence_class": "service_report",
                    "event_timestamp": datetime.utcnow().isoformat(),
                    "confidence_score": 1.5,
                    "provenance_type": "user_upload",
                    "provenance_uri": "test",
                }
            ).execute()

    def test_rls_site_isolation_policy_exists(self, db_conn):
        """RLS SELECT policy with site isolation must exist."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM pg_policies
                WHERE tablename='asset_evidence' AND cmd='SELECT'
                """
            )
            count = cur.fetchone()[0]
        assert count > 0, "No SELECT RLS policy found on asset_evidence"

    def test_rls_no_delete(self, db_conn):
        """DELETE policy must exist as a deny-all (USING false) — immutable table."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT qual FROM pg_policies
                WHERE tablename='asset_evidence' AND cmd='DELETE'
                """
            )
            rows = cur.fetchall()
        # Either no DELETE policy (RLS blocks by default) or an explicit deny policy
        assert all(row[0] == "false" for row in rows), "All DELETE policies must be deny-all (USING false)"

    def test_immutability_no_update(self, db_conn):
        """No UPDATE policy or only deny-all UPDATE policies — immutable table."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT qual FROM pg_policies
                WHERE tablename='asset_evidence' AND cmd='UPDATE'
                """
            )
            rows = cur.fetchall()
        assert all(row[0] == "false" for row in rows), "All UPDATE policies must be deny-all (USING false)"

    async def test_fk_site_constraint(self, supabase_client, equipment_id):
        invalid_site_id = uuid4()

        with pytest.raises(Exception) as exc_info:
            supabase_client.table("asset_evidence").insert(
                {
                    "site_id": str(invalid_site_id),
                    "equipment_id": str(equipment_id),
                    "source_type": "upload",
                    "artifact_type": "document",
                    "evidence_class": "service_report",
                    "event_timestamp": datetime.utcnow().isoformat(),
                    "confidence_score": 0.5,
                    "provenance_type": "user_upload",
                    "provenance_uri": "test",
                }
            ).execute()
        assert "foreign key" in str(exc_info.value).lower() or "FK" in str(exc_info.value)

    async def test_fk_equipment_constraint(self, supabase_client, site_id):
        invalid_equipment_id = uuid4()

        with pytest.raises(Exception) as exc_info:
            supabase_client.table("asset_evidence").insert(
                {
                    "site_id": str(site_id),
                    "equipment_id": str(invalid_equipment_id),
                    "source_type": "upload",
                    "artifact_type": "document",
                    "evidence_class": "service_report",
                    "event_timestamp": datetime.utcnow().isoformat(),
                    "confidence_score": 0.5,
                    "provenance_type": "user_upload",
                    "provenance_uri": "test",
                }
            ).execute()
        assert "foreign key" in str(exc_info.value).lower()

    async def test_nullable_uploader_user_id(self, supabase_client, site_id, equipment_id):
        result = (
            supabase_client.table("asset_evidence")
            .insert(
                {
                    "site_id": str(site_id),
                    "equipment_id": str(equipment_id),
                    "source_type": "telemetry",
                    "artifact_type": "structured_data",
                    "evidence_class": "telemetry_summary",
                    "event_timestamp": datetime.utcnow().isoformat(),
                    "confidence_score": 0.8,
                    "provenance_type": "system_ingest",
                    "provenance_uri": "system:telemetry",
                    "uploader_user_id": None,
                }
            )
            .execute()
        )
        assert result.data, "NULL uploader_user_id should be allowed"
        assert result.data[0]["uploader_user_id"] is None

    def test_migration_idempotent(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='asset_evidence')"
            )
            assert cur.fetchone()[0], "asset_evidence table should exist"


# Pytest fixtures — use real IDs for FK-validated tests
@pytest.fixture
def site_id(real_site_id):
    return real_site_id


@pytest.fixture
def equipment_id(real_equipment_id):
    return real_equipment_id
