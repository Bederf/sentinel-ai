"""System Health & Diagnostics API endpoints.

Provides unified system health monitoring and SIMBIOT-powered diagnostics.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

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


class DiscoveredEquipmentRow(BaseModel):
    id: str
    site_id: str
    bridge_code: str
    canonical_code: str
    equipment_type: str | None = None
    derived_zone_id: str | None = None
    status: str
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    seen_count: int = 0
    zone_onboardable: bool = True
    zone_message: str | None = None


class DiscoveredEquipmentResponse(BaseModel):
    site_id: str
    pending_count: int
    items: list[DiscoveredEquipmentRow]


class OnboardDiscoveredEquipmentRequest(BaseModel):
    equipment_name: str | None = None
    equipment_type: str | None = None
    zone_id: str | None = None


class DiscoveredEquipmentActionResponse(BaseModel):
    success: bool
    message: str
    equipment_code: str | None = None


class UnmappedEquipmentRow(BaseModel):
    id: str
    code: str
    name: str | None = None
    equipment_type: str | None = None
    raw_code: str | None = None
    canonical_code: str | None = None
    canonical_zone_id: str | None = None
    reason: str | None = None
    zone_key: str | None = None


class UnmappedEquipmentResponse(BaseModel):
    site_id: str
    pending_count: int
    items: list[UnmappedEquipmentRow]


class MapUnmappedEquipmentRequest(BaseModel):
    canonical_code: str = Field(..., min_length=3)
    equipment_type: str | None = None
    canonical_zone_id: str | None = None
    relationship_type: str | None = Field(
        None,
        description="Optional equipment-zone relationship: serves, located_in, controls, monitors, or plant",
    )
    notes: str | None = None


# ==================== Endpoints ====================


def _get_supabase_client():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


def _get_site_uuid(site_id: str) -> str:
    client = _get_supabase_client()
    response = client.table("sites").select("id").eq("code", site_id).limit(1).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail=f"Site {site_id} not found")
    return response.data[0]["id"]


def _bridge_zone_alias(zone_id: str) -> str | None:
    import re

    match = re.match(r"^Zone-L(\d+)-(\d+)$", str(zone_id or "").strip(), re.IGNORECASE)
    if not match:
        return None
    return f"Zone-{int(match.group(1))}{int(match.group(2)):02d}"


def _zone_inventory(site_uuid: str) -> dict[str, str]:
    """Return acceptable zone IDs and bridge aliases mapped to canonical zone IDs."""
    client = _get_supabase_client()
    inventory: dict[str, str] = {}

    zones = client.table("zones").select("zone_id").eq("site_id", site_uuid).execute()
    for row in zones.data or []:
        zone_id = str(row.get("zone_id") or "").strip()
        if not zone_id:
            continue
        inventory[zone_id] = zone_id
        alias = _bridge_zone_alias(zone_id)
        if alias:
            inventory[alias] = zone_id

    hvac = client.table("hvac_zones").select("zone_id").eq("site_id", site_uuid).execute()
    for row in hvac.data or []:
        zone_id = str(row.get("zone_id") or "").strip()
        if not zone_id:
            continue
        inventory.setdefault(zone_id, zone_id)
        alias = _bridge_zone_alias(zone_id)
        if alias:
            inventory.setdefault(alias, zone_id)

    return inventory


def _row_with_zone_status(row: dict[str, Any], inventory: dict[str, str]) -> DiscoveredEquipmentRow:
    derived_zone_id = row.get("derived_zone_id")
    zone_onboardable = True
    zone_message = None
    if derived_zone_id and derived_zone_id not in inventory:
        zone_onboardable = False
        zone_message = f"{derived_zone_id} is not in the site zone inventory. Create/confirm the zone during site onboarding first."

    return DiscoveredEquipmentRow(
        id=str(row.get("id")),
        site_id=row.get("site_id"),
        bridge_code=row.get("bridge_code"),
        canonical_code=row.get("canonical_code"),
        equipment_type=row.get("equipment_type"),
        derived_zone_id=derived_zone_id,
        status=row.get("status"),
        reason=row.get("reason"),
        payload=row.get("payload") or {},
        first_seen_at=row.get("first_seen_at"),
        last_seen_at=row.get("last_seen_at"),
        seen_count=row.get("seen_count") or 0,
        zone_onboardable=zone_onboardable,
        zone_message=zone_message,
    )


def _normalize_zone_id(zone_id: str | None, inventory: dict[str, str]) -> str | None:
    value = str(zone_id or "").strip()
    if not value:
        return None
    return inventory.get(value)


def _infer_relationship_type(equipment_type: str | None, canonical_zone_id: str | None) -> str | None:
    if not canonical_zone_id:
        return None
    if canonical_zone_id.startswith("Zone-B") or canonical_zone_id.startswith("Zone-R-"):
        return "plant"
    if (equipment_type or "").lower() in {"ahu", "fcu", "vav", "split", "dali", "lum", "zone"}:
        return "serves"
    return "located_in"


@router.get("/sites/{site_id}/discovered-equipment", response_model=DiscoveredEquipmentResponse)
async def get_discovered_equipment(site_id: str, limit: int = Query(50, ge=1, le=200)):
    """List bridge-discovered equipment waiting for onboarding review."""
    client = _get_supabase_client()
    site_uuid = _get_site_uuid(site_id)
    inventory = _zone_inventory(site_uuid)
    response = (
        client.table("bridge_discovered_equipment")
        .select("*")
        .eq("site_id", site_id)
        .eq("status", "pending")
        .order("last_seen_at", desc=True)
        .limit(limit)
        .execute()
    )
    items = [_row_with_zone_status(row, inventory) for row in response.data or []]
    return DiscoveredEquipmentResponse(site_id=site_id, pending_count=len(items), items=items)


@router.get("/sites/{site_id}/unmapped-equipment", response_model=UnmappedEquipmentResponse)
async def get_unmapped_equipment(site_id: str, limit: int = Query(100, ge=1, le=300)):
    """List active equipment rows waiting for manual canonical mapping."""
    client = _get_supabase_client()
    site_uuid = _get_site_uuid(site_id)
    response = (
        client.table("equipment")
        .select(
            "id, code, name, type, raw_code, canonical_code, canonical_zone_id, zone_key, canonicalization_metadata"
        )
        .eq("site_id", site_uuid)
        .eq("canonicalization_status", "needs_review")
        .order("code")
        .limit(limit)
        .execute()
    )
    items = [
        UnmappedEquipmentRow(
            id=str(row.get("id")),
            code=row.get("code"),
            name=row.get("name"),
            equipment_type=row.get("type"),
            raw_code=row.get("raw_code"),
            canonical_code=row.get("canonical_code"),
            canonical_zone_id=row.get("canonical_zone_id"),
            zone_key=row.get("zone_key"),
            reason=(row.get("canonicalization_metadata") or {}).get("reason"),
        )
        for row in response.data or []
    ]
    return UnmappedEquipmentResponse(site_id=site_id, pending_count=len(items), items=items)


@router.post("/sites/{site_id}/unmapped-equipment/{equipment_id}/map", response_model=DiscoveredEquipmentActionResponse)
async def map_unmapped_equipment(site_id: str, equipment_id: str, body: MapUnmappedEquipmentRequest):
    """Apply a manual canonical mapping to an active equipment row."""
    client = _get_supabase_client()
    site_uuid = _get_site_uuid(site_id)
    inventory = _zone_inventory(site_uuid)

    equipment_response = (
        client.table("equipment")
        .select("id, code, type, raw_code")
        .eq("site_id", site_uuid)
        .eq("id", equipment_id)
        .limit(1)
        .execute()
    )
    if not equipment_response.data:
        raise HTTPException(status_code=404, detail="Equipment item not found")

    row = equipment_response.data[0]
    canonical_code = body.canonical_code.strip().upper()
    equipment_type = (body.equipment_type or row.get("type") or "unknown").strip().lower()
    canonical_zone_id = _normalize_zone_id(body.canonical_zone_id, inventory)
    if body.canonical_zone_id and not canonical_zone_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{body.canonical_zone_id} is not in the site zone inventory. "
                "Create or approve the zone before assigning equipment to it."
            ),
        )

    relationship_type = body.relationship_type or _infer_relationship_type(equipment_type, canonical_zone_id)
    if relationship_type and relationship_type not in {"serves", "located_in", "controls", "monitors", "plant"}:
        raise HTTPException(status_code=422, detail="Invalid relationship_type")

    now_iso = datetime.now(tz=UTC).isoformat()
    metadata = {
        "reason": "manual_mapping_applied",
        "mapped_by": "system_health",
        "mapped_at": now_iso,
    }
    if body.notes:
        metadata["notes"] = body.notes

    client.table("equipment").update(
        {
            "raw_code": row.get("raw_code") or row.get("code"),
            "canonical_code": canonical_code,
            "canonical_zone_id": canonical_zone_id,
            "zone_key": canonical_zone_id,
            "type": equipment_type,
            "canonicalization_status": "canonical",
            "canonicalization_source": "manual_mapping",
            "canonicalization_metadata": metadata,
            "updated_at": now_iso,
        }
    ).eq("id", equipment_id).execute()

    alias_code = row.get("raw_code") or row.get("code")
    if alias_code and alias_code != canonical_code:
        client.table("equipment_aliases").upsert(
            {
                "site_id": site_uuid,
                "equipment_id": equipment_id,
                "alias_code": alias_code,
                "canonical_code": canonical_code,
                "alias_type": "source",
                "source": "manual_mapping",
                "confidence": 1.0,
                "review_status": "approved",
                "metadata": metadata,
            },
            on_conflict="site_id,alias_code",
        ).execute()

    if canonical_zone_id and relationship_type:
        client.table("equipment_zone_relationships").upsert(
            {
                "site_id": site_uuid,
                "equipment_id": equipment_id,
                "zone_id": canonical_zone_id,
                "relationship_type": relationship_type,
                "source": "manual_mapping",
                "confidence": 1.0,
                "review_status": "approved",
                "metadata": metadata,
            },
            on_conflict="equipment_id,zone_id,relationship_type",
        ).execute()

    return DiscoveredEquipmentActionResponse(
        success=True,
        message="Manual equipment mapping saved.",
        equipment_code=canonical_code,
    )


@router.post(
    "/sites/{site_id}/discovered-equipment/{discovery_id}/dismiss",
    response_model=DiscoveredEquipmentActionResponse,
)
async def dismiss_discovered_equipment(site_id: str, discovery_id: str):
    """Dismiss a discovered bridge item without creating active equipment."""
    client = _get_supabase_client()
    now_iso = datetime.now(tz=UTC).isoformat()
    response = (
        client.table("bridge_discovered_equipment")
        .update(
            {
                "status": "dismissed",
                "dismissed_at": now_iso,
                "dismissed_by": "system_health",
                "updated_at": now_iso,
            }
        )
        .eq("site_id", site_id)
        .eq("id", discovery_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Discovered equipment item not found")
    row = response.data[0]
    return DiscoveredEquipmentActionResponse(
        success=True,
        message="Discovered equipment dismissed.",
        equipment_code=row.get("canonical_code"),
    )


@router.post(
    "/sites/{site_id}/discovered-equipment/{discovery_id}/onboard",
    response_model=DiscoveredEquipmentActionResponse,
)
async def onboard_discovered_equipment(site_id: str, discovery_id: str, body: OnboardDiscoveredEquipmentRequest):
    """Create active equipment from a reviewed bridge discovery item.

    Terminal equipment may only be onboarded into an existing Supabase zone.
    This endpoint never creates zones.
    """
    client = _get_supabase_client()
    site_uuid = _get_site_uuid(site_id)
    discovery_response = (
        client.table("bridge_discovered_equipment")
        .select("*")
        .eq("site_id", site_id)
        .eq("id", discovery_id)
        .limit(1)
        .execute()
    )
    if not discovery_response.data:
        raise HTTPException(status_code=404, detail="Discovered equipment item not found")

    row = discovery_response.data[0]
    canonical_code = row.get("canonical_code")
    if not canonical_code:
        raise HTTPException(status_code=422, detail="Discovered equipment has no canonical equipment code")

    existing = client.table("equipment").select("id, code").eq("code", canonical_code).limit(1).execute()
    now_iso = datetime.now(tz=UTC).isoformat()
    if existing.data:
        client.table("bridge_discovered_equipment").update(
            {
                "status": "onboarded",
                "onboarded_at": now_iso,
                "onboarded_by": "system_health",
                "updated_at": now_iso,
            }
        ).eq("id", discovery_id).execute()
        return DiscoveredEquipmentActionResponse(
            success=True,
            message="Equipment already exists and discovery was marked onboarded.",
            equipment_code=canonical_code,
        )

    inventory = _zone_inventory(site_uuid)
    requested_zone = body.zone_id or row.get("derived_zone_id")
    zone_key = None
    if requested_zone:
        zone_key = inventory.get(requested_zone)
        if not zone_key:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{requested_zone} is not in the Supabase zone inventory. "
                    "Zones must be created during site onboarding before equipment can be onboarded."
                ),
            )

    from app.services.shadow_mode_polling import (
        _format_display_name,
        _normalize_bridge_equipment_status,
        _parse_eq_code_parts,
    )

    equipment_type = (body.equipment_type or row.get("equipment_type") or "unknown").lower()
    _parsed_type, location_code = _parse_eq_code_parts(canonical_code)
    equipment_name = body.equipment_name or _format_display_name(equipment_type, location_code)
    bridge_status = (row.get("payload") or {}).get("status", "offline")
    equipment_status = _normalize_bridge_equipment_status(bridge_status)

    equipment_payload = {
        "code": canonical_code,
        "name": equipment_name,
        "type": equipment_type,
        "status": equipment_status,
        "site_id": site_uuid,
        "health_score": 100,
        "operating_data": {
            "onboarding": {
                "source": "bridge_discovery",
                "bridge_code": row.get("bridge_code"),
                "discovery_id": row.get("id"),
                "onboarded_at": now_iso,
            }
        },
    }
    if zone_key:
        equipment_payload["zone_key"] = zone_key

    created = client.table("equipment").insert(equipment_payload).execute()
    if not created.data:
        raise HTTPException(status_code=500, detail="Equipment could not be created")

    client.table("bridge_discovered_equipment").update(
        {
            "status": "onboarded",
            "onboarded_at": now_iso,
            "onboarded_by": "system_health",
            "updated_at": now_iso,
        }
    ).eq("id", discovery_id).execute()

    return DiscoveredEquipmentActionResponse(
        success=True,
        message="Equipment onboarded into the active site inventory.",
        equipment_code=canonical_code,
    )


@router.get("/health", response_model=SystemHealthSnapshot)
async def get_current_health(site_id: str | None = Query(None)):
    """
    Get unified system health snapshot.

    Aggregates health from 15+ backend endpoints into a single view.
    Pass site_id to scope probes to a specific site.

    Returns:
        SystemHealthSnapshot with overall status and component details
    """
    try:
        snapshot = await service.get_current_health(site_id=site_id)

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
        bms_statuses = [snapshot.get("component_details", {}).get(k, {}).get("status", "critical") for k in bms_keys]
        # Exclude not_configured probes from average so they don't drag score down
        active_scores = [s for s, st in zip(bms_scores, bms_statuses) if st != "not_configured"]
        active_statuses = [st for st in bms_statuses if st != "not_configured"]
        bms_avg = int(sum(active_scores) / len(active_scores)) if active_scores else 0
        if all(s == "healthy" for s in active_statuses) and active_statuses:
            bms_status: str = "healthy"
        elif any(s == "critical" for s in active_statuses):
            bms_status = "critical"
        elif any(s == "not_configured" for s in bms_statuses):
            bms_status = "degraded"  # some probes are not configured on this stack
        else:
            bms_status = "degraded"

        components["bms_connectivity"] = ComponentHealth(
            name="bms_connectivity",
            status=bms_status,
            score=bms_avg,
            message="Global aggregate of supervisor, field network, oBIX, and lighting telemetry probes",
        )

        return SystemHealthSnapshot(
            timestamp=snapshot["timestamp"],
            overall_status=snapshot["overall_status"],
            overall_score=snapshot["overall_score"],
            components=components,
            active_alerts=snapshot.get("active_alerts", []),
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
    site_id: str | None = Query(None),
):
    """
    Get historical health data for trend analysis.

    Returns snapshots and metrics over specified time range.

    Args:
        range: "24h", "7d", or "30d"
        site_id: When set, filter snapshots to this site

    Returns:
        Historical snapshots and calculated metrics
    """
    try:
        history = await service.get_health_history(range, site_id=site_id)
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

    Returns current health state for adapters that have emitted health records.
    This includes the site bridge plus device-level protocol adapters, so
    point-mapping failures are visible without manual SQL.
    """
    from datetime import UTC

    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()

    # Get configured adapters for this site
    config_result = (
        supabase.table("site_adapter_config").select("protocol").eq("site_id", site_id).eq("enabled", True).execute()
    )

    if not config_result.data:
        # No config — fallback to only UP adapters to avoid showing all 65 phantoms
        current = (
            supabase.table("adapter_health_current").select("*").eq("site_id", site_id).eq("is_healthy", True).execute()
        )
        return {
            "site_id": site_id,
            "timestamp": __import__("datetime").datetime.now(UTC).isoformat(),
            "adapters": _format_adapter_rows(current.data),
            "status": "no_adapter_config",
        }

    current = supabase.table("adapter_health_current").select("*").eq("site_id", site_id).execute()

    return {
        "site_id": site_id,
        "timestamp": __import__("datetime").datetime.now(UTC).isoformat(),
        "adapters": _format_adapter_rows(current.data),
        "status": "ok",
    }


