"""Solar PV & BESS API endpoints.

Provides real-time and historical data for solar installations:
  - Site overview (total generation, BESS SOC, grid flow)
  - Inverter fleet status and per-inverter detail with string data
  - BESS container status (SOC, mode, power, health)
  - Grid meter readings (import/export, PF, THD)
  - Normalised readings filtered by type
  - Connector health status
  - Performance monitoring: PR, inverter peer comparison, string anomalies
  - Diagnostics: prioritised issues with cost impact and recommended actions
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.solar_ingestion_service import get_solar_ingestion_service
from app.services.solar_performance_service import get_solar_performance_service

router = APIRouter()


# === Ingestion endpoints (from 34-01) ===


@router.get("/solar/sites")
async def list_solar_sites():
    """List all registered solar sites."""
    svc = get_solar_ingestion_service()
    return {"sites": svc.get_registered_sites()}


@router.get("/solar/sites/{site_id}/overview")
async def get_site_overview(site_id: str):
    """Get high-level site overview: total generation, BESS SOC, grid import/export."""
    svc = get_solar_ingestion_service()
    overview = await svc.get_site_overview(site_id)
    if not overview:
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found")
    return overview


@router.get("/solar/sites/{site_id}/inverters")
async def get_inverters(site_id: str):
    """Get all inverters for a site with current readings."""
    svc = get_solar_ingestion_service()
    inverters = await svc.get_inverters(site_id)
    if not inverters and site_id not in [s["site_id"] for s in svc.get_registered_sites()]:
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found")
    return {
        "site_id": site_id,
        "inverter_count": len(inverters),
        "inverters": [inv.to_dict() for inv in inverters],
    }


@router.get("/solar/sites/{site_id}/inverters/{inverter_id}")
async def get_inverter_detail(site_id: str, inverter_id: str):
    """Get single inverter detail with string-level data."""
    svc = get_solar_ingestion_service()
    detail = await svc.get_inverter_detail(site_id, inverter_id)
    if not detail:
        raise HTTPException(
            status_code=404,
            detail=f"Inverter '{inverter_id}' not found at site '{site_id}'"
        )
    return detail


@router.get("/solar/sites/{site_id}/bess")
async def get_bess_status(site_id: str):
    """Get BESS container status: SOC, mode, power, health, alarms."""
    svc = get_solar_ingestion_service()
    bess = await svc.get_bess_status(site_id)
    if not bess:
        raise HTTPException(
            status_code=404,
            detail=f"No BESS found at site '{site_id}'"
        )
    return bess.to_dict()


@router.get("/solar/sites/{site_id}/meter")
async def get_meter_readings(site_id: str):
    """Get grid meter readings: import/export, voltage, frequency, PF, THD."""
    svc = get_solar_ingestion_service()
    meters = await svc.get_meter_readings(site_id)
    if not meters and site_id not in [s["site_id"] for s in svc.get_registered_sites()]:
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found")
    return {
        "site_id": site_id,
        "meter_count": len(meters),
        "meters": [m.to_dict() for m in meters],
    }


@router.get("/solar/sites/{site_id}/readings")
async def get_readings(
    site_id: str,
    type: Optional[str] = Query(None, description="Filter by reading type (power, energy, soc, etc.)"),
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type (inverter, bess, meter)"),
):
    """Get normalised readings, optionally filtered by reading type and equipment type."""
    svc = get_solar_ingestion_service()
    readings = await svc.get_readings(site_id, reading_type=type, equipment_type=equipment_type)
    return {
        "site_id": site_id,
        "reading_count": len(readings),
        "readings": [r.to_dict() for r in readings],
    }


@router.get("/solar/sites/{site_id}/connectors")
async def get_connector_status(site_id: str):
    """Get health status of all manufacturer connectors for a site."""
    svc = get_solar_ingestion_service()
    statuses = svc.get_connector_status(site_id)
    if not statuses and site_id not in [s["site_id"] for s in svc.get_registered_sites()]:
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found")
    return {
        "site_id": site_id,
        "connector_count": len(statuses),
        "connectors": statuses,
    }


# === Performance monitoring endpoints (34-02) ===


@router.get("/solar/sites/{site_id}/performance")
async def get_performance_metrics(
    site_id: str,
    period: str = Query("day", description="Period: day, week, or month"),
):
    """Get Performance Ratio metrics for a site with daily/weekly/monthly trend.

    Returns PR calculation, rating (excellent/good/acceptable/poor),
    target PR for SA commercial installations, and trend direction.
    """
    perf = get_solar_performance_service()
    metrics = await perf.calculate_pr(site_id, period=period)
    if not metrics:
        raise HTTPException(
            status_code=404,
            detail=f"Solar site '{site_id}' not found or no generation data"
        )
    return metrics.to_dict()


@router.get("/solar/sites/{site_id}/performance/inverters")
async def get_inverter_peer_comparison(site_id: str):
    """Get inverter peer comparison table with rankings.

    Compares inverters within their peer group (same manufacturer/model).
    Returns specific yield, deviation from group mean, rank, and flags
    underperformers with probable cause and cost impact.
    """
    perf = get_solar_performance_service()
    comparisons = await perf.compare_inverter_peers(site_id)
    if not comparisons:
        ingestion = get_solar_ingestion_service()
        if site_id not in [s["site_id"] for s in ingestion.get_registered_sites()]:
            raise HTTPException(
                status_code=404,
                detail=f"Solar site '{site_id}' not found"
            )
    return {
        "site_id": site_id,
        "inverter_count": len(comparisons),
        "underperforming": sum(
            1 for c in comparisons if c.status != "normal"
        ),
        "inverters": [c.to_dict() for c in comparisons],
    }


@router.get("/solar/sites/{site_id}/performance/strings")
async def get_string_anomalies(
    site_id: str,
    inverter_id: Optional[str] = Query(
        None, description="Filter to specific inverter"
    ),
):
    """Get string-level detail with anomaly flags.

    Compares strings on same MPPT tracker using statistical thresholds.
    Detects: string_underperform (soiling/shade), string_open_circuit
    (disconnection), string_short (bypass diode), mppt_fault (tracker hardware).
    """
    perf = get_solar_performance_service()
    anomalies = await perf.detect_string_anomalies(
        site_id, inverter_id=inverter_id
    )

    # If filtering by inverter, include total string count for context
    total_strings = 0
    if inverter_id:
        ingestion = get_solar_ingestion_service()
        detail = await ingestion.get_inverter_detail(site_id, inverter_id)
        if detail:
            total_strings = detail.get("string_count", 0)

    return {
        "site_id": site_id,
        "inverter_id": inverter_id,
        "anomaly_count": len(anomalies),
        "total_strings": total_strings,
        "anomalies": [a.to_dict() for a in anomalies],
    }


@router.get("/solar/sites/{site_id}/diagnostics")
async def get_diagnostics(site_id: str):
    """Get full diagnostic report with prioritised issues.

    Aggregates: PR metrics, underperforming inverters, string anomalies,
    BESS health flags. Returns prioritised list of issues with severity,
    probable cause, recommended action, confidence score, and cost impact.
    """
    perf = get_solar_performance_service()
    report = await perf.get_diagnostic_summary(site_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"Solar site '{site_id}' not found or no data available"
        )
    return report.to_dict()
