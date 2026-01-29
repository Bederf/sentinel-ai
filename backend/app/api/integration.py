"""API endpoints for integration setup and log ingestion."""

import time
import csv
import io
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import PlainTextResponse

from app.models.integration import (
    LogSource, LogSourceCreate, LogSourceUpdate,
    ColumnMapping, ColumnMappingCreate,
    PointAssetMapping, PointAssetMappingCreate,
    FormatDetectionResult, ParseResult, BulkMatchResult,
    ColumnMapping as CMModel,
)
from app.database.repositories.integration_repository import IntegrationRepository
from app.database.repositories.building_repository import BuildingRepository
from app.database.repositories.equipment_repository import EquipmentRepository
from app.services.log_parser import LogParserService
from app.services.point_matcher import PointMatcherService


router = APIRouter(prefix="/api/integration", tags=["Integration"])

# Services
integration_repo = IntegrationRepository()
building_repo = BuildingRepository()
equipment_repo = EquipmentRepository()
parser_service = LogParserService()
matcher_service = PointMatcherService()


# ==================== Log Sources ====================

@router.get("/sources", response_model=List[LogSource])
async def list_log_sources(
    building_id: Optional[str] = None,
    source_type: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List configured log sources."""
    return integration_repo.get_log_sources(
        building_id=building_id,
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
    # Verify building exists
    building = building_repo.get_by_uuid(source.building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    data = source.model_dump(exclude_none=True)
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
    updated = integration_repo.update_log_source(source_id, {'is_active': True})
    if not updated:
        raise HTTPException(status_code=404, detail="Log source not found")
    return updated


@router.post("/sources/{source_id}/deactivate", response_model=LogSource)
async def deactivate_log_source(source_id: str):
    """Deactivate a log source."""
    updated = integration_repo.update_log_source(source_id, {'is_active': False})
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
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        text_content = content.decode('latin-1')

    try:
        result = parser_service.detect_format(text_content, file.filename or '')
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Column Mappings ====================

@router.get("/sources/{source_id}/mappings", response_model=List[ColumnMapping])
async def get_column_mappings(source_id: str):
    """Get column mappings for a log source."""
    return integration_repo.get_column_mappings(source_id)


@router.post("/sources/{source_id}/mappings", response_model=List[ColumnMapping])
async def save_column_mappings(source_id: str, mappings: List[ColumnMappingCreate]):
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

@router.post("/buildings/{building_id}/match-points", response_model=BulkMatchResult)
async def match_points_to_assets(
    building_id: str,
    file: UploadFile = File(...),
):
    """
    Upload a log file and match BMS points to CAFM assets.

    This is Step 3 of the setup wizard.
    """
    # Get CAFM assets for building
    cafm_assets = integration_repo.get_cafm_assets(building_id)
    if not cafm_assets:
        # Fall back to equipment table if no CAFM sync yet
        building = building_repo.get_by_uuid(building_id)
        if building:
            equipment = equipment_repo.get_by_building(building['id'])
            cafm_assets = [{'asset_tag': e['code'], 'description': e['name']} for e in equipment]

    # Parse file to extract point IDs
    content = await file.read()
    try:
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        text_content = content.decode('latin-1')

    # Detect format and extract point column
    detection = parser_service.detect_format(text_content, file.filename or '')
    point_column = detection.suggested_mappings.get('point_id')

    if not point_column:
        raise HTTPException(
            status_code=400,
            detail="Could not detect point ID column. Please specify manually."
        )

    # Extract unique point IDs
    rows = list(csv.DictReader(io.StringIO(text_content), delimiter=detection.delimiter))
    point_ids = list(set(r.get(point_column, '') for r in rows if r.get(point_column)))

    # Run matching
    result = matcher_service.bulk_match(point_ids, cafm_assets)

    return result


@router.post("/buildings/{building_id}/point-mappings")
async def save_point_mappings(
    building_id: str,
    mappings: List[PointAssetMappingCreate],
):
    """Save point-to-asset mappings after review."""
    mapping_dicts = [m.model_dump() for m in mappings]
    count = integration_repo.bulk_upsert_point_mappings(building_id, mapping_dicts)
    return {"saved": count}


@router.patch("/point-mappings/{mapping_id}/verify")
async def verify_point_mapping(mapping_id: str, cafm_asset_id: str):
    """Manually verify/correct a point mapping."""
    return integration_repo.verify_point_mapping(mapping_id, cafm_asset_id)


@router.get("/buildings/{building_id}/point-mappings", response_model=List[PointAssetMapping])
async def get_point_mappings(
    building_id: str,
    confidence: Optional[str] = None,
    verified_only: bool = False,
):
    """Get point-to-asset mappings for a building."""
    return integration_repo.get_point_mappings(
        building_id,
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
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        text_content = content.decode('latin-1')

    # Parse based on source type
    if source['source_type'] in ['bms_alarm', 'bcc_alarm']:
        result = parser_service.parse_alarms(
            text_content,
            mapping_models,
            source.get('date_format', 'YYYY-MM-DD HH:MI:SS'),
            source.get('delimiter', ','),
        )
    else:
        result = parser_service.parse_trends(
            text_content,
            mapping_models,
            source.get('date_format', 'YYYY-MM-DD HH:MI:SS'),
            source.get('delimiter', ','),
        )

    if dry_run:
        return result

    # Get point mappings for asset lookup
    point_mappings = {
        m['bms_point_id']: m.get('cafm_asset_id')
        for m in integration_repo.get_point_mappings(source['building_id'])
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
                    'log_source_id': source_id,
                    'building_id': source['building_id'],
                    'occurred_at': alarm.occurred_at.isoformat(),
                    'point_id': alarm.point_id,
                    'asset_id': point_mappings.get(alarm.point_id) or alarm.asset_id,
                    'alarm_code': alarm.alarm_code,
                    'sentinel_code': alarm.sentinel_code,
                    'description': alarm.description,
                    'value': alarm.value,
                    'threshold': alarm.threshold,
                    'severity': alarm.severity.value if alarm.severity else None,
                    'state': alarm.state.value if alarm.state else None,
                    'acknowledged_by': alarm.acknowledged_by,
                    'notes': alarm.notes,
                    'raw_data': alarm.raw_data,
                    'source_hash': parser_service.compute_hash(alarm),
                }
                alarms_to_insert.append(alarm_dict)

            inserted = integration_repo.insert_alarms(alarms_to_insert)

        if result.parsed_trends:
            trends_to_insert = []
            for trend in result.parsed_trends:
                trend_dict = {
                    'log_source_id': source_id,
                    'building_id': source['building_id'],
                    'recorded_at': trend.recorded_at.isoformat(),
                    'point_id': trend.point_id,
                    'asset_id': point_mappings.get(trend.point_id) or trend.asset_id,
                    'parameter_name': trend.parameter_name,
                    'value': trend.value,
                    'unit': trend.unit,
                    'quality': trend.quality,
                }
                trends_to_insert.append(trend_dict)

            inserted = integration_repo.insert_trends(trends_to_insert)

        # Complete job
        processing_time = int((time.time() - start_time) * 1000)
        integration_repo.complete_sync_job(
            job['id'],
            status='success',
            processed=result.total_rows,
            inserted=inserted,
            skipped=result.total_rows - result.valid_rows,
            failed=result.error_count,
            processing_time_ms=processing_time,
        )

        # Update source sync status
        integration_repo.update_sync_status(source_id, 'success', inserted)

    except Exception as e:
        integration_repo.complete_sync_job(
            job['id'],
            status='failed',
            processed=result.total_rows,
            inserted=0,
            skipped=0,
            failed=result.total_rows,
            error_message=str(e),
        )
        integration_repo.update_sync_status(source_id, 'failed', 0, str(e))
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
async def get_severity_mappings(source_id: Optional[str] = None):
    """Get severity mappings (global or per-source)."""
    return integration_repo.get_severity_mappings(source_id)


# ==================== CAFM Assets ====================

@router.get("/buildings/{building_id}/cafm-assets")
async def get_cafm_assets(building_id: str):
    """Get synced CAFM assets for a building."""
    return integration_repo.get_cafm_assets(building_id)


@router.get("/buildings/{building_id}/alarms")
async def get_recent_alarms(
    building_id: str,
    limit: int = Query(100, ge=1, le=1000),
    severity: Optional[str] = None,
):
    """Get recent ingested alarms for a building."""
    return integration_repo.get_recent_alarms(building_id, limit, severity)
