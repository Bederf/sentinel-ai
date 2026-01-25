"""Work Orders API endpoints."""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime

from app.services.csv_loader import WorkOrderData, AssetData

router = APIRouter()


class WorkOrderResponse(BaseModel):
    """Work order response model."""
    id: str
    work_order_id: str
    site_id: str
    site_name: str
    asset_id: str
    asset_tag: str
    asset_category: str
    reported_date: datetime | None
    completed_date: datetime | None
    fault_code: str
    category: str
    priority: str
    type: str
    description: str
    resolution: str
    technician_notes: str
    technician_name: str
    labour_hours: float
    labour_cost: float
    parts_cost: float
    contractor_cost: float
    total_cost: float
    sla_target_hours: int
    sla_met: bool
    repeat_call: bool
    related_wo: str


class AssetResponse(BaseModel):
    """Asset response model."""
    id: str
    asset_id: str
    site_id: str
    site_name: str
    asset_tag: str
    asset_category: str
    make: str
    model: str
    serial_number: str
    install_date: datetime | None
    warranty_expiry: datetime | None
    expected_life_years: int
    age_years: int
    remaining_life_years: int
    criticality: str
    condition: str
    last_service_date: datetime | None
    next_service_date: datetime | None
    notes: str


class FailureStoryResponse(BaseModel):
    """Failure story response with work order chain."""
    asset_id: str
    asset_tag: str
    site_name: str
    story_type: str  # "disaster", "active_risk", "proactive_save"
    summary: str
    total_cost: float
    work_order_count: int
    work_orders: list[dict]
    timeline_months: int
    key_warnings: list[str]


@router.get("/work-orders", response_model=list[WorkOrderResponse])
async def get_work_orders(
    site_id: str | None = Query(None, description="Filter by site ID"),
    asset_id: str | None = Query(None, description="Filter by asset ID"),
    priority: str | None = Query(None, description="Filter by priority"),
    repeat_only: bool = Query(False, description="Show only repeat calls"),
    limit: int = Query(50, description="Maximum number of results"),
):
    """Get work orders with optional filters."""
    work_orders = WorkOrderData.load()

    # Apply filters
    if site_id:
        work_orders = [wo for wo in work_orders if wo["site_id"] == site_id]
    if asset_id:
        work_orders = [wo for wo in work_orders if wo["asset_id"] == asset_id]
    if priority:
        work_orders = [wo for wo in work_orders if wo["priority"] == priority]
    if repeat_only:
        work_orders = [wo for wo in work_orders if wo["repeat_call"]]

    # Sort by date (most recent first)
    work_orders.sort(key=lambda x: x["reported_date"] or datetime.min, reverse=True)

    return work_orders[:limit]


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderResponse)
async def get_work_order(work_order_id: str):
    """Get a specific work order by ID."""
    work_orders = WorkOrderData.load()
    for wo in work_orders:
        if wo["work_order_id"] == work_order_id:
            return wo
    return {"error": "Work order not found"}


@router.get("/assets", response_model=list[AssetResponse])
async def get_assets(
    site_id: str | None = Query(None, description="Filter by site ID"),
    condition: str | None = Query(None, description="Filter by condition"),
    criticality: str | None = Query(None, description="Filter by criticality"),
):
    """Get assets with optional filters."""
    assets = AssetData.load()

    if site_id:
        assets = [a for a in assets if a["site_id"] == site_id]
    if condition:
        assets = [a for a in assets if a["condition"] == condition]
    if criticality:
        assets = [a for a in assets if a["criticality"] == criticality]

    return assets


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str):
    """Get a specific asset by ID."""
    asset = AssetData.get_by_id(asset_id)
    if asset:
        return asset
    return {"error": "Asset not found"}


@router.get("/assets/{asset_id}/history")
async def get_asset_history(asset_id: str):
    """Get complete work order history for an asset."""
    asset = AssetData.get_by_id(asset_id)
    if not asset:
        return {"error": "Asset not found"}

    work_orders = WorkOrderData.get_failure_chain(asset_id)

    return {
        "asset": asset,
        "work_orders": work_orders,
        "total_work_orders": len(work_orders),
        "total_cost": sum(wo["total_cost"] for wo in work_orders),
        "repeat_calls": len([wo for wo in work_orders if wo["repeat_call"]]),
    }


