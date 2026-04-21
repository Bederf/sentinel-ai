"""API endpoints for integration setup and log ingestion."""

import csv
import io
import time
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.models.integration import (
    BuildingStatus,
    BulkMatchResult,
    ColumnMapping,
    ColumnMappingCreate,
    FormatDetectionResult,
    LogSource,
    LogSourceCreate,
    LogSourceUpdate,
    ParseResult,
    PointAssetMapping,
    PointAssetMappingCreate,
    ValidationChecklist,
)
from app.models.integration import (
    ColumnMapping as CMModel,
)

# ==================== Monitoring Response Models ====================


class IntegrationAlert(BaseModel):
    """An alert from integration health monitoring."""

    id: str = ""
    type: str  # 'stale_data', 'high_error_rate', 'low_match_coverage'
    severity: str  # 'warning', 'critical'
    message: str
    timestamp: str = ""
    value: float | None = None
    threshold: float | None = None


class DALISourceHealth(BaseModel):
    """Health status for a DALI lighting data source."""

    site_id: str
    source_name: str
    source_type: str = "dali_lighting"
    connection_type: str = "file_drop"
    status: str  # healthy, degraded, offline
    controllers_online: int = 0
    controllers_total: int = 0
    sensors_online: int = 0
    sensors_total: int = 0
    luminaires_total: int = 0
    last_poll: str | None = None
    description: str = ""


class IntegrationHealthSummary(BaseModel):
    """Integration health summary for monitoring dashboard."""

    sources_count: int
    active_sources: int
    last_sync: datetime | None = None
    total_records_ingested: int
    total_points_mapped: int
    unmatched_points: int
    recent_errors_count: int
    alerts: list[IntegrationAlert] = Field(default_factory=list)
    dali_sources: list[DALISourceHealth] = Field(default_factory=list)


class DataQualityMetrics(BaseModel):
    """Data quality metrics for a building."""

    match_coverage: float = Field(..., ge=0, le=100, description="Percentage of points matched")
    data_freshness_hours: float = Field(..., description="Hours since last sync")
    error_rate: float = Field(..., ge=0, le=100, description="Percentage of failed sync jobs")
    duplicate_rate: float = Field(..., ge=0, le=100, description="Percentage of skipped records")
    overall_score: float = Field(..., ge=0, le=100, description="Weighted quality score")
    trend: Literal["improving", "stable", "degrading"]


class SyncJobSummary(BaseModel):
    """Summary of a sync job."""

    id: str
    log_source_id: str
    source_name: str | None = None
    status: str
    records_processed: int | None = None
    records_inserted: int | None = None
    records_failed: int | None = None
    records_skipped: int | None = None
    processing_time_ms: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    file_name: str | None = None


# ==================== Building Status Response Models ====================


class BuildingStatusUpdate(BaseModel):
    """Request to update building status."""

    status: str  # BuildingStatus enum value
    notes: str | None = None


class ActivationResult(BaseModel):
    """Result of building activation attempt."""

    success: bool
    site_id: str
    new_status: str  # BuildingStatus enum value
    message: str
    validation_errors: list[str] = Field(default_factory=list)


class BuildingStatusResponse(BaseModel):
    """Current building status."""

    site_id: str
    status: str  # BuildingStatus enum value
    last_validated_at: datetime | None = None
    notes: str | None = None


from app.core.site_resolver import get_primary_site_code  # noqa: E402
from app.database.repositories.equipment_repository import EquipmentRepository  # noqa: E402
from app.database.repositories.integration_repository import IntegrationRepository  # noqa: E402
from app.database.repositories.site_repository import SiteRepository  # noqa: E402
from app.models.commissioning import TruthCheckSubmission  # noqa: E402
from app.services.commissioning_service import CommissioningService  # noqa: E402
from app.services.log_parser import LogParserService  # noqa: E402
from app.services.point_matcher import PointMatcherService  # noqa: E402

router = APIRouter(prefix="/api/integration", tags=["Integration"])

# Services
integration_repo = IntegrationRepository()
building_repo = SiteRepository()
equipment_repo = EquipmentRepository()
parser_service = LogParserService()
matcher_service = PointMatcherService()
commissioning_service = CommissioningService()


_site_uuid_cache: dict[str, str] = {}


def resolve_site_uuid(site_id: str) -> str:
    """Resolve a site code (e.g. 'site-002') to the Supabase building UUID.

    The frontend uses site codes from /api/sites, but integration tables
    store building UUIDs. This bridges the two ID systems.
    Results are cached for the lifetime of the process.
    """
    if site_id in _site_uuid_cache:
        return _site_uuid_cache[site_id]

    try:
        building = building_repo.get_by_id(site_id)
        if building:
            resolved = building["id"]
            _site_uuid_cache[site_id] = resolved
            return resolved
    except Exception:
        pass
    return site_id


