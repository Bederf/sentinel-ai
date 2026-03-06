"""
Concept Evolution CAFM Integration API

Exposes Concept job card and asset data for health/condition assessment.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.services.concept_loader import concept_loader

router = APIRouter(prefix="/api/concept", tags=["concept-cafm"])


@router.get("/health")
async def get_integration_health():
    """Check Concept integration health and data availability."""
    return {
        "status": "connected",
        "job_cards_loaded": len(concept_loader.job_cards),
        "assets_loaded": len(concept_loader.assets),
        "data_source": "concept_evolution",
        "last_sync": "2026-01-29T00:00:00Z",  # Would be actual sync time
    }


@router.get("/assets")
async def get_assets(
    site_code: Optional[str] = Query(None, description="Filter by building"),
    criticality: Optional[str] = Query(None, description="Filter by criticality"),
    condition: Optional[str] = Query(None, description="Filter by condition"),
):
    """Get all assets from Concept with optional filters."""
    assets = concept_loader.assets

    if site_code:
        assets = [a for a in assets if a.site_code == site_code]
    if criticality:
        assets = [a for a in assets if a.criticality.lower() == criticality.lower()]
    if condition:
        assets = [a for a in assets if a.condition.lower() == condition.lower()]

    return {
        "total": len(assets),
        "assets": [
            {
                "asset_code": a.asset_code,
                "asset_desc": a.asset_desc,
                "asset_category": a.asset_category,
                "asset_type": a.asset_type,
                "manufacturer": a.manufacturer,
                "model": a.model,
                "site_code": a.site_code,
                "site_name": a.site_name,
                "location": a.location_desc,
                "install_date": a.install_date.isoformat() if a.install_date else None,
                "age_years": a.age_years,
                "expected_life_years": a.expected_life_years,
                "remaining_life": a.remaining_life_years,
                "beyond_life": a.is_beyond_life,
                "criticality": a.criticality,
                "condition": a.condition,
                "condition_score": a.condition_score,
                "risk_rating": a.risk_rating,
                "replacement_cost": a.replacement_cost,
            }
            for a in assets
        ],
    }


@router.get("/assets/{asset_code}")
async def get_asset(asset_code: str):
    """Get single asset details."""
    asset = concept_loader.get_asset(asset_code)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    return {
        "asset_code": asset.asset_code,
        "asset_desc": asset.asset_desc,
        "asset_category": asset.asset_category,
        "asset_type": asset.asset_type,
        "manufacturer": asset.manufacturer,
        "model": asset.model,
        "serial_no": asset.serial_no,
        "site_code": asset.site_code,
        "site_name": asset.site_name,
        "location_code": asset.location_code,
        "location_desc": asset.location_desc,
        "install_date": asset.install_date.isoformat() if asset.install_date else None,
        "warranty_expiry": asset.warranty_expiry.isoformat() if asset.warranty_expiry else None,
        "age_years": asset.age_years,
        "expected_life_years": asset.expected_life_years,
        "remaining_life": asset.remaining_life_years,
        "beyond_life": asset.is_beyond_life,
        "criticality": asset.criticality,
        "condition": asset.condition,
        "condition_score": asset.condition_score,
        "last_service_date": asset.last_service_date.isoformat() if asset.last_service_date else None,
        "next_service_date": asset.next_service_date.isoformat() if asset.next_service_date else None,
        "ppm_frequency": asset.ppm_frequency,
        "replacement_cost": asset.replacement_cost,
        "annual_maint_cost": asset.annual_maint_cost,
        "risk_rating": asset.risk_rating,
        "compliance_req": asset.compliance_req,
        "notes": asset.notes,
    }


@router.get("/assets/{asset_code}/health")
async def get_asset_health(asset_code: str):
    """
    Get comprehensive health assessment for an asset.

    Combines condition score, work order history, PPM compliance,
    age factors, and technician warnings into a single health score.
    """
    health = concept_loader.calculate_health_score(asset_code)
    if "error" in health:
        raise HTTPException(status_code=404, detail=health["error"])

    return health


@router.get("/assets/{asset_code}/job-cards")
async def get_asset_job_cards(
    asset_code: str,
    limit: int = Query(20, description="Maximum results"),
):
    """Get job card history for an asset."""
    job_cards = concept_loader.get_job_cards_for_asset(asset_code)

    # Sort by logged date descending
    job_cards.sort(key=lambda x: x.logged_date or "", reverse=True)

    return {
        "asset_code": asset_code,
        "total_job_cards": len(job_cards),
        "job_cards": [
            {
                "job_card_no": jc.job_card_no,
                "priority": jc.priority,
                "priority_level": jc.priority_level,
                "status": jc.status,
                "logged_date": jc.logged_date.isoformat() if jc.logged_date else None,
                "completed_date": jc.completed_date.isoformat() if jc.completed_date else None,
                "sla_met": jc.sla_met,
                "fault_code": jc.fault_code,
                "fault_desc": jc.fault_desc,
                "problem_desc": jc.problem_desc,
                "cause_code": jc.cause_code,
                "cause_desc": jc.cause_desc,
                "action_taken": jc.action_taken,
                "technician_name": jc.technician_name,
                "total_cost": jc.total_cost,
                "repeat_call": jc.repeat_call,
                "related_job_card": jc.related_job_card,
                "tech_notes": jc.tech_notes,
                "has_warning": jc.has_warning_flags,
            }
            for jc in job_cards[:limit]
        ],
    }


@router.get("/job-cards")
async def get_job_cards(
    site_code: Optional[str] = Query(None, description="Filter by building"),
    asset_code: Optional[str] = Query(None, description="Filter by asset"),
    priority: Optional[str] = Query(None, description="Filter by priority (P1-P4)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    repeat_only: bool = Query(False, description="Show only repeat calls"),
    warnings_only: bool = Query(False, description="Show only jobs with warnings"),
    limit: int = Query(50, description="Maximum results"),
):
    """Get job cards with optional filters."""
    job_cards = concept_loader.job_cards

    if site_code:
        job_cards = [jc for jc in job_cards if jc.site_code == site_code]
    if asset_code:
        job_cards = [jc for jc in job_cards if jc.asset_code == asset_code]
    if priority:
        job_cards = [jc for jc in job_cards if jc.priority == priority]
    if status:
        job_cards = [jc for jc in job_cards if jc.status.lower() == status.lower()]
    if repeat_only:
        job_cards = [jc for jc in job_cards if jc.repeat_call]
    if warnings_only:
        job_cards = [jc for jc in job_cards if jc.has_warning_flags]

    # Sort by logged date descending
    job_cards.sort(key=lambda x: x.logged_date or "", reverse=True)

    return {
        "total": len(job_cards),
        "job_cards": [
            {
                "job_card_no": jc.job_card_no,
                "priority": jc.priority,
                "status": jc.status,
                "logged_date": jc.logged_date.isoformat() if jc.logged_date else None,
                "site_name": jc.site_name,
                "asset_code": jc.asset_code,
                "asset_desc": jc.asset_desc,
                "fault_desc": jc.fault_desc,
                "technician_name": jc.technician_name,
                "total_cost": jc.total_cost,
                "repeat_call": jc.repeat_call,
                "has_warning": jc.has_warning_flags,
            }
            for jc in job_cards[:limit]
        ],
    }


@router.get("/at-risk")
async def get_assets_at_risk():
    """
    Get all assets with health score below 60.

    These assets need attention based on condition, repeat calls,
    age, and technician warnings.
    """
    at_risk = concept_loader.get_assets_at_risk()

    return {"total_at_risk": len(at_risk), "assets": at_risk}


@router.get("/buildings/{site_code}/summary")
async def get_site_summary(site_code: str):
    """Get health summary for all assets in a building."""
    summary = concept_loader.get_site_summary(site_code)

    if "error" in summary:
        raise HTTPException(status_code=404, detail=summary["error"])

    return summary


@router.get("/stats")
async def get_concept_stats():
    """Get overall statistics from Concept data."""
    job_cards = concept_loader.job_cards
    assets = concept_loader.assets

    # Calculate stats
    total_cost = sum(jc.total_cost for jc in job_cards)
    repeat_calls = len([jc for jc in job_cards if jc.repeat_call])
    sla_failures = len([jc for jc in job_cards if not jc.sla_met])
    critical_assets = len([a for a in assets if a.criticality == "Critical"])
    poor_condition = len([a for a in assets if a.condition_score < 50])
    beyond_life = len([a for a in assets if a.is_beyond_life])

    # Cost by category
    cost_by_category = {}
    for jc in job_cards:
        cat = jc.asset_category
        cost_by_category[cat] = cost_by_category.get(cat, 0) + jc.total_cost

    # Priority distribution
    priority_dist = {}
    for jc in job_cards:
        priority_dist[jc.priority] = priority_dist.get(jc.priority, 0) + 1

    return {
        "job_cards": {
            "total": len(job_cards),
            "total_cost": total_cost,
            "repeat_calls": repeat_calls,
            "repeat_rate": f"{(repeat_calls / len(job_cards) * 100):.1f}%" if job_cards else "0%",
            "sla_failures": sla_failures,
            "sla_compliance": f"{((len(job_cards) - sla_failures) / len(job_cards) * 100):.1f}%" if job_cards else "0%",
            "by_priority": priority_dist,
            "cost_by_category": cost_by_category,
        },
        "assets": {
            "total": len(assets),
            "critical": critical_assets,
            "poor_condition": poor_condition,
            "beyond_expected_life": beyond_life,
            "total_replacement_value": sum(a.replacement_cost for a in assets),
            "annual_maint_budget": sum(a.annual_maint_cost for a in assets),
        },
    }
