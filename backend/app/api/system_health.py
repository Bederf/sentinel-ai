"""System Health & Diagnostics API endpoints.

Provides unified system health monitoring and SIMBIOT-powered diagnostics.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
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
    message: str | None = None
    details: dict | None = None


class SystemHealthSnapshot(BaseModel):
    """Current system health snapshot."""

    timestamp: str
    overall_status: str  # "healthy", "degraded", "critical"
    overall_score: int = Field(..., ge=0, le=100)
    components: dict[str, ComponentHealth]
    active_alerts: list[dict] = []
    recommendations: list[str] = []


class DiagnosticResult(BaseModel):
    """SIMBIOT diagnostic result."""

    diagnostic_id: str
    timestamp: str
    target: str
    status: str  # "pending", "running", "completed", "failed"
    duration_seconds: int | None = None
    device_inventory: dict | None = None
    site_config: dict | None = None
    alarms_found: list[dict] | None = None
    health_scores: dict | None = None
    asset_details: list[dict] | None = None
    issues_found: list[str] = []
    recommendations: list[str] = []
    next_steps: list[str] = []
    error_message: str | None = None


class ErrorLog(BaseModel):
    """System error log entry."""

    id: str
    timestamp: str
    category: str  # "bms", "api", "database", "service", "other"
    severity: str  # "warning", "error", "critical"
    component: str
    message: str
    details: dict | None = None
    resolved: bool
    resolved_at: str | None = None


class ErrorLogResponse(BaseModel):
    """Paginated error logs response."""

    total: int
    logs: list[ErrorLog]
    page: int
    page_size: int


class HealthHistoryData(BaseModel):
    """Historical health data for trend analysis."""

    range: str  # "24h", "7d", "30d"
    snapshots: list[dict]
    metrics: dict
    snapshot_count: int


class DiagnosticsRequest(BaseModel):
    """Request to run diagnostics."""

    target: str = "full_system"  # "full_system", "building:{code}", "component:{name}"
    site_code: str | None = None


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
            status = component_detail.get("status", "healthy")

            components[key] = ComponentHealth(
                name=key,
                status=status,
                score=score,
                message=component_detail.get("note"),
                details=component_detail,
            )

        # Derive BMS connectivity as aggregate of the 4 protocol subsystems
        bms_keys = ["supervisor", "field_network", "obix", "lighting"]
        bms_scores = [snapshot.get("component_scores", {}).get(k, 0) for k in bms_keys]
        bms_avg = int(sum(bms_scores) / len(bms_scores)) if bms_scores else 0
        bms_statuses = [snapshot.get("component_details", {}).get(k, {}).get("status", "critical") for k in bms_keys]
        if all(s == "healthy" for s in bms_statuses):
            bms_status: str = "healthy"
        elif any(s == "critical" for s in bms_statuses):
            bms_status = "critical"
        else:
            bms_status = "degraded"

        components["bms_connectivity"] = ComponentHealth(
            name="bms_connectivity",
            status=bms_status,
            score=bms_avg,
            message="Aggregate BMS protocol connectivity",
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
        raise HTTPException(status_code=500, detail=f"Health check failed: {e!s}")


@router.get("/health/history", response_model=HealthHistoryData)
async def get_health_history(
    range: str = Query("24h", pattern="^(24h|7d|30d)$"),
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
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {e!s}")


@router.get("/health/extended")
async def get_extended_health():
    """Extended health including disk, LLM, ML models, background jobs, RAG.

    Returns the standard 7 probes plus 5 extended probes for a comprehensive
    system health overview.
    """
    try:
        return await service.get_extended_health()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extended health check failed: {e!s}")


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
        request: Diagnostics request with target and optional site_code

    Returns:
        {"diagnostic_id": "uuid", "status": "pending"}
    """
    try:
        diagnostic_id = await service.run_diagnostics(
            target=request.target,
            site_code=request.site_code,
        )
        return {
            "diagnostic_id": diagnostic_id,
            "status": "pending",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start diagnostics: {e!s}")


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
            site_config=result.get("results", {}).get("sites"),
            alarms_found=result.get("results", {}).get("alarms"),
            health_scores=result.get("results", {}).get("health_score"),
            asset_details=result.get("results", {}).get("asset_details"),
            recommendations=result.get("recommendations", []),
            error_message=result.get("error_message"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch diagnostics: {e!s}")


@router.get("/error-logs", response_model=ErrorLogResponse)
async def get_error_logs(
    category: str | None = Query(None, description="Filter by category"),
    severity: str | None = Query(None, description="Filter by severity"),
    resolved: bool | None = Query(None, description="Filter by resolved status"),
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
        raise HTTPException(status_code=500, detail=f"Failed to fetch error logs: {e!s}")


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
        raise HTTPException(status_code=500, detail=f"Failed to log error: {e!s}")


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
async def get_monitoring_snapshot(site_id: str | None = Query(None)):
    """Unified monitoring snapshot — ingestion, control, alerts, quality gate."""
    from app.services.monitoring_service import MonitoringService

    svc = MonitoringService()
    return await svc.get_snapshot(site_id=site_id)


# ==================== Adapter Health (SLI Tier 1) ====================


@router.get("/sites/{site_id}/adapter-health")
async def get_adapter_health(site_id: str):
    """Current adapter health + uptime stats per site.

    Returns health state for all registered adapters (BACnet, Niagara, OBIX, shadow bridge).
    """
    from datetime import UTC

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()

    current = supabase.table("adapter_health_current").select("*").eq("site_id", site_id).execute()

    if not current.data:
        return {"site_id": site_id, "adapters": [], "status": "no_data"}

    return {
        "site_id": site_id,
        "timestamp": __import__("datetime").datetime.now(UTC).isoformat(),
        "adapters": [
            {
                "name": row["adapter_name"],
                "type": row["adapter_type"],
                "is_healthy": row["is_healthy"],
                "uptime_1h_percent": row.get("uptime_1h_percent"),
                "uptime_24h_percent": row.get("uptime_24h_percent"),
                "last_check": row["last_check"],
                "consecutive_failures": row.get("consecutive_failures", 0),
            }
            for row in current.data
        ],
    }


@router.get("/sites/{site_id}/adapter-health/history")
async def get_adapter_health_history(
    site_id: str,
    adapter_name: str | None = Query(None),
    window_hours: int = Query(24, ge=1, le=168),
):
    """Time-series history of adapter health checks.

    Args:
        site_id: Site identifier (e.g. 'site-002')
        adapter_name: Filter to a specific adapter (optional)
        window_hours: Lookback window (1-168h, default 24h)
    """
    from datetime import UTC, timedelta

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    cutoff = __import__("datetime").datetime.now(UTC) - timedelta(hours=window_hours)

    query = (
        supabase.table("adapter_health")
        .select("adapter_name, adapter_type, timestamp, is_healthy, latency_ms, consecutive_failures, error_message")
        .eq("site_id", site_id)
        .gte("timestamp", cutoff.isoformat())
        .order("timestamp", desc=True)
    )

    if adapter_name:
        query = query.eq("adapter_name", adapter_name)

    result = query.execute()

    return {
        "site_id": site_id,
        "window_hours": window_hours,
        "adapter_name": adapter_name,
        "records": result.data,
    }


@router.get("/sites/{site_id}/adapter-health/alerts")
async def get_adapter_alerts(site_id: str, unacknowledged: bool = Query(True)):
    """Unacknowledged (or all) adapter failure/recovery alerts."""
    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()

    query = (
        supabase.table("adapter_health_alerts")
        .select("*")
        .eq("site_id", site_id)
        .order("created_at", desc=True)
        .limit(50)
    )

    if unacknowledged:
        query = query.is_("acknowledged_at", "null")

    alerts = query.execute()

    return {
        "site_id": site_id,
        "count": len(alerts.data),
        "alerts": alerts.data,
    }


@router.post("/sites/{site_id}/adapter-health/alerts/{alert_id}/acknowledge")
async def acknowledge_adapter_alert(site_id: str, alert_id: int, user_email: str):
    """Human acknowledges an adapter alert after manual remediation."""
    from datetime import UTC

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()

    result = (
        supabase.table("adapter_health_alerts")
        .update(
            {
                "acknowledged_at": __import__("datetime").datetime.now(UTC).isoformat(),
                "acknowledged_by": user_email,
            }
        )
        .eq("id", alert_id)
        .eq("site_id", site_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"status": "acknowledged", "alert_id": alert_id}


# ==================== Backup Management ====================


@router.get("/backup-status")
async def get_backup_status():
    """Get current PostgreSQL backup status: last run timestamp, set count, size, state."""
    from app.services.backup_service import backup_service

    return backup_service.get_status()


@router.post("/backup/trigger")
async def trigger_backup(background_tasks: BackgroundTasks):
    """Trigger a manual PostgreSQL logical backup. Runs in background.

    ADMIN role required. Returns immediately with status.
    """
    from app.services.backup_service import backup_service

    status = backup_service.get_status()
    if status["state"] == "running":
        raise HTTPException(status_code=409, detail="Backup already in progress")

    background_tasks.add_task(backup_service.run_backup)

    return {
        "status": "started",
        "message": "Backup triggered. Check /api/system/backup-status for progress.",
    }


# ==================== Data Freshness (SLI Tier 2) ====================


@router.get("/sites/{site_id}/data-freshness")
async def get_data_freshness(site_id: str):
    """Current age and SLI pass/fail for all data sources at a site.

    Sources: bms_telemetry (target: 30s), documents (7200s), anomalies (300s),
    recommendations (900s).
    """
    from app.services.system_health_service import SystemHealthService

    health_service = SystemHealthService()
    return await health_service.get_data_freshness(site_id)


@router.get("/sites/{site_id}/data-freshness/history")
async def get_data_freshness_history(
    site_id: str,
    source: str = Query(..., description="data_source value, e.g. bms_telemetry"),
    hours: int = Query(24, ge=1, le=168),
):
    """Breach history for a data source over N hours (default: 24h, max: 168h/7d)."""
    from app.services.system_health_service import SystemHealthService

    health_service = SystemHealthService()
    return await health_service.get_data_freshness_history(site_id, source, hours)


# ==================== API Uptime (SLI Tier 4) ====================


@router.get("/uptime/daily")
async def get_daily_uptime(days: int = Query(30, ge=1, le=365)):
    """Last N days of daily uptime aggregates."""
    from datetime import date, timedelta

    from app.database.supabase_client import get_supabase_client

    cutoff = date.today() - timedelta(days=days)
    supabase = get_supabase_client()

    daily = (
        await supabase.table("api_uptime_daily")
        .select("check_date, total_checks, successful_checks, uptime_percent, avg_latency_ms, max_latency_ms")
        .gte("check_date", cutoff.isoformat())
        .order("check_date", desc=False)
        .execute()
    )

    return {"data": daily.data}


@router.get("/uptime/monthly/current")
async def get_current_month_uptime():
    """Current month's SLO status."""
    from datetime import date

    from app.database.supabase_client import get_supabase_client

    month = date.today().strftime("%Y-%m")
    supabase = get_supabase_client()

    result = await supabase.table("api_uptime_monthly").select("*").eq("month", month).execute()

    if not result.data:
        return {"data": None, "month": month}

    return {"data": result.data[0], "month": month}


@router.get("/uptime/monthly/{month}")
async def get_month_uptime(month: str):
    """Specific month's SLO audit data (YYYY-MM format)."""
    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    result = await supabase.table("api_uptime_monthly").select("*").eq("month", month).execute()

    if not result.data:
        return {"data": None, "month": month}

    return {"data": result.data[0], "month": month}


# ==================== Critical Path Latency (SLI Tier 3) ====================


@router.get("/sites/{site_id}/critical-path")
async def get_critical_path(site_id: str):
    """Current hour's critical path latency stats for a site.

    Returns p50/p99/p99.9/max/avg total latency (ms) from critical_path_hourly
    for the most recent complete hour. SLO target: p99 < 7000ms.
    """
    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    now = datetime.now(timezone.utc)
    hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    result = (
        await supabase.table("critical_path_hourly")
        .select(
            "site_id, hour_start, total_actions, p50_total_ms, p99_total_ms, "
            "p99_9_total_ms, max_total_ms, avg_total_ms, slo_pass"
        )
        .eq("site_id", site_id)
        .eq("hour_start", hour_start.isoformat())
        .execute()
    )

    if not result.data:
        return {
            "site_id": site_id,
            "hour_start": hour_start.isoformat(),
            "data": None,
            "message": "No traces for this hour yet",
        }

    return {"site_id": site_id, "hour_start": hour_start.isoformat(), "data": result.data[0]}


@router.get("/sites/{site_id}/critical-path/history")
async def get_critical_path_history(
    site_id: str,
    days: int = Query(7, ge=1, le=30),
):
    """Last N days of hourly critical path aggregates for a site."""
    from datetime import date, timedelta

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    cutoff = date.today() - timedelta(days=days)

    result = (
        await supabase.table("critical_path_hourly")
        .select(
            "site_id, hour_start, total_actions, p50_total_ms, p99_total_ms, "
            "p99_9_total_ms, max_total_ms, avg_total_ms, slo_pass"
        )
        .eq("site_id", site_id)
        .gte("hour_start", cutoff.isoformat())
        .order("hour_start", desc=False)
        .execute()
    )

    return {"site_id": site_id, "days": days, "data": result.data}
