"""Sustainability & ESG Module API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.sustainability_service import sustainability_service

router = APIRouter()
logger = logging.getLogger(__name__)


class GreenStarUpdateRequest(BaseModel):
    """Request to update a Green Star category score."""
    achieved_points: int
    notes: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    """Request to update sustainability config."""
    building_sqm: Optional[float] = None
    occupancy_capacity: Optional[int] = None
    target_reduction_pct: Optional[float] = None
    monthly_water_kl: Optional[float] = None
    monthly_waste_tons: Optional[float] = None
    working_days_per_month: Optional[int] = None
    avg_occupancy_pct: Optional[float] = None
    emission_factors: Optional[dict] = None


@router.get("/sustainability/{site_id}/summary")
async def get_sustainability_summary(site_id: str):
    """Dashboard summary: current month, YTD, trend, targets, Green Star progress."""
    try:
        return sustainability_service.get_summary(site_id)
    except Exception as e:
        logger.error(f"Error getting sustainability summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sustainability/{site_id}/emissions")
async def get_emissions_history(
    site_id: str,
    months: int = Query(default=12, ge=1, le=36),
):
    """Monthly emissions history with scope 1/2/3 breakdown."""
    try:
        history = sustainability_service.get_emissions_history(site_id, months)
        return {
            "site_id": site_id,
            "months": months,
            "data": [s.to_dict() for s in history],
        }
    except Exception as e:
        logger.error(f"Error getting emissions history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sustainability/{site_id}/emissions/current")
async def get_current_emissions(site_id: str):
    """Current month emissions snapshot."""
    try:
        snapshot = sustainability_service.calculate_current_emissions(site_id)
        return snapshot.to_dict()
    except Exception as e:
        logger.error(f"Error calculating current emissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sustainability/{site_id}/emissions/breakdown")
async def get_emissions_breakdown(site_id: str):
    """Emissions breakdown by scope and system."""
    try:
        current = sustainability_service.calculate_current_emissions(site_id)
        return {
            "site_id": site_id,
            "month": current.month,
            "by_scope": {
                "scope1_diesel": round(current.scope1_kg_co2, 2),
                "scope2_grid": round(current.scope2_kg_co2, 2),
                "scope3_other": round(current.scope3_kg_co2, 2),
                "total": round(current.total_kg_co2, 2),
            },
            "by_system": current.breakdown_by_system,
            "scope_percentages": {
                "scope1_pct": round(
                    (current.scope1_kg_co2 / current.total_kg_co2 * 100)
                    if current.total_kg_co2 > 0 else 0, 1
                ),
                "scope2_pct": round(
                    (current.scope2_kg_co2 / current.total_kg_co2 * 100)
                    if current.total_kg_co2 > 0 else 0, 1
                ),
                "scope3_pct": round(
                    (current.scope3_kg_co2 / current.total_kg_co2 * 100)
                    if current.total_kg_co2 > 0 else 0, 1
                ),
            },
        }
    except Exception as e:
        logger.error(f"Error getting emissions breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sustainability/{site_id}/efficiency")
async def get_efficiency_metrics(site_id: str):
    """Energy and carbon intensity with SA office benchmarks."""
    try:
        return sustainability_service.get_efficiency_metrics(site_id)
    except Exception as e:
        logger.error(f"Error getting efficiency metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sustainability/{site_id}/green-star")
async def get_green_star_assessment(site_id: str):
    """Green Star SA self-assessment tracker."""
    try:
        assessment = sustainability_service.get_green_star_assessment(site_id)
        return assessment.to_dict()
    except Exception as e:
        logger.error(f"Error getting Green Star assessment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sustainability/{site_id}/green-star/{category_id}")
async def update_green_star_score(
    site_id: str,
    category_id: str,
    request: GreenStarUpdateRequest,
):
    """Update a Green Star category score."""
    try:
        assessment = sustainability_service.update_green_star_score(
            site_id, category_id.upper(), request.achieved_points, request.notes
        )
        return assessment.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating Green Star score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sustainability/{site_id}/config")
async def get_sustainability_config(site_id: str):
    """Get site sustainability configuration."""
    try:
        config = sustainability_service.get_config(site_id)
        return config.to_dict()
    except Exception as e:
        logger.error(f"Error getting sustainability config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sustainability/{site_id}/config")
async def update_sustainability_config(
    site_id: str,
    request: ConfigUpdateRequest,
):
    """Update site sustainability configuration."""
    try:
        updates = request.model_dump(exclude_none=True)
        config = sustainability_service.update_config(site_id, updates)
        return config.to_dict()
    except Exception as e:
        logger.error(f"Error updating sustainability config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
