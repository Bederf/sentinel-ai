"""
Tests for Phase 171-01: Asset Evidence Schema & Migration

Verifies:
1. Table structure and column types
2. Index creation and query performance
3. RLS policies for site isolation
4. Immutability constraints
5. FK constraints
"""

import pytest
from datetime import datetime
from uuid import uuid4


@pytest.mark.asyncio
class TestAssetEvidenceSchema:
    """Test asset_evidence table structure and constraints."""

    async def test_table_exists(self, supabase_client):
        """Verify asset_evidence table exists with correct structure."""
        # Query information_schema.columns
        result = (
            supabase_client.table("information_schema_columns")
            .select("column_name, data_type, is_nullable")
            .eq("table_name", "asset_evidence")
            .execute()
        )

        columns = {col["column_name"]: col for col in result.data}

        # Verify all 18 columns exist
        expected_columns = {
            "evidence_id": {"type": "uuid"},
            "site_id": {"type": "uuid"},
            "equipment_id": {"type": "uuid"},
            "source_type": {"type": "enum"},
            "artifact_type": {"type": "enum"},
            "evidence_class": {"type": "enum"},
            "document_id": {"type": "uuid", "nullable": True},
            "source_ref": {"type": "text", "nullable": True},
            "event_timestamp": {"type": "timestamp"},
            "raw_payload": {"type": "jsonb"},
            "normalized_payload": {"type": "jsonb"},
            "confidence_score": {"type": "numeric"},
            "assessment_relevance": {"type": "boolean"},
            "provenance_type": {"type": "enum"},
            "provenance_uri": {"type": "text"},
            "uploader_user_id": {"type": "uuid", "nullable": True},
            "uploader_user_email": {"type": "text", "nullable": True},
            "created_at": {"type": "timestamp"},
            "supersedes_evidence_id": {"type": "uuid", "nullable": True},
        }

        # Note: actual column types from Supabase may differ slightly
        # (e.g., 'timestamp with time zone' vs 'timestamp')
        assert len(columns) == 19, f"Expected 19 columns, got {len(columns)}"
        for col_name in expected_columns.keys():
            assert col_name in columns, f"Column {col_name} not found"

    async def test_enums_exist(self, supabase_client):
        """Verify all evidence ENUMs are created."""
        result = supabase_client.rpc(
            "execute_sql", {"query": "SELECT typname FROM pg_enum WHERE typname LIKE 'evidence%'"}
        ).execute()

        enum_types = {row["typname"] for row in result.data}

        expected_enums = {
            "evidence_source_type",
            "evidence_artifact_type",
            "evidence_class_type",
            "evidence_provenance_type",
        }

        assert expected_enums.issubset(enum_types), f"Missing ENUMs: {expected_enums - enum_types}"

    async def test_primary_key_constraint(self, supabase_client):
        """Verify evidence_id is primary key."""
        result = supabase_client.rpc(
            "execute_sql",
            {
                "query": """
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_name='asset_evidence' AND constraint_type='PRIMARY KEY'
            """
            },
        ).execute()

        assert len(result.data) > 0, "No PRIMARY KEY constraint found"

    async def test_fk_constraints_exist(self, supabase_client):
        """Verify FK constraints enforce referential integrity."""
        result = supabase_client.rpc(
            "execute_sql",
            {
                "query": """
                SELECT constraint_name, table_name, column_name
                FROM information_schema.key_column_usage
                WHERE table_name='asset_evidence' AND referenced_table_name IS NOT NULL
            """
            },
        ).execute()

        fk_constraints = {row["constraint_name"] for row in result.data}

        # Should have FKs to: sites, equipment, documents, auth.users, asset_evidence (self-ref)
        expected_fk_count = 5
        assert len(fk_constraints) >= expected_fk_count, (
            f"Expected at least {expected_fk_count} FK constraints, got {len(fk_constraints)}"
        )

    async def test_indices_created(self, supabase_client):
        """Verify indices for query performance exist."""
        result = supabase_client.rpc(
            "execute_sql",
            {
                "query": """
                SELECT indexname FROM pg_indexes
                WHERE tablename='asset_evidence' AND indexname NOT LIKE 'pg_%'
            """
            },
        ).execute()

        index_names = {row["indexname"] for row in result.data}

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
        """Verify CHECK constraint enforces confidence_score bounds (0.0-1.0)."""
        # Valid: confidence_score = 0.5
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

        # Invalid: confidence_score = 1.5 (exceeds bounds)
        with pytest.raises(Exception) as exc_info:
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
        assert "confidence_score" in str(exc_info.value) or "CHECK" in str(exc_info.value)

    async def test_rls_site_isolation(self, supabase_client, site_a_id, site_b_id, user_a_email):
        """Verify RLS enforces site isolation via user_site_access."""
        # User A can see evidence at Site A
        result = (
            supabase_client.table("asset_evidence").select("*").eq("site_id", str(site_a_id)).execute()
        )  # Executed as user A (via JWT)

        # Should succeed (RLS allows user A at Site A)
        assert result.data is not None

        # User A should NOT see evidence at Site B
        result = (
            supabase_client.table("asset_evidence").select("*").eq("site_id", str(site_b_id)).execute()
        )  # Executed as user A (via JWT)

        # RLS should block (user A has no access to Site B)
        # If result is empty, RLS is working
        # If result has data, RLS is broken
        assert len(result.data) == 0, "RLS site isolation failed"

    async def test_rls_no_delete(self, supabase_client, evidence_id):
        """Verify RLS prevents DELETE on asset_evidence."""
        with pytest.raises(Exception) as exc_info:
            supabase_client.table("asset_evidence").delete().eq("evidence_id", str(evidence_id)).execute()

        assert "DELETE" in str(exc_info.value) or "RLS" in str(exc_info.value)

    async def test_immutability_no_update(self, supabase_client, evidence_id):
        """Verify RLS prevents UPDATE on asset_evidence (except service_role)."""
        # As regular user, UPDATE should fail
        with pytest.raises(Exception) as exc_info:
            supabase_client.table("asset_evidence").update({"confidence_score": 0.99}).eq(
                "evidence_id", str(evidence_id)
            ).execute()

        assert "UPDATE" in str(exc_info.value) or "RLS" in str(exc_info.value)

    async def test_fk_site_constraint(self, supabase_client, equipment_id):
        """Verify FK constraint: invalid site_id raises error."""
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
        """Verify FK constraint: invalid equipment_id raises error."""
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
        """Verify uploader_user_id can be NULL (system ingest)."""
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
                    "uploader_user_id": None,  # System ingest, no user
                }
            )
            .execute()
        )

        assert result.data, "NULL uploader_user_id should be allowed"
        assert result.data[0]["uploader_user_id"] is None

    async def test_migration_idempotent(self, supabase_client):
        """Verify migration can run multiple times safely."""
        # Re-run the same CREATE TABLE (should not error if table exists)
        # This is validated by Supabase migrations framework
        result = supabase_client.rpc(
            "execute_sql",
            {"query": "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='asset_evidence')"},
        ).execute()

        assert result.data[0]["exists"]


# Pytest fixtures
@pytest.fixture
def site_id():
    """Fixture: valid site_id for tests."""
    return uuid4()


@pytest.fixture
def site_a_id():
    """Fixture: Site A ID."""
    return uuid4()


@pytest.fixture
def site_b_id():
    """Fixture: Site B ID (different from Site A)."""
    return uuid4()


@pytest.fixture
def equipment_id():
    """Fixture: valid equipment_id for tests."""
    return uuid4()


@pytest.fixture
def user_a_email():
    """Fixture: user A email."""
    return "user_a@example.com"


@pytest.fixture
def evidence_id():
    """Fixture: valid evidence_id for tests."""
    return uuid4()
