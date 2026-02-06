"""
Budget Repository - Database operations for contract budgets.

Phase 48: Contract Management
"""

from typing import Optional, List, Dict, Any
from ..supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)


class BudgetRepository:
    """Repository for budget CRUD operations."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_by_contract(
        self,
        contract_id: str,
        year: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get budgets for a contract with optional year filter.

        Args:
            contract_id: Contract UUID
            year: Optional budget year filter

        Returns:
            List of budget dicts
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        try:
            query = self.client.table("budgets").select(
                "*"
            ).eq("contract_id", contract_id).order(
                "budget_year", desc=True
            ).order("budget_month")

            if year:
                query = query.eq("budget_year", year)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting budgets for contract {contract_id}: {e}")
            return []

    def get_spending_summary(
        self,
        contract_id: str,
        year: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get aggregate budget vs actual for a contract year.

        Uses the v_budget_summary view if available, otherwise aggregates manually.

        Args:
            contract_id: Contract UUID
            year: Budget year

        Returns:
            Summary dict with totals, or None on error
        """
        if not self.client:
            return None

        try:
            # Get all budget entries for the contract/year
            budgets = self.get_by_contract(contract_id, year)

            if not budgets:
                return None

            # Aggregate
            total_budget = sum(b.get("total_budget_zar", 0) or 0 for b in budgets)
            total_actual = sum(b.get("total_actual_zar", 0) or 0 for b in budgets)
            total_variance = sum(b.get("variance_zar", 0) or 0 for b in budgets)

            spend_pct = round(
                (total_actual / total_budget * 100), 2
            ) if total_budget > 0 else 0.0

            return {
                "contract_id": contract_id,
                "year": year,
                "total_budget_zar": total_budget,
                "total_actual_zar": total_actual,
                "variance_zar": total_variance,
                "spend_percentage": spend_pct,
                "budget_count": len(budgets),
            }

        except Exception as e:
            logger.error(f"Error getting spending summary: {e}")
            return None

    def create(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new budget entry.

        Args:
            data: Budget data (code, contract_id, budget_year, amounts, etc.)

        Returns:
            Created budget dict, or None on error
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            result = self.client.table("budgets").insert(data).execute()

            if result.data and len(result.data) > 0:
                created = result.data[0]
                logger.info(f"Created budget: {created.get('code')}")
                return created
            return None

        except Exception as e:
            logger.error(f"Error creating budget: {e}")
            return None

    def update(self, budget_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update a budget entry (typically actuals).

        Args:
            budget_id: Budget UUID
            data: Fields to update

        Returns:
            Updated budget dict, or None on error
        """
        if not self.client:
            return None

        try:
            result = self.client.table("budgets").update(
                data
            ).eq("id", budget_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error updating budget {budget_id}: {e}")
            return None

    def get_by_id(self, budget_id: str) -> Optional[Dict[str, Any]]:
        """Get a single budget entry by ID."""
        if not self.client:
            return None

        try:
            result = self.client.table("budgets").select(
                "*"
            ).eq("id", budget_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting budget {budget_id}: {e}")
            return None


# Singleton instance
_repository: Optional[BudgetRepository] = None


def get_budget_repository() -> BudgetRepository:
    """Get singleton budget repository."""
    global _repository
    if _repository is None:
        _repository = BudgetRepository()
    return _repository
