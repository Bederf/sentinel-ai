"""
ServiceNow Integration API Routes.

Phase 138: Read-only ITSM integration endpoints for incident/work-order intelligence.

Auth gating:
- BASE endpoints (status, discover, incidents): require_auth(AuthLevel.AUTHENTICATED)
- MAINTENANCE endpoints (work-orders, query, schema, history, aggregate): require_module(ModuleType.MAINTENANCE)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.middleware.auth_middleware import require_auth, require_module
from app.models.auth import AuthContext, AuthLevel
from app.models.module_registry import ModuleType
from app.services.servicenow_service import get_servicenow_service

logger = logging.getLogger("sentinel.api.servicenow")

router = APIRouter(prefix="/api/servicenow", tags=["servicenow"])


# =============================================================================
# BASE endpoints — available to any authenticated user
# =============================================================================


@router.get("/status")
async def get_servicenow_status(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Return current ServiceNow connection status.

    Used by System Health dashboard to show integration state.
    """
    svc = get_servicenow_service()
    status = svc.status
    return {
        "status": status.status.value,
        "message": status.message,
        "instance_name": status.instance_name,
        "discovered_tables": status.discovered_tables,
        "last_checked": status.last_checked,
        "is_configured": svc.is_configured,
    }


@router.post("/discover")
async def discover_servicenow(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Force a connection check and table re-discovery.

    Useful after updating credentials or troubleshooting connectivity.
    """
    svc = get_servicenow_service()
    status = await svc.check_connection()
    return {
        "status": status.status.value,
        "message": status.message,
        "instance_name": status.instance_name,
        "discovered_tables": status.discovered_tables,
        "last_checked": status.last_checked,
    }


@router.get("/incidents")
async def get_incidents(
    priority: Optional[int] = Query(None, ge=1, le=4, description="Priority filter (1=Critical..4=Low)"),
    category: Optional[str] = Query(None, description="Category filter"),
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Fetch open incidents with optional filters.

    Read-only intelligence for portfolio dashboards and alert correlation.
    """
    svc = get_servicenow_service()
    return await svc.get_open_incidents(
        priority=priority,
        category=category,
        limit=limit,
    )


@router.get("/incidents/summary")
async def get_incident_summary(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Aggregate incident counts by priority and state.

    Used by portfolio dashboard for at-a-glance ITSM metrics.
    """
    svc = get_servicenow_service()
    return await svc.get_incident_summary()


# =============================================================================
# MAINTENANCE-gated endpoints — require maintenance module
# =============================================================================


@router.get("/work-orders")
async def get_work_orders(
    state: Optional[str] = Query(None, description="State filter"),
    priority: Optional[int] = Query(None, ge=1, le=4, description="Priority filter"),
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    auth: AuthContext = Depends(require_module(ModuleType.MAINTENANCE)),
):
    """Fetch work orders / service tasks from ServiceNow.

    Requires the MAINTENANCE module to be active.
    """
    svc = get_servicenow_service()
    return await svc.get_work_orders(
        state=state,
        priority=priority,
        limit=limit,
    )


@router.get("/work-orders/summary")
async def get_work_order_summary(
    auth: AuthContext = Depends(require_module(ModuleType.MAINTENANCE)),
):
    """Aggregate work order counts by state and priority.

    Requires the MAINTENANCE module to be active.
    """
    svc = get_servicenow_service()
    return await svc.get_aggregate(
        table="wm_order",
        query="",
        group_by="state,priority",
    )


@router.get("/query/{table}")
async def query_table(
    table: str,
    query: Optional[str] = Query(None, description="Encoded query string"),
    fields: Optional[str] = Query(None, description="Comma-separated field names"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    order_by: Optional[str] = Query(None, description="Sort field (prefix '-' for desc)"),
    auth: AuthContext = Depends(require_module(ModuleType.MAINTENANCE)),
):
    """Generic read-only table query.

    Requires the MAINTENANCE module to be active.
    """
    svc = get_servicenow_service()
    return await svc.query_table(
        table=table,
        query=query or "",
        fields=fields or "",
        limit=limit,
        offset=offset,
        order_by=order_by or "",
    )


@router.get("/schema/{table}")
async def get_table_schema(
    table: str,
    auth: AuthContext = Depends(require_module(ModuleType.MAINTENANCE)),
):
    """Inspect table columns via sys_dictionary.

    Results are session-cached. Requires the MAINTENANCE module.
    """
    svc = get_servicenow_service()
    return await svc.get_table_schema(table)


@router.get("/history/{table}/{sys_id}")
async def get_record_history(
    table: str,
    sys_id: str,
    auth: AuthContext = Depends(require_module(ModuleType.MAINTENANCE)),
):
    """Fetch audit trail for a specific ServiceNow record.

    Requires the MAINTENANCE module to be active.
    """
    svc = get_servicenow_service()
    return await svc.get_record_history(table, sys_id)


@router.get("/aggregate/{table}")
async def get_aggregate(
    table: str,
    query: Optional[str] = Query(None, description="Encoded query string"),
    group_by: Optional[str] = Query(None, description="Comma-separated group-by fields"),
    auth: AuthContext = Depends(require_module(ModuleType.MAINTENANCE)),
):
    """Stats API for counts and breakdowns on any table.

    Requires the MAINTENANCE module to be active.
    """
    svc = get_servicenow_service()
    return await svc.get_aggregate(
        table=table,
        query=query or "",
        group_by=group_by or "",
    )
