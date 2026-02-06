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
  - Grid compliance: NRS 097-2-1 monitoring, SSEG reporting, certificates
  - Energy arbitrage: TOU tariff optimisation, BESS dispatch scheduling, savings
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.solar_ingestion_service import get_solar_ingestion_service
from app.services.solar_performance_service import get_solar_performance_service
from app.services.solar_compliance_service import get_solar_compliance_service
from app.services.solar_arbitrage_engine import get_solar_arbitrage_engine
from app.services.solar_dispatch_service import get_solar_dispatch_service

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


# === Grid compliance endpoints (34-03) ===


@router.get("/solar/sites/{site_id}/compliance")
async def get_compliance_status(site_id: str):
    """Get overall grid compliance status (traffic-light) with breakdown per standard.

    Returns NRS 097-2-1 compliance summary covering voltage, frequency,
    power quality, export limits, and certificate validity. Status is
    compliant (green), warning (yellow), or violation (red).
    """
    svc = get_solar_compliance_service()
    result = await svc.get_overall_compliance(site_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Solar site '{site_id}' not found"
        )
    return result


@router.get("/solar/sites/{site_id}/compliance/voltage")
async def get_voltage_compliance(site_id: str):
    """Get voltage compliance detail with violation history.

    Checks all meter/inverter voltage readings against NRS 097-2-1 limits:
    normal range 207-253V, disconnect thresholds 195.5V/264.5V.
    Includes 24-hour violation count and current reading details.
    """
    svc = get_solar_compliance_service()
    result = await svc.check_voltage_compliance(site_id)
    return result.to_dict()


@router.get("/solar/sites/{site_id}/compliance/frequency")
async def get_frequency_compliance(site_id: str):
    """Get frequency compliance detail with violation history.

    Checks grid frequency against NRS 097-2-1 limits:
    normal range 49.0-51.0 Hz, disconnect thresholds 47.5/52.0 Hz.
    Includes 24-hour violation count and current reading details.
    """
    svc = get_solar_compliance_service()
    result = await svc.check_frequency_compliance(site_id)
    return result.to_dict()


@router.get("/solar/sites/{site_id}/compliance/power-quality")
async def get_power_quality_compliance(site_id: str):
    """Get power quality compliance: THD, power factor, DC injection.

    Monitors Total Harmonic Distortion (max 5%), DC injection (max 0.5%),
    and power factor (min 0.95) per NRS 097-2-1 requirements.
    """
    svc = get_solar_compliance_service()
    result = await svc.check_power_quality(site_id)
    return result.to_dict()


@router.get("/solar/sites/{site_id}/compliance/export")
async def get_export_compliance(site_id: str):
    """Get export limit compliance status.

    Verifies grid export against SSEG Category B limits. Checks zero-export
    enforcement (with tolerance) or export cap if configured. Returns current
    export power and limit details.
    """
    svc = get_solar_compliance_service()
    result = await svc.check_export_compliance(site_id)
    return result.to_dict()


@router.get("/solar/sites/{site_id}/compliance/certificates")
async def get_certificate_status(site_id: str):
    """Get NRS 097 certificate status for all equipment.

    Tracks certificate validity, edition currency (current edition is
    NRS 097-2-1:2024 Ed.3), and expiry dates. Flags outdated editions
    and approaching/passed expiry dates.
    """
    svc = get_solar_compliance_service()
    certificates = await svc.check_certificate_validity(site_id)
    return {
        "site_id": site_id,
        "certificate_count": len(certificates),
        "valid": sum(1 for c in certificates if c.status == "valid"),
        "warnings": sum(1 for c in certificates if c.status in ("expiry_warning", "edition_outdated")),
        "expired": sum(1 for c in certificates if c.status == "expired"),
        "certificates": [c.to_dict() for c in certificates],
    }


@router.get("/solar/sites/{site_id}/compliance/report")
async def get_compliance_report(
    site_id: str,
    period: str = Query("month", description="Reporting period: day, week, or month"),
):
    """Generate full compliance report for utility (SSEG) submission.

    Aggregates all compliance checks (voltage, frequency, power quality,
    export, certificates) and compliance events into a structured report
    suitable for submission to City Power Johannesburg.
    """
    svc = get_solar_compliance_service()
    report = await svc.generate_compliance_report(site_id, period=period)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"Solar site '{site_id}' not found"
        )
    return report.to_dict()


