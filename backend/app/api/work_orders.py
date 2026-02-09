"""Work Orders API endpoints."""

from fastapi import APIRouter, Query, HTTPException, Depends, Request
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
import uuid
import logging

from app.services.csv_loader import WorkOrderData, AssetData
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthLevel, AuthContext

logger = logging.getLogger(__name__)

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
async def create_technician_work_order(
    order: TechnicianWorkOrderCreate,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))
):
    """
    Create work order from technician chat.

    Creates a draft work order that can be reviewed and submitted.
    Requires authentication (AUTHENTICATED or higher).
    """
    from app.database.repositories.work_order_repository import get_work_order_repository
    from app.database.repositories.audit_repository import AuditRepository

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
        "source": "technician",  # Distinguish from other work orders
    }

    # Store in database
    try:
        repo = get_work_order_repository()
        created = await repo.create_work_order(work_order)

        # Log audit event
        audit_repo = AuditRepository()
        audit_repo.create({
            'action': 'WORK_ORDER_CREATED',
            'user_id': auth.user_id,
            'details': {'work_order_id': work_order_id, 'equipment_id': order.equipment_id},
            'result': 'SUCCESS'
        })

        logger.info(f"Created technician work order {work_order_id} by user {auth.user_id}")
        return work_order
    except Exception as e:
        logger.error(f"Failed to create technician work order: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create work order")


@router.get("/work-orders/technician", response_model=List[TechnicianWorkOrderResponse])
async def get_technician_work_orders(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    technician_id: Optional[str] = Query(None, description="Filter by technician"),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))
):
    """
    Get technician work orders with optional filters.

    Returns work orders created from technician chat interface.
    Requires authentication (AUTHENTICATED or higher).
    """
    from app.database.repositories.work_order_repository import get_work_order_repository

    try:
        repo = get_work_order_repository()
        # Retrieve only technician-sourced work orders
        work_orders = await repo.get_work_orders_by_source("technician")

        if site_id:
            work_orders = [wo for wo in work_orders if wo.get("site_id") == site_id]
        if status:
            work_orders = [wo for wo in work_orders if wo.get("status") == status]
        if technician_id:
            work_orders = [wo for wo in work_orders if wo.get("technician_id") == technician_id]

        # Sort by created_at descending
        work_orders.sort(key=lambda x: x.get("created_at") or datetime.now(), reverse=True)

        return work_orders
    except Exception as e:
        logger.error(f"Failed to get technician work orders: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve work orders")


@router.get("/work-orders/technician/{work_order_id}", response_model=TechnicianWorkOrderResponse)
async def get_technician_work_order(work_order_id: str):
    """Get a specific technician work order by ID."""
    if work_order_id not in _technician_work_orders:
        raise HTTPException(status_code=404, detail="Work order not found")

    return _technician_work_orders[work_order_id]


@router.put("/work-orders/technician/{work_order_id}", response_model=TechnicianWorkOrderResponse)
async def update_technician_work_order(
    work_order_id: str,
    update: TechnicianWorkOrderUpdate,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))
):
    """
    Update technician work order.

    Can update diagnosis, notes, parts, status, or duration.
    Requires authentication (AUTHENTICATED or higher).
    """
    from app.database.repositories.work_order_repository import get_work_order_repository
    from app.database.repositories.audit_repository import AuditRepository

    try:
        repo = get_work_order_repository()
        work_order = await repo.get_work_order_by_id(work_order_id)

        if not work_order:
            raise HTTPException(status_code=404, detail="Work order not found")

        # Build update payload
        update_data = {}
        if update.diagnosis is not None:
            update_data["diagnosis"] = update.diagnosis
        if update.technician_notes is not None:
            update_data["technician_notes"] = update.technician_notes
        if update.parts_needed is not None:
            update_data["parts_needed"] = update.parts_needed
        if update.status is not None:
            update_data["status"] = update.status
        if update.estimated_duration is not None:
            update_data["estimated_duration"] = update.estimated_duration

        # Update in database
        updated = await repo.update_work_order(work_order_id, update_data)

        # Log audit event
        audit_repo = AuditRepository()
        audit_repo.create({
            'action': 'WORK_ORDER_UPDATED',
            'user_id': auth.user_id,
            'details': {'work_order_id': work_order_id, 'changes': update_data},
            'result': 'SUCCESS'
        })

        logger.info(f"Updated technician work order {work_order_id} by user {auth.user_id}")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update technician work order: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update work order")


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

    # Workflow integration: trigger repair completed
    try:
        from app.services.workflow_triggers import get_trigger_engine

        trigger_engine = get_trigger_engine()
        await trigger_engine.on_repair_completed(
            work_order_id=work_order_id,
            equipment_id=work_order.get("equipment_id"),
            completion_data={
                "completion_notes": completion.resolution,
                "parts_used": completion.parts_used,
                "actual_hours": completion.time_spent,
            }
        )
    except Exception:
        # Non-blocking: workflow trigger failures should not break API
        pass

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


