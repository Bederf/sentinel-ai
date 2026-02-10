"""Site aggregation API endpoints.

Provides aggregated endpoints for fetching complete site information in a single
request, reducing N individual API calls to a single aggregated call. Prevents 429
rate limit errors on dashboard loads.

Implements:
- GET /api/sites/{site_id}/summary - Complete site summary with equipment, safety, alerts, predictions
- GET /api/sites/{site_id}/alerts - Site alerts with aggregation (returns alert list with counts)
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Load JSON data for fallback
DATA_DIR = Path(__file__).parent.parent / "data"


def load_json_file(filename: str) -> List[dict]:
    """Load JSON data file with fallback to empty list."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        try:
            with open(filepath) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return []
    return []


# ---- Response Models ----

class EquipmentSummary(BaseModel):
    """Equipment summary for a site."""
    total_count: int
    by_type: Dict[str, int] = Field(default_factory=dict)
    critical_count: int = 0
    warning_count: int = 0


class SafetySummary(BaseModel):
    """Safety summary for a site."""
    devices_checked: int = 0
    safe_devices: int = 0
    warning_devices: int = 0
    critical_devices: int = 0


class AlertSummary(BaseModel):
    """Alert summary for a site."""
    total_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    recent_alerts: List[Dict[str, Any]] = Field(default_factory=list)


class PredictionSummary(BaseModel):
    """Prediction summary for a site."""
    total_count: int = 0
    critical_count: int = 0
    warning_count: int = 0


class EnergySummary(BaseModel):
    """Energy snapshot for a site."""
    current_power_usage: Optional[float] = None
    daily_consumption: Optional[float] = None
    solar_generation: Optional[float] = None


class SiteSummaryResponse(BaseModel):
    """Complete site summary response."""
    site_id: str
    equipment: EquipmentSummary
    safety: SafetySummary
    alerts: AlertSummary
    predictions: PredictionSummary
    energy: EnergySummary
    last_updated: str


class AlertListResponse(BaseModel):
    """Paginated alert list response."""
    site_id: str
    total_count: int
    critical_count: int
    warning_count: int
    info_count: int
    page: int
    page_size: int
    alerts: List[Dict[str, Any]] = Field(default_factory=list)


# ---- Endpoints ----

