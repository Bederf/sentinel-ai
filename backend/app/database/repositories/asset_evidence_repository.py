"""
Asset Evidence Repository (Phase 171-02)

Async CRUD operations for asset evidence with immutability enforcement.
Supports querying, supersession chain traversal, and RLS integration.
"""

from typing import List, Optional
from uuid import UUID
import logging

from backend.app.models.asset_evidence import (
    AssetEvidence,
    CreateAssetEvidenceInput,
    AssetEvidenceFilter,
)
from backend.app.database import get_supabase_client

logger = logging.getLogger(__name__)


class AssetEvidenceRepository:
    """Repository for asset evidence CRUD and immutability management."""

    def __init__(self):
        """Initialize with Supabase client."""
        self.client = get_supabase_client()
        self.table_name = "asset_evidence"

    async def create(self, input: CreateAssetEvidenceInput) -> AssetEvidence:
        """
        Create new evidence record.

        Args:
            input: Evidence creation input

        Returns:
            Created evidence record with generated evidence_id

        Raises:
            Exception: If creation fails (FK constraint, RLS, etc.)
        """
        try:
            payload = {
                "site_id": str(input.site_id),
                "equipment_id": str(input.equipment_id),
                "source_type": input.source_type.value,
                "artifact_type": input.artifact_type.value,
                "evidence_class": input.evidence_class.value,
                "document_id": str(input.document_id) if input.document_id else None,
                "source_ref": input.source_ref,
                "event_timestamp": input.event_timestamp.isoformat(),
                "raw_payload": input.raw_payload,
                "normalized_payload": input.normalized_payload,
                "confidence_score": float(input.confidence_score),
                "assessment_relevance": input.assessment_relevance,
                "provenance_type": input.provenance_type.value,
                "provenance_uri": input.provenance_uri,
                "uploader_user_id": str(input.uploader_user_id) if input.uploader_user_id else None,
            }

            result = self.client.table(self.table_name).insert(payload).execute()

            if not result.data:
                raise Exception("Insert returned no data")

            return AssetEvidence(**result.data[0])

        except Exception as e:
            logger.error(f"Failed to create asset evidence: {e}")
            raise

    async def get(self, evidence_id: UUID) -> Optional[AssetEvidence]:
        """
        Retrieve evidence by ID.

        Args:
            evidence_id: Evidence UUID

        Returns:
            Evidence record or None if not found

        Raises:
            Exception: If query fails or RLS denies access
        """
        try:
            result = self.client.table(self.table_name).select("*").eq("evidence_id", str(evidence_id)).execute()

            if not result.data:
                return None

            return AssetEvidence(**result.data[0])

        except Exception as e:
            logger.error(f"Failed to retrieve asset evidence {evidence_id}: {e}")
            raise

    async def list_by_equipment(
        self,
        equipment_id: UUID,
        limit: int = 100,
        offset: int = 0,
        active_only: bool = False,
    ) -> List[AssetEvidence]:
        """
        Get all evidence for equipment, ordered by event_timestamp DESC.

        Args:
            equipment_id: Equipment UUID
            limit: Max records to return
            offset: Record offset for pagination
            active_only: Only return non-superseded evidence

        Returns:
            List of evidence records
        """
        try:
            query = self.client.table(self.table_name).select("*").eq("equipment_id", str(equipment_id))

            if active_only:
                query = query.is_("supersedes_evidence_id", "null")

            query = query.order("event_timestamp", desc=True).limit(limit).offset(offset)
            result = query.execute()

            return [AssetEvidence(**row) for row in result.data] if result.data else []

        except Exception as e:
            logger.error(f"Failed to list evidence for equipment {equipment_id}: {e}")
            raise

    async def list_by_site(
        self,
        site_id: UUID,
        limit: int = 100,
        offset: int = 0,
        active_only: bool = False,
    ) -> List[AssetEvidence]:
        """
        Get all evidence for site, ordered by event_timestamp DESC.

        Args:
            site_id: Site UUID
            limit: Max records to return
            offset: Record offset for pagination
            active_only: Only return non-superseded evidence

        Returns:
            List of evidence records
        """
        try:
            query = self.client.table(self.table_name).select("*").eq("site_id", str(site_id))

            if active_only:
                query = query.is_("supersedes_evidence_id", "null")

            query = query.order("event_timestamp", desc=True).limit(limit).offset(offset)
            result = query.execute()

            return [AssetEvidence(**row) for row in result.data] if result.data else []

        except Exception as e:
            logger.error(f"Failed to list evidence for site {site_id}: {e}")
            raise

    async def query(
        self,
        filter: AssetEvidenceFilter,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AssetEvidence]:
        """
        Flexible evidence query with optional filters.

        Args:
            filter: Filter criteria
            limit: Max records
            offset: Record offset

        Returns:
            List of evidence records matching filters
        """
        try:
            query = self.client.table(self.table_name).select("*")

            # Apply filters
            if filter.site_id:
                query = query.eq("site_id", str(filter.site_id))
            if filter.equipment_id:
                query = query.eq("equipment_id", str(filter.equipment_id))
            if filter.source_type:
                query = query.eq("source_type", filter.source_type.value)
            if filter.evidence_class:
                query = query.eq("evidence_class", filter.evidence_class.value)
            if filter.start_date:
                query = query.gte("event_timestamp", filter.start_date.isoformat())
            if filter.end_date:
                query = query.lte("event_timestamp", filter.end_date.isoformat())
            if filter.active_only:
                query = query.is_("supersedes_evidence_id", "null")

            query = query.order("event_timestamp", desc=True).limit(limit).offset(offset)
            result = query.execute()

            return [AssetEvidence(**row) for row in result.data] if result.data else []

        except Exception as e:
            logger.error(f"Failed to query asset evidence: {e}")
            raise

    async def supersede(
        self,
        old_evidence_id: UUID,
        new_evidence_id: UUID,
        reason: Optional[str] = None,
    ) -> AssetEvidence:
        """
        Mark old evidence as superseded by new evidence.

        Only service_role can perform this operation (soft supersession only, no deletion).

        Args:
            old_evidence_id: Evidence to supersede
            new_evidence_id: New evidence that supersedes it
            reason: Optional reason for supersession

        Returns:
            Updated evidence record

        Raises:
            Exception: If RLS denies (non-service-role) or update fails
        """
        try:
            result = (
                self.client.table(self.table_name)
                .update({"supersedes_evidence_id": str(new_evidence_id)})
                .eq("evidence_id", str(old_evidence_id))
                .execute()
            )

            if not result.data:
                raise Exception("Update returned no data")

            logger.info(f"Superseded evidence {old_evidence_id} with {new_evidence_id}: {reason or 'no reason'}")
            return AssetEvidence(**result.data[0])

        except Exception as e:
            logger.error(f"Failed to supersede evidence: {e}")
            raise

    async def get_supersession_chain(self, evidence_id: UUID) -> List[AssetEvidence]:
        """
        Get the chain of supersessions for a piece of evidence.

        Traverses the supersession chain: [new → old → older → ...]

        Args:
            evidence_id: Starting evidence ID

        Returns:
            Ordered list of evidence records in supersession chain

        Raises:
            Exception: If traversal encounters error (e.g., RLS denial)
        """
        chain = []
        current_id = evidence_id
        visited = set()

        try:
            while current_id:
                if current_id in visited:
                    logger.warning(f"Cycle detected in supersession chain starting from {evidence_id}")
                    break

                visited.add(current_id)

                evidence = await self.get(current_id)
                if not evidence:
                    break

                chain.append(evidence)

                # Move to next in chain (what this one supersedes)
                current_id = evidence.supersedes_evidence_id

            return chain

        except Exception as e:
            logger.error(f"Failed to traverse supersession chain from {evidence_id}: {e}")
            raise

    async def get_active_for_equipment(self, equipment_id: UUID) -> List[AssetEvidence]:
        """
        Get active (non-superseded) evidence for equipment.

        Convenience method that filters for supersedes_evidence_id IS NULL.

        Args:
            equipment_id: Equipment UUID

        Returns:
            List of active evidence records
        """
        return await self.list_by_equipment(equipment_id, active_only=True)

    async def get_active_for_site(self, site_id: UUID) -> List[AssetEvidence]:
        """
        Get active (non-superseded) evidence for site.

        Convenience method that filters for supersedes_evidence_id IS NULL.

        Args:
            site_id: Site UUID

        Returns:
            List of active evidence records
        """
        return await self.list_by_site(site_id, active_only=True)