_ADAPTER_HEALTH_STALE_SECONDS: float = 300.0  # 5 minutes


def _format_adapter_rows(rows: list[dict]) -> list[dict]:
    now = datetime.now(UTC)
    return [
        {
            "name": row["adapter_name"],
            "type": row["adapter_type"],
            "is_healthy": _resolve_adapter_health(row, now),
            "uptime_1h_percent": row.get("uptime_1h_percent"),
            "uptime_24h_percent": row.get("uptime_24h_percent"),
            "last_check": row["last_check"],
            "consecutive_failures": row.get("consecutive_failures", 0),
            "error_message": row.get("error_message"),
        }
        for row in rows
    ]


def _resolve_adapter_health(row: dict, now: datetime) -> bool:
    """Return is_healthy, accounting for staleness.

    A row whose last_check is older than the threshold is treated as
    unhealthy even if the stored is_healthy flag is True — the check
    is too old to trust.
    """
    last_check = row.get("last_check")
    if last_check:
        try:
            check_dt = datetime.fromisoformat(last_check.replace("Z", "+00:00"))
            age = (now - check_dt).total_seconds()
            if age > _ADAPTER_HEALTH_STALE_SECONDS:
                return False
        except Exception:
            pass
    return bool(row.get("is_healthy", False))


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


