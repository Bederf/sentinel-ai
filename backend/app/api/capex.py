"""CapEx Planning API endpoints (Phase 128).

Provides replace-vs-repair analysis, portfolio CapEx planning,
budget forecasting, and what-if scenario modeling.
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import capex_planning_service

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request/Response Models
# --------------------------------------------------------------------------- #


class ScenarioRequest(BaseModel):
    """Request for what-if scenario analysis."""

    equipment_type: str = Field(..., description="Equipment type (e.g. chiller, ahu)")
    age_years: float = Field(..., ge=0, description="Current equipment age in years")
    health_score: float = Field(..., ge=0, le=100, description="Current health score (0-100)")
    replacement_cost_zar: Optional[float] = Field(None, ge=0, description="Override replacement cost")
    repair_cost_zar: Optional[float] = Field(None, ge=0, description="Override repair cost")
    annual_maintenance_zar: Optional[float] = Field(None, ge=0, description="Override annual maintenance")
    condition_score: Optional[float] = Field(None, ge=0, le=100, description="Condition score from inspection")
    scenarios: List[Dict[str, Any]] = Field(
        ...,
        description="List of scenario parameter overrides. Each dict may contain: "
        "name, discount_rate, horizon_years, maintenance_escalation, "
        "replacement_cost_zar, repair_cost_zar",
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.get("/capex/analysis/{equipment_code}")
async def get_capex_analysis(
    equipment_code: str,
    age_years: Optional[float] = Query(None, ge=0, description="Override equipment age"),
    health_score: Optional[float] = Query(None, ge=0, le=100, description="Override health score"),
    replacement_cost_zar: Optional[float] = Query(None, ge=0),
    repair_cost_zar: Optional[float] = Query(None, ge=0),
    annual_maintenance_zar: Optional[float] = Query(None, ge=0),
    condition_score: Optional[float] = Query(None, ge=0, le=100),
    discount_rate: Optional[float] = Query(None, ge=0, le=1.0),
    horizon_years: Optional[int] = Query(None, ge=1, le=30),
) -> Dict[str, Any]:
    """Replace vs repair analysis for a single piece of equipment.

    Looks up equipment data from Concept Evolution assets first,
    then falls back to equipment type defaults.
    """
    # Try to resolve from Concept Evolution data
    concept_asset = capex_planning_service.get_concept_asset(equipment_code)
    equipment_type = "unknown"
    resolved_age = age_years
    resolved_health = health_score
    resolved_condition = condition_score

    if concept_asset:
        equipment_type = (concept_asset.get("AssetType") or "unknown").lower()
        if resolved_age is None:
            install_date = concept_asset.get("InstallDate")
            if install_date:
                try:
                    install = datetime.strptime(install_date, "%Y-%m-%d").date()
                    resolved_age = round((date.today() - install).days / 365.25, 1)
                except ValueError:
                    pass
        if resolved_health is None:
            cs = concept_asset.get("ConditionScore")
            if cs:
                try:
                    resolved_health = float(cs)
                except (ValueError, TypeError):
                    pass
        if resolved_condition is None:
            cs = concept_asset.get("ConditionScore")
            if cs:
                try:
                    resolved_condition = float(cs)
                except (ValueError, TypeError):
                    pass
    else:
        # Parse type from equipment code pattern {site}-{type}-{zone}
        parts = equipment_code.split("-")
        if len(parts) >= 3:
            equipment_type = parts[1].lower()
        elif len(parts) >= 2:
            equipment_type = parts[1].lower()

    if resolved_age is None:
        resolved_age = 10.0  # Default assumption
    if resolved_health is None:
        resolved_health = 50.0  # Default assumption

    analysis = capex_planning_service.analyze_replace_vs_repair(
        equipment_type=equipment_type,
        age_years=resolved_age,
        health_score=resolved_health,
        replacement_cost_zar=replacement_cost_zar,
        repair_cost_zar=repair_cost_zar,
        annual_maintenance_zar=annual_maintenance_zar,
        condition_score=resolved_condition,
        discount_rate=discount_rate,
        horizon_years=horizon_years,
        concept_asset_code=equipment_code if concept_asset else None,
    )
    analysis["equipment_code"] = equipment_code

    # Persist analysis
    try:
        from app.database.repositories.capex_repository import get_capex_repository

        repo = get_capex_repository()
        await repo.save_analysis(analysis)
    except Exception as e:
        logger.debug(f"CapEx analysis persistence skipped: {e}")

    return analysis


@router.get("/capex/portfolio/{site_id}")
async def get_capex_portfolio(
    site_id: str,
    discount_rate: Optional[float] = Query(None, ge=0, le=1.0),
    horizon_years: Optional[int] = Query(None, ge=1, le=30),
) -> Dict[str, Any]:
    """Portfolio CapEx analysis for all Concept Evolution assets at a site.

    Returns prioritized replacement list with budget forecast.
    """
    from app.services.capex_planning_service import _load_concept_assets

    assets = _load_concept_assets()

    # Filter by building code prefix if site_id maps to one
    # Concept assets use building codes like GW-JHB-001, CM-PTA-001, SC-JHB-001
    site_assets = assets  # Default: all assets (no site filter applied)

    equipment_list = []
    for asset in site_assets:
        install_date = asset.get("InstallDate")
        age = 10.0
        if install_date:
            try:
                install = datetime.strptime(install_date, "%Y-%m-%d").date()
                age = round((date.today() - install).days / 365.25, 1)
            except ValueError:
                pass

        cs = None
        try:
            cs = float(asset.get("ConditionScore", ""))
        except (ValueError, TypeError):
            pass

        repl_cost = None
        try:
            repl_cost = float(asset.get("ReplacementCost", ""))
        except (ValueError, TypeError):
            pass

        maint_cost = None
        try:
            maint_cost = float(asset.get("AnnualMaintCost", ""))
        except (ValueError, TypeError):
            pass

        equipment_list.append(
            {
                "code": asset.get("AssetCode", ""),
                "name": asset.get("AssetDesc", ""),
                "type": (asset.get("AssetType") or "unknown").lower(),
                "age_years": age,
                "health_score": cs or 50.0,
                "condition_score": cs,
                "replacement_cost_zar": repl_cost,
                "annual_maintenance_zar": maint_cost,
                "concept_asset_code": asset.get("AssetCode"),
            }
        )

    if not equipment_list:
        raise HTTPException(status_code=404, detail=f"No equipment found for site {site_id}")

    portfolio = capex_planning_service.analyze_portfolio(
        site_id=site_id,
        equipment_list=equipment_list,
        discount_rate=discount_rate,
        horizon_years=horizon_years,
    )
    return portfolio


@router.get("/capex/budget-forecast/{site_id}")
async def get_capex_budget_forecast(
    site_id: str,
    horizon_years: int = Query(10, ge=1, le=30),
    discount_rate: Optional[float] = Query(None, ge=0, le=1.0),
) -> Dict[str, Any]:
    """Projected CapEx needs by year for a site.

    Runs portfolio analysis and extracts the budget forecast.
    """
    portfolio = await get_capex_portfolio(
        site_id=site_id,
        discount_rate=discount_rate,
        horizon_years=horizon_years,
    )

    return {
        "site_id": site_id,
        "analysis_date": portfolio["analysis_date"],
        "horizon_years": horizon_years,
        "total_capex_needed_zar": portfolio["total_capex_needed_zar"],
        "total_npv_savings_zar": portfolio["total_npv_savings_zar"],
        "replace_count": portfolio["replace_count"],
        "budget_forecast": portfolio["budget_forecast"],
    }


@router.post("/capex/scenario")
async def run_capex_scenario(request: ScenarioRequest) -> Dict[str, Any]:
    """Run what-if scenario analysis with multiple parameter sets.

    Useful for sensitivity analysis: "What if discount rate changes?"
    """
    if not request.scenarios:
        raise HTTPException(status_code=422, detail="At least one scenario required")

    if len(request.scenarios) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 scenarios per request")

    result = capex_planning_service.run_scenario(
        equipment_type=request.equipment_type,
        age_years=request.age_years,
        health_score=request.health_score,
        scenarios=request.scenarios,
        base_replacement_cost_zar=request.replacement_cost_zar,
        base_repair_cost_zar=request.repair_cost_zar,
        base_annual_maintenance_zar=request.annual_maintenance_zar,
        condition_score=request.condition_score,
    )
    return result


@router.get("/capex/type-financials")
async def get_type_financials() -> Dict[str, Any]:
    """Return equipment type financial defaults for reference."""
    return capex_planning_service._load_type_financials()


@router.get("/capex/concept-assets")
async def get_concept_assets() -> List[Dict[str, Any]]:
    """Return Concept Evolution asset data for reference."""
    return capex_planning_service._load_concept_assets()
