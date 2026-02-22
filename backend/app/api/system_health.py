"""System Health & Diagnostics API endpoints.

Provides unified system health monitoring and SIMBIOT-powered diagnostics.
"""

from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.system_health_service import SystemHealthService

router = APIRouter(prefix="/api/system", tags=["system-health"])
service = SystemHealthService()


# ==================== Response Models ====================


class ComponentHealth(BaseModel):
    """Health status of a system component."""

    name: str
    status: str  # "healthy", "degraded", "critical"
    score: int = Field(..., ge=0, le=100)
    message: Optional[str] = None
    details: Optional[dict] = None


class SystemHealthSnapshot(BaseModel):
    """Current system health snapshot."""

    timestamp: str
    overall_status: str  # "healthy", "degraded", "critical"
    overall_score: int = Field(..., ge=0, le=100)
    components: dict[str, ComponentHealth]
    active_alerts: List[dict] = []
    recommendations: List[str] = []


class DiagnosticResult(BaseModel):
    """SIMBIOT diagnostic result."""

    diagnostic_id: str
    timestamp: str
    target: str
    status: str  # "pending", "running", "completed", "failed"
    duration_seconds: Optional[int] = None
    device_inventory: Optional[dict] = None
    building_config: Optional[dict] = None
    alarms_found: Optional[List[dict]] = None
    health_scores: Optional[dict] = None
    asset_details: Optional[List[dict]] = None
    issues_found: List[str] = []
    recommendations: List[str] = []
    next_steps: List[str] = []
    error_message: Optional[str] = None


class ErrorLog(BaseModel):
    """System error log entry."""

    id: str
    timestamp: str
    category: str  # "bms", "api", "database", "service", "other"
    severity: str  # "warning", "error", "critical"
    component: str
    message: str
    details: Optional[dict] = None
    resolved: bool
    resolved_at: Optional[str] = None


class ErrorLogResponse(BaseModel):
    """Paginated error logs response."""

    total: int
    logs: List[ErrorLog]
    page: int
    page_size: int


class HealthHistoryData(BaseModel):
    """Historical health data for trend analysis."""

    range: str  # "24h", "7d", "30d"
    snapshots: List[dict]
    metrics: dict
    snapshot_count: int


class DiagnosticsRequest(BaseModel):
    """Request to run diagnostics."""

    target: str = "full_system"  # "full_system", "building:{code}", "component:{name}"
    building_code: Optional[str] = None


# ==================== Endpoints ====================


