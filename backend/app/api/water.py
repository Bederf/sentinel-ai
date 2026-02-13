"""Water Meter API endpoints.

Provides real-time and historical data for water meter installations:
  - Consumption data by site, meter, and time range
  - Current flow rate and latest readings
  - Leak alerts with severity filtering
  - Active (unresolved) alerts
  - Alert resolution workflow
  - Consumption trending with period comparison
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from app.middleware.rate_limiter import limiter

from app.services.water_ingestion_service import get_water_ingestion_service
from app.services.water_alert_service import get_water_alert_service, WaterAlertThresholds
from app.database.repositories.water_consumption_repository import WaterConsumptionRepository
from app.models.water_meter import WaterAlert, WaterTrend

logger = logging.getLogger(__name__)

router = APIRouter()


# === Consumption endpoints ===


@limiter.limit("30/minute")
@router.get("/water/sites/{site}/flow")
async def get_current_flow(request: Request, site: str):
    """Get current flow rate for a site.

    Args:
        site: Building site code (e.g., "site-002")

    Returns:
        Current flow rate in LPM with timestamp
    """
    try:
        svc = get_water_ingestion_service()
        latest = svc.get_latest_consumption(site)

        if not latest:
            raise HTTPException(
                status_code=404,
                detail=f"No consumption data found for site '{site}'"
            )

        return {
            "site": site,
            "flow_rate_lpm": latest.flow_rate_lpm if latest else 0.0,
            "timestamp": latest.timestamp if latest else datetime.now().isoformat(),
            "meter_id": latest.meter_id if latest else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching current flow for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/water/sites/{site}/consumption")
async def get_consumption(
    request: Request,
    site: str,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    meter_id: Optional[str] = Query(None, description="Filter by meter ID"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum records to return"),
):
    """Get water consumption data for a site.

    Args:
        site: Building site code (e.g., "site-002")
        start_date: Optional start date (default: 30 days ago)
        end_date: Optional end date (default: today)
        meter_id: Optional meter filter
        limit: Maximum records to return

    Returns:
        Consumption records with timestamps, volumes, and flow rates
    """
    try:
        repo = WaterConsumptionRepository()

        # Parse dates
        start = datetime.fromisoformat(start_date).date() if start_date else None
        end = datetime.fromisoformat(end_date).date() if end_date else None

        # Get data
        if meter_id:
            records = repo.get_consumption_by_meter(meter_id, start, end, limit)
        else:
            records = repo.get_consumption_by_site(site, start, end, limit)

        return {
            "site": site,
            "meter_id": meter_id,
            "record_count": len(records),
            "consumption": records,
        }

    except Exception as e:
        logger.error(f"Error fetching consumption for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/water/sites/{site}/current")
async def get_current_consumption(request: Request, site: str):
    """Get current flow rate and latest consumption reading.

    Args:
        site: Building site code

    Returns:
        Latest consumption reading with flow rate
    """
    try:
        svc = get_water_ingestion_service()
        latest = svc.get_latest_consumption(site)

        if not latest:
            raise HTTPException(
                status_code=404,
                detail=f"No consumption data found for site '{site}'"
            )

        return latest.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching current consumption for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/water/sites/{site}/trending")
async def get_consumption_trends(
    request: Request,
    site: str,
    period: str = Query("week", description="Period: day, week, month"),
):
    """Get consumption trends with comparison to baseline.

    Args:
        site: Building site code
        period: Analysis period (day, week, month)

    Returns:
        Trend analysis with total volume, average flow, comparison to baseline
    """
    try:
        repo = WaterConsumptionRepository()

        # Determine date range based on period
        end_date = date.today()
        if period == "day":
            start_date = end_date
        elif period == "week":
            start_date = end_date - timedelta(days=7)
        elif period == "month":
            start_date = end_date - timedelta(days=30)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid period '{period}'. Use: day, week, month"
            )

        # Get current period data
        current_records = repo.get_consumption_by_site(site, start_date, end_date)

        if not current_records:
            return {
                "site": site,
                "period": period,
                "total_volume_liters": 0,
                "average_flow_rate_lpm": 0,
                "peak_flow_rate_lpm": 0,
                "baseline_comparison_percent": 0,
                "trend_direction": "stable",
                "record_count": 0,
            }

        # Calculate metrics
        volumes = [r["volume_liters"] for r in current_records]
        flows = [r["flow_rate_lpm"] for r in current_records]

        total_volume = max(volumes) - min(volumes) if volumes else 0
        average_flow = sum(flows) / len(flows) if flows else 0
        peak_flow = max(flows) if flows else 0

        # Get baseline for comparison (previous period)
        baseline_end = start_date - timedelta(days=1)
        baseline_start = baseline_end - (end_date - start_date)
        baseline_records = repo.get_consumption_by_site(site, baseline_start, baseline_end)

        baseline_volume = 0
        if baseline_records:
            baseline_volumes = [r["volume_liters"] for r in baseline_records]
            baseline_volume = max(baseline_volumes) - min(baseline_volumes)

        # Calculate comparison
        if baseline_volume > 0:
            comparison_percent = ((total_volume - baseline_volume) / baseline_volume) * 100
            if comparison_percent > 10:
                trend_direction = "up"
            elif comparison_percent < -10:
                trend_direction = "down"
            else:
                trend_direction = "stable"
        else:
            comparison_percent = 0
            trend_direction = "stable"

        return {
            "site": site,
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_volume_liters": round(total_volume, 2),
            "average_flow_rate_lpm": round(average_flow, 2),
            "peak_flow_rate_lpm": round(peak_flow, 2),
            "baseline_comparison_percent": round(comparison_percent, 1),
            "trend_direction": trend_direction,
            "record_count": len(current_records),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching trends for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Alert endpoints ===


@limiter.limit("30/minute")
@router.get("/water/sites/{site}/alerts")
async def get_alerts(
    request: Request,
    site: str,
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high, critical"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    status: Optional[str] = Query(None, description="Filter by status: active, resolved, acknowledged"),
):
    """Get water leak alerts for a site.

    Args:
        site: Building site code
        severity: Optional severity filter
        start_date: Optional start date
        end_date: Optional end date
        status: Optional status filter

    Returns:
        List of water alerts
    """
    try:
        alert_svc = get_water_alert_service()

        # Parse dates
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None

        # Get alerts
        alerts = alert_svc.get_leak_alerts(
            site=site,
            severity=severity,
            start_date=start,
            end_date=end,
            status=status,
        )

        return {
            "site": site,
            "alert_count": len(alerts),
            "alerts": [alert.to_dict() for alert in alerts],
        }

    except Exception as e:
        logger.error(f"Error fetching alerts for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/water/sites/{site}/alerts/active")
async def get_active_alerts(request: Request, site: str):
    """Get all active (unresolved) leak alerts.

    Args:
        site: Building site code

    Returns:
        List of active alerts requiring attention
    """
    try:
        alert_svc = get_water_alert_service()
        alerts = alert_svc.get_active_alerts(site)

        return {
            "site": site,
            "active_alert_count": len(alerts),
            "alerts": [alert.to_dict() for alert in alerts],
        }

    except Exception as e:
        logger.error(f"Error fetching active alerts for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/water/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolved_by: str = Query(..., description="User resolving the alert"),
    resolution_notes: str = Query(..., description="Resolution description"),
):
    """Mark a water leak alert as resolved.

    Args:
        alert_id: Alert identifier
        resolved_by: User resolving the alert
        resolution_notes: Description of how the issue was fixed

    Returns:
        Updated alert record
    """
    try:
        alert_svc = get_water_alert_service()
        success = alert_svc.resolve_alert(alert_id, resolved_by, resolution_notes)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert '{alert_id}' not found or update failed"
            )

        return {
            "alert_id": alert_id,
            "status": "resolved",
            "resolved_by": resolved_by,
            "resolution_notes": resolution_notes,
            "message": "Alert resolved successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Ingestion status endpoints ===


@limiter.limit("20/minute")
@router.get("/water/ingestion/status")
async def get_ingestion_status(request: Request):
    """Get water ingestion service status.

    Returns:
        List of registered sites with meter counts and last poll time
    """
    try:
        svc = get_water_ingestion_service()
        sites = svc.get_sites()

        status_list = []
        for site_id in sites:
            status = svc.get_site_status(site_id)
            status_list.append(status)

        return {
            "service": "water_ingestion",
            "site_count": len(sites),
            "sites": status_list,
        }

    except Exception as e:
        logger.error(f"Error fetching ingestion status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("20/minute")
@router.get("/water/ingestion/{site}/status")
async def get_site_ingestion_status(request: Request, site: str):
    """Get ingestion status for a specific site.

    Args:
        site: Building site code

    Returns:
        Site registration status, meter count, last poll time
    """
    try:
        svc = get_water_ingestion_service()
        status = svc.get_site_status(site)

        if "error" in status:
            raise HTTPException(status_code=404, detail=status["error"])

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching ingestion status for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Advanced alert filtering and threshold management ===


@limiter.limit("30/minute")
@router.get("/water/alerts/advanced")
async def get_advanced_alerts(
    request: Request,
    site: str = Query(..., description="Building site code"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    zone_id: Optional[str] = Query(None, description="Filter by zone ID"),
    start: Optional[str] = Query(None, description="Start date (ISO format)"),
    end: Optional[str] = Query(None, description="End date (ISO format)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
):
    """Get advanced water alerts with filtering by type, severity, zone, and time range.

    Args:
        site: Building site code
        alert_type: Optional alert type filter
        severity: Optional severity filter
        zone_id: Optional zone filter
        start: Optional start date
        end: Optional end date
        status: Optional status filter
        limit: Maximum records to return

    Returns:
        Filtered list of water alerts with metadata
    """
    try:
        repo = WaterConsumptionRepository()

        # Parse dates
        start_date = datetime.fromisoformat(start).date() if start else None
        end_date = datetime.fromisoformat(end).date() if end else None

        # Get alerts
        alerts = repo.get_alerts(
            site=site,
            severity=severity,
            start_date=start_date,
            end_date=end_date,
            status=status,
        )

        # Additional filtering by alert_type and zone_id
        if alert_type:
            alerts = [a for a in alerts if a.get("alert_type") == alert_type]
        if zone_id:
            alerts = [a for a in alerts if zone_id in a.get("meter_id", "")]

        # Apply limit
        alerts = alerts[:limit]

        return {
            "site": site,
            "filters": {
                "alert_type": alert_type,
                "severity": severity,
                "zone_id": zone_id,
                "start": start,
                "end": end,
                "status": status,
            },
            "alert_count": len(alerts),
            "alerts": alerts,
        }

    except Exception as e:
        logger.error(f"Error fetching advanced alerts for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.post("/water/alerts/thresholds/{site}")
async def set_alert_thresholds(
    request: Request,
    site: str,
    thresholds: WaterAlertThresholds,
):
    """Set custom alert thresholds for a site.

    Args:
        site: Building site code
        thresholds: Threshold configuration

    Returns:
        Confirmation with updated thresholds
    """
    try:
        repo = WaterConsumptionRepository()
        threshold_dict = thresholds.dict()

        success = await repo.set_alert_thresholds(site, threshold_dict)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save thresholds for site {site}"
            )

        return {
            "site": site,
            "thresholds": threshold_dict,
            "updated_at": datetime.now().isoformat(),
            "default": False,
        }

    except Exception as e:
        logger.error(f"Error setting alert thresholds for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/water/alerts/thresholds/{site}")
async def get_alert_thresholds(request: Request, site: str):
    """Get current alert thresholds for a site.

    Args:
        site: Building site code

    Returns:
        Current threshold configuration (default or custom)
    """
    try:
        repo = WaterConsumptionRepository()
        thresholds = repo.get_alert_thresholds(site)

        return {
            "site": site,
            "thresholds": thresholds,
            "default": all(
                thresholds.get(k) == v
                for k, v in repo._get_default_thresholds().items()
            ),
        }

    except Exception as e:
        logger.error(f"Error fetching alert thresholds for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/water/zones/{zone_id}/anomaly-history")
async def get_zone_anomaly_history(
    request: Request,
    zone_id: str,
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
):
    """Get anomaly history and statistical baseline for a zone.

    Args:
        zone_id: Zone identifier
        days: Number of days to analyze

    Returns:
        Historical anomalies and statistical baseline metrics
    """
    try:
        repo = WaterConsumptionRepository()
        alert_svc = get_water_alert_service()

        # Get historical flow data
        cutoff_date = date.today() - timedelta(days=days)
        records = repo.get_consumption_by_meter(
            meter_id=f"{zone_id}-meter",
            start_date=cutoff_date,
            end_date=date.today(),
            limit=10000,
        )

        if not records:
            return {
                "zone_id": zone_id,
                "days": days,
                "anomalies": [],
                "baseline": None,
                "count": 0,
            }

        # Extract flows and calculate baseline
        flows = [r.get("flow_rate_lpm", 0) for r in records if r.get("flow_rate_lpm")]
        baseline = alert_svc.calculate_statistical_baseline(flows)

        # Get anomalous alerts for this zone
        all_alerts = repo.get_alerts(
            site="",  # Will search all sites
            start_date=cutoff_date,
            end_date=date.today(),
        )
        zone_anomalies = [a for a in all_alerts if zone_id in a.get("meter_id", "")]

        return {
            "zone_id": zone_id,
            "days": days,
            "baseline": baseline,
            "anomalies": zone_anomalies[:100],
            "count": len(zone_anomalies),
        }

    except Exception as e:
        logger.error(f"Error fetching anomaly history for zone {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
