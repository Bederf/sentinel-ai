"""Demand Response API endpoints.

Provides real-time curtailable load signals for BESS controllers and
demand response aggregators (IES, LTM Energy / eSUMS).
"""

from fastapi import APIRouter, Query

from app.models.demand_response_models import CurtailableLoadResponse
from app.services.demand_response_service import get_demand_response_service

router = APIRouter(prefix="/api/demand-response", tags=["Demand Response"])
_service = get_demand_response_service()


@router.get("/curtailable-load", response_model=CurtailableLoadResponse)
async def get_curtailable_load(
    site_id: str = Query(..., description="Sentinel site ID e.g. site-002"),
    min_priority: int = Query(
        3,
        ge=1,
        le=5,
        description=(
            "Minimum zone priority (1=critical, 5=lowest). Default P3+ means P3, P4, P5 only — never shed P1/P2"
        ),
    ),
    include_zones: bool = Query(True, description="Include per-zone breakdown in response"),
):
    """Returns real-time curtailable HVAC load signal for a site.

    Used by BESS controllers and demand response aggregators to determine
    exactly how much load can be safely shed, for how long, and with what confidence.

    **Compatible with Eskom DDMP requirements.**

    ## Parameters
    - **site_id**: Sentinel site identifier (e.g., site-002)
    - **min_priority**: Minimum zone priority (1=critical/never shed, 5=lowest/shed first)
    - **include_zones**: Whether to include detailed per-zone breakdown

    ## Response
    - **curtailable_load_kw**: Total HVAC load that can be curtailed
    - **safe_duration_minutes**: Minutes until comfort breach
    - **confidence**: Prediction confidence (0.0-0.95)
    - **limiting_factor**: Primary constraint (thermal_mass, comfort_boundary, etc.)
    - **ddmp_eligible**: Whether site meets DDMP minimum requirements
    - **zone_breakdown**: Per-zone details (if include_zones=true)

    ## Errors
    - **404**: Site not found
    - **503**: Insufficient live sensor data (stale data > 5 minutes)
    - **422**: Invalid parameters
    """
    return await _service.get_curtailable_load(
        site_id=site_id,
        min_priority=min_priority,
        include_zones=include_zones,
    )


@router.get("/health")
async def demand_response_health():
    """Integration health check for external DR consumers.

    Returns service status and compatibility information.
    """
    return {
        "status": "ok",
        "endpoint": "/api/demand-response/curtailable-load",
        "version": "1.0.0",
        "ddmp_compatible": True,
        "documentation": "See /docs for full API schema",
    }