@router.get("/failure-stories", response_model=list[FailureStoryResponse])
async def get_failure_stories():
    """Get key failure stories for dashboard display."""
    stories = []

    # Story 1: Centurion AHU-002 Disaster
    ahe002_orders = WorkOrderData.get_by_asset("ASSET-011")
    if ahe002_orders:
        key_warnings = [
            wo["technician_notes"]
            for wo in ahe002_orders
            if "URGENT" in wo["technician_notes"].upper() or "WILL fail" in wo["technician_notes"]
        ]
        stories.append({
            "asset_id": "ASSET-011",
            "asset_tag": "CM-HVAC-AHU-002",
            "site_name": "Centurion Mall",
            "story_type": "disaster",
            "summary": "Motor burnt out after 8 months of ignored warnings. Quote R28,500 → Emergency cost R63,300 + R150K+ tenant loss.",
            "total_cost": sum(wo["total_cost"] for wo in ahe002_orders),
            "work_order_count": len(ahe002_orders),
            "work_orders": ahe002_orders,
            "timeline_months": 14,
            "key_warnings": key_warnings[:3],
        })

    # Story 2: Gateway Chiller Active Risk
    chiller_orders = WorkOrderData.get_by_asset("ASSET-020")
    if chiller_orders:
        key_warnings = [
            wo["technician_notes"]
            for wo in chiller_orders
            if "EXACTLY" in wo["technician_notes"] or "CRITICAL" in wo["technician_notes"].upper()
        ]
        stories.append({
            "asset_id": "ASSET-020",
            "asset_tag": "GW-HVAC-CH-001",
            "site_name": "Gateway Theatre of Shopping",
            "story_type": "active_risk",
            "summary": "Same failure pattern as Centurion. Oil analysis confirms metal contamination. 4-8 weeks to failure if not addressed.",
            "total_cost": sum(wo["total_cost"] for wo in chiller_orders),
            "work_order_count": len(chiller_orders),
            "work_orders": chiller_orders,
            "timeline_months": 6,
            "key_warnings": key_warnings[:3],
        })

    # Story 3: Centurion AHU-001 Proactive Save
    ahe001_orders = WorkOrderData.get_by_asset("ASSET-010")
    if ahe001_orders:
        stories.append({
            "asset_id": "ASSET-010",
            "asset_tag": "CM-HVAC-AHU-001",
            "site_name": "Centurion Mall",
            "story_type": "proactive_save",
            "summary": "Twin unit to failed AHU-002. Client approved proactive replacement. Cost R28,300 vs R63,300+ if waited.",
            "total_cost": sum(wo["total_cost"] for wo in ahe001_orders),
            "work_order_count": len(ahe001_orders),
            "work_orders": ahe001_orders,
            "timeline_months": 1,
            "key_warnings": ["CLIENT APPROVED proactive work based on AHU-002 experience."],
        })

    return stories


@router.get("/stats/work-orders")
async def get_work_order_stats():
    """Get work order statistics for dashboard."""
    work_orders = WorkOrderData.load()
    assets = AssetData.load()

    # Calculate metrics
    total_wo = len(work_orders)
    critical_wo = len([wo for wo in work_orders if wo["priority"] == "critical"])
    repeat_calls = len([wo for wo in work_orders if wo["repeat_call"]])
    sla_failures = len([wo for wo in work_orders if not wo["sla_met"]])
    total_cost = sum(wo["total_cost"] for wo in work_orders)

    # Asset metrics
    poor_assets = len(AssetData.get_poor_condition())
    eol_assets = len(AssetData.get_end_of_life())

    # Cost by category
    cost_by_category = {}
    for wo in work_orders:
        cat = wo["category"]
        if cat not in cost_by_category:
            cost_by_category[cat] = 0
        cost_by_category[cat] += wo["total_cost"]

    return {
        "total_work_orders": total_wo,
        "critical_work_orders": critical_wo,
        "repeat_calls": repeat_calls,
        "sla_failures": sla_failures,
        "total_cost": total_cost,
        "total_assets": len(assets),
        "poor_condition_assets": poor_assets,
        "end_of_life_assets": eol_assets,
        "cost_by_category": cost_by_category,
    }
