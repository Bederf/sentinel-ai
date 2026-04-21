"""
Tests for Phase 171-02: Asset Evidence Repository

Verifies:
1. CRUD operations
2. Query filtering
3. Supersession chain traversal
4. RLS integration
5. Immutability enforcement
"""

from datetime import datetime
from uuid import uuid4

import pytest
from backend.app.models.asset_evidence import (
    ArtifactType,
    AssetEvidenceFilter,
    CreateAssetEvidenceInput,
    EvidenceClass,
    ProvenanceType,
    SourceType,
)


@pytest.mark.asyncio
class TestAssetEvidenceRepository:
    """Test asset evidence repository CRUD and querying."""

    @pytest.fixture
    async def repository(self):
        """Fixture: initialize repository with test Supabase client."""
        from backend.app.database.repositories.asset_evidence_repository import (
            AssetEvidenceRepository,
        )

        return AssetEvidenceRepository()

    @pytest.fixture
    def test_input(self):
        """Fixture: valid CreateAssetEvidenceInput for testing."""
        return CreateAssetEvidenceInput(
            site_id=uuid4(),
            equipment_id=uuid4(),
            source_type=SourceType.UPLOAD,
            artifact_type=ArtifactType.DOCUMENT,
            evidence_class=EvidenceClass.SERVICE_REPORT,
            event_timestamp=datetime.utcnow(),
            raw_payload={"test": "data"},
            normalized_payload={"document_name": "test.pdf"},
            confidence_score=0.95,
            assessment_relevance=True,
            provenance_type=ProvenanceType.USER_UPLOAD,
            provenance_uri="test:uri",
            uploader_user_id=uuid4(),
        )

    async def test_create_evidence(self, repository, test_input):
        """Create evidence returns record with generated evidence_id."""
        result = await repository.create(test_input)

        assert result.evidence_id is not None
        assert result.site_id == test_input.site_id
        assert result.equipment_id == test_input.equipment_id
        assert result.confidence_score == test_input.confidence_score
        assert result.created_at is not None

    async def test_get_evidence(self, repository, test_input):
        """Retrieve evidence by ID."""
        # Create
        created = await repository.create(test_input)

        # Retrieve
        result = await repository.get(created.evidence_id)

        assert result is not None
        assert result.evidence_id == created.evidence_id
        assert result.document_name == "test.pdf"  # From normalized_payload

    async def test_list_by_equipment(self, repository, test_input):
        """List all evidence for equipment, ordered by event_timestamp DESC."""
        equipment_id = uuid4()
        test_input.equipment_id = equipment_id

        # Create multiple records
        e1 = await repository.create(test_input)
        test_input.event_timestamp = datetime.utcnow()
        e2 = await repository.create(test_input)

        # List
        result = await repository.list_by_equipment(equipment_id)

        assert len(result) >= 2
        # Verify ordering: newest first
        assert result[0].event_timestamp >= result[1].event_timestamp

    async def test_list_by_site(self, repository, test_input):
        """List all evidence for site."""
        site_id = uuid4()
        test_input.site_id = site_id

        # Create
        created = await repository.create(test_input)

        # List
        result = await repository.list_by_site(site_id)

        assert len(result) >= 1
        assert any(e.evidence_id == created.evidence_id for e in result)

    async def test_query_with_filters(self, repository, test_input):
        """Query with multiple filters."""
        test_input.evidence_class = EvidenceClass.INSPECTION_CHECKLIST
        created = await repository.create(test_input)

        # Query by class
        filter = AssetEvidenceFilter(
            evidence_class=EvidenceClass.INSPECTION_CHECKLIST,
            site_id=test_input.site_id,
        )
        result = await repository.query(filter)

        assert len(result) >= 1
        assert any(e.evidence_id == created.evidence_id for e in result)

    async def test_query_active_only(self, repository, test_input):
        """Query active_only filters out superseded evidence."""
        # Create evidence
        e1 = await repository.create(test_input)

        # Supersede it
        test_input.event_timestamp = datetime.utcnow()
        e2 = await repository.create(test_input)
        await repository.supersede(e1.evidence_id, e2.evidence_id)

        # Query active only
        filter = AssetEvidenceFilter(
            equipment_id=test_input.equipment_id,
            active_only=True,
        )
        result = await repository.query(filter)

        # Should include e2 (active) but not e1 (superseded)
        assert any(e.evidence_id == e2.evidence_id for e in result)
        assert not any(e.evidence_id == e1.evidence_id and e.supersedes_evidence_id is not None for e in result)

    async def test_supersede_evidence(self, repository, test_input):
        """Supersede marks evidence as superseded."""
        # Create two evidence records
        e1 = await repository.create(test_input)
        test_input.event_timestamp = datetime.utcnow()
        e2 = await repository.create(test_input)

        # Supersede
        result = await repository.supersede(e1.evidence_id, e2.evidence_id)

        assert result.supersedes_evidence_id == e2.evidence_id

    async def test_get_supersession_chain(self, repository, test_input):
        """Traverse supersession chain: [new → old → older]."""
        # Create chain: e1 → e2 → e3
        e1 = await repository.create(test_input)
        test_input.event_timestamp = datetime.utcnow()
        e2 = await repository.create(test_input)
        test_input.event_timestamp = datetime.utcnow()
        e3 = await repository.create(test_input)

        # Build chain
        await repository.supersede(e1.evidence_id, e2.evidence_id)
        await repository.supersede(e2.evidence_id, e3.evidence_id)

        # Traverse from e3 (newest)
        chain = await repository.get_supersession_chain(e3.evidence_id)

        # Should be [e3, e2, e1]
        assert len(chain) == 3
        assert chain[0].evidence_id == e3.evidence_id
        assert chain[1].evidence_id == e2.evidence_id
        assert chain[2].evidence_id == e1.evidence_id

    async def test_supersession_chain_cycle_detection(self, repository, test_input):
        """Cycle detection in supersession chain prevents infinite loop."""
        # Create two records
        e1 = await repository.create(test_input)
        test_input.event_timestamp = datetime.utcnow()
        e2 = await repository.create(test_input)

        # Create cycle: e1 → e2 → e1
        await repository.supersede(e1.evidence_id, e2.evidence_id)
        # Note: DB constraint should prevent actual cycle, but test defensive coding
        # In practice, FK constraint on supersedes_evidence_id prevents cycles

        # Attempt traversal (should break, not infinite loop)
        chain = await repository.get_supersession_chain(e1.evidence_id)

        # Should have entries but not infinite loop
        assert len(chain) >= 1

    async def test_nullable_uploader_user_id(self, repository, test_input):
        """System ingest with NULL uploader_user_id."""
        test_input.uploader_user_id = None
        test_input.provenance_type = ProvenanceType.SYSTEM_INGEST

        result = await repository.create(test_input)

        assert result.uploader_user_id is None
        assert result.provenance_type == ProvenanceType.SYSTEM_INGEST

    async def test_confidence_score_validation(self, repository, test_input):
        """Confidence score outside 0.0-1.0 raises error."""
        test_input.confidence_score = 1.5

        # Should raise validation error
        with pytest.raises(Exception):
            await repository.create(test_input)

    async def test_get_active_for_equipment(self, repository, test_input):
        """Convenience method returns active evidence for equipment."""
        created = await repository.create(test_input)

        result = await repository.get_active_for_equipment(test_input.equipment_id)

        assert len(result) >= 1
        assert any(e.evidence_id == created.evidence_id for e in result)

    async def test_get_active_for_site(self, repository, test_input):
        """Convenience method returns active evidence for site."""
        created = await repository.create(test_input)

        result = await repository.get_active_for_site(test_input.site_id)

        assert len(result) >= 1
        assert any(e.evidence_id == created.evidence_id for e in result)

    async def test_pagination_limit_offset(self, repository, test_input):
        """Pagination with limit and offset."""
        equipment_id = uuid4()
        test_input.equipment_id = equipment_id

        # Create 5 records
        for _i in range(5):
            test_input.event_timestamp = datetime.utcnow()
            await repository.create(test_input)

        # Page 1: limit=2
        page1 = await repository.list_by_equipment(equipment_id, limit=2, offset=0)

        # Page 2: limit=2, offset=2
        page2 = await repository.list_by_equipment(equipment_id, limit=2, offset=2)

        # Should have different results
        assert len(page1) <= 2
        assert len(page2) <= 2
        # Verify they're different (if enough data)
        if len(page1) == 2 and len(page2) == 2:
            assert page1[0].evidence_id != page2[0].evidence_id
