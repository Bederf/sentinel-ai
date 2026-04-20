"""
Budget Repository - Database operations for contract budgets.

Phase 48: Contract Management
"""

import logging
from typing import Any

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class BudgetRepository:
    """Repository for budget CRUD operations with template support."""

    def __init__(self):
        self.client = get_supabase_client()
        self._templates: dict[str, Any] | None = None
        self._load_templates()

    def get_by_contract(self, contract_id: str, year: int | None = None) -> list[dict[str, Any]]:
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
            query = (
                self.client.table("budgets")
                .select("*")
                .eq("contract_id", contract_id)
                .order("budget_year", desc=True)
                .order("budget_month")
            )

            if year:
                query = query.eq("budget_year", year)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting budgets for contract {contract_id}: {e}")
            return []

    def get_spending_summary(self, contract_id: str, year: int) -> dict[str, Any] | None:
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

            spend_pct = round((total_actual / total_budget * 100), 2) if total_budget > 0 else 0.0

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

    def create(self, data: dict[str, Any]) -> dict[str, Any] | None:
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

    def update(self, budget_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
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
            result = self.client.table("budgets").update(data).eq("id", budget_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error updating budget {budget_id}: {e}")
            return None

    def get_by_id(self, budget_id: str) -> dict[str, Any] | None:
        """Get a single budget entry by ID."""
        if not self.client:
            return None

        try:
            result = self.client.table("budgets").select("*").eq("id", budget_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting budget {budget_id}: {e}")
            return None

    def _load_templates(self) -> None:
        """
        Load budget templates from JSON file into memory cache.

        Templates are loaded once on initialization and cached for performance.
        """
        import json
        from pathlib import Path

        template_file = Path(__file__).parent.parent.parent / "data" / "budget_templates.json"

        if not template_file.exists():
            logger.warning(f"Budget templates file not found: {template_file}")
            self._templates = {}
            return

        try:
            with open(template_file) as f:
                self._templates = json.load(f)
            logger.info(f"Loaded {len(self._templates)} budget templates")
        except Exception as e:
            logger.error(f"Error loading budget templates: {e}")
            self._templates = {}

    def get_template(self, equipment_type: str) -> dict[str, Any] | None:
        """
        Get budget template for a specific equipment type.

        Args:
            equipment_type: Equipment type (chiller, ahu, generator, etc.)

        Returns:
            Template dict, or None if not found
        """
        return self._templates.get(equipment_type)

    def get_budget_templates(self) -> dict[str, Any]:
        """
        Get all available budget templates.

        Returns:
            Dict of all templates keyed by equipment_type
        """
        return self._templates.copy() if self._templates else {}

    def create_from_template(
        self, contract_id: str, equipment_type: str, year: int, month: int | None = None
    ) -> dict[str, Any] | None:
        """
        Create a budget entry using equipment-type template defaults.

        Args:
            contract_id: Contract UUID
            equipment_type: Equipment type for template lookup
            year: Budget year
            month: Optional budget month (1-12), if None creates annual budget

        Returns:
            Created budget dict, or None on error
        """
        template = self.get_template(equipment_type)
        if not template:
            logger.warning(f"No template found for equipment type: {equipment_type}")
            return None

        breakdown = template.get("typical_monthly_breakdown", {})

        # Generate unique code
        import uuid

        code = f"BUD-{equipment_type.upper()}-{year}"
        if month:
            code += f"-{month:02d}"

        budget_data = {
            "id": str(uuid.uuid4()),
            "code": code,
            "contract_id": contract_id,
            "equipment_type": equipment_type,
            "budget_year": year,
            "budget_month": month,
            "labor_budget_zar": breakdown.get("labor_budget_zar", 0.0),
            "parts_budget_zar": breakdown.get("parts_budget_zar", 0.0),
            "consumables_budget_zar": breakdown.get("consumables_budget_zar", 0.0),
            "subcontractor_budget_zar": breakdown.get("subcontractor_budget_zar", 0.0),
            "callout_budget_zar": breakdown.get("callout_budget_zar", 0.0),
            "warning_threshold_pct": 80.0,
            "critical_threshold_pct": 100.0,
            "status": "draft",
        }

        return self.create(budget_data)


# Singleton instance
_repository: BudgetRepository | None = None


def get_budget_repository() -> BudgetRepository:
    """Get singleton budget repository."""
    global _repository
    if _repository is None:
        _repository = BudgetRepository()
    return _repository