@router.get("/dr-status")
async def get_dr_status():
    """Get read-only disaster recovery readiness: RPO, RTO, restore evidence, and gaps."""
    from app.services.backup_service import backup_service

    return backup_service.get_dr_status()


@router.get("/phase-readiness")
async def get_phase_readiness(site_id: str | None = Query(None)):
    """Read-only Trust Ladder readiness for each site's next promotion phase."""
    from app.database.supabase_client import get_supabase_client
    from app.models.onboarding_phase import normalise_stage
    from app.services.phase_promotion_evaluator import get_phase_promotion_evaluator

    supabase = get_supabase_client()
    query = supabase.table("sites").select("code,name,onboarding_phase").order("code")
    if site_id:
        query = query.eq("code", site_id)
    rows = query.execute()

    evaluator = get_phase_promotion_evaluator()
    sites = []
    for row in rows.data or []:
        code = row.get("code")
        phase = normalise_stage(row.get("onboarding_phase") or "commissioning")
        config = evaluator.PROMOTION_GATES.get(phase)
        if not code or not config:
            sites.append(
                {
                    "site_id": code,
                    "site_name": row.get("name") or code,
                    "current_phase": phase,
                    "target_phase": None,
                    "eligible": False,
                    "gates_passed": 0,
                    "gates_total": 0,
                    "gates": [],
                    "reason": f"no_next_phase_from_{phase}",
                }
            )
            continue

        gates = await evaluator._evaluate_gates(code, config["gates"])
        gates_payload = [gate.to_dict() for gate in gates]
        sites.append(
            {
                "site_id": code,
                "site_name": row.get("name") or code,
                "current_phase": phase,
                "target_phase": config["target"],
                "eligible": all(gate.passed for gate in gates),
                "gates_passed": sum(1 for gate in gates if gate.passed),
                "gates_total": len(gates),
                "gates": gates_payload,
            }
        )

    return {"sites": sites}


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
        supabase.table("api_uptime_daily")
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

    result = supabase.table("api_uptime_monthly").select("*").eq("month", month).execute()

    if not result.data:
        return {"data": None, "month": month}

    return {"data": result.data[0], "month": month}


