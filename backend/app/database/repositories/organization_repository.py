"""
Organization Repository - Database operations for FM client organizations.

Phase 48: Contract Management
"""

from typing import Optional, List, Dict, Any
from ..supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)


class OrganizationRepository:
    """Repository for organization CRUD operations."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_all(
        self, tier: Optional[str] = None, status: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List organizations with optional filters.

        Args:
            tier: Filter by tier (platinum, gold, silver, bronze)
            status: Filter by status (active, suspended, terminated)
            limit: Maximum results to return

        Returns:
            List of organization dicts
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        try:
            query = self.client.table("organizations").select("*").order("name").limit(limit)

            if tier:
                query = query.eq("tier", tier)
            if status:
                query = query.eq("status", status)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error listing organizations: {e}")
            return []

    def get_by_id(self, org_id: str) -> Optional[Dict[str, Any]]:
        """Get a single organization by ID."""
        if not self.client:
            return None

        try:
            result = self.client.table("organizations").select("*").eq("id", org_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting organization {org_id}: {e}")
            return None

    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Get a single organization by its unique code."""
        if not self.client:
            return None

        try:
            result = self.client.table("organizations").select("*").eq("code", code).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting organization by code {code}: {e}")
            return None

    def create(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new organization.

        Args:
            data: Organization data (code, name, tier, contact fields, etc.)

        Returns:
            Created organization dict with generated id, or None on error
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            result = self.client.table("organizations").insert(data).execute()

            if result.data and len(result.data) > 0:
                created = result.data[0]
                logger.info(f"Created organization: {created.get('code')}")
                return created
            return None

        except Exception as e:
            logger.error(f"Error creating organization: {e}")
            return None

    def update(self, org_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Partial update of an organization.

        Args:
            org_id: Organization UUID
            data: Fields to update

        Returns:
            Updated organization dict, or None on error
        """
        if not self.client:
            return None

        try:
            result = self.client.table("organizations").update(data).eq("id", org_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error updating organization {org_id}: {e}")
            return None


# Singleton instance
_repository: Optional[OrganizationRepository] = None


def get_organization_repository() -> OrganizationRepository:
    """Get singleton organization repository."""
    global _repository
    if _repository is None:
        _repository = OrganizationRepository()
    return _repository