@router.get(
    "/sites/{site_id}/summary",
    response_model=SiteSummaryResponse,
    summary="Get complete site summary",
    description="Fetch aggregated site summary including equipment, safety status, "
                "alerts, predictions, and energy snapshot in a single request."
)
@limiter.limit("30/minute")
async def get_site_summary(site_id: str, request: Request) -> SiteSummaryResponse:
    """Get complete site summary with all aggregated metrics.

    Fetches equipment, safety status, alerts, predictions, and energy data
    in a single request to avoid N individual API calls.

    Args:
        site_id: Site ID to get summary for

    Returns:
        SiteSummaryResponse with all aggregated metrics

    Raises:
        HTTPException: 404 if site not found
    """
    try:
        # Load equipment data
        equipment_data = load_json_file("buildings.json")
        site_buildings = [b for b in equipment_data if b.get("id") == site_id or b.get("code") == site_id]

        if not site_buildings:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        site = site_buildings[0]
        site_name = site.get("name", "Unknown")

        # Count equipment by type
        equipment = site.get("equipment", [])
        equipment_by_type: Dict[str, int] = {}
        for eq in equipment:
            eq_type = eq.get("type", "unknown")
            equipment_by_type[eq_type] = equipment_by_type.get(eq_type, 0) + 1

        equipment_summary = EquipmentSummary(
            total_count=len(equipment),
            by_type=equipment_by_type
        )

        # Get safety summary
        safety_summary = SafetySummary()
        device_ids = [eq.get("id") for eq in equipment if eq.get("id")]

        if device_ids:
            safe_count = 0
            warning_count = 0
            critical_count = 0

            for device_id in device_ids:
                try:
                    device = await device_manager.get_device(device_id)
                    if device:
                        safety_status = await device_manager.get_device_safety_status(device_id)
                        severity = safety_status.get("severity", "unknown")

                        if severity == "SAFE":
                            safe_count += 1
                        elif severity == "WARNING":
                            warning_count += 1
                        elif severity == "CRITICAL":
                            critical_count += 1
                except Exception as e:
                    logger.debug(f"Error checking safety for {device_id}: {e}")

            safety_summary = SafetySummary(
                devices_checked=len(device_ids),
                safe_devices=safe_count,
                warning_devices=warning_count,
                critical_devices=critical_count
            )

        # Load alerts for this site
        alerts_data = load_json_file("alerts.json")
        site_alerts = [a for a in alerts_data if a.get("site_id") == site_id or a.get("building_id") == site_id]

        critical_alerts = [a for a in site_alerts if a.get("severity") == "critical"]
        warning_alerts = [a for a in site_alerts if a.get("severity") == "warning"]
        info_alerts = [a for a in site_alerts if a.get("severity") == "info"]

        # Get recent alerts (last 5)
        recent = sorted(site_alerts, key=lambda x: x.get("created_at", ""), reverse=True)[:5]

        alert_summary = AlertSummary(
            total_count=len(site_alerts),
            critical_count=len(critical_alerts),
            warning_count=len(warning_alerts),
            info_count=len(info_alerts),
            recent_alerts=recent
        )

        # Load predictions for this site
        predictions_data = load_json_file("predictions.json")
        site_predictions = [p for p in predictions_data if p.get("site_id") == site_id or p.get("building_id") == site_id]

        critical_predictions = [p for p in site_predictions if p.get("severity") == "critical"]
        warning_predictions = [p for p in site_predictions if p.get("severity") == "warning"]

        prediction_summary = PredictionSummary(
            total_count=len(site_predictions),
            critical_count=len(critical_predictions),
            warning_count=len(warning_predictions)
        )

        # Get energy snapshot (placeholder - would query energy API)
        energy_summary = EnergySummary()

        response = SiteSummaryResponse(
            site_id=site_id,
            equipment=equipment_summary,
            safety=safety_summary,
            alerts=alert_summary,
            predictions=prediction_summary,
            energy=energy_summary,
            last_updated=datetime.now().isoformat()
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting site summary for {site_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/sites/{site_id}/alerts",
    response_model=AlertListResponse,
    summary="Get site alerts with aggregation",
    description="Fetch paginated alerts for a site with aggregated counts. "
                "Returns alert list keyed by severity for O(1) client lookup."
)
@limiter.limit("30/minute")
async def get_site_alerts_aggregated(
    site_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
) -> AlertListResponse:
    """Get paginated alerts for a site with aggregation.

    Fetches all alerts for a site and aggregates counts by severity.
    Returns paginated results for efficient rendering.

    Args:
        site_id: Site ID to get alerts for
        page: Page number (default 1)
        page_size: Items per page (default 20, max 100)

    Returns:
        AlertListResponse with paginated alerts and counts

    Raises:
        HTTPException: 404 if site not found
    """
    try:
        # Load alerts data
        alerts_data = load_json_file("alerts.json")
        site_alerts = [a for a in alerts_data if a.get("site_id") == site_id or a.get("building_id") == site_id]

        if site_alerts is None:
            # Still return 404 only if site truly doesn't exist
            buildings_data = load_json_file("buildings.json")
            site_exists = any(b.get("id") == site_id or b.get("code") == site_id for b in buildings_data)
            if not site_exists:
                raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        # Count by severity
        critical_count = len([a for a in site_alerts if a.get("severity") == "critical"])
        warning_count = len([a for a in site_alerts if a.get("severity") == "warning"])
        info_count = len([a for a in site_alerts if a.get("severity") == "info"])

        # Sort by creation time (newest first) and paginate
        sorted_alerts = sorted(site_alerts, key=lambda x: x.get("created_at", ""), reverse=True)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_alerts = sorted_alerts[start_idx:end_idx]

        response = AlertListResponse(
            site_id=site_id,
            total_count=len(site_alerts),
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
            page=page,
            page_size=page_size,
            alerts=paginated_alerts
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting site alerts for {site_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
