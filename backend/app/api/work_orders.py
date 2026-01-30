"""Work Orders API endpoints."""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
import uuid

from app.services.csv_loader import WorkOrderData, AssetData

router = APIRouter()

# In-memory storage for technician-created work orders
_technician_work_orders: dict[str, dict] = {}


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


# ============================================================================
# Technician Work Order Endpoints (Create/Update/Complete)
# ============================================================================

class TechnicianWorkOrderCreate(BaseModel):
    """Create work order from technician chat."""
    site_id: str
    equipment_id: str
    fault_description: str
    diagnosis: str
    priority: str = "medium"  # low, medium, high, critical
    technician_notes: Optional[str] = None
    parts_needed: Optional[List[str]] = None
    estimated_duration: Optional[str] = None


class TechnicianWorkOrderUpdate(BaseModel):
    """Update work order fields."""
    diagnosis: Optional[str] = None
    technician_notes: Optional[str] = None
    parts_needed: Optional[List[str]] = None
    status: Optional[str] = None
    estimated_duration: Optional[str] = None


class TechnicianWorkOrderComplete(BaseModel):
    """Complete work order with resolution details."""
    resolution: str
    parts_used: List[str] = []
    time_spent: str
    technician_notes: Optional[str] = None


class TechnicianWorkOrderResponse(BaseModel):
    """Response model for technician work orders."""
    id: str
    site_id: str
    equipment_id: str
    fault_description: str
    diagnosis: str
    priority: str
    status: str  # draft, assigned, in_progress, complete
    created_at: datetime
    updated_at: Optional[datetime] = None
    technician_id: Optional[str] = None
    technician_notes: Optional[str] = None
    parts_needed: List[str] = []
    estimated_duration: Optional[str] = None
    resolution: Optional[str] = None
    parts_used: List[str] = []
    time_spent: Optional[str] = None


@router.post("/work-orders/technician", response_model=TechnicianWorkOrderResponse)
async def create_technician_work_order(order: TechnicianWorkOrderCreate):
    """
    Create work order from technician chat.

    Creates a draft work order that can be reviewed and submitted.
    """
    work_order_id = f"TWO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    work_order = {
        "id": work_order_id,
        "site_id": order.site_id,
        "equipment_id": order.equipment_id,
        "fault_description": order.fault_description,
        "diagnosis": order.diagnosis,
        "priority": order.priority,
        "status": "draft",
        "created_at": datetime.now(),
        "updated_at": None,
        "technician_id": None,
        "technician_notes": order.technician_notes,
        "parts_needed": order.parts_needed or [],
        "estimated_duration": order.estimated_duration,
        "resolution": None,
        "parts_used": [],
        "time_spent": None,
    }

    _technician_work_orders[work_order_id] = work_order

    return work_order


@router.get("/work-orders/technician", response_model=List[TechnicianWorkOrderResponse])
async def get_technician_work_orders(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    technician_id: Optional[str] = Query(None, description="Filter by technician"),
):
    """
    Get technician work orders with optional filters.

    Returns work orders created from technician chat interface.
    """
    work_orders = list(_technician_work_orders.values())

    if site_id:
        work_orders = [wo for wo in work_orders if wo["site_id"] == site_id]
    if status:
        work_orders = [wo for wo in work_orders if wo["status"] == status]
    if technician_id:
        work_orders = [wo for wo in work_orders if wo.get("technician_id") == technician_id]

    # Sort by created_at descending
    work_orders.sort(key=lambda x: x["created_at"], reverse=True)

    return work_orders


@router.get("/work-orders/technician/{work_order_id}", response_model=TechnicianWorkOrderResponse)
async def get_technician_work_order(work_order_id: str):
    """Get a specific technician work order by ID."""
    if work_order_id not in _technician_work_orders:
        raise HTTPException(status_code=404, detail="Work order not found")

    return _technician_work_orders[work_order_id]


@router.put("/work-orders/technician/{work_order_id}", response_model=TechnicianWorkOrderResponse)
async def update_technician_work_order(work_order_id: str, update: TechnicianWorkOrderUpdate):
    """
    Update technician work order.

    Can update diagnosis, notes, parts, status, or duration.
    """
    if work_order_id not in _technician_work_orders:
        raise HTTPException(status_code=404, detail="Work order not found")

    work_order = _technician_work_orders[work_order_id]

    if update.diagnosis is not None:
        work_order["diagnosis"] = update.diagnosis
    if update.technician_notes is not None:
        work_order["technician_notes"] = update.technician_notes
    if update.parts_needed is not None:
        work_order["parts_needed"] = update.parts_needed
    if update.status is not None:
        work_order["status"] = update.status
    if update.estimated_duration is not None:
        work_order["estimated_duration"] = update.estimated_duration

    work_order["updated_at"] = datetime.now()

    return work_order


@router.post("/work-orders/technician/{work_order_id}/complete", response_model=TechnicianWorkOrderResponse)
async def complete_technician_work_order(work_order_id: str, completion: TechnicianWorkOrderComplete):
    """
    Mark work order as complete with resolution details.

    Called by technician when job is finished.
    """
    if work_order_id not in _technician_work_orders:
        raise HTTPException(status_code=404, detail="Work order not found")

    work_order = _technician_work_orders[work_order_id]

    work_order["status"] = "complete"
    work_order["resolution"] = completion.resolution
    work_order["parts_used"] = completion.parts_used
    work_order["time_spent"] = completion.time_spent
    if completion.technician_notes:
        existing_notes = work_order.get("technician_notes") or ""
        work_order["technician_notes"] = f"{existing_notes}\n\nCompletion Notes: {completion.technician_notes}".strip()
    work_order["updated_at"] = datetime.now()

    return work_order


@router.post("/work-orders/technician/{work_order_id}/assign", response_model=TechnicianWorkOrderResponse)
async def assign_technician_work_order(work_order_id: str, technician_id: str = Query(...)):
    """Assign work order to a technician."""
    if work_order_id not in _technician_work_orders:
        raise HTTPException(status_code=404, detail="Work order not found")

    work_order = _technician_work_orders[work_order_id]
    work_order["technician_id"] = technician_id
    work_order["status"] = "assigned"
    work_order["updated_at"] = datetime.now()

    return work_order


@router.post("/work-orders/technician/{work_order_id}/start", response_model=TechnicianWorkOrderResponse)
async def start_technician_work_order(work_order_id: str):
    """Mark work order as in progress."""
    if work_order_id not in _technician_work_orders:
        raise HTTPException(status_code=404, detail="Work order not found")

    work_order = _technician_work_orders[work_order_id]
    work_order["status"] = "in_progress"
    work_order["updated_at"] = datetime.now()

    return work_order