# ============================================================================
# Supabase Work Order Endpoints (for Clawd bot integration)
# ============================================================================

class SupabaseWorkOrderCreate(BaseModel):
    """Create work order in Supabase."""
    equipment_code: str
    title: str
    description: Optional[str] = None
    priority: str = "medium"  # low, medium, high, urgent
    scheduled_date: Optional[str] = None
    estimated_duration_hours: Optional[int] = None
    created_by: str = "SENTINEL"


class SupabaseWorkOrderResponse(BaseModel):
    """Response from Supabase work order creation."""
    id: str
    code: str
    equipment_code: Optional[str] = None
    title: str
    priority: str
    status: str
    assigned_to: Optional[str] = None
    technician_email: Optional[str] = None
    technician_phone: Optional[str] = None
    technician_telegram_id: Optional[str] = None
    created_at: str


class TechnicianLookupResponse(BaseModel):
    """Technician lookup response."""
    id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram_id: Optional[str] = None
    specialty: Optional[str] = None
    found: bool = False


@router.get("/work-orders/technician-for-equipment/{equipment_code}", response_model=TechnicianLookupResponse)
async def get_technician_for_equipment(equipment_code: str):
    """
    Get the assigned technician for a piece of equipment.

    Looks up the site assignment based on equipment type → specialty mapping.
    Used by Clawd bot to determine who to email for a work order.

    UNAUTHENTICATED - Accepted risk: Clawd bot integration requires external
    webhook access without auth. Technician data exposure is acceptable for
    operations (names, emails, phones are already in technician_repository).
    Used only for work order routing, not for administrative actions.
    See 65-04 for security rationale.
    """
    from app.database.repositories.technician_repository import get_technician_repository

    repo = get_technician_repository()
    tech = await repo.get_technician_for_equipment_code(equipment_code)

    if tech:
        return TechnicianLookupResponse(
            id=tech.get("id"),
            name=tech.get("name"),
            email=tech.get("email"),
            phone=tech.get("phone"),
            telegram_id=tech.get("telegram_id"),
            specialty=tech.get("specialty"),
            found=True
        )

    return TechnicianLookupResponse(found=False)


@router.post("/work-orders/supabase", response_model=SupabaseWorkOrderResponse)
async def create_supabase_work_order(
    work_order: SupabaseWorkOrderCreate,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR))
):
    """
    Create a work order in Supabase, linked to equipment.

    Automatically looks up and assigns the technician for the equipment.
    Requires authentication (OPERATOR or higher).
    """
    from app.database.repositories.work_order_repository import get_work_order_repository
    from app.database.repositories.technician_repository import get_technician_repository
    from app.database.repositories.audit_repository import AuditRepository

    try:
        wo_repo = get_work_order_repository()
        tech_repo = get_technician_repository()

        # Get technician for this equipment
        tech = await tech_repo.get_technician_for_equipment_code(work_order.equipment_code)

        # Create work order payload
        wo_data = {
            "equipment_code": work_order.equipment_code,
            "title": work_order.title,
            "description": work_order.description,
            "priority": work_order.priority,
            "scheduled_date": work_order.scheduled_date,
            "estimated_duration_hours": work_order.estimated_duration_hours,
            "created_by": work_order.created_by or auth.user_id,
            "status": "scheduled",
        }

        # Assign technician if found
        if tech:
            wo_data["assigned_to"] = tech.get("name")
            wo_data["assigned_team"] = tech.get("specialty")

        # Create in Supabase
        created = await wo_repo.create_work_order(wo_data)

        if not created:
            raise HTTPException(status_code=500, detail="Failed to create work order in Supabase")

        # Log audit event
        audit_repo = AuditRepository()
        audit_repo.create({
            'action': 'WORK_ORDER_CREATED',
            'user_id': auth.user_id,
            'details': {'work_order_id': created.get("id"), 'equipment_code': work_order.equipment_code},
            'result': 'SUCCESS'
        })

        logger.info(f"Created Supabase work order {created.get('code')} by user {auth.user_id}")

        return SupabaseWorkOrderResponse(
            id=created.get("id"),
            code=created.get("code"),
            equipment_code=work_order.equipment_code,
            title=created.get("title"),
            priority=created.get("priority"),
            status=created.get("status"),
            assigned_to=created.get("assigned_to"),
            technician_email=tech.get("email") if tech else None,
            technician_phone=tech.get("phone") if tech else None,
            technician_telegram_id=tech.get("telegram_id") if tech else None,
            created_at=created.get("created_at")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create Supabase work order: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create work order")


@router.get("/work-orders/supabase", response_model=List[dict])
async def list_supabase_work_orders(
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(50, description="Maximum number of results"),
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR))
):
    """List work orders from Supabase with optional filters.

    Requires authentication (OPERATOR or higher).
    """
    from app.database.repositories.work_order_repository import get_work_order_repository

    try:
        repo = get_work_order_repository()
        work_orders = await repo.get_all_work_orders(limit=limit)

        if status:
            work_orders = [wo for wo in work_orders if wo.get("status") == status]
        if priority:
            work_orders = [wo for wo in work_orders if wo.get("priority") == priority]

        return work_orders
    except Exception as e:
        logger.error(f"Failed to list Supabase work orders: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve work orders")


