"""
SLA Terms Repository - Database operations for contract SLA definitions.

Phase 48: Contract Management
"""

from typing import Optional, List, Dict, Any
from ..supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)


class SLATermsRepository:
    """Repository for SLA term CRUD operations."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_by_contract(self, contract_id: str) -> List[Dict[str, Any]]:
        """
        Get all SLA terms for a contract.

        Args:
            contract_id: Contract UUID

        Returns:
            List of SLA term dicts
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        try:
            result = self.client.table("sla_terms").select(
                "*"
            ).eq("contract_id", contract_id).order("sla_type").execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting SLA terms for contract {contract_id}: {e}")
            return []

    def create(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a single SLA term.

        Args:
            data: SLA term data (contract_id, sla_type, target_value, etc.)

        Returns:
            Created SLA term dict, or None on error
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            result = self.client.table("sla_terms").insert(data).execute()

            if result.data and len(result.data) > 0:
                created = result.data[0]
                logger.info(
                    f"Created SLA term: {created.get('sla_type')} "
                    f"for contract {created.get('contract_id')}"
                )
                return created
            return None

        except Exception as e:
            logger.error(f"Error creating SLA term: {e}")
            return None

    def create_many(self, terms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Bulk insert SLA terms.

        Args:
            terms: List of SLA term data dicts

        Returns:
            List of created SLA term dicts
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        if not terms:
            return []

        try:
            result = self.client.table("sla_terms").insert(terms).execute()

            created = result.data or []
            logger.info(f"Created {len(created)} SLA terms in bulk")
            return created

        except Exception as e:
            logger.error(f"Error bulk creating SLA terms: {e}")
            return []

    def update(self, term_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update an SLA term.

        Args:
            term_id: SLA term UUID
            data: Fields to update

        Returns:
            Updated SLA term dict, or None on error
        """
        if not self.client:
            return None

        try:
            result = self.client.table("sla_terms").update(
                data
            ).eq("id", term_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error updating SLA term {term_id}: {e}")
            return None

    def delete(self, term_id: str) -> bool:
        """
        Delete an SLA term.

        Args:
            term_id: SLA term UUID

        Returns:
            True if deleted successfully, False on error
        """
        if not self.client:
            return False

        try:
            self.client.table("sla_terms").delete().eq("id", term_id).execute()
            logger.info(f"Deleted SLA term: {term_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting SLA term {term_id}: {e}")
            return False

    def delete_by_contract(self, contract_id: str) -> bool:
        """
        Delete all SLA terms for a contract (used when replacing terms).

        Args:
            contract_id: Contract UUID

        Returns:
            True if deleted successfully, False on error
        """
        if not self.client:
            return False

        try:
            self.client.table("sla_terms").delete().eq(
                "contract_id", contract_id
            ).execute()
            logger.info(f"Deleted all SLA terms for contract: {contract_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting SLA terms for contract {contract_id}: {e}")
            return False


# Singleton instance
_repository: Optional[SLATermsRepository] = None


def get_sla_terms_repository() -> SLATermsRepository:
    """Get singleton SLA terms repository."""
    global _repository
    if _repository is None:
        _repository = SLATermsRepository()
    return _repository
