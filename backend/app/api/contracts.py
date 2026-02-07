"""
Contract Management API Endpoints
==================================
REST API for FM commercial intelligence: organizations, contracts,
SLA terms, equipment assignments, budgets, and condition assessments.

Phase 48: Contract Management

Prefix: /contracts (registered as /api/contracts in main.py)
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.contract import (
    AssetContractCreate,
    BudgetCreate,
    ConditionAssessmentCreate,
    ContractCreate,
    ContractUpdate,
    OrganizationCreate,
    OrganizationUpdate,
    SLATermCreate,
    SLATermUpdate,
)
from app.services.contract_service import get_contract_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contracts", tags=["contracts"])


# ============================================================================
# Helper request bodies
# ============================================================================


class StatusChangeRequest(BaseModel):
    """Request body for contract status change."""
    status: str
    reason: Optional[str] = None


# ============================================================================
# Organization Endpoints
# ============================================================================


@router.get("/organizations")
async def list_organizations(
    tier: Optional[str] = Query(None, description="Filter by tier (platinum, gold, silver, bronze)"),
):
    """
    List all organizations with optional tier filter.

    Returns all FM client organizations, optionally filtered by service tier.
    """
    svc = get_contract_service()
    orgs = svc.get_organizations(tier=tier)
    return {"organizations": orgs, "count": len(orgs)}


@router.post("/organizations", status_code=201)
async def create_organization(data: OrganizationCreate):
    """
    Create a new FM client organization.

    The organization code must be unique. Duplicates will return a 409 error.
    """
    svc = get_contract_service()
    result = svc.create_organization(data)
    if result is None:
        raise HTTPException(
            status_code=409,
            detail=f"Organization with code '{data.code}' already exists or creation failed",
        )
    return result


@router.get("/organizations/{org_id}")
async def get_organization(org_id: str):
    """
    Get a single organization by its UUID.
    """
    svc = get_contract_service()
    org = svc.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.put("/organizations/{org_id}")
async def update_organization(org_id: str, data: OrganizationUpdate):
    """
    Update an existing organization.

    Only provided fields are updated (partial update).
    """
    svc = get_contract_service()
    svc._ensure_repos()

    # Verify org exists
    existing = svc._org_repo.get_by_id(org_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Organization not found")

    update_payload = data.model_dump(exclude_none=True)
    if not update_payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = svc._org_repo.update(org_id, update_payload)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to update organization")
    return result


# ============================================================================
# Contract Endpoints
# ============================================================================


@router.get("/")
async def list_contracts(
    building_id: Optional[str] = Query(None, description="Filter by building UUID"),
    organization_id: Optional[str] = Query(None, description="Filter by organization UUID"),
    status: Optional[str] = Query(None, description="Filter by status (draft, active, expired, etc.)"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
):
    """
    List contracts with optional filters.

    Supports filtering by building, organization, and status.
    """
    svc = get_contract_service()
    contracts = svc.get_contracts(
        building_id=building_id,
        organization_id=organization_id,
        status=status,
    )
    return {"contracts": contracts[:limit], "count": len(contracts[:limit])}


@router.post("/", status_code=201)
async def create_contract(data: ContractCreate):
    """
    Create a new contract in draft status.

    Links an organization to a building with fee structure and terms.
    The contract starts in 'draft' status regardless of any status provided.
    """
    svc = get_contract_service()
    result = svc.create_contract(data)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Failed to create contract. Verify organization_id and building_id exist.",
        )
    return result


@router.get("/{contract_id}")
async def get_contract(contract_id: str):
    """
    Get a single contract by UUID, with summary info.

    Returns contract details along with organization, SLA count, and budget info.
    """
    svc = get_contract_service()
    summary = svc.get_contract_summary(contract_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return summary


@router.put("/{contract_id}")
async def update_contract(contract_id: str, data: ContractUpdate):
    """
    Update contract fields.

    Only provided fields are updated (partial update).
    Cannot be used to change status - use PATCH /status instead.
    """
    svc = get_contract_service()
    svc._ensure_repos()

    existing = svc._contract_repo.get_by_id(contract_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

    update_payload = data.model_dump(exclude_none=True)
    if not update_payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Convert date objects to ISO strings for JSON serialization
    for date_field in ("end_date",):
        if date_field in update_payload and update_payload[date_field] is not None:
            update_payload[date_field] = str(update_payload[date_field])
    if "approved_at" in update_payload and update_payload["approved_at"] is not None:
        update_payload["approved_at"] = update_payload["approved_at"].isoformat()

    result = svc._contract_repo.update(contract_id, update_payload)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to update contract")
    return result


@router.patch("/{contract_id}/status")
async def change_contract_status(contract_id: str, body: StatusChangeRequest):
    """
    Change contract lifecycle status.

    Valid transitions:
    - draft/pending_approval -> active (approve)
    - active -> suspended (suspend)
    - active -> expired (expire)
    - active -> terminated (terminate)
    - suspended -> active (reactivate)
    """
    svc = get_contract_service()
    target_status = body.status.lower()

    if target_status == "active":
        result = svc.approve_contract(
            contract_id, approved_by=body.reason or "api_user"
        )
    elif target_status == "suspended":
        result = svc.suspend_contract(contract_id, reason=body.reason)
    elif target_status == "expired":
        result = svc.expire_contract(contract_id)
    elif target_status == "terminated":
        # Terminate via direct repo update
        svc._ensure_repos()
        contract = svc._contract_repo.get_by_id(contract_id)
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        if contract.get("status") not in ("active", "suspended"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot terminate contract in status '{contract.get('status')}'",
            )
        update_data: Dict[str, Any] = {"status": "terminated"}
        if body.reason:
            existing_notes = contract.get("notes") or ""
            update_data["notes"] = (
                existing_notes
                + f"\n[TERMINATED {datetime.utcnow().isoformat()}] {body.reason}"
            )
        result = svc._contract_repo.update(contract_id, update_data)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target status: '{body.status}'. "
            "Valid: active, suspended, expired, terminated",
        )

    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"Status change to '{body.status}' failed. "
            "Check current status allows this transition.",
        )
    return result


@router.get("/{contract_id}/summary")
async def get_contract_summary(contract_id: str):
    """
    Get comprehensive contract summary.

    Returns contract details, organization info, SLA terms,
    budget summary, equipment count, and profitability data.
    """
    svc = get_contract_service()
    summary = svc.get_contract_summary(contract_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Enrich with organization data
    svc._ensure_repos()
    contract = summary.get("contract", {})
    org_id = contract.get("organization_id")
    if org_id:
        org = svc.get_organization(org_id)
        summary["organization"] = org

    return summary


# ============================================================================
# SLA Term Endpoints
# ============================================================================


@router.get("/{contract_id}/sla-terms")
async def list_sla_terms(contract_id: str):
    """
    List all SLA terms for a contract.

    Returns active and inactive terms with penalty configuration.
    """
    svc = get_contract_service()
    terms = svc.get_sla_terms(contract_id)
    return {"sla_terms": terms, "count": len(terms)}


@router.post("/{contract_id}/sla-terms", status_code=201)
async def add_sla_term(contract_id: str, data: SLATermCreate):
    """
    Add a single SLA term to a contract.

    The contract_id in the URL takes precedence over any contract_id in the body.
    """
    svc = get_contract_service()
    svc._ensure_repos()

    # Verify contract exists
    contract = svc._contract_repo.get_by_id(contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    payload = data.model_dump(exclude_none=True)
    payload["contract_id"] = contract_id

    result = svc._sla_repo.create(payload)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to create SLA term")
    return result


@router.put("/sla-terms/{term_id}")
async def update_sla_term(term_id: str, data: SLATermUpdate):
    """
    Update an existing SLA term.

    Only provided fields are updated.
    """
    svc = get_contract_service()
    svc._ensure_repos()

    update_payload = data.model_dump(exclude_none=True)
    if not update_payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = svc._sla_repo.update(term_id, update_payload)
    if result is None:
        raise HTTPException(status_code=404, detail="SLA term not found")
    return result


@router.delete("/sla-terms/{term_id}", status_code=204)
async def delete_sla_term(term_id: str):
    """
    Remove an SLA term by ID.
    """
    svc = get_contract_service()
    svc._ensure_repos()

    success = svc._sla_repo.delete(term_id)
    if not success:
        raise HTTPException(status_code=404, detail="SLA term not found")
    return None


# ============================================================================
# Asset (Equipment) Assignment Endpoints
# ============================================================================


@router.get("/{contract_id}/equipment")
async def list_contract_equipment(contract_id: str):
    """
    List all equipment assigned to a contract.

    Returns equipment details with coverage type, fee allocation, and criticality.
    """
    svc = get_contract_service()
    equipment = svc.get_contract_equipment(contract_id)
    return {"equipment": equipment, "count": len(equipment)}


@router.post("/{contract_id}/equipment", status_code=201)
async def assign_equipment(contract_id: str, data: AssetContractCreate):
    """
    Assign equipment to a contract.

    Links a piece of equipment with fee allocation and coverage configuration.
    """
    svc = get_contract_service()

    # Override contract_id from URL
    result = svc.assign_equipment_to_contract(
        contract_id=contract_id,
        equipment_id=data.equipment_id,
        data=data,
    )
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Failed to assign equipment. Verify contract and equipment IDs.",
        )
    return result


@router.delete("/{contract_id}/equipment/{equipment_id}", status_code=204)
async def unassign_equipment(contract_id: str, equipment_id: str):
    """
    Remove equipment from a contract.
    """
    svc = get_contract_service()
    svc._ensure_repos()

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            raise HTTPException(status_code=500, detail="Database unavailable")

        result = (
            client.table("asset_contracts")
            .delete()
            .eq("contract_id", contract_id)
            .eq("equipment_id", equipment_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Equipment assignment not found for this contract",
            )
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unassigning equipment: {e}")
        raise HTTPException(status_code=500, detail="Failed to unassign equipment")


# ============================================================================
# Budget Endpoints
# ============================================================================


@router.get("/{contract_id}/budgets")
async def list_budgets(
    contract_id: str,
    year: Optional[int] = Query(None, description="Filter by budget year"),
):
    """
    List budget entries for a contract.

    Optionally filter by year. Returns budget vs actual amounts.
    """
    svc = get_contract_service()
    svc._ensure_repos()

    budgets = svc._budget_repo.get_by_contract(contract_id, year=year)
    return {"budgets": budgets, "count": len(budgets)}


@router.post("/{contract_id}/budgets", status_code=201)
async def create_budget(contract_id: str, data: BudgetCreate):
    """
    Create a budget entry for a contract period.

    Sets planned budget amounts by cost category (labor, parts, consumables, etc.).
    """
    svc = get_contract_service()

    result = svc.set_budget(contract_id=contract_id, data=data)
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to create budget entry")
    return result


@router.get("/{contract_id}/budget-variance")
async def get_budget_variance(
    contract_id: str,
    year: int = Query(..., description="Budget year for variance calculation"),
):
    """
    Get budget vs actual variance report for a contract year.

    Returns total budgeted, total actual, variance, and per-category breakdown.
    """
    svc = get_contract_service()
    variance = svc.get_budget_variance(contract_id, year)
    if variance is None:
        return {
            "contract_id": contract_id,
            "year": year,
            "message": "No budget data found for this period",
            "total_budget_zar": 0,
            "total_actual_zar": 0,
            "variance_zar": 0,
        }
    return variance


# ============================================================================
# Budget Template Endpoints (Phase 49)
# ============================================================================


@router.get("/budgets/templates")
async def get_budget_templates():
    """
    Get all available budget templates by equipment type.

    Returns template definitions with typical monthly breakdowns for
    different equipment categories (chiller, AHU, generator, etc.).
    """
    from app.database.repositories.budget_repository import get_budget_repository

    repo = get_budget_repository()
    templates = repo.get_budget_templates()
    return {"templates": templates, "count": len(templates)}


@router.get("/budgets/templates/{equipment_type}")
async def get_budget_template(equipment_type: str):
    """
    Get budget template for a specific equipment type.

    Args:
        equipment_type: Equipment type (chiller, ahu, generator, dali_controller, power_meter)

    Returns:
        Template dict with labor rate, planned hours, and monthly breakdown
    """
    from app.database.repositories.budget_repository import get_budget_repository

    repo = get_budget_repository()
    template = repo.get_template(equipment_type)

    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"No budget template found for equipment type: {equipment_type}"
        )

    return template


@router.post("/budgets/from-template", status_code=201)
async def create_budget_from_template(
    contract_id: str = Query(..., description="Contract UUID"),
    equipment_type: str = Query(..., description="Equipment type for template lookup"),
    year: int = Query(..., description="Budget year", ge=2020, le=2100),
    month: Optional[int] = Query(None, description="Budget month (1-12), if None creates annual budget", ge=1, le=12)
):
    """
    Create a budget entry using equipment-type template defaults.

    Automatically populates budget amounts from the predefined template
    for the specified equipment type. Templates include typical monthly
    breakdowns for labor, parts, consumables, subcontractor, and callout costs.

    Args:
        contract_id: Contract UUID to link budget to
        equipment_type: Equipment type (chiller, ahu, generator, dali_controller, power_meter)
        year: Budget year (e.g., 2026)
        month: Optional budget month (1-12). If omitted, creates annual budget

    Returns:
        Created budget entry with template-based amounts
    """
    from app.database.repositories.budget_repository import get_budget_repository

    repo = get_budget_repository()

    # Validate template exists
    template = repo.get_template(equipment_type)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"No budget template found for equipment type: {equipment_type}. "
                   f"Available types: chiller, ahu, generator, dali_controller, power_meter"
        )

    # Create budget from template
    budget = repo.create_from_template(contract_id, equipment_type, year, month)

    if not budget:
        raise HTTPException(
            status_code=500,
            detail="Failed to create budget from template"
        )

    return budget


# ============================================================================
# Condition Assessment Endpoints
# ============================================================================


@router.get("/assessments")
async def list_assessments(
    building_id: Optional[str] = Query(None, description="Filter by building UUID"),
):
    """
    List all condition assessments.

    Optionally filter by building. Returns assessments sorted by date descending.
    """
    svc = get_contract_service()
    svc._ensure_repos()

    assessments = svc._assessment_repo.get_all(building_id=building_id)
    return {"assessments": assessments, "count": len(assessments)}


@router.post("/assessments", status_code=201)
async def create_assessment(data: ConditionAssessmentCreate):
    """
    Create a condition assessment for equipment or a building.

    Records inspection scores, findings, defects, and recommendations.
    """
    svc = get_contract_service()
    result = svc.record_assessment(data)
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to create assessment")
    return result


@router.get("/assessments/equipment/{equipment_id}")
async def get_equipment_assessment(equipment_id: str):
    """
    Get the latest condition assessment for a piece of equipment.

    Returns the most recent assessment with scores and findings.
    """
    svc = get_contract_service()
    assessment = svc.get_equipment_condition(equipment_id)
    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail=f"No assessments found for equipment {equipment_id}",
        )
    return assessment


# ============================================================================
# Profitability Analytics Endpoints (Phase 51)
# ============================================================================


@router.get("/profitability/portfolio")
async def get_portfolio_profitability(
    period_start: Optional[str] = Query(None, description="Period start (YYYY-MM-DD)"),
    period_end: Optional[str] = Query(None, description="Period end (YYYY-MM-DD)"),
):
    """
    Get portfolio-wide profitability metrics.

    Returns aggregated revenue, costs, margins, and contract counts
    across all active contracts for the specified period.
    """
    from datetime import datetime
    from app.services.profitability_service import get_profitability_service

    # Default to current month
    if not period_start:
        today = date.today()
        period_start = today.replace(day=1).isoformat()
    if not period_end:
        from datetime import timedelta
        today = date.today()
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        period_end = (next_month - timedelta(days=1)).isoformat()

    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)

    service = get_profitability_service()
    metrics = service.calculate_portfolio_metrics(start_date, end_date)
    return metrics


@router.get("/profitability/contract/{contract_id}")
async def get_contract_profitability(
    contract_id: str,
    period_start: Optional[str] = Query(None, description="Period start (YYYY-MM-DD)"),
    period_end: Optional[str] = Query(None, description="Period end (YYYY-MM-DD)"),
):
    """
    Get detailed profitability for a single contract.

    Returns revenue breakdown, cost components, margin analysis,
    trend data, and asset metrics for the specified contract.
    """
    from app.services.profitability_service import get_profitability_service

    # Default to current month
    if not period_start:
        today = date.today()
        period_start = today.replace(day=1).isoformat()
    if not period_end:
        from datetime import timedelta
        today = date.today()
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        period_end = (next_month - timedelta(days=1)).isoformat()

    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)

    service = get_profitability_service()
    profitability = service.calculate_contract_profitability(
        contract_id, start_date, end_date
    )
    return profitability


@router.get("/profitability/loss-leaders")
async def get_loss_leaders(
    period_start: Optional[str] = Query(None, description="Period start (YYYY-MM-DD)"),
    period_end: Optional[str] = Query(None, description="Period end (YYYY-MM-DD)"),
):
    """
    Get list of loss-making contracts with root cause analysis.

    Returns contracts with negative margins, identified root causes,
    actionable recommendations, and cumulative loss tracking.
    """
    from app.services.profitability_service import get_profitability_service

    # Default to current month
    if not period_start:
        today = date.today()
        period_start = today.replace(day=1).isoformat()
    if not period_end:
        from datetime import timedelta
        today = date.today()
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        period_end = (next_month - timedelta(days=1)).isoformat()

    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)

    service = get_profitability_service()
    loss_leaders = service.identify_loss_leaders(start_date, end_date)
    return {"loss_leaders": loss_leaders, "count": len(loss_leaders)}


@router.get("/profitability/trends/{contract_id}")
async def get_profitability_trends(
    contract_id: str,
    months: int = Query(12, ge=1, le=24, description="Number of months to analyze"),
):
    """
    Get monthly profitability trends for a contract.

    Returns historical profitability data with trend indicators
    (improving, stable, declining) for each month.
    """
    from app.services.profitability_service import get_profitability_service

    service = get_profitability_service()
    trends = service.calculate_profitability_trends(contract_id, months)
    return {"contract_id": contract_id, "trends": trends}


@router.get("/profitability/asset-roi/{contract_id}/{equipment_id}")
async def get_asset_roi(
    contract_id: str,
    equipment_id: str,
):
    """
    Get ROI calculation for a specific asset within a contract.

    Returns allocated revenue, costs, margin, and ROI percentage
    for individual equipment.
    """
    from app.services.profitability_service import get_profitability_service

    service = get_profitability_service()
    roi = service.calculate_asset_roi(contract_id, equipment_id)
    return roi
