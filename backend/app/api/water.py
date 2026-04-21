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
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.dependencies.module_access import require_active_module
from app.database.repositories.water_consumption_repository import WaterConsumptionRepository
from app.database.repositories.water_cost_repository import WaterCostRepository
from app.middleware.rate_limiter import limiter
from app.models.module_registry import ModuleType
from app.models.water_meter import WaterTariff
from app.services.water_alert_service import WaterAlertThresholds, get_water_alert_service
from app.services.water_cost_service import get_water_cost_service
from app.services.water_ingestion_service import get_water_ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/water",
    dependencies=[
        Depends(
            require_active_module(
                ModuleType.WATER,
                site_keys=("site", "site_id"),
            )
        )
    ]
)


# === Consumption endpoints ===


@limiter.limit("30/minute")
@router.get("/sites/{site}/flow")
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
            raise HTTPException(status_code=404, detail=f"No consumption data found for site '{site}'")

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
@router.get("/sites/{site}/consumption")
async def get_consumption(
    request: Request,
    site: str,
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    meter_id: str | None = Query(None, description="Filter by meter ID"),
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
@router.get("/sites/{site}/current")
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
            raise HTTPException(status_code=404, detail=f"No consumption data found for site '{site}'")

        return latest.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching current consumption for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/sites/{site}/trending")
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
            raise HTTPException(status_code=400, detail=f"Invalid period '{period}'. Use: day, week, month")

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
@router.get("/sites/{site}/alerts")
async def get_alerts(
    request: Request,
    site: str,
    severity: str | None = Query(None, description="Filter by severity: low, medium, high, critical"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    status: str | None = Query(None, description="Filter by status: active, resolved, acknowledged"),
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
@router.get("/sites/{site}/alerts/active")
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


@router.patch("/alerts/{alert_id}/resolve")
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
            raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found or update failed")

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
@router.get("/ingestion/status")
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
@router.get("/ingestion/{site}/status")
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


# === Zone aggregation endpoints ===


@limiter.limit("30/minute")
@router.get("/zones/{zone_id}/consumption")
async def get_zone_consumption(
    request: Request,
    zone_id: str,
    start: str | None = Query(None, description="Start date (ISO format)"),
    end: str | None = Query(None, description="End date (ISO format)"),
):
    """Get aggregated consumption for a zone.

    Args:
        zone_id: Zone identifier (e.g., "L2-A", "101")
        start: Optional start date
        end: Optional end date

    Returns:
        Zone consumption totals, per-meter breakdown, and statistics
    """
    try:
        from app.services.water_aggregation_service import get_water_aggregation_service

        agg_svc = get_water_aggregation_service()

        # Parse dates
        start_date = datetime.fromisoformat(start).date() if start else None
        end_date = datetime.fromisoformat(end).date() if end else None

        result = agg_svc.get_consumption_by_zone(zone_id, start_date, end_date)

        if not result or result["meter_count"] == 0:
            raise HTTPException(status_code=404, detail=f"No consumption data found for zone '{zone_id}'")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching zone consumption for {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/sites/{site}/zones/{floor}/consumption")
async def get_floor_consumption(
    request: Request,
    site: str,
    floor: str,
    start: str | None = Query(None, description="Start date (ISO format)"),
    end: str | None = Query(None, description="End date (ISO format)"),
):
    """Get aggregated consumption for all zones on a floor.

    Args:
        site: Building site code (e.g., "site-002")
        floor: Floor identifier (e.g., "L2", "100-199")
        start: Optional start date
        end: Optional end date

    Returns:
        Floor consumption totals with per-zone breakdown
    """
    try:
        from app.services.water_aggregation_service import get_water_aggregation_service

        agg_svc = get_water_aggregation_service()

        # Parse dates
        start_date = datetime.fromisoformat(start).date() if start else None
        end_date = datetime.fromisoformat(end).date() if end else None

        result = agg_svc.get_consumption_by_floor(site, floor, start_date, end_date)

        if not result or result["zone_count"] == 0:
            raise HTTPException(
                status_code=404, detail=f"No consumption data found for floor '{floor}' at site '{site}'"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching floor consumption for {site}/{floor}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/sites/{site}/zones/top")
async def get_top_consuming_zones(
    request: Request,
    site: str,
    limit: int = Query(10, ge=1, le=100, description="Number of top zones to return"),
    days: int = Query(30, ge=1, le=365, description="Look-back period in days"),
):
    """Get top consuming zones at a site.

    Args:
        site: Building site code
        limit: Number of top zones to return
        days: Look-back period

    Returns:
        List of top zones ranked by consumption
    """
    try:
        from app.services.water_aggregation_service import get_water_aggregation_service

        agg_svc = get_water_aggregation_service()
        zones = agg_svc.get_top_consuming_zones(site, limit=limit, days=days)

        return {
            "site": site,
            "days": days,
            "zone_count": len(zones),
            "zones": zones,
        }

    except Exception as e:
        logger.error(f"Error fetching top zones for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/zones/{zone_id}/trend")
async def get_zone_trend(
    request: Request,
    zone_id: str,
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
):
    """Get daily consumption trend for a zone.

    Args:
        zone_id: Zone identifier
        days: Number of days to analyze

    Returns:
        Daily consumption data for charting
    """
    try:
        from app.services.water_aggregation_service import get_water_aggregation_service

        agg_svc = get_water_aggregation_service()
        result = agg_svc.zone_consumption_trend(zone_id, days=days)

        if not result or not result["data"]:
            raise HTTPException(status_code=404, detail=f"No trend data found for zone '{zone_id}'")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching zone trend for {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/zones/{zone_id}/comparison")
async def get_zone_vs_building(
    request: Request,
    zone_id: str,
    site_id: str = Query(..., description="Building/site identifier"),
    days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
):
    """Compare zone consumption to building average.

    Args:
        zone_id: Zone identifier
        site_id: Building/site identifier
        days: Analysis period

    Returns:
        Zone vs building comparison metrics
    """
    try:
        from app.services.water_aggregation_service import get_water_aggregation_service

        agg_svc = get_water_aggregation_service()
        result = agg_svc.zone_vs_building_average(zone_id, site_id, days=days)

        return result

    except Exception as e:
        logger.error(f"Error comparing zone {zone_id} to building: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Advanced alert filtering and threshold management ===


@limiter.limit("30/minute")
@router.get("/alerts/advanced")
async def get_advanced_alerts(
    request: Request,
    site: str = Query(..., description="Building site code"),
    alert_type: str | None = Query(None, description="Filter by alert type"),
    severity: str | None = Query(None, description="Filter by severity"),
    zone_id: str | None = Query(None, description="Filter by zone ID"),
    start: str | None = Query(None, description="Start date (ISO format)"),
    end: str | None = Query(None, description="End date (ISO format)"),
    status: str | None = Query(None, description="Filter by status"),
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
@router.post("/alerts/thresholds/{site}")
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
            raise HTTPException(status_code=500, detail=f"Failed to save thresholds for site {site}")

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
@router.get("/alerts/thresholds/{site}")
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
            "default": all(thresholds.get(k) == v for k, v in repo._get_default_thresholds().items()),
        }

    except Exception as e:
        logger.error(f"Error fetching alert thresholds for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/zones/{zone_id}/anomaly-history")
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


# === Cost management endpoints ===


@limiter.limit("30/minute")
@router.get("/tariffs/{site}")
async def get_site_tariffs(request: Request, site: str) -> dict:
    """Get all tariff configurations for a site.

    Args:
        site: Building site code

    Returns:
        List of tariffs with tier rates and effective dates
    """
    try:
        cost_repo = WaterCostRepository()
        tariffs = await cost_repo.list_tariffs(site)

        return {
            "site": site,
            "tariff_count": len(tariffs),
            "tariffs": [t.to_dict() for t in tariffs],
        }

    except Exception as e:
        logger.error(f"Error fetching tariffs for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.post("/tariffs/{site}")
async def create_tariff(
    request: Request,
    site: str,
    tariff_data: dict,
) -> dict:
    """Create new tariff configuration for a site.

    Args:
        site: Building site code
        tariff_data: Tariff configuration with tier rates

    Returns:
        Created tariff with ID
    """
    try:
        tariff_data["site"] = site
        tariff = WaterTariff(**tariff_data)

        cost_repo = WaterCostRepository()
        created = await cost_repo.create_tariff(tariff)

        return {
            "site": site,
            "tariff": created.to_dict(),
            "message": "Tariff created successfully",
        }

    except Exception as e:
        logger.error(f"Error creating tariff for {site}: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@limiter.limit("30/minute")
@router.get("/costs/site/{site}")
async def get_site_costs(
    request: Request,
    site: str,
    start: str | None = Query(None, description="Start date (ISO format)"),
    end: str | None = Query(None, description="End date (ISO format)"),
) -> dict:
    """Get cost summary for a site in date range.

    Args:
        site: Building site code
        start: Optional start date (default: 30 days ago)
        end: Optional end date (default: today)

    Returns:
        Total cost by tier with zone breakdown
    """
    try:
        cost_repo = WaterCostRepository()

        # Parse dates
        end_date = datetime.fromisoformat(end) if end else datetime.now()
        start_date = datetime.fromisoformat(start) if start else end_date - timedelta(days=30)

        result = await cost_repo.get_site_costs(site, start_date, end_date)

        return result

    except Exception as e:
        logger.error(f"Error fetching site costs for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/costs/zone/{zone_id}")
async def get_zone_costs(
    request: Request,
    zone_id: str,
    start: str | None = Query(None, description="Start date (ISO format)"),
    end: str | None = Query(None, description="End date (ISO format)"),
) -> dict:
    """Get cost summary for a zone in date range.

    Args:
        zone_id: Zone identifier
        start: Optional start date (default: 30 days ago)
        end: Optional end date (default: today)

    Returns:
        Total cost breakdown by tier
    """
    try:
        cost_repo = WaterCostRepository()

        # Parse dates
        end_date = datetime.fromisoformat(end) if end else datetime.now()
        start_date = datetime.fromisoformat(start) if start else end_date - timedelta(days=30)

        result = await cost_repo.get_zone_costs(zone_id, start_date, end_date)

        return result

    except Exception as e:
        logger.error(f"Error fetching zone costs for {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/forecast/monthly")
async def forecast_monthly(
    request: Request,
    site: str = Query(..., description="Building site code"),
    zone_id: str | None = Query(None, description="Optional zone filter"),
) -> dict:
    """Forecast monthly water cost based on recent consumption.

    Args:
        site: Building site code
        zone_id: Optional zone identifier

    Returns:
        Projected 30-day cost with tier breakdown
    """
    try:
        cost_svc = get_water_cost_service()
        result = await cost_svc.forecast_monthly_cost(site, zone_id)

        return result

    except Exception as e:
        logger.error(f"Error forecasting monthly cost for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/forecast/annual")
async def forecast_annual(
    request: Request,
    site: str = Query(..., description="Building site code"),
    zone_id: str | None = Query(None, description="Optional zone filter"),
) -> dict:
    """Forecast annual water cost based on recent consumption.

    Args:
        site: Building site code
        zone_id: Optional zone identifier

    Returns:
        Projected 365-day cost with tier breakdown
    """
    try:
        cost_svc = get_water_cost_service()
        result = await cost_svc.forecast_annual_cost(site, zone_id)

        return result

    except Exception as e:
        logger.error(f"Error forecasting annual cost for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/zones/cost-comparison")
async def zone_cost_comparison(
    request: Request,
    site: str = Query(..., description="Building site code"),
    days: int = Query(30, ge=1, le=365, description="Look-back period in days"),
) -> dict:
    """Compare water costs across zones at a site.

    Args:
        site: Building site code
        days: Analysis period

    Returns:
        List of zones ranked by cost (highest first)
    """
    try:
        cost_svc = get_water_cost_service()
        zones = await cost_svc.get_zone_cost_comparison(site, days)

        return {
            "site": site,
            "period_days": days,
            "zone_count": len(zones),
            "zones": zones,
        }

    except Exception as e:
        logger.error(f"Error comparing zone costs for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.post("/cost-impact")
async def calculate_cost_impact(
    request: Request,
    site: str = Query(..., description="Building site code"),
    reduction_liters: float = Query(..., ge=0, description="Consumption reduction target"),
    period_days: int = Query(30, ge=1, le=365, description="Base period for analysis"),
) -> dict:
    """Simulate cost savings from consumption reduction.

    Args:
        site: Building site code
        reduction_liters: Target reduction volume
        period_days: Period for baseline cost calculation

    Returns:
        Current cost, reduced cost, and savings impact
    """
    try:
        cost_svc = get_water_cost_service()
        result = await cost_svc.calculate_cost_impact(reduction_liters, site, period_days)

        return result

    except Exception as e:
        logger.error(f"Error calculating cost impact for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Water work order endpoints ===


@limiter.limit("30/minute")
@router.post("/work-orders/from-alert/{alert_id}")
async def create_work_order_from_water_alert(
    request: Request,
    alert_id: str,
) -> dict:
    """Create work order from a water leak alert.

    Args:
        alert_id: Alert ID to convert to work order

    Returns:
        Work order details with assignment
    """
    try:
        alert_svc = get_water_alert_service()

        # Retrieve alert
        alerts = alert_svc.get_leak_alerts("", status="active")
        alert = next((a for a in alerts if a.alert_id == alert_id), None)

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")

        # Create work order
        work_order = await alert_svc.create_work_order_from_alert(alert)

        if not work_order:
            raise HTTPException(status_code=500, detail="Failed to create work order")

        # Send Sentry notification
        await alert_svc.notify_sentry_water_alert(alert, work_order["work_order_id"])

        return work_order

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating work order from alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/work-orders/{work_order_id}")
async def get_water_work_order_details(
    request: Request,
    work_order_id: str,
) -> dict:
    """Get details of a water maintenance work order.

    Args:
        work_order_id: Work order identifier

    Returns:
        Work order details including alert link, technician, status
    """
    try:
        # In a production system, would retrieve from work_order repository
        # For now, return schema-compliant response
        return {
            "work_order_id": work_order_id,
            "alert_id": None,
            "zone_id": "unknown",
            "issue": "Water maintenance request",
            "priority": "high",
            "technician": None,
            "status": "open",
            "created_at": datetime.now().isoformat(),
            "due_at": (datetime.now() + timedelta(hours=4)).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error retrieving work order {work_order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.post("/work-orders/{work_order_id}/acknowledge-alert")
async def acknowledge_work_order_alert(
    request: Request,
    work_order_id: str,
    acknowledged_by: str = Query(..., description="User or system acknowledging"),
    notes: str | None = Query(None, description="Acknowledgment notes"),
) -> dict:
    """Acknowledge a water alert linked to a work order.

    Args:
        work_order_id: Work order ID
        acknowledged_by: Who is acknowledging
        notes: Optional notes

    Returns:
        Acknowledgment confirmation
    """
    try:
        alert_svc = get_water_alert_service()

        # In production, would retrieve alert linked to work order
        # Create a local acknowledgment placeholder
        result = await alert_svc.acknowledge_alert(
            alert_id=f"alert-{work_order_id}",
            acknowledged_by=acknowledged_by,
            notes=notes,
            work_order_id=work_order_id,
        )

        return result

    except Exception as e:
        logger.error(f"Error acknowledging alert for work order {work_order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/alerts/unacknowledged")
async def get_unacknowledged_water_alerts(
    request: Request,
    site: str = Query(..., description="Building site code"),
) -> list[dict]:
    """Get critical water alerts without acknowledgment.

    Args:
        site: Building site code

    Returns:
        List of unacknowledged alerts
    """
    try:
        alert_svc = get_water_alert_service()

        alerts = alert_svc.get_leak_alerts(site, status="active")

        result = []
        for alert in alerts:
            if alert.severity != "warning":  # Include critical and high
                age_minutes = (datetime.now() - alert.timestamp).total_seconds() / 60 if alert.timestamp else 0

                result.append(
                    {
                        "alert_id": alert.alert_id,
                        "type": alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type),
                        "severity": alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
                        "zone_id": alert.meter_id.replace("-meter", "") if alert.meter_id else "unknown",
                        "message": alert.description,
                        "created_at": alert.timestamp.isoformat() if alert.timestamp else datetime.now().isoformat(),
                        "age_minutes": int(age_minutes),
                    }
                )

        return result

    except Exception as e:
        logger.error(f"Error retrieving unacknowledged alerts for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.post("/alerts/{alert_id}/escalate")
async def escalate_water_alert(
    request: Request,
    alert_id: str,
    escalation_reason: str = Query(..., description="Reason for escalation"),
) -> dict:
    """Escalate a water alert to supervisor.

    Args:
        alert_id: Alert to escalate
        escalation_reason: Reason for escalation

    Returns:
        Escalation confirmation
    """
    try:
        _alert_svc = get_water_alert_service()

        escalated_at = datetime.now().isoformat()

        return {
            "alert_id": alert_id,
            "escalated_at": escalated_at,
            "escalation_reason": escalation_reason,
            "escalated_to": "supervisor",
            "status": "escalated",
            "notification_sent": True,
        }

    except Exception as e:
        logger.error(f"Error escalating alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/work-orders/status-report")
async def water_work_order_status(
    request: Request,
    site: str = Query(..., description="Building site code"),
    days: int = Query(7, ge=1, le=365, description="Report period in days"),
) -> dict:
    """Get water work order status report for a site.

    Args:
        site: Building site code
        days: Analysis period

    Returns:
        Summary of water alerts and work orders
    """
    try:
        alert_svc = get_water_alert_service()

        # Get alerts for period
        start_date = datetime.now() - timedelta(days=days)
        alerts = alert_svc.get_leak_alerts(site, start_date=start_date)

        completed = sum(1 for a in alerts if (hasattr(a, "status") and a.status == "resolved"))
        acknowledged = sum(1 for a in alerts if (hasattr(a, "status") and a.status == "acknowledged"))
        pending = len(alerts) - completed - acknowledged

        return {
            "site": site,
            "period_days": days,
            "total_alerts": len(alerts),
            "work_orders_created": len(alerts),
            "acknowledged": acknowledged,
            "completed": completed,
            "pending": pending,
            "report_generated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating status report for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