@router.get("/solar/sites/{site_id}/compliance/events")
async def get_compliance_events(
    site_id: str,
    from_ts: Optional[str] = Query(None, alias="from", description="Start timestamp (ISO 8601)"),
    to_ts: Optional[str] = Query(None, alias="to", description="End timestamp (ISO 8601)"),
):
    """Get compliance event log filtered by time range.

    Returns historical compliance events including voltage/frequency violations,
    reconnection events, certificate warnings, and export limit breaches.
    Events are sorted by timestamp (most recent first).
    """
    svc = get_solar_compliance_service()
    events = await svc.get_compliance_events(site_id, from_ts=from_ts, to_ts=to_ts)
    return {
        "site_id": site_id,
        "event_count": len(events),
        "events": [e.to_dict() for e in events],
    }


# === Energy arbitrage & dispatch endpoints (34-05) ===


@router.get("/solar/sites/{site_id}/dispatch/schedule")
async def get_dispatch_schedule(site_id: str):
    """Get today's 24-hour BESS dispatch schedule optimised for TOU arbitrage.

    Returns time slots with charge/discharge/idle/solar_priority actions,
    target SOC, tariff band, rate, and projected daily savings in ZAR.
    Load shedding adjustments are included when announced.
    """
    engine = get_solar_arbitrage_engine()
    schedule = engine.generate_dispatch_schedule(site_id)
    return schedule.to_dict()


@router.get("/solar/sites/{site_id}/dispatch/status")
async def get_dispatch_status(site_id: str):
    """Get current dispatch state: mode, action, BESS SOC, savings so far.

    Returns the autonomous dispatch service status including current action,
    BESS state of charge, tariff band, next scheduled action change,
    cumulative savings for today, and dispatch cycle count.
    """
    svc = get_solar_dispatch_service()
    status = svc.get_dispatch_status(site_id)
    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"No dispatch service running for site '{site_id}'",
        )
    return status.to_dict()


@router.get("/solar/sites/{site_id}/dispatch/log")
async def get_dispatch_log(
    site_id: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of history (1-168)"),
):
    """Get dispatch event history for a site.

    Returns timestamped dispatch events showing BESS actions, SOC changes,
    tariff bands, grid flows, and solar generation. Events are sorted
    most recent first. Default 24 hours, max 7 days.
    """
    svc = get_solar_dispatch_service()
    events = svc.get_dispatch_log(site_id, hours=hours)
    return {
        "site_id": site_id,
        "hours": hours,
        "event_count": len(events),
        "events": [e.to_dict() for e in events],
    }


@router.get("/solar/sites/{site_id}/arbitrage/savings")
async def get_arbitrage_savings(
    site_id: str,
    period: str = Query("day", description="Period: day, week, or month"),
):
    """Get energy arbitrage savings calculation.

    Compares actual cost with BESS (TOU optimisation) vs hypothetical cost
    without BESS (all energy at prevailing tariff). Returns savings in ZAR,
    percentage, and breakdown of peak kWh avoided and off-peak kWh charged.
    """
    engine = get_solar_arbitrage_engine()
    if period not in ("day", "week", "month"):
        raise HTTPException(
            status_code=400,
            detail="Period must be 'day', 'week', or 'month'",
        )
    savings = engine.calculate_daily_savings(site_id, period=period)
    return savings.to_dict()


@router.get("/solar/sites/{site_id}/tariff/current")
async def get_current_tariff(site_id: str):
    """Get the current City Power TOU tariff band and rate.

    Returns the active tariff band (peak/standard/off_peak), energy charge,
    network charge, total rate in ZAR/kWh, season (summer/winter),
    and the current period time window.
    """
    engine = get_solar_arbitrage_engine()
    band = engine.get_current_tariff_band()
    return {
        "site_id": site_id,
        "tariff": band.to_dict(),
        "utility": "City Power Johannesburg",
        "tariff_name": "TOU Commercial - Large Power User",
    }
