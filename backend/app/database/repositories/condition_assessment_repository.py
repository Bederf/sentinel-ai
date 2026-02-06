"""
Condition Assessment Repository - Database operations for equipment/building assessments.

Phase 48: Contract Management
"""

from typing import Optional, List, Dict, Any
from ..supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)


class ConditionAssessmentRepository:
    """Repository for condition assessment CRUD operations."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_by_building(self, building_id: str) -> List[Dict[str, Any]]:
        """
        Get all condition assessments for a building.

        Args:
            building_id: Building UUID

        Returns:
            List of assessment dicts ordered by date descending
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        try:
            result = self.client.table("condition_assessments").select(
                "*"
            ).eq("building_id", building_id).order(
                "assessment_date", desc=True
            ).execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting assessments for building {building_id}: {e}")
            return []

    def get_latest_for_equipment(
        self,
        equipment_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent assessment for a specific equipment item.

        Args:
            equipment_id: Equipment UUID

        Returns:
            Latest assessment dict, or None if no assessments exist
        """
        if not self.client:
            return None

        try:
            result = self.client.table("condition_assessments").select(
                "*"
            ).eq("equipment_id", equipment_id).order(
                "assessment_date", desc=True
            ).limit(1).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(
                f"Error getting latest assessment for equipment {equipment_id}: {e}"
            )
            return None

    def create(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new condition assessment.

        Args:
            data: Assessment data (code, building_id/equipment_id, scores, etc.)

        Returns:
            Created assessment dict, or None on error
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            result = self.client.table("condition_assessments").insert(
                data
            ).execute()

            if result.data and len(result.data) > 0:
                created = result.data[0]
                logger.info(f"Created condition assessment: {created.get('code')}")
                return created
            return None

        except Exception as e:
            logger.error(f"Error creating condition assessment: {e}")
            return None

    def get_by_id(self, assessment_id: str) -> Optional[Dict[str, Any]]:
        """Get a single assessment by ID."""
        if not self.client:
            return None

        try:
            result = self.client.table("condition_assessments").select(
                "*"
            ).eq("id", assessment_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting assessment {assessment_id}: {e}")
            return None

    def get_by_contract(self, contract_id: str) -> List[Dict[str, Any]]:
        """
        Get all assessments linked to a contract.

        Args:
            contract_id: Contract UUID

        Returns:
            List of assessment dicts
        """
        if not self.client:
            return []

        try:
            result = self.client.table("condition_assessments").select(
                "*"
            ).eq("contract_id", contract_id).order(
                "assessment_date", desc=True
            ).execute()

            return result.data or []

        except Exception as e:
            logger.error(
                f"Error getting assessments for contract {contract_id}: {e}"
            )
            return []

    def update(
        self,
        assessment_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an assessment.

        Args:
            assessment_id: Assessment UUID
            data: Fields to update

        Returns:
            Updated assessment dict, or None on error
        """
        if not self.client:
            return None

        try:
            result = self.client.table("condition_assessments").update(
                data
            ).eq("id", assessment_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error updating assessment {assessment_id}: {e}")
            return None


# Singleton instance
_repository: Optional[ConditionAssessmentRepository] = None


def get_condition_assessment_repository() -> ConditionAssessmentRepository:
    """Get singleton condition assessment repository."""
    global _repository
    if _repository is None:
        _repository = ConditionAssessmentRepository()
    return _repository
