"""
ODS-E Export API Router

Provides ODS-E v0.4.0 compliant endpoints for energy data export.
Endpoints are registered under /api/integration/odse
"""

import csv
import io
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from app.models.odse_models import ODSEAssetExport, ODSETimeseriesExport
from app.services.odse_service import odse_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["ODS-E"])


@router.get("/timeseries", response_model=ODSETimeseriesExport)
async def export_timeseries(
    site_id: str = Query(..., description="Sentinel site ID (e.g., site-002)"),
    start: datetime = Query(..., description="Start of export window (ISO 8601 UTC)"),
    end: datetime = Query(..., description="End of export window (ISO 8601 UTC)"),
    equipment_id: str | None = Query(None, description="Filter to single equipment"),
    direction: Literal["consumption", "generation", "net"] = Query(
        default="consumption", description="Energy flow direction"
    ),
    interval_minutes: int = Query(default=15, ge=1, le=1440, description="Aggregation interval"),
    format: Literal["json", "csv"] = Query(default="json", description="Output format"),
) -> ODSETimeseriesExport | PlainTextResponse:
    """
    Export Sentinel energy timeseries data in ODS-E format.

    Returns energy consumption/generation records with ODS-E v0.4.0 schema compliance.
    """
    logger.info(
        f"ODS-E timeseries export request: site={site_id}, start={start}, end={end}, "
        f"format={format}"
    )

    try:
        result = await odse_service.export_timeseries(
            site_id=site_id,
            start=start,
            end=end,
            equipment_id=equipment_id,
            direction=direction,
            interval_minutes=interval_minutes,
        )

        if format == "csv":
            # Convert to CSV format
            return _export_timeseries_csv(result)

        return result

    except Exception as e:
        logger.error(f"ODS-E timeseries export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/asset-metadata", response_model=ODSEAssetExport)
async def export_asset_metadata(
    site_id: str = Query(..., description="Sentinel site ID"),
    equipment_type: str | None = Query(None, description="Filter by equipment type"),
    include_health: bool = Query(default=True, description="Include health scores"),
) -> ODSEAssetExport:
    """
    Export Sentinel equipment inventory as ODS-E asset metadata.

    Returns asset records with ODS-E v0.4.0 schema and Sentinel extensions.
    """
    logger.info(
        f"ODS-E asset metadata export request: site={site_id}, "
        f"type={equipment_type}, include_health={include_health}"
    )

    try:
        result = await odse_service.export_asset_metadata(
            site_id=site_id,
            equipment_type=equipment_type,
            include_health=include_health,
        )
        return result

    except Exception as e:
        logger.error(f"ODS-E asset metadata export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint for ODS-E export service."""
    return {
        "status": "healthy",
        "service": "odse-export",
        "schema_version": "0.4.0",
    }


def _export_timeseries_csv(export: ODSETimeseriesExport) -> PlainTextResponse:
    """Convert ODS-E timeseries export to CSV format."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Write metadata header
    writer.writerow(["# ODS-E Export"])
    writer.writerow(["# Schema Version:", export.schema_version])
    writer.writerow(["# Source System:", export.source_system])
    writer.writerow(["# Site ID:", export.site_id])
    writer.writerow(["# Exported At:", export.exported_at])
    writer.writerow(["# Record Count:", export.record_count])
    writer.writerow([])

    # Write column headers
    writer.writerow([
        "timestamp", "kWh", "error_type", "direction", "fuel_type",
        "end_use", "kVA", "PF", "tariff_currency", "tariff_period"
    ])

    # Write records
    for record in export.records:
        writer.writerow([
            record.timestamp,
            record.kWh,
            record.error_type,
            record.direction,
            record.fuel_type,
            record.end_use or "",
            record.kVA or "",
            record.PF or "",
            record.tariff_currency or "",
            record.tariff_period or "",
        ])

    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=odse-export-{export.site_id}.csv"}
    )
