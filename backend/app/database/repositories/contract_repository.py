"""
Contract Repository - Database operations for FM contracts.

Phase 48: Contract Management
"""

from typing import Optional, List, Dict, Any
from ..supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)


class ContractRepository:
    """Repository for contract CRUD operations."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_all(
        self,
        building_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List contracts with optional filters.

        Args:
            building_id: Filter by building UUID
            organization_id: Filter by organization UUID
            status: Filter by status (draft, active, expired, etc.)
            limit: Maximum results to return

        Returns:
            List of contract dicts
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        try:
            query = self.client.table("contracts").select(
                "*, organizations(code, name), buildings(code, name)"
            ).order("created_at", desc=True).limit(limit)

            if building_id:
                query = query.eq("building_id", building_id)
            if organization_id:
                query = query.eq("organization_id", organization_id)
            if status:
                query = query.eq("status", status)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error listing contracts: {e}")
            return []

    def get_by_id(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Get a single contract by ID with org and building details."""
        if not self.client:
            return None

        try:
            result = self.client.table("contracts").select(
                "*, organizations(code, name, tier), buildings(code, name)"
            ).eq("id", contract_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting contract {contract_id}: {e}")
            return None

    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Get a single contract by its unique code."""
        if not self.client:
            return None

        try:
            result = self.client.table("contracts").select(
                "*, organizations(code, name), buildings(code, name)"
            ).eq("code", code).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting contract by code {code}: {e}")
            return None

    def get_by_building(self, building_id: str) -> List[Dict[str, Any]]:
        """Get all contracts for a building."""
        if not self.client:
            return []

        try:
            result = self.client.table("contracts").select(
                "*, organizations(code, name)"
            ).eq("building_id", building_id).order(
                "created_at", desc=True
            ).execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting contracts for building {building_id}: {e}")
            return []

    def get_active(self) -> List[Dict[str, Any]]:
        """Get all active contracts."""
        if not self.client:
            return []

        try:
            result = self.client.table("contracts").select(
                "*, organizations(code, name), buildings(code, name)"
            ).eq("status", "active").order("created_at", desc=True).execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting active contracts: {e}")
            return []

    def create(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new contract.

        Args:
            data: Contract data (code, organization_id, building_id, fees, etc.)

        Returns:
            Created contract dict with generated id, or None on error
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            result = self.client.table("contracts").insert(data).execute()

            if result.data and len(result.data) > 0:
                created = result.data[0]
                logger.info(f"Created contract: {created.get('code')}")
                return created
            return None

        except Exception as e:
            logger.error(f"Error creating contract: {e}")
            return None

    def update(self, contract_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Partial update of a contract.

        Args:
            contract_id: Contract UUID
            data: Fields to update

        Returns:
            Updated contract dict, or None on error
        """
        if not self.client:
            return None

        try:
            result = self.client.table("contracts").update(
                data
            ).eq("id", contract_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error updating contract {contract_id}: {e}")
            return None

    def update_status(
        self,
        contract_id: str,
        status: str
    ) -> Optional[Dict[str, Any]]:
        """
        Update contract status.

        Args:
            contract_id: Contract UUID
            status: New status (draft, pending_approval, active, suspended, expired, terminated)

        Returns:
            Updated contract dict, or None on error
        """
        return self.update(contract_id, {"status": status})


# Singleton instance
_repository: Optional[ContractRepository] = None


def get_contract_repository() -> ContractRepository:
    """Get singleton contract repository."""
    global _repository
    if _repository is None:
        _repository = ContractRepository()
    return _repository