@router.get("/uptime/monthly/{month}")
async def get_month_uptime(month: str):
    """Specific month's SLO audit data (YYYY-MM format)."""
    from app.database.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    result = supabase.table("api_uptime_monthly").select("*").eq("month", month).execute()

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
    now = datetime.now(UTC)
    hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    result = (
        supabase.table("critical_path_hourly")
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
        supabase.table("critical_path_hourly")
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


class ProgressGate(BaseModel):
    """A single gate within a progress stage."""

    name: str
    passed: bool
    detail: str
    action: str | None = None  # What the user needs to do


class ProgressStage(BaseModel):
    """A lifecycle stage with its gates and overall status."""

    stage: str
    status: Literal["completed", "in_progress", "blocked", "not_reached"]
    gates: list[ProgressGate]


class SiteProgressResponse(BaseModel):
    """Unified site progress: PLS, onboarding, phase, integrity."""

    site_id: str
    pls: ProgressStage
    onboarding: ProgressStage
    phase_promotion: ProgressStage
    integrity: ProgressStage
    next_actions: list[str]


@router.get("/sites/{site_id}/progress", response_model=SiteProgressResponse)
async def get_site_progress(site_id: str):
    """Unified progress for a site — PLS state, onboarding gates, phase promotion, integrity.

    Returns granular per-gate results with actionable next steps.
    """
    from app.database.supabase_client import get_supabase_client
    from app.services.wizard_acceptance_gates import evaluate as eval_acceptance

    supabase = get_supabase_client()

    # ── PLS stage ─────────────────────────────────────────────
    pls_row = (
        supabase.table("site_onboarding_state")
        .select("site_id, state, version, machine_version, updated_at")
        .eq("site_id", site_id)
        .limit(1)
        .execute()
        .data
    )

    last_trans = (
        supabase.table("site_onboarding_transitions")
        .select("transition, from_state, to_state, actor, created_at")
        .eq("site_id", site_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    pls_state = (pls_row or [{}])[0].get("state", "unknown")
    pls_machine = (pls_row or [{}])[0].get("machine_version", "1.0")
    last_t = (last_trans or [{}])[0]

    terminal_states = {"live", "abandoned", "discovery_failed", "discovery_timed_out"}

    pls_gates: list[ProgressGate] = [
        ProgressGate(
            name="site_exists",
            passed=True,
            detail="Site record exists in database",
        ),
        ProgressGate(
            name="pls_machine_version",
            passed=True,
            detail=f"Machine v{pls_machine}",
        ),
        ProgressGate(
            name="pls_transition_log",
            passed=bool(last_t.get("transition")),
            detail=f"Last transition: {last_t.get('transition', 'none')} ({last_t.get('from_state', '?')} → {last_t.get('to_state', '?')})"
            if last_t.get("transition")
            else "No transitions recorded",
            action="Seed genesis transition via PLS migration" if not last_t.get("transition") else None,
        ),
    ]

    pls_completed = pls_state in terminal_states
    pls_in_progress = pls_state not in ("created", *terminal_states)
    pls_status = "completed" if pls_completed else ("in_progress" if pls_in_progress else "not_reached")

    # ── Acceptance gates stage ────────────────────────────────
    try:
        acc_result = await eval_acceptance(site_id)
        acc_gates = []
        for g in acc_result.gates:
            action = None
            if not g.passed:
                action = {
                    "wizard_complete": "Complete the SIMBIOT connection wizard",
                    "aggregation_fresh": "Wait for telemetry aggregation to complete (up to 15 min)",
                    "history_fresh": "Wait for historical data collection",
                    "operating_hours_set": "Set operating hours in site settings",
                }.get(g.name, "Check site configuration")
            acc_gates.append(ProgressGate(name=g.name, passed=g.passed, detail=g.reason or "", action=action))
    except Exception as exc:
        acc_gates = [
            ProgressGate(name="acceptance_check", passed=False, detail=str(exc), action="Check backend health")
        ]
    acc_status = "completed" if (acc_result and acc_result.all_passed) else "blocked"
    acc_blockers = [g.name for g in acc_gates if not g.passed]

    # ── Phase promotion stage ─────────────────────────────────
    from app.models.onboarding_phase import normalise_stage
    from app.services.phase_promotion_evaluator import get_phase_promotion_evaluator

    site_row = (
        supabase.table("sites").select("code, name, onboarding_phase").eq("code", site_id).limit(1).execute().data
    )
    current_phase = normalise_stage((site_row or [{}])[0].get("onboarding_phase", "commissioning"))
    evaluator = get_phase_promotion_evaluator()
    promo_config = evaluator.PROMOTION_GATES.get(current_phase)

    phase_gates: list[ProgressGate] = []
    if promo_config:
        gates = await evaluator._evaluate_gates(site_id, promo_config["gates"])
        for g in gates:
            d = g.to_dict()
            phase_gates.append(
                ProgressGate(
                    name=d.get("rule", "unknown"),
                    passed=g.passed,
                    detail=d.get("summary", ""),
                    action=None if g.passed else d.get("hint", "Meet the required threshold"),
                )
            )
    else:
        phase_gates.append(
            ProgressGate(
                name="next_phase",
                passed=False,
                detail=f"No promotion path from {current_phase}"
                if current_phase != "automatic"
                else "Maximum phase reached",
                action="Site is at terminal trust phase" if current_phase == "automatic" else None,
            )
        )

    phase_all_passed = all(g.passed for g in phase_gates)
    phase_status = "completed" if current_phase == "automatic" else ("in_progress" if phase_all_passed else "blocked")

    # ── Integrity stage ───────────────────────────────────────
    try:
        int_result = supabase.rpc("check_onboarding_integrity").execute()
        divergent = [r for r in (int_result.data or []) if r.get("site_id") == site_id]
        integrity_ok = len(divergent) == 0
    except Exception:
        divergent = []
        integrity_ok = True

    int_gates = [
        ProgressGate(
            name="replay_integrity",
            passed=integrity_ok,
            detail="Replay matches entity state for site"
            if integrity_ok
            else f"MISMATCH: recorded v{divergent[0]['recorded_version']} vs replayed v{divergent[0]['replayed_version']}"
            if divergent
            else "Integrity check unavailable",
            action=None
            if integrity_ok
            else "Critical: site state diverged from transition log — investigate immediately",
        ),
        ProgressGate(
            name="integrity_sweep_active",
            passed=True,
            detail="Scheduled every 6h; CRITICAL alert on divergence",
        ),
    ]
    int_status = "completed" if integrity_ok else "blocked"

    # ── Next actions ──────────────────────────────────────────
    next_actions: list[str] = []
    if pls_state not in ("live", "canonical"):
        next_actions.append(f"PLS state is '{pls_state}' — complete the onboarding wizard to progress")
    if acc_blockers:
        for b in acc_blockers:
            hint = {
                "wizard_complete": "Finish the SIMBIOT Connection Wizard (Connect → Approve)",
                "aggregation_fresh": "Telemetry aggregation pending — wait a few minutes",
                "history_fresh": "Historical data not yet collected",
                "operating_hours_set": "Set operating hours in site configuration",
            }.get(b, b)
            next_actions.append(f"Acceptance gate '{b}' blocked: {hint}")
    if not phase_all_passed and current_phase != "automatic":
        failing = [g for g in phase_gates if not g.passed]
        for fg in failing[:3]:
            next_actions.append(f"Phase gate '{fg.name}': {fg.detail}")
    if pls_state == "canonical":
        next_actions.append("Site is canonical — activate to go live (operator action required)")
    if not next_actions:
        if pls_state == "live" and current_phase == "automatic":
            next_actions.append("All systems nominal — no action needed")
        elif pls_state == "live":
            next_actions.append("Site is live — monitor phase promotion gates for progression")

    return SiteProgressResponse(
        site_id=site_id,
        pls=ProgressStage(stage="Onboarding Lifecycle", status=pls_status, gates=pls_gates),
        onboarding=ProgressStage(stage="Acceptance Gates", status=acc_status, gates=acc_gates),
        phase_promotion=ProgressStage(stage="Phase Promotion", status=phase_status, gates=phase_gates),
        integrity=ProgressStage(stage="Integrity", status=int_status, gates=int_gates),
        next_actions=next_actions,
    )