# ==================== Log Sources ====================


@router.get("/sources", response_model=list[LogSource])
async def list_log_sources(
    site_id: str | None = None,
    source_type: str | None = None,
    is_active: bool | None = None,
):
    """List configured log sources."""
    resolved_id = resolve_site_uuid(site_id) if site_id else None
    return integration_repo.get_log_sources(
        site_id=resolved_id,
        source_type=source_type,
        is_active=is_active,
    )


@router.get("/sources/{source_id}", response_model=LogSource)
async def get_log_source(source_id: str):
    """Get log source by ID."""
    source = integration_repo.get_log_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Log source not found")
    return source


@router.post("/sources", response_model=LogSource, status_code=201)
async def create_log_source(source: LogSourceCreate):
    """Create a new log source configuration."""
    # Resolve site code to UUID and verify building exists
    resolved_id = resolve_site_uuid(source.site_id)
    building = building_repo.get_by_uuid(resolved_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    data = source.model_dump(exclude_none=True)
    data["site_id"] = resolved_id
    return integration_repo.create_log_source(data)


@router.patch("/sources/{source_id}", response_model=LogSource)
async def update_log_source(source_id: str, source: LogSourceUpdate):
    """Update a log source configuration."""
    data = source.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = integration_repo.update_log_source(source_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Log source not found")
    return updated


@router.delete("/sources/{source_id}", status_code=204)
async def delete_log_source(source_id: str):
    """Delete a log source."""
    if not integration_repo.delete_log_source(source_id):
        raise HTTPException(status_code=404, detail="Log source not found")


@router.post("/sources/{source_id}/activate", response_model=LogSource)
async def activate_log_source(source_id: str):
    """Activate a log source for scheduled sync."""
    updated = integration_repo.update_log_source(source_id, {"is_active": True})
    if not updated:
        raise HTTPException(status_code=404, detail="Log source not found")
    return updated


@router.post("/sources/{source_id}/deactivate", response_model=LogSource)
async def deactivate_log_source(source_id: str):
    """Deactivate a log source."""
    updated = integration_repo.update_log_source(source_id, {"is_active": False})
    if not updated:
        raise HTTPException(status_code=404, detail="Log source not found")
    return updated


# ==================== Format Detection ====================


@router.post("/detect-format", response_model=FormatDetectionResult)
async def detect_file_format(file: UploadFile = File(...)):
    """
    Upload a sample log file to auto-detect format, columns, and suggest mappings.

    This is Step 1 of the setup wizard.
    """
    content = await file.read()

    # Try UTF-8 first, fall back to Latin-1
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    try:
        result = parser_service.detect_format(text_content, file.filename or "")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Column Mappings ====================


@router.get("/sources/{source_id}/mappings", response_model=list[ColumnMapping])
async def get_column_mappings(source_id: str):
    """Get column mappings for a log source."""
    return integration_repo.get_column_mappings(source_id)


@router.post("/sources/{source_id}/mappings", response_model=list[ColumnMapping])
async def save_column_mappings(source_id: str, mappings: list[ColumnMappingCreate]):
    """
    Save column mappings for a log source.

    This is Step 2 of the setup wizard - confirming the column mappings.
    """
    # Verify source exists
    source = integration_repo.get_log_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Log source not found")

    mapping_dicts = [m.model_dump() for m in mappings]
    return integration_repo.save_column_mappings(source_id, mapping_dicts)


# ==================== Point-Asset Matching ====================


@router.post("/buildings/{site_id}/match-points", response_model=BulkMatchResult)
async def match_points_to_assets(
    site_id: str,
    file: UploadFile = File(...),
):
    """
    Upload a log file and match BMS points to CAFM assets.

    This is Step 3 of the setup wizard.
    """
    resolved_id = resolve_site_uuid(site_id)
    # Get CAFM assets for building
    cafm_assets = integration_repo.get_cafm_assets(resolved_id)
    if not cafm_assets:
        # Fall back to equipment table if no CAFM sync yet
        building = building_repo.get_by_uuid(resolved_id)
        if building:
            equipment = equipment_repo.get_by_site(building["id"])
            cafm_assets = [{"asset_tag": e["code"], "description": e["name"]} for e in equipment]

    # Parse file to extract point IDs
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    # Detect format and extract point column
    detection = parser_service.detect_format(text_content, file.filename or "")
    point_column = detection.suggested_mappings.get("point_id")

    if not point_column:
        raise HTTPException(status_code=400, detail="Could not detect point ID column. Please specify manually.")

    # Extract unique point IDs
    rows = list(csv.DictReader(io.StringIO(text_content), delimiter=detection.delimiter))
    point_ids = list({r.get(point_column, "") for r in rows if r.get(point_column)})

    # Run matching
    result = matcher_service.bulk_match(point_ids, cafm_assets)

    return result


@router.post("/buildings/{site_id}/point-mappings")
async def save_point_mappings(
    site_id: str,
    mappings: list[PointAssetMappingCreate],
):
    """Save point-to-asset mappings after review."""
    resolved_id = resolve_site_uuid(site_id)
    mapping_dicts = [m.model_dump() for m in mappings]
    count = integration_repo.bulk_upsert_point_mappings(resolved_id, mapping_dicts)
    return {"saved": count}


@router.patch("/point-mappings/{mapping_id}/verify")
async def verify_point_mapping(mapping_id: str, cafm_asset_id: str):
    """Manually verify/correct a point mapping."""
    return integration_repo.verify_point_mapping(mapping_id, cafm_asset_id)


@router.get("/point-mappings")
async def get_all_point_mappings(
    site_id: str | None = Query(None, description="Filter by building ID"),
    confidence: str | None = Query(None, description="Filter by confidence level (high, medium, low, unmatched)"),
    verified_only: bool = Query(False, description="Only return verified mappings"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Get point-to-asset mappings across all buildings or for a specific building.

    Use this endpoint for monitoring dashboard overviews.
    For building-specific operations, use /buildings/{site_id}/point-mappings instead.
    """
    resolved_id = resolve_site_uuid(site_id) if site_id else None
    return integration_repo.get_all_point_mappings(
        site_id=resolved_id,
        confidence=confidence,
        verified_only=verified_only,
        limit=limit,
        offset=offset,
    )


@router.get("/buildings/{site_id}/point-mappings", response_model=list[PointAssetMapping])
async def get_point_mappings(
    site_id: str,
    confidence: str | None = None,
    verified_only: bool = False,
):
    """Get point-to-asset mappings for a building."""
    resolved_id = resolve_site_uuid(site_id)
    return integration_repo.get_point_mappings(
        resolved_id,
        confidence=confidence,
        verified_only=verified_only,
    )


# ==================== Log Ingestion ====================


@router.post("/sources/{source_id}/ingest", response_model=ParseResult)
async def ingest_log_file(
    source_id: str,
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Validate only, don't save"),
):
    """
    Ingest a log file using the configured mappings.

    Set dry_run=true to validate without saving.
    """
    start_time = time.time()

    # Get source config
    source = integration_repo.get_log_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Log source not found")

    # Get mappings
    mappings = integration_repo.get_column_mappings(source_id)
    if not mappings:
        raise HTTPException(status_code=400, detail="No column mappings configured")

    # Convert to model objects
    mapping_models = [CMModel(**m) for m in mappings]

    # Read file
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    # Parse based on source type
    if source["source_type"] in ["bms_alarm", "bcc_alarm"]:
        result = parser_service.parse_alarms(
            text_content,
            mapping_models,
            source.get("date_format", "YYYY-MM-DD HH:MI:SS"),
            source.get("delimiter", ","),
        )
    else:
        result = parser_service.parse_trends(
            text_content,
            mapping_models,
            source.get("date_format", "YYYY-MM-DD HH:MI:SS"),
            source.get("delimiter", ","),
        )

    if dry_run:
        return result

    # Get point mappings for asset lookup
    point_mappings = {
        m["bms_point_id"]: m.get("cafm_asset_id") for m in integration_repo.get_point_mappings(source["site_id"])
    }

    # Create sync job
    job = integration_repo.create_sync_job(source_id, file.filename)

    try:
        inserted = 0

        if result.parsed_alarms:
            # Enrich with asset IDs and prepare for insert
            alarms_to_insert = []
            for alarm in result.parsed_alarms:
                alarm_dict = {
                    "log_source_id": source_id,
                    "site_id": source["site_id"],
                    "occurred_at": alarm.occurred_at.isoformat(),
                    "point_id": alarm.point_id,
                    "asset_id": point_mappings.get(alarm.point_id) or alarm.asset_id,
                    "alarm_code": alarm.alarm_code,
                    "sentinel_code": alarm.sentinel_code,
                    "description": alarm.description,
                    "value": alarm.value,
                    "threshold": alarm.threshold,
                    "severity": alarm.severity.value if alarm.severity else None,
                    "state": alarm.state.value if alarm.state else None,
                    "acknowledged_by": alarm.acknowledged_by,
                    "notes": alarm.notes,
                    "raw_data": alarm.raw_data,
                    "source_hash": parser_service.compute_hash(alarm),
                }
                alarms_to_insert.append(alarm_dict)

            inserted = integration_repo.insert_alarms(alarms_to_insert)

        if result.parsed_trends:
            trends_to_insert = []
            for trend in result.parsed_trends:
                trend_dict = {
                    "log_source_id": source_id,
                    "site_id": source["site_id"],
                    "recorded_at": trend.recorded_at.isoformat(),
                    "point_id": trend.point_id,
                    "asset_id": point_mappings.get(trend.point_id) or trend.asset_id,
                    "parameter_name": trend.parameter_name,
                    "value": trend.value,
                    "unit": trend.unit,
                    "quality": trend.quality,
                }
                trends_to_insert.append(trend_dict)

            inserted = integration_repo.insert_trends(trends_to_insert)

        # Complete job
        processing_time = int((time.time() - start_time) * 1000)
        integration_repo.complete_sync_job(
            job["id"],
            status="success",
            processed=result.total_rows,
            inserted=inserted,
            skipped=result.total_rows - result.valid_rows,
            failed=result.error_count,
            processing_time_ms=processing_time,
        )

        # Update source sync status
        integration_repo.update_sync_status(source_id, "success", inserted)

    except Exception as e:
        integration_repo.complete_sync_job(
            job["id"],
            status="failed",
            processed=result.total_rows,
            inserted=0,
            skipped=0,
            failed=result.total_rows,
            error_message=str(e),
        )
        integration_repo.update_sync_status(source_id, "failed", 0, str(e))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    return result


@router.get("/sources/{source_id}/jobs")
async def get_sync_jobs(source_id: str, limit: int = Query(20, ge=1, le=100)):
    """Get recent sync jobs for a log source."""
    return integration_repo.get_sync_jobs(source_id, limit)


# ==================== Reference Data ====================


@router.get("/reference/alarm-taxonomy")
async def get_alarm_taxonomy():
    """Get standard alarm code taxonomy."""
    return integration_repo.get_alarm_taxonomy()


@router.get("/reference/severity-mappings")
async def get_severity_mappings(source_id: str | None = None):
    """Get severity mappings (global or per-source)."""
    return integration_repo.get_severity_mappings(source_id)


# ==================== CAFM Assets ====================


@router.get("/buildings/{site_id}/cafm-assets")
async def get_cafm_assets(site_id: str):
    """Get synced CAFM assets for a building."""
    resolved_id = resolve_site_uuid(site_id)
    return integration_repo.get_cafm_assets(resolved_id)


@router.get("/buildings/{site_id}/alarms")
async def get_recent_alarms(
    site_id: str,
    limit: int = Query(100, ge=1, le=1000),
    severity: str | None = None,
):
    """Get recent ingested alarms for a building."""
    resolved_id = resolve_site_uuid(site_id)
    return integration_repo.get_recent_alarms(resolved_id, limit, severity)


# ==================== Monitoring Endpoints ====================


@router.get("/health", response_model=IntegrationHealthSummary)
async def get_integration_health(
    site_id: str | None = Query(None, description="Filter by building ID"),
):
    """
    Get integration health summary for monitoring dashboard.

    Returns aggregate metrics on integration status including:
    - Source counts (total and active)
    - Last sync timestamp
    - Total records ingested
    - Point mapping status
    - Recent errors
    - Generated alerts for problematic conditions
    """
    resolved_id = resolve_site_uuid(site_id) if site_id else None
    health = integration_repo.get_integration_health(resolved_id)

    # Generate alerts based on conditions
    alerts: list[IntegrationAlert] = []

    # Stale data alert (>24 hours since last sync)
    if health["last_sync"]:
        try:
            last_sync_str = health["last_sync"]
            if isinstance(last_sync_str, str):
                last_sync = datetime.fromisoformat(last_sync_str.replace("Z", "+00:00").replace("+00:00", ""))
            else:
                last_sync = last_sync_str
            hours_since_sync = (datetime.utcnow() - last_sync).total_seconds() / 3600
            if hours_since_sync > 24:
                alerts.append(
                    IntegrationAlert(
                        id=str(uuid.uuid4()),
                        type="stale_data",
                        severity="warning" if hours_since_sync < 48 else "critical",
                        message=(
                            f"Data is {int(hours_since_sync)} hours old. "
                            f"Last sync was {last_sync.strftime('%Y-%m-%d %H:%M')}."
                        ),
                        timestamp=datetime.utcnow().isoformat(),
                        value=round(hours_since_sync, 1),
                        threshold=24,
                    )
                )
        except (ValueError, TypeError):
            pass

    # High error rate alert (>10% of recent syncs failed)
    if health["recent_errors_count"] > 0 and health["active_sources"] > 0:
        # Approximate error rate based on active sources
        error_ratio = health["recent_errors_count"] / health["active_sources"]
        if error_ratio > 0.1:
            alerts.append(
                IntegrationAlert(
                    id=str(uuid.uuid4()),
                    type="high_error_rate",
                    severity="warning" if error_ratio < 0.25 else "critical",
                    message=f"{health['recent_errors_count']} sync failures in the last 24 hours.",
                    timestamp=datetime.utcnow().isoformat(),
                    value=health["recent_errors_count"],
                    threshold=health["active_sources"] * 0.1,
                )
            )

    # Low match coverage alert (<50% of points matched)
    if health["total_points_mapped"] > 0:
        match_rate = (health["total_points_mapped"] - health["unmatched_points"]) / health["total_points_mapped"] * 100
        if match_rate < 50:
            alerts.append(
                IntegrationAlert(
                    id=str(uuid.uuid4()),
                    type="low_match_coverage",
                    severity="warning" if match_rate > 25 else "critical",
                    message=(
                        f"Only {match_rate:.0f}% of points are matched to assets. "
                        f"{health['unmatched_points']} points unmatched."
                    ),
                    timestamp=datetime.utcnow().isoformat(),
                    value=round(match_rate, 1),
                    threshold=50,
                )
            )

    # Get DALI source health
    dali_sources: list[DALISourceHealth] = []
    try:
        from app.services.lighting_service import get_lighting_service

        lighting_service = get_lighting_service()
        for dh in lighting_service.get_sources_health():
            # If filtering by site_id, only include matching site
            if resolved_id and dh.get("site_id") != site_id:
                continue
            dali_sources.append(DALISourceHealth(**dh))
    except Exception:
        pass  # DALI service may not be available

    return IntegrationHealthSummary(
        sources_count=health["sources_count"],
        active_sources=health["active_sources"],
        last_sync=health["last_sync"],
        total_records_ingested=health["total_records_ingested"],
        total_points_mapped=health["total_points_mapped"],
        unmatched_points=health["unmatched_points"],
        recent_errors_count=health["recent_errors_count"],
        alerts=alerts,
        dali_sources=dali_sources,
    )


@router.get("/quality-metrics/{site_id}", response_model=DataQualityMetrics)
async def get_quality_metrics(site_id: str):
    """
    Get data quality metrics for a specific building.

    Returns quality scores including:
    - match_coverage: Percentage of BMS points matched to CAFM assets (0-100)
    - data_freshness_hours: Hours since last successful sync
    - error_rate: Percentage of failed sync jobs in last 7 days (0-100)
    - duplicate_rate: Percentage of skipped/duplicate records (0-100)
    - overall_score: Weighted quality score (0-100)
    - trend: Quality trend ('improving', 'stable', 'degrading')
    """
    resolved_id = resolve_site_uuid(site_id)
    metrics = integration_repo.get_quality_metrics(resolved_id)

    return DataQualityMetrics(
        match_coverage=metrics["match_coverage"],
        data_freshness_hours=metrics["data_freshness_hours"],
        error_rate=metrics["error_rate"],
        duplicate_rate=metrics["duplicate_rate"],
        overall_score=metrics["overall_score"],
        trend=metrics["trend"],
    )


@router.get("/sync-jobs", response_model=list[SyncJobSummary])
async def get_sync_jobs_summary(
    site_id: str | None = Query(None, description="Filter by building ID"),
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
):
    """
    Get sync job history for monitoring.

    Returns list of sync jobs from the last N days (default 7, max 30).
    Includes job status, record counts, processing time, and timestamps.
    """
    resolved_id = resolve_site_uuid(site_id) if site_id else None
    jobs = integration_repo.get_sync_jobs_summary(resolved_id, days)

    # Look up source names for display
    source_ids = list({job["log_source_id"] for job in jobs})
    source_names: dict[str, str] = {}
    if source_ids:
        sources = integration_repo.get_log_sources_by_ids(source_ids)
        for s in sources:
            source_names[s["id"]] = s.get("name") or s["id"][:8]

    return [
        SyncJobSummary(
            id=job["id"],
            log_source_id=job["log_source_id"],
            source_name=source_names.get(job["log_source_id"]),
            status=job["status"],
            records_processed=job.get("records_processed"),
            records_inserted=job.get("records_inserted"),
            records_failed=job.get("records_failed"),
            records_skipped=job.get("records_skipped"),
            processing_time_ms=job.get("processing_time_ms"),
            started_at=job.get("started_at"),
            completed_at=job.get("completed_at"),
            file_name=job.get("file_name"),
        )
        for job in jobs
    ]


# ==================== Building Status / Go-Live Workflow ====================


@router.get("/buildings/{site_id}/validation-checklist", response_model=ValidationChecklist)
async def get_validation_checklist(site_id: str):
    """
    Get go-live validation checklist for a building.

    Runs all validation checks and returns a checklist with pass/fail/warning status.
    Checks include:
    - Data source configuration and activity
    - Point mapping coverage
    - Data quality metrics
    - Configuration completeness
    """
    resolved_id = resolve_site_uuid(site_id)
    checklist = integration_repo.get_validation_checklist(resolved_id)

    # Get building name from building_repo if available
    try:
        building = building_repo.get_by_uuid(resolved_id)
        if not building:
            building = building_repo.get_by_id(site_id)
        if building:
            checklist["site_name"] = building.get("name")
    except Exception:
        pass

    # Get current building status
    status_record = integration_repo.get_site_status(resolved_id)
    current_status = BuildingStatus(status_record["status"]) if status_record else BuildingStatus.DRAFT

    return ValidationChecklist(
        site_id=site_id,
        site_name=checklist.get("site_name"),
        status=current_status,
        checked_at=datetime.utcnow(),
        items=checklist["items"],
        summary=checklist["summary"],
        can_activate=checklist["can_activate"],
        blocking_issues=checklist["blocking_issues"],
    )


@router.get("/buildings/{site_id}/status", response_model=BuildingStatusResponse)
async def get_site_status(site_id: str):
    """
    Get current building status.

    Returns the activation status (draft, pending_validation, active, suspended).
    If no status record exists, returns DRAFT.
    """
    resolved_id = resolve_site_uuid(site_id)
    status_record = integration_repo.get_site_status(resolved_id)

    if not status_record:
        return BuildingStatusResponse(
            site_id=site_id,
            status=BuildingStatus.DRAFT.value,
        )

    return BuildingStatusResponse(
        site_id=site_id,
        status=status_record["status"],
        last_validated_at=status_record.get("last_validated_at"),
        notes=status_record.get("notes"),
    )


@router.post("/buildings/{site_id}/validate", response_model=ValidationChecklist)
async def validate_building(site_id: str):
    """
    Validate building configuration for go-live.

    Runs validation checklist and updates building status to PENDING_VALIDATION
    if all critical checks pass. Returns the validation checklist.
    """
    resolved_id = resolve_site_uuid(site_id)

    # Run validation checklist
    checklist = integration_repo.get_validation_checklist(resolved_id)

    # Get building name if available
    try:
        building = building_repo.get_by_uuid(resolved_id)
        if not building:
            building = building_repo.get_by_id(site_id)
        if building:
            checklist["site_name"] = building.get("name")
    except Exception:
        pass

    # Determine new status based on validation
    if checklist["can_activate"]:
        new_status = BuildingStatus.PENDING_VALIDATION
        integration_repo.update_site_status(
            resolved_id,
            new_status.value,
            notes="Passed validation - ready for activation",
        )
    else:
        # Stay in DRAFT or current status if validation fails
        current = integration_repo.get_site_status(resolved_id)
        new_status = BuildingStatus(current["status"]) if current else BuildingStatus.DRAFT

    return ValidationChecklist(
        site_id=site_id,
        site_name=checklist.get("site_name"),
        status=new_status,
        checked_at=datetime.utcnow(),
        items=checklist["items"],
        summary=checklist["summary"],
        can_activate=checklist["can_activate"],
        blocking_issues=checklist["blocking_issues"],
    )


@router.post("/buildings/{site_id}/activate", response_model=ActivationResult)
async def activate_building(site_id: str):
    """
    Activate a building after successful validation.

    Requirements:
    - Current status must be PENDING_VALIDATION
    - All critical validation checks must pass

    Returns activation result with success/failure and any validation errors.
    """
    resolved_id = resolve_site_uuid(site_id)

    # Check current status
    current = integration_repo.get_site_status(resolved_id)
    if not current or current["status"] != BuildingStatus.PENDING_VALIDATION.value:
        return ActivationResult(
            success=False,
            site_id=site_id,
            new_status=current["status"] if current else BuildingStatus.DRAFT.value,
            message="Building must be in PENDING_VALIDATION status to activate. Run /validate first.",
            validation_errors=["Status is not PENDING_VALIDATION"],
        )

    # Run validation again to confirm
    checklist = integration_repo.get_validation_checklist(resolved_id)

    if not checklist["can_activate"]:
        return ActivationResult(
            success=False,
            site_id=site_id,
            new_status=BuildingStatus.PENDING_VALIDATION.value,
            message="Activation blocked by failed validation checks.",
            validation_errors=checklist["blocking_issues"],
        )

    # Activate the building
    integration_repo.update_site_status(
        resolved_id,
        BuildingStatus.ACTIVE.value,
        notes="Activated after successful validation",
    )

    return ActivationResult(
        success=True,
        site_id=site_id,
        new_status=BuildingStatus.ACTIVE.value,
        message="Building successfully activated.",
        validation_errors=[],
    )


@router.post("/buildings/{site_id}/suspend", response_model=BuildingStatusResponse)
async def suspend_building(
    site_id: str,
    body: BuildingStatusUpdate = None,
):
    """
    Suspend a building (deactivate).

    Sets the building status to SUSPENDED. Can be used to temporarily
    disable a building without losing configuration.
    """
    resolved_id = resolve_site_uuid(site_id)
    notes = body.notes if body else None
    integration_repo.update_site_status(
        resolved_id,
        BuildingStatus.SUSPENDED.value,
        notes=notes or "Manually suspended",
    )

    return BuildingStatusResponse(
        site_id=site_id,
        status=BuildingStatus.SUSPENDED.value,
        last_validated_at=datetime.utcnow(),
        notes=notes or "Manually suspended",
    )


# ==================== Seed Data Helpers ====================


@router.get("/unmatched-points")
async def get_unmatched_points(
    site_id: str | None = Query(None, description="Filter by building ID"),
    limit: int = Query(10, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Get unmatched points for monitoring dashboard.

    Returns BMS points that haven't been mapped to CAFM assets yet.
    """
    resolved_id = resolve_site_uuid(site_id) if site_id else None
    result = integration_repo.get_unmatched_points(resolved_id, limit, offset)
    return result


@router.post("/seed-integration-data")
async def seed_integration_data():
    """
    Seed integration data for the monitoring dashboard.

    Creates seeded point_asset_mappings and column_mappings for testing.
    Uses REAL equipment IDs from the primary registered building for realistic data.
    """
    import random

    # Get primary registered building UUID
    _primary_site = get_primary_site_code() or "unknown"
    building = building_repo.get_by_id(_primary_site)
    if not building:
        raise HTTPException(status_code=404, detail=f"Primary building '{_primary_site}' not found")

    site_id = building["id"]

    # Get existing log source
    sources = integration_repo.get_log_sources(site_id=site_id)
    if not sources:
        raise HTTPException(status_code=404, detail="No log sources found. Create one first.")

    source_id = sources[0]["id"]

    # Get REAL equipment from the primary site
    equipment_list = equipment_repo.get_by_site_code(_primary_site)
    if not equipment_list:
        # Fallback: try get_all with site_id filter
        equipment_list = equipment_repo.get_all(site_id=_primary_site)
    if not equipment_list:
        raise HTTPException(status_code=404, detail=f"No equipment found for {_primary_site}")

    # Build point mappings from real equipment
    point_mappings = []
    parameter_templates = {
        "fcu": [
            ("ZoneTemp", "Zone Temperature", "analog"),
            ("FanSpeed", "Fan Speed", "analog"),
            ("ValvePos", "Valve Position", "analog"),
        ],
        "ahu": [
            ("SupplyTemp", "Supply Air Temp", "analog"),
            ("ReturnTemp", "Return Air Temp", "analog"),
            ("FanStatus", "Fan Status", "binary"),
        ],
        "vav": [("DamperPos", "Damper Position", "analog"), ("FlowRate", "Air Flow Rate", "analog")],
        "chiller": [
            ("ChwSupply", "CHW Supply Temp", "analog"),
            ("ChwReturn", "CHW Return Temp", "analog"),
            ("LoadPct", "Load Percentage", "analog"),
        ],
        "generator": [
            ("RunStatus", "Run Status", "binary"),
            ("Voltage", "Output Voltage", "analog"),
            ("Frequency", "Frequency", "analog"),
        ],
        "lighting": [("LightLevel", "Light Level", "analog"), ("OccStatus", "Occupancy Status", "binary")],
        "sensor": [("Reading", "Sensor Reading", "analog")],
    }

    confidences = ["exact", "exact", "exact", "fuzzy", "fuzzy", "manual"]  # Weighted towards exact

    for eq in equipment_list[:50]:  # Limit to 50 equipment items
        eq_id = eq.get("code") or eq.get("equipment_id") or eq.get("id")
        eq_type = (eq.get("type") or "sensor").lower()
        _eq_name = eq.get("name") or eq_id

        # Get parameter templates for this equipment type
        params = parameter_templates.get(eq_type, [("Value", "Value", "analog")])

        for param_suffix, param_name, param_type in params:
            bms_point_id = f"BMS.{eq_id}.{param_suffix}"
            confidence = random.choice(confidences)

            point_mappings.append(
                {
                    "bms_point_id": bms_point_id,
                    "extracted_asset_id": eq_id,
                    "cafm_asset_id": f"CAFM-{eq_id}" if confidence != "unmatched" else None,
                    "parameter_name": param_name,
                    "parameter_type": param_type,
                    "match_confidence": confidence,
                    "is_verified": confidence in ["exact", "manual"],
                }
            )

    # Add a few unmatched points for realism
    point_mappings.extend(
        [
            {
                "bms_point_id": "BMS.Legacy.Sensor42",
                "extracted_asset_id": None,
                "cafm_asset_id": None,
                "parameter_name": None,
                "parameter_type": None,
                "match_confidence": "unmatched",
                "is_verified": False,
            },
            {
                "bms_point_id": "BMS.Unknown.PointX",
                "extracted_asset_id": None,
                "cafm_asset_id": None,
                "parameter_name": None,
                "parameter_type": None,
                "match_confidence": "unmatched",
                "is_verified": False,
            },
            {
                "bms_point_id": "BMS.Orphan.TempSensor",
                "extracted_asset_id": None,
                "cafm_asset_id": None,
                "parameter_name": None,
                "parameter_type": None,
                "match_confidence": "unmatched",
                "is_verified": False,
            },
        ]
    )

    mappings_created = integration_repo.bulk_upsert_point_mappings(site_id, point_mappings)

    # Seed column_mappings for the log source
    # Schema: source_column, sentinel_field, transform, transform_params (jsonb)
    column_mappings = [
        {
            "source_column": "TIMESTAMP",
            "sentinel_field": "occurred_at",
            "transform": "datetime",
            "transform_params": {"format": "YYYY-MM-DD HH:MI:SS"},
        },
        {"source_column": "POINT_ID", "sentinel_field": "point_id", "transform": None, "transform_params": None},
        {"source_column": "VALUE", "sentinel_field": "value", "transform": "number", "transform_params": None},
        {"source_column": "ALARM_CODE", "sentinel_field": "alarm_code", "transform": None, "transform_params": None},
        {"source_column": "DESCRIPTION", "sentinel_field": "description", "transform": None, "transform_params": None},
        {"source_column": "SEVERITY", "sentinel_field": "severity", "transform": "uppercase", "transform_params": None},
    ]

    mappings_saved = integration_repo.save_column_mappings(source_id, column_mappings)

    return {
        "success": True,
        "site_id": site_id,
        "source_id": source_id,
        "point_mappings_created": mappings_created,
        "column_mappings_created": len(mappings_saved),
        "message": "Demo integration data seeded successfully",
    }


# ==================== Commissioning Scorecard (Phase 107b) ====================


@router.get("/buildings/{site_id}/commissioning-scorecard")
async def get_commissioning_scorecard(site_id: str):
    """Run the commissioning scorecard for a building.

    Evaluates 8 hard gates and returns pass/fail status, truth check results,
    consecutive pass days, and promotion readiness.
    """
    scorecard = await commissioning_service.run_scorecard(site_id)
    return scorecard.model_dump()


@router.post("/buildings/{site_id}/truth-check")
async def submit_truth_check(site_id: str, submission: TruthCheckSubmission):
    """Submit a truth check for a building (minimum 20 entries).

    Compares SENTINEL readings against native BMS values to verify accuracy.
    """
    result = commissioning_service.submit_truth_check(site_id, submission.entries)
    return result.model_dump()


@router.post("/buildings/{site_id}/promote-to-live")
async def promote_to_live(site_id: str):
    """Attempt to promote a building from SHADOW_LIVE to LIVE_CONTROL.

    Requires: all gates passed, >= 2 consecutive pass days, passing truth check,
    and current ingestion mode must be shadow_live.
    """
    from app.config.settings import IngestionMode, settings

    current_mode = settings.resolved_ingestion_mode
    if current_mode != IngestionMode.SHADOW_LIVE:
        return {
            "success": False,
            "site_id": site_id,
            "previous_mode": current_mode.value,
            "message": f"Cannot promote: current mode is {current_mode.value}, must be shadow_live",
            "blocking_reasons": [f"mode_is_{current_mode.value}"],
        }

    result = await commissioning_service.promote_to_live(site_id)
    return result.model_dump()
