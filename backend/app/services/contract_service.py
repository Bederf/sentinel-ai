"""
Contract Management Service - Business logic for FM commercial operations.

Provides contract lifecycle management, SLA term configuration,
equipment-contract linking, budget tracking, and condition assessments.

Phase 48: Contract Management

Usage:
    from app.services.contract_service import get_contract_service

    svc = get_contract_service()
    orgs = svc.get_organizations(tier="gold")
    contract = svc.create_contract(data)
    svc.approve_contract(contract_id, approved_by="admin@example.com")
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import logging

from app.models.contract import (
    AssetContractCreate,
    BudgetCreate,
    ConditionAssessmentCreate,
    ContractCreate,
    ContractStatus,
    OrganizationCreate,
    SLATermCreate,
)

logger = logging.getLogger(__name__)


class ContractManagementService:
    """
    Service layer for contract management business logic.

    Lazy-initializes repository singletons on first use. All methods
    return dicts (not Pydantic models) for API compatibility.
    """

    def __init__(self):
        """Initialize with lazy repository references."""
        self._org_repo = None
        self._contract_repo = None
        self._sla_repo = None
        self._budget_repo = None
        self._assessment_repo = None

    def _ensure_repos(self):
        """Lazy-initialize all repository singletons."""
        if self._org_repo is None:
            from app.database.repositories.organization_repository import (
                get_organization_repository,
            )

            self._org_repo = get_organization_repository()

        if self._contract_repo is None:
            from app.database.repositories.contract_repository import (
                get_contract_repository,
            )

            self._contract_repo = get_contract_repository()

        if self._sla_repo is None:
            from app.database.repositories.sla_terms_repository import (
                get_sla_terms_repository,
            )

            self._sla_repo = get_sla_terms_repository()

        if self._budget_repo is None:
            from app.database.repositories.budget_repository import (
                get_budget_repository,
            )

            self._budget_repo = get_budget_repository()

        if self._assessment_repo is None:
            from app.database.repositories.condition_assessment_repository import (
                get_condition_assessment_repository,
            )

            self._assessment_repo = get_condition_assessment_repository()

    # ========================================================================
    # Organization Methods
    # ========================================================================

    def create_organization(self, data: OrganizationCreate) -> Optional[Dict[str, Any]]:
        """
        Create a new organization after validating unique code.

        Args:
            data: OrganizationCreate model

        Returns:
            Created organization dict, or None on error/duplicate
        """
        self._ensure_repos()

        try:
            # Check for duplicate code
            existing = self._org_repo.get_by_code(data.code)
            if existing:
                logger.warning(f"Organization with code '{data.code}' already exists")
                return None

            payload = data.model_dump(exclude_none=True)
            return self._org_repo.create(payload)

        except Exception as e:
            logger.error(f"Error creating organization: {e}")
            return None

    def get_organizations(self, tier: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List organizations with optional tier filter.

        Args:
            tier: Filter by tier (platinum, gold, silver, bronze)

        Returns:
            List of organization dicts
        """
        self._ensure_repos()
        return self._org_repo.get_all(tier=tier)

    def get_organization(self, org_id: str) -> Optional[Dict[str, Any]]:
        """Get a single organization by ID."""
        self._ensure_repos()
        return self._org_repo.get_by_id(org_id)

    # ========================================================================
    # Contract Lifecycle Methods
    # ========================================================================

    def create_contract(self, data: ContractCreate) -> Optional[Dict[str, Any]]:
        """
        Create a new contract with status=draft.

        Validates that organization and building exist before creating.

        Args:
            data: ContractCreate model

        Returns:
            Created contract dict, or None on error
        """
        self._ensure_repos()

        try:
            # Validate organization exists
            org = self._org_repo.get_by_id(data.organization_id)
            if not org:
                logger.warning(f"Organization {data.organization_id} not found")
                return None

            payload = data.model_dump(exclude_none=True)

            # Convert date objects to ISO strings for JSON serialization
            if "start_date" in payload:
                payload["start_date"] = str(payload["start_date"])
            if "end_date" in payload:
                payload["end_date"] = str(payload["end_date"])

            # Force draft status on creation
            payload["status"] = ContractStatus.DRAFT.value

            return self._contract_repo.create(payload)

        except Exception as e:
            logger.error(f"Error creating contract: {e}")
            return None

    def approve_contract(self, contract_id: str, approved_by: str) -> Optional[Dict[str, Any]]:
        """
        Transition contract from draft/pending_approval to active.

        Args:
            contract_id: Contract UUID
            approved_by: Email or name of approver

        Returns:
            Updated contract dict, or None if invalid transition
        """
        self._ensure_repos()

        try:
            contract = self._contract_repo.get_by_id(contract_id)
            if not contract:
                logger.warning(f"Contract {contract_id} not found")
                return None

            current_status = contract.get("status")
            if current_status not in ("draft", "pending_approval"):
                logger.warning(f"Cannot approve contract in status '{current_status}'")
                return None

            return self._contract_repo.update(
                contract_id,
                {
                    "status": ContractStatus.ACTIVE.value,
                    "approved_by": approved_by,
                    "approved_at": datetime.utcnow().isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error approving contract {contract_id}: {e}")
            return None

    def suspend_contract(self, contract_id: str, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Transition contract from active to suspended.

        Args:
            contract_id: Contract UUID
            reason: Reason for suspension (stored in notes)

        Returns:
            Updated contract dict, or None if invalid transition
        """
        self._ensure_repos()

        try:
            contract = self._contract_repo.get_by_id(contract_id)
            if not contract:
                return None

            if contract.get("status") != "active":
                logger.warning(f"Cannot suspend contract in status '{contract.get('status')}'")
                return None

            update_data: Dict[str, Any] = {
                "status": ContractStatus.SUSPENDED.value,
            }
            if reason:
                existing_notes = contract.get("notes") or ""
                suspension_note = f"\n[SUSPENDED {datetime.utcnow().isoformat()}] {reason}"
                update_data["notes"] = existing_notes + suspension_note

            return self._contract_repo.update(contract_id, update_data)

        except Exception as e:
            logger.error(f"Error suspending contract {contract_id}: {e}")
            return None

    def expire_contract(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """
        Transition contract from active to expired.

        Args:
            contract_id: Contract UUID

        Returns:
            Updated contract dict, or None if invalid transition
        """
        self._ensure_repos()

        try:
            contract = self._contract_repo.get_by_id(contract_id)
            if not contract:
                return None

            if contract.get("status") != "active":
                logger.warning(f"Cannot expire contract in status '{contract.get('status')}'")
                return None

            return self._contract_repo.update(
                contract_id,
                {
                    "status": ContractStatus.EXPIRED.value,
                },
            )

        except Exception as e:
            logger.error(f"Error expiring contract {contract_id}: {e}")
            return None

    def get_contract_summary(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive contract summary including org, SLAs, and budget.

        Args:
            contract_id: Contract UUID

        Returns:
            Dict with contract details, organization, sla_terms, and budget_summary
        """
        self._ensure_repos()

        try:
            contract = self._contract_repo.get_by_id(contract_id)
            if not contract:
                return None

            # Get SLA terms
            sla_terms = self._sla_repo.get_by_contract(contract_id)

            # Get budget summary for current year
            current_year = datetime.utcnow().year
            budget_summary = self._budget_repo.get_spending_summary(contract_id, current_year)

            # Get equipment count
            equipment = self.get_contract_equipment(contract_id)

            return {
                "contract": contract,
                "sla_terms": sla_terms,
                "budget_summary": budget_summary,
                "equipment_count": len(equipment),
            }

        except Exception as e:
            logger.error(f"Error getting contract summary {contract_id}: {e}")
            return None

    def get_contracts(
        self, building_id: Optional[str] = None, organization_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List contracts with optional filters."""
        self._ensure_repos()
        return self._contract_repo.get_all(
            building_id=building_id,
            organization_id=organization_id,
            status=status,
        )

    def get_active_contracts(self) -> List[Dict[str, Any]]:
        """Get all active contracts."""
        self._ensure_repos()
        return self._contract_repo.get_active()

    # ========================================================================
    # SLA Methods
    # ========================================================================

    def set_sla_terms(self, contract_id: str, terms: List[SLATermCreate]) -> List[Dict[str, Any]]:
        """
        Replace all SLA terms for a contract.

        Deletes existing terms and inserts new ones.

        Args:
            contract_id: Contract UUID
            terms: List of SLATermCreate models

        Returns:
            List of created SLA term dicts
        """
        self._ensure_repos()

        try:
            # Delete existing terms
            self._sla_repo.delete_by_contract(contract_id)

            # Insert new terms
            payloads = []
            for term in terms:
                payload = term.model_dump(exclude_none=True)
                payload["contract_id"] = contract_id
                payloads.append(payload)

            if payloads:
                return self._sla_repo.create_many(payloads)
            return []

        except Exception as e:
            logger.error(f"Error setting SLA terms for {contract_id}: {e}")
            return []

    def get_sla_terms(self, contract_id: str) -> List[Dict[str, Any]]:
        """Get current SLA terms for a contract."""
        self._ensure_repos()
        return self._sla_repo.get_by_contract(contract_id)

    # ========================================================================
    # Asset Linking Methods
    # ========================================================================

    def assign_equipment_to_contract(
        self, contract_id: str, equipment_id: str, data: AssetContractCreate
    ) -> Optional[Dict[str, Any]]:
        """
        Link equipment to a contract via the asset_contracts table.

        Args:
            contract_id: Contract UUID
            equipment_id: Equipment UUID
            data: AssetContractCreate model

        Returns:
            Created asset contract link dict, or None on error
        """
        self._ensure_repos()

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            if not client:
                return None

            payload = data.model_dump(exclude_none=True)
            payload["contract_id"] = contract_id
            payload["equipment_id"] = equipment_id

            result = client.table("asset_contracts").insert(payload).execute()

            if result.data and len(result.data) > 0:
                logger.info(f"Assigned equipment {equipment_id} to contract {contract_id}")
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error assigning equipment {equipment_id} to contract {contract_id}: {e}")
            return None

    def get_contract_equipment(self, contract_id: str) -> List[Dict[str, Any]]:
        """
        List all equipment assigned to a contract.

        Args:
            contract_id: Contract UUID

        Returns:
            List of asset contract dicts with equipment details
        """
        self._ensure_repos()

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            if not client:
                return []

            result = (
                client.table("asset_contracts")
                .select("*, equipment(code, name, type)")
                .eq("contract_id", contract_id)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.error(f"Error getting equipment for contract {contract_id}: {e}")
            return []

    # ========================================================================
    # Budget Methods
    # ========================================================================

    def set_budget(self, contract_id: str, data: BudgetCreate) -> Optional[Dict[str, Any]]:
        """
        Create a budget entry for a contract period.

        Args:
            contract_id: Contract UUID
            data: BudgetCreate model

        Returns:
            Created budget dict, or None on error
        """
        self._ensure_repos()

        try:
            payload = data.model_dump(exclude_none=True)
            payload["contract_id"] = contract_id
            return self._budget_repo.create(payload)

        except Exception as e:
            logger.error(f"Error setting budget for {contract_id}: {e}")
            return None

    def get_budget_variance(self, contract_id: str, year: int) -> Optional[Dict[str, Any]]:
        """
        Get budget vs actual variance for a contract year.

        Args:
            contract_id: Contract UUID
            year: Budget year

        Returns:
            Spending summary dict with totals and variance
        """
        self._ensure_repos()
        return self._budget_repo.get_spending_summary(contract_id, year)

    # ========================================================================
    # Condition Assessment Methods
    # ========================================================================

    def record_assessment(self, data: ConditionAssessmentCreate) -> Optional[Dict[str, Any]]:
        """
        Record a condition assessment for equipment or building.

        Args:
            data: ConditionAssessmentCreate model

        Returns:
            Created assessment dict, or None on error
        """
        self._ensure_repos()

        try:
            payload = data.model_dump(exclude_none=True)

            # Convert date to string for serialization
            if "assessment_date" in payload:
                payload["assessment_date"] = str(payload["assessment_date"])

            return self._assessment_repo.create(payload)

        except Exception as e:
            logger.error(f"Error recording assessment: {e}")
            return None

    def get_equipment_condition(self, equipment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest condition assessment for equipment.

        Args:
            equipment_id: Equipment UUID

        Returns:
            Latest assessment dict, or None if no assessments
        """
        self._ensure_repos()
        return self._assessment_repo.get_latest_for_equipment(equipment_id)


# ============================================================================
# Singleton Factory
# ============================================================================

_service: Optional[ContractManagementService] = None


def get_contract_service() -> ContractManagementService:
    """
    Get singleton instance of ContractManagementService.

    Returns:
        ContractManagementService instance with lazy-initialized repositories.
    """
    global _service
    if _service is None:
        _service = ContractManagementService()
    return _service