@router.get("/work-orders/supabase/{code}")
async def get_supabase_work_order(
    code: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR))
):
    """Get a work order from Supabase by its code.

    Requires authentication (OPERATOR or higher).
    """
    from app.database.repositories.work_order_repository import get_work_order_repository

    try:
        repo = get_work_order_repository()
        wo = await repo.get_work_order_by_code(code)

        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")

        return wo
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Supabase work order: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve work order")


@router.get("/work-orders/equipment-info/{equipment_code}")
async def get_equipment_info_for_technician(equipment_code: str):
    """Get detailed equipment information for technicians.

    This endpoint is designed for Clawd bot integration - when a technician
    asks for more details about the equipment they're working on, Clawd can
    fetch this information.

    Returns comprehensive equipment details including:
    - Basic info (name, type, category, location)
    - Network info (IP, MAC, protocol addresses)
    - Device info (manufacturer, model, serial, firmware)
    - Operating data (runtime hours, lamp hours, capacity)
    - Notes from facility managers
    - Health status and recent issues

    Args:
        equipment_code: Equipment code (e.g., S002-CHILLER-B1-001)

    Returns:
        Equipment details formatted for technician reference

    UNAUTHENTICATED - Accepted risk: Clawd bot integration requires external
    webhook access without auth. Equipment metadata is acceptable for operations
    (manufacturer, model, serial are on the device itself). No sensitive control
    parameters or credentials exposed. Used only for technician information lookups.
    See 65-04 for security rationale.
    """
    from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository
    from app.database.supabase_client import get_supabase_client

    repo = EquipmentMetadataRepository()
    metadata = repo.get_equipment_metadata(equipment_code)

    if not metadata:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_code} not found")

    # Parse JSONB fields if they're strings
    import json
    network_info = metadata.get("network_info") or {}
    device_info = metadata.get("device_info") or {}
    operating_data = metadata.get("operating_data") or {}

    if isinstance(network_info, str):
        network_info = json.loads(network_info) if network_info else {}
    if isinstance(device_info, str):
        device_info = json.loads(device_info) if device_info else {}
    if isinstance(operating_data, str):
        operating_data = json.loads(operating_data) if operating_data else {}

    # Format response for technician (easy to read in Telegram)
    response = {
        "equipment_code": metadata.get("code", equipment_code),
        "name": metadata.get("name", "Unknown"),
        "type": metadata.get("type", "unknown"),
        "status": metadata.get("status", "unknown"),
        "health_score": metadata.get("health_score"),
        "location": metadata.get("location"),

        # Device identification
        "manufacturer": device_info.get("manufacturer") or metadata.get("manufacturer"),
        "model": device_info.get("model") or metadata.get("model"),
        "serial_number": device_info.get("serial_number") or metadata.get("serial_number"),
        "firmware_version": device_info.get("firmware_version"),
        "gtin": device_info.get("gtin"),

        # Network/addressing info
        "ip_address": network_info.get("ip_address"),
        "mac_address": network_info.get("mac_address"),
        "protocol": network_info.get("protocol"),
        "dali_address": (
            f"Line {network_info.get('dali_line', 1)}, Address {network_info.get('dali_address')}"
            if network_info.get("dali_address") is not None else None
        ),
        "bacnet_device_id": network_info.get("bacnet_device_id"),
        "modbus_address": network_info.get("modbus_address"),

        # Operating data
        "runtime_hours": operating_data.get("runtime_hours"),
        "lamp_hours": operating_data.get("lamp_hours"),
        "rated_capacity": operating_data.get("rated_capacity"),
        "power_cycles": operating_data.get("power_cycles"),

        # Service info
        "install_date": metadata.get("install_date"),
        "last_service": metadata.get("last_service"),
        "commissioning_date": metadata.get("commissioning_date"),
        "warranty_expiry": metadata.get("warranty_expiry"),

        # Notes from facility manager
        "notes": metadata.get("notes"),

        # Discovery info
        "last_discovery": metadata.get("last_discovery"),
    }

    # Remove None values for cleaner response
    response = {k: v for k, v in response.items() if v is not None}

    return response