@router.get("/health", response_model=SystemHealthSnapshot)
async def get_current_health():
    """
    Get unified system health snapshot.

    Aggregates health from 15+ backend endpoints into a single view.
    Cached with 30-second TTL.

    Returns:
        SystemHealthSnapshot with overall status and component details
    """
    try:
        snapshot = await service.get_current_health()

        # Transform to response model
        components = {}
        for key, score in snapshot.get("component_scores", {}).items():
            component_detail = snapshot.get("component_details", {}).get(key, {})

            if score >= 80:
                status = "healthy"
            elif score >= 60:
                status = "degraded"
            else:
                status = "critical"

            components[key] = ComponentHealth(
                name=key,
                status=status,
                score=score,
                details=component_detail,
            )

        return SystemHealthSnapshot(
            timestamp=snapshot["timestamp"],
            overall_status=snapshot["overall_status"],
            overall_score=snapshot["overall_score"],
            components=components,
            recommendations=[
                "Monitor system performance",
                "Review error logs for issues",
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/health/history", response_model=HealthHistoryData)
async def get_health_history(
    range: str = Query("24h", regex="^(24h|7d|30d)$"),
):
    """
    Get historical health data for trend analysis.

    Returns snapshots and metrics over specified time range.

    Args:
        range: "24h", "7d", or "30d"

    Returns:
        Historical snapshots and calculated metrics
    """
    try:
        history = await service.get_health_history(range)
        return HealthHistoryData(
            range=history["range"],
            snapshots=history["snapshots"],
            metrics=history["metrics"],
            snapshot_count=history["snapshot_count"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


@router.post("/diagnostics")
async def run_diagnostics(
    request: DiagnosticsRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger SIMBIOT diagnostics workflow.

    Runs 6 diagnostic tools:
    1. Device inventory
    2. DALI gateway check
    3. Building configuration
    4. Active alarms
    5. Health scores
    6. Asset details

    Returns immediately with diagnostic_id for polling.

    Args:
        request: Diagnostics request with target and optional building_code

    Returns:
        {"diagnostic_id": "uuid", "status": "pending"}
    """
    try:
        diagnostic_id = await service.run_diagnostics(
            target=request.target,
            building_code=request.building_code,
        )
        return {
            "diagnostic_id": diagnostic_id,
            "status": "pending",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start diagnostics: {str(e)}")


@router.get("/diagnostics/{diagnostic_id}", response_model=DiagnosticResult)
async def get_diagnostic_results(diagnostic_id: str):
    """
    Poll diagnostic results by ID.

    Clients should poll this endpoint every 5 seconds until status is not "pending" or "running".

    Args:
        diagnostic_id: Diagnostic request ID

    Returns:
        Diagnostic result with findings and recommendations
    """
    try:
        result = await service.get_diagnostic_results(diagnostic_id)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return DiagnosticResult(
            diagnostic_id=result["diagnostic_id"],
            timestamp=result["timestamp"],
            target=result["target"],
            status=result["status"],
            duration_seconds=result.get("duration_seconds"),
            device_inventory=result.get("results", {}).get("device_inventory"),
            building_config=result.get("results", {}).get("buildings"),
            alarms_found=result.get("results", {}).get("alarms"),
            health_scores=result.get("results", {}).get("health_score"),
            asset_details=result.get("results", {}).get("asset_details"),
            recommendations=result.get("recommendations", []),
            error_message=result.get("error_message"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch diagnostics: {str(e)}")


@router.get("/error-logs", response_model=ErrorLogResponse)
async def get_error_logs(
    category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get error logs with filtering and pagination.

    Args:
        category: Filter by category (bms, api, database, service, other)
        severity: Filter by severity (warning, error, critical)
        resolved: Filter by resolved status (true/false)
        limit: Max results (1-500, default 100)
        offset: Pagination offset

    Returns:
        Paginated list of error logs
    """
    try:
        result = await service.get_error_logs(
            category=category,
            severity=severity,
            resolved=resolved,
            limit=limit,
            offset=offset,
        )

        return ErrorLogResponse(
            total=result["total"],
            logs=[ErrorLog(**log) for log in result["logs"]],
            page=result["page"],
            page_size=result["page_size"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch error logs: {str(e)}")


# ==================== Internal Endpoints ====================


@router.post("/error-logs/log")
async def log_error(
    category: str,
    severity: str,
    component: str,
    message: str,
):
    """
    Log a system error (internal endpoint).

    Args:
        category: Error category
        severity: Error severity
        component: Component name
        message: Error message

    Returns:
        {"error_id": "uuid"}
    """
    try:
        error_id = await service.log_system_error(
            category=category,
            severity=severity,
            component=component,
            message=message,
        )
        return {"error_id": error_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log error: {str(e)}")


@router.post("/maintenance/auto-resolve-errors")
async def trigger_auto_resolve_errors(background_tasks: BackgroundTasks):
    """
    Trigger auto-resolution of stale errors (internal endpoint).

    Runs as background task to avoid blocking request.

    Returns:
        {"task_started": true}
    """
    background_tasks.add_task(service.auto_resolve_stale_errors)
    return {"task_started": True}


@router.post("/maintenance/store-snapshot")
async def trigger_store_snapshot(background_tasks: BackgroundTasks):
    """
    Trigger immediate health snapshot storage (internal endpoint).

    Returns:
        {"task_started": true}
    """

    async def store_task():
        snapshot = await service.get_current_health()
        await service.store_health_snapshot(snapshot)

    background_tasks.add_task(store_task)
    return {"task_started": True}


@router.get("/monitoring")
async def get_monitoring_snapshot(building_id: Optional[str] = Query(None)):
    """Unified monitoring snapshot — ingestion, control, alerts, quality gate."""
    from app.services.monitoring_service import MonitoringService

    svc = MonitoringService()
    return await svc.get_snapshot(building_id=building_id)
