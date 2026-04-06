"""API endpoints for CAFM system integration (Archibus, Planon, Maximo)."""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.cafm_connector import CAFMConnector, CAFMSystem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cafm")

# In-memory connector instance (local mode)
_connector: CAFMConnector | None = None


# ==================== Request/Response Models ====================


class CAFMConfig(BaseModel):
    system: str = Field(..., description="CAFM system: archibus, planon, maximo")
    api_url: str = Field(..., description="CAFM API base URL")
    username: str | None = None
    password: str | None = None
    api_key: str | None = None


class CAFMConnectionStatus(BaseModel):
    connected: bool
    system: str | None = None
    api_url: str | None = None
    last_sync: str | None = None


class SyncRequest(BaseModel):
    since: str | None = Field(None, description="ISO datetime to sync from")


class WorkOrderPush(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    assigned_to: str = ""
    equipment_code: str = ""
    estimated_hours: float = 0


class StatusUpdate(BaseModel):
    status: str
    resolution: str = ""


# ==================== Endpoints ====================


@router.get("/status", response_model=CAFMConnectionStatus)
async def get_connection_status():
    """Get current CAFM connection status."""
    if _connector and _connector.session:
        return CAFMConnectionStatus(
            connected=True,
            system=_connector.system.value,
            api_url=_connector.config.get("api_url", ""),
        )
    return CAFMConnectionStatus(connected=False)


@router.post("/connect")
async def connect_cafm(config: CAFMConfig):
    """Establish connection to a CAFM system."""
    global _connector

    try:
        system = CAFMSystem(config.system.lower())
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported CAFM system: {config.system}. Use archibus, planon, or maximo.",
        ) from e

    connector_config = {
        "api_url": config.api_url,
        "username": config.username,
        "password": config.password,
        "api_key": config.api_key,
    }

    connector = CAFMConnector(system=system, config=connector_config)
    success = await connector.connect()

    if not success:
        raise HTTPException(status_code=502, detail=f"Failed to connect to {config.system}")

    # Close previous connector if any
    if _connector:
        await _connector.close()

    _connector = connector
    return {"status": "connected", "system": system.value}


@router.post("/disconnect")
async def disconnect_cafm():
    """Disconnect from CAFM system."""
    global _connector
    if _connector:
        await _connector.close()
        _connector = None
    return {"status": "disconnected"}


@router.post("/sync/work-orders")
async def sync_work_orders(request: SyncRequest):
    """Sync work orders from CAFM to SENTINEL."""
    if not _connector or not _connector.session:
        raise HTTPException(status_code=400, detail="Not connected to any CAFM system")

    since = None
    if request.since:
        try:
            since = datetime.fromisoformat(request.since)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid datetime format for 'since'") from e

    work_orders = await _connector.sync_work_orders(since=since)
    return {
        "count": len(work_orders),
        "work_orders": work_orders,
        "synced_at": datetime.now().isoformat(),
    }


@router.post("/work-orders/push")
async def push_work_order(order: WorkOrderPush):
    """Push a SENTINEL work order to the connected CAFM system."""
    if not _connector or not _connector.session:
        raise HTTPException(status_code=400, detail="Not connected to any CAFM system")

    result = await _connector.push_work_order_to_cafm(order.model_dump())
    if not result:
        raise HTTPException(status_code=502, detail="Failed to create work order in CAFM")

    return result


@router.put("/work-orders/{order_id}/status")
async def update_work_order_status(order_id: str, update: StatusUpdate):
    """Update work order status in the connected CAFM system."""
    if not _connector or not _connector.session:
        raise HTTPException(status_code=400, detail="Not connected to any CAFM system")

    result = await _connector.update_cafm_status(order_id, update.status, update.resolution)
    if not result:
        raise HTTPException(status_code=502, detail="Failed to update status in CAFM")

    return result


@router.get("/sync/assets/{site_id}")
async def sync_assets(site_id: str):
    """Sync asset catalog from CAFM for a specific site."""
    if not _connector or not _connector.session:
        raise HTTPException(status_code=400, detail="Not connected to any CAFM system")

    assets = await _connector.sync_assets(site_id=site_id)
    return {
        "count": len(assets),
        "assets": assets,
        "synced_at": datetime.now().isoformat(),
    }