@router.get("/work-orders/equipment-summary/{equipment_code}")
async def get_equipment_summary_for_telegram(equipment_code: str):
    """Get a formatted text summary of equipment for Telegram display.

    Returns a pre-formatted text block suitable for sending directly
    to Telegram without additional formatting.

    Args:
        equipment_code: Equipment code

    Returns:
        Text summary formatted for Telegram

    UNAUTHENTICATED - Accepted risk: Clawd bot integration requires external
    webhook access without auth. Summary is derived from equipment-info endpoint
    (already unauthenticated). Used only for technician information display.
    See 65-04 for security rationale.
    """
    # Reuse the detailed endpoint
    try:
        info = await get_equipment_info_for_technician(equipment_code)
    except HTTPException:
        raise

    # Format as readable text for Telegram
    lines = [
        f"📋 *{info.get('name', 'Unknown Equipment')}*",
        f"Code: `{info.get('equipment_code', equipment_code)}`",
        "",
    ]

    # Status and health
    status = info.get("status", "unknown").upper()
    status_emoji = "🟢" if status == "NORMAL" else "🟡" if status == "WARNING" else "🔴" if status == "CRITICAL" else "⚪"
    lines.append(f"{status_emoji} Status: {status}")
    if info.get("health_score"):
        lines.append(f"❤️ Health: {info['health_score']}%")

    # Location
    if info.get("location"):
        lines.append(f"📍 Location: {info['location']}")

    lines.append("")

    # Device info section
    if any(info.get(k) for k in ["manufacturer", "model", "serial_number"]):
        lines.append("*Device Info:*")
        if info.get("manufacturer"):
            lines.append(f"  Manufacturer: {info['manufacturer']}")
        if info.get("model"):
            lines.append(f"  Model: {info['model']}")
        if info.get("serial_number"):
            lines.append(f"  Serial: `{info['serial_number']}`")
        if info.get("firmware_version"):
            lines.append(f"  Firmware: v{info['firmware_version']}")
        lines.append("")

    # Network info section
    if any(info.get(k) for k in ["ip_address", "dali_address", "bacnet_device_id", "modbus_address"]):
        lines.append("*Network Info:*")
        if info.get("ip_address"):
            lines.append(f"  IP: `{info['ip_address']}`")
        if info.get("mac_address"):
            lines.append(f"  MAC: `{info['mac_address']}`")
        if info.get("protocol"):
            lines.append(f"  Protocol: {info['protocol'].upper()}")
        if info.get("dali_address"):
            lines.append(f"  DALI: {info['dali_address']}")
        if info.get("bacnet_device_id"):
            lines.append(f"  BACnet ID: {info['bacnet_device_id']}")
        if info.get("modbus_address"):
            lines.append(f"  Modbus: {info['modbus_address']}")
        lines.append("")

    # Operating data section
    if any(info.get(k) for k in ["runtime_hours", "lamp_hours", "rated_capacity"]):
        lines.append("*Operating Data:*")
        if info.get("runtime_hours"):
            lines.append(f"  Runtime: {info['runtime_hours']:,} hrs")
        if info.get("lamp_hours"):
            lines.append(f"  Lamp Hours: {info['lamp_hours']:,} hrs")
        if info.get("rated_capacity"):
            lines.append(f"  Capacity: {info['rated_capacity']}")
        lines.append("")

    # Service info
    if any(info.get(k) for k in ["last_service", "warranty_expiry"]):
        lines.append("*Service Info:*")
        if info.get("last_service"):
            lines.append(f"  Last Service: {info['last_service']}")
        if info.get("warranty_expiry"):
            lines.append(f"  Warranty: {info['warranty_expiry']}")
        lines.append("")

    # Notes
    if info.get("notes"):
        lines.append("*Notes:*")
        lines.append(f"_{info['notes']}_")

    return {
        "equipment_code": equipment_code,
        "text": "\n".join(lines),
        "parse_mode": "Markdown",
    }
