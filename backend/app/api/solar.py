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
  - Demand management: peak shaving, NMD tracking, load deferral
  - Self-consumption: ratio tracking, energy balance, export management
  - Generation forecasting: 72-hour ensemble forecast, clear-sky profile, accuracy
  - Generator coordination: priority dispatch, diesel avoidance, LS automation
  - Health analytics: degradation tracking, BESS SoH, warranty evidence (34-08)
  - Maintenance scheduling: condition-based recommendations, work orders, PPM (34-09)
  - Financial reporting: monthly savings, YTD summary, carbon offset (34-09)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.middleware.rate_limiter import limiter

from app.api.dependencies.module_access import require_active_module
from app.models.module_registry import ModuleType
from app.models.solar import BESSContainer
from app.services.solar_ingestion_service import get_solar_ingestion_service
from app.services.solar_performance_service import get_solar_performance_service
from app.services.solar_compliance_service import get_solar_compliance_service
from app.services.solar_arbitrage_engine import get_solar_arbitrage_engine
from app.services.solar_dispatch_service import get_solar_dispatch_service
from app.services.solar_demand_service import get_solar_demand_service
from app.services.solar_selfconsumption_service import get_solar_selfconsumption_service
from app.services.solar_forecast_service import get_solar_forecast_service
from app.services.solar_generator_coordinator import get_solar_generator_coordinator
from app.services.solar_health_service import get_solar_health_service
from app.services.solar_maintenance_service import get_solar_maintenance_service
from app.services.solar_financial_service import get_solar_financial_service
from app.services.solar_config_service import get_site_solar_config

router = APIRouter(
    dependencies=[
        Depends(
            require_active_module(
                ModuleType.SOLAR,
                site_keys=("site_id", "site"),
                default_site_id="site-002",
            )
        )
    ]
)


# === Ingestion endpoints (from 34-01) ===


@limiter.limit("30/minute")
@router.get("/solar/sites")
async def list_solar_sites(request: Request):
    """List all registered solar sites."""
    svc = get_solar_ingestion_service()
    return {"sites": svc.get_registered_sites()}


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/overview")
async def get_site_overview(request: Request, site_id: str):
    """Get high-level site overview: total generation, BESS SOC, grid import/export."""
    svc = get_solar_ingestion_service()
    overview = await svc.get_site_overview(site_id)
    if not overview:
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found")
    return overview


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/inverters")
async def get_inverters(request: Request, site_id: str):
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


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/inverters/{inverter_id}")
async def get_inverter_detail(request: Request, site_id: str, inverter_id: str):
    """Get single inverter detail with string-level data."""
    svc = get_solar_ingestion_service()
    detail = await svc.get_inverter_detail(site_id, inverter_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Inverter '{inverter_id}' not found at site '{site_id}'")
    return detail


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/bess")
async def get_bess_status(request: Request, site_id: str):
    """Get BESS container status: SOC, mode, power, health, alarms."""
    svc = get_solar_ingestion_service()
    bess = await svc.get_bess_status(site_id)

    # Fallback to mock data for demo mode when no device connected
    if not bess:
        # Try to load BESS config from site configs
        sites = svc.get_registered_sites()
        site_config = next((s for s in sites if s.get("site_id") == site_id), None)

        if site_config and site_config.get("config", {}).get("bess"):
            bess_cfg = site_config["config"]["bess"]
            bess = BESSContainer(
                container_id=bess_cfg.get("container_id", "S002-BESS-001"),
                site_id=site_id,
                name=bess_cfg.get("name", "BESS"),
                manufacturer=bess_cfg.get("manufacturer", "Huawei"),
                model=bess_cfg.get("model", "LUNA2000"),
                capacity_kwh=bess_cfg.get("capacity_kwh", 200),
                rated_power_kw=bess_cfg.get("rated_power_kw", 100),
                rack_count=bess_cfg.get("rack_count", 2),
                cell_chemistry=bess_cfg.get("cell_chemistry", "LFP"),
                protocol=bess_cfg.get("protocol", "modbus_tcp"),
                # Mock runtime state
                soc_pct=65.0,
                soh_pct=98.5,
                charge_power_kw=0.0,
                discharge_power_kw=45.2,
                mode="discharging",
                temp_c=28.5,
                cell_min_v=3.22,
                cell_max_v=3.38,
                cell_imbalance_mv=15.0,
                cycles_count=245,
                alarms=[],
                last_poll=None,
            )
        else:
            # Default mock BESS for site-002 (from solar_config_service)
            bess_cfg_fallback = get_site_solar_config(site_id).bess
            bess = BESSContainer(
                container_id="S002-BESS-B1-001",
                site_id=site_id,
                name="LUNA2000 BESS",
                manufacturer=bess_cfg_fallback.manufacturer,
                model=bess_cfg_fallback.model,
                capacity_kwh=bess_cfg_fallback.capacity_kwh,
                rated_power_kw=bess_cfg_fallback.rated_power_kw,
                rack_count=bess_cfg_fallback.rack_count,
                cell_chemistry="LFP",
                protocol="modbus_tcp",
                # Mock runtime state
                soc_pct=72.0,
                soh_pct=97.8,
                charge_power_kw=0.0,
                discharge_power_kw=38.5,
                mode="discharging",
                temp_c=26.8,
                cell_min_v=3.24,
                cell_max_v=3.41,
                cell_imbalance_mv=12.0,
                cycles_count=189,
                alarms=[],
                last_poll=None,
            )

    return bess.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/meter")
async def get_meter_readings(request: Request, site_id: str):
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


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/connectors")
async def get_connector_status(request: Request, site_id: str):
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
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found or no generation data")
    return metrics.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/performance/inverters")
async def get_inverter_peer_comparison(request: Request, site_id: str):
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
            raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found")
    return {
        "site_id": site_id,
        "inverter_count": len(comparisons),
        "underperforming": sum(1 for c in comparisons if c.status != "normal"),
        "inverters": [c.to_dict() for c in comparisons],
    }


@router.get("/solar/sites/{site_id}/performance/strings")
async def get_string_anomalies(
    site_id: str,
    inverter_id: Optional[str] = Query(None, description="Filter to specific inverter"),
):
    """Get string-level detail with anomaly flags.

    Compares strings on same MPPT tracker using statistical thresholds.
    Detects: string_underperform (soiling/shade), string_open_circuit
    (disconnection), string_short (bypass diode), mppt_fault (tracker hardware).
    """
    perf = get_solar_performance_service()
    anomalies = await perf.detect_string_anomalies(site_id, inverter_id=inverter_id)

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


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/diagnostics")
async def get_diagnostics(request: Request, site_id: str):
    """Get full diagnostic report with prioritised issues.

    Aggregates: PR metrics, underperforming inverters, string anomalies,
    BESS health flags. Returns prioritised list of issues with severity,
    probable cause, recommended action, confidence score, and cost impact.
    """
    perf = get_solar_performance_service()
    report = await perf.get_diagnostic_summary(site_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found or no data available")
    return report.to_dict()


# === Grid compliance endpoints (34-03) ===


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/compliance")
async def get_compliance_status(request: Request, site_id: str):
    """Get overall grid compliance status (traffic-light) with breakdown per standard.

    Returns NRS 097-2-1 compliance summary covering voltage, frequency,
    power quality, export limits, and certificate validity. Status is
    compliant (green), warning (yellow), or violation (red).
    """
    svc = get_solar_compliance_service()
    result = await svc.get_overall_compliance(site_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found")
    return result


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/compliance/voltage")
async def get_voltage_compliance(request: Request, site_id: str):
    """Get voltage compliance detail with violation history.

    Checks all meter/inverter voltage readings against NRS 097-2-1 limits:
    normal range 207-253V, disconnect thresholds 195.5V/264.5V.
    Includes 24-hour violation count and current reading details.
    """
    svc = get_solar_compliance_service()
    result = await svc.check_voltage_compliance(site_id)
    return result.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/compliance/frequency")
async def get_frequency_compliance(request: Request, site_id: str):
    """Get frequency compliance detail with violation history.

    Checks grid frequency against NRS 097-2-1 limits:
    normal range 49.0-51.0 Hz, disconnect thresholds 47.5/52.0 Hz.
    Includes 24-hour violation count and current reading details.
    """
    svc = get_solar_compliance_service()
    result = await svc.check_frequency_compliance(site_id)
    return result.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/compliance/power-quality")
async def get_power_quality_compliance(request: Request, site_id: str):
    """Get power quality compliance: THD, power factor, DC injection.

    Monitors Total Harmonic Distortion (max 5%), DC injection (max 0.5%),
    and power factor (min 0.95) per NRS 097-2-1 requirements.
    """
    svc = get_solar_compliance_service()
    result = await svc.check_power_quality(site_id)
    return result.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/compliance/export")
async def get_export_compliance(request: Request, site_id: str):
    """Get export limit compliance status.

    Verifies grid export against SSEG Category B limits. Checks zero-export
    enforcement (with tolerance) or export cap if configured. Returns current
    export power and limit details.
    """
    svc = get_solar_compliance_service()
    result = await svc.check_export_compliance(site_id)
    return result.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/compliance/certificates")
async def get_certificate_status(request: Request, site_id: str):
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
        raise HTTPException(status_code=404, detail=f"Solar site '{site_id}' not found")
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


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/dispatch/schedule")
async def get_dispatch_schedule(request: Request, site_id: str):
    """Get today's 24-hour BESS dispatch schedule optimised for TOU arbitrage.

    Returns time slots with charge/discharge/idle/solar_priority actions,
    target SOC, tariff band, rate, and projected daily savings in ZAR.
    Load shedding adjustments are included when announced.
    """
    engine = get_solar_arbitrage_engine()
    schedule = engine.generate_dispatch_schedule(site_id)
    return schedule.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/dispatch/status")
async def get_dispatch_status(request: Request, site_id: str):
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


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/tariff/current")
async def get_current_tariff(request: Request, site_id: str):
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


# === Demand management endpoints (34-06) ===


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/demand/status")
async def get_demand_status(request: Request, site_id: str):
    """Get current demand status with NMD headroom and peak shaving state.

    Returns current building demand, monthly peak, NMD limit, headroom,
    demand trend, alert level, and whether BESS peak shaving is active.
    """
    svc = get_solar_demand_service()
    status = svc.get_current_demand(site_id)
    return status.to_dict()


@router.get("/solar/sites/{site_id}/demand/profile")
async def get_demand_profile(
    site_id: str,
    period: str = Query("day", description="Period: day or week"),
):
    """Get 15-minute demand profile with BESS peak shaving overlay.

    Returns demand intervals showing building load, solar offset, BESS
    offset, and net demand. Includes peak demand time, average demand,
    and peak reduction from BESS shaving.
    """
    svc = get_solar_demand_service()
    profile = svc.get_demand_profile(site_id, period=period)
    return profile.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/demand/nmd")
async def get_nmd_status(request: Request, site_id: str):
    """Get NMD compliance status with ratchet history and alert level.

    Returns NMD limit, current utilisation, alert level (normal/warning/critical),
    ratchet risk flag, 12-month peak history, and estimated annual penalty.
    City Power demand charge: R155.50/kVA/month.
    """
    svc = get_solar_demand_service()
    nmd = svc.check_nmd_status(site_id)
    return nmd.to_dict()


@router.get("/solar/sites/{site_id}/demand/savings")
async def get_demand_savings(
    site_id: str,
    period: str = Query("month", description="Period: month"),
):
    """Get demand charge savings from BESS peak shaving.

    Compares unmanaged peak (without BESS) vs managed peak (with BESS
    shaving). Calculates savings at City Power demand charge rate of
    R155.50/kVA/month. Shows peak reduction in kW and savings in ZAR.
    """
    svc = get_solar_demand_service()
    savings = svc.calculate_demand_savings(site_id, period=period)
    return savings.to_dict()


# === Self-consumption endpoints (34-06) ===


@router.get("/solar/sites/{site_id}/selfconsumption")
async def get_selfconsumption(
    site_id: str,
    period: str = Query("day", description="Period: day, week, or month"),
):
    """Get self-consumption and self-sufficiency ratios for a period.

    Self-consumption ratio: % of solar generation used on-site (target >95%).
    Self-sufficiency ratio: % of building consumption met by solar + BESS.
    Returns full breakdown of solar flows (self-consumed, to BESS, exported)
    and grid/BESS contribution.
    """
    svc = get_solar_selfconsumption_service()
    if period not in ("day", "week", "month"):
        raise HTTPException(
            status_code=400,
            detail="Period must be 'day', 'week', or 'month'",
        )
    metrics = svc.get_selfconsumption_ratio(site_id, period=period)
    return metrics.to_dict()


@router.get("/solar/sites/{site_id}/energy-balance")
async def get_energy_balance(
    site_id: str,
    period: str = Query("day", description="Period: day, week, or month"),
):
    """Get complete energy balance breakdown for a period.

    Shows all energy flows: solar generated, solar self-consumed, solar to
    BESS, solar exported, grid imported, BESS discharged, building consumed.
    Includes 15-minute interval detail for daily view and balance sanity check
    (supply = demand).
    """
    svc = get_solar_selfconsumption_service()
    if period not in ("day", "week", "month"):
        raise HTTPException(
            status_code=400,
            detail="Period must be 'day', 'week', or 'month'",
        )
    balance = svc.get_energy_balance(site_id, period=period)
    return balance.to_dict()


# === Generation forecast endpoints (34-07) ===


@router.get("/solar/sites/{site_id}/forecast")
async def get_generation_forecast(
    site_id: str,
    hours: int = Query(72, ge=1, le=168, description="Forecast horizon in hours (1-168)"),
):
    """Get 72-hour generation forecast with confidence bands.

    Returns hourly generation predictions using a weighted ensemble model
    (30% persistence, 30% clear-sky, 40% historical average). Confidence
    bands widen from 5% to 35% over the forecast horizon. Includes daily
    totals, clear-sky comparison, and 7-day accuracy metrics (RMSE, MAE, bias).
    """
    svc = get_solar_forecast_service()
    forecast = svc.get_forecast(site_id, hours_ahead=hours)
    if not forecast.hourly:
        raise HTTPException(
            status_code=404,
            detail=f"Solar site '{site_id}' not found or no forecast data",
        )
    return forecast.to_dict()


@router.get("/solar/sites/{site_id}/forecast/accuracy")
async def get_forecast_accuracy(
    site_id: str,
    days: int = Query(7, ge=1, le=30, description="Accuracy period in days (1-30)"),
):
    """Get forecast vs actual accuracy metrics.

    Returns RMSE (root mean square error), MAE (mean absolute error),
    and bias percentage comparing forecast predictions against metered
    generation. RMSE is also expressed as percentage of peak capacity.
    Target: RMSE < 15% of peak for statistical models.
    """
    svc = get_solar_forecast_service()
    accuracy = svc.get_forecast_accuracy(site_id, days=days)
    return accuracy.to_dict()


# === Generator coordination endpoints (34-07) ===


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/generator/status")
async def get_generator_status(request: Request, site_id: str):
    """Get current dispatch priority stack and generator need assessment.

    Returns the active energy source (Solar > BESS > Grid > Generator),
    status of each tier in the priority stack, and whether the generator
    should be started based on current BESS SOC, load shedding state,
    and solar availability. Generator is the absolute last resort.
    """
    coord = get_solar_generator_coordinator()
    priority = coord.get_dispatch_priority(site_id)
    assessment = coord.evaluate_generator_need(site_id)
    return {
        "site_id": site_id,
        "priority": priority.to_dict(),
        "generator_assessment": assessment.to_dict(),
    }


@router.get("/solar/sites/{site_id}/generator/avoidance")
async def get_diesel_avoidance(
    site_id: str,
    period: str = Query("month", description="Period: day, week, or month"),
):
    """Get diesel avoidance savings from Solar+BESS.

    Calculates generator hours avoided, diesel litres saved, and ZAR
    saved by using Solar+BESS instead of generators during load shedding.
    Generator consumption: ~30 L/hour at 70% load, diesel at R22/litre.
    Shows load shedding event count, generator starts, and avoided starts.
    """
    coord = get_solar_generator_coordinator()
    if period not in ("day", "week", "month"):
        raise HTTPException(
            status_code=400,
            detail="Period must be 'day', 'week', or 'month'",
        )
    avoidance = coord.calculate_diesel_avoidance(site_id, period=period)
    return avoidance.to_dict()


@router.get("/solar/sites/{site_id}/generator/events")
async def get_generator_events(
    site_id: str,
    period: str = Query("month", description="Period: day, week, or month"),
):
    """Get generator event log for a period.

    Returns timestamped generator events including starts, stops, avoided
    starts (BESS sustained load), and LS override events. Each event
    includes BESS SOC, solar generation, building load, and fuel usage.
    Events sorted most recent first.
    """
    coord = get_solar_generator_coordinator()
    if period not in ("day", "week", "month"):
        raise HTTPException(
            status_code=400,
            detail="Period must be 'day', 'week', or 'month'",
        )
    events = coord.get_generator_events(site_id, period=period)
    return {
        "site_id": site_id,
        "period": period,
        "event_count": len(events),
        "events": [e.to_dict() for e in events],
    }


# === Health analytics endpoints (34-08) ===


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/health")
async def get_fleet_health(request: Request, site_id: str):
    """Get fleet health overview: degradation summary, BESS SoH, alerts.

    Returns average fleet degradation rate, worst inverter with degradation
    details, BESS State-of-Health summary (SoH, cycles, cell imbalance),
    estimated replacement year, and prioritised health issues.
    """
    svc = get_solar_health_service()
    health = await svc.get_fleet_health(site_id)
    if not health:
        raise HTTPException(
            status_code=404,
            detail=f"Solar site '{site_id}' not found",
        )
    return health


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/health/inverters/{inverter_id}")
async def get_inverter_health(request: Request, site_id: str, inverter_id: str):
    """Get single inverter health detail with degradation rate.

    Returns commissioning date, years in service, baseline vs current PR,
    annual degradation rate with rating (normal/elevated/accelerated),
    end-of-life prediction, monthly health timeline, and cost impact.
    """
    svc = get_solar_health_service()

    # Get degradation for this specific inverter
    degradation = await svc.calculate_degradation_rate(site_id, inverter_id=inverter_id)
    if not degradation or not degradation.inverters:
        raise HTTPException(
            status_code=404,
            detail=f"Inverter '{inverter_id}' not found at site '{site_id}'",
        )

    inv = degradation.inverters[0]

    # Get timeline and EOL prediction
    timeline = await svc.get_health_timeline(site_id, inverter_id, months=12)
    eol = await svc.predict_end_of_life(site_id, inverter_id)

    result = inv.to_dict()
    if timeline:
        result["health_timeline"] = timeline.to_dict()
    if eol:
        result["eol_prediction"] = eol.to_dict()

    return result


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/health/bess")
async def get_bess_health(request: Request, site_id: str):
    """Get BESS State-of-Health with rack-level detail.

    Returns SoH percentage, cycle count vs warranty limit, cell imbalance
    per rack, temperature distribution, calendar aging, estimated
    replacement year, and health alerts.
    """
    svc = get_solar_health_service()
    health = await svc.get_bess_health(site_id)
    if not health:
        raise HTTPException(
            status_code=404,
            detail=f"No BESS found at site '{site_id}'",
        )
    return health.to_dict()


@router.get("/solar/sites/{site_id}/health/bess/cycles")
async def get_bess_cycle_history(
    site_id: str,
    months: int = Query(12, ge=1, le=24, description="Months of history (1-24)"),
):
    """Get monthly BESS cycle history.

    Returns monthly cycle count, average depth of discharge, equivalent
    full cycles (cycle_count x avg_DoD), and average temperature.
    Shows seasonal patterns: summer months have fewer grid cycles
    (more solar), winter months have more.
    """
    svc = get_solar_health_service()
    history = await svc.get_bess_cycle_history(site_id, months=months)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"No BESS found at site '{site_id}'",
        )
    return {
        "site_id": site_id,
        "months": months,
        "cycle_history": [c.to_dict() for c in history],
    }


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/health/degradation")
async def get_degradation_ranking(request: Request, site_id: str):
    """Get fleet-wide degradation ranking for all inverters.

    Returns all inverters sorted by degradation rate (worst first)
    with commissioning date, baseline vs current PR, annual decline
    rate, degradation rating, end-of-life prediction, and cost impact.
    """
    svc = get_solar_health_service()
    degradation = await svc.calculate_degradation_rate(site_id)
    if not degradation:
        raise HTTPException(
            status_code=404,
            detail=f"Solar site '{site_id}' not found",
        )
    return degradation.to_dict()


@router.post("/solar/sites/{site_id}/health/warranty-evidence/{equipment_id}")
async def generate_warranty_evidence(site_id: str, equipment_id: str):
    """Generate warranty evidence package for an inverter or BESS.

    Collects operational data summary, degradation trend, environmental
    conditions, fault log, and performance vs specification into a
    structured report suitable for manufacturer warranty claim submission.

    Equipment ID must contain 'INV' for inverters or 'BESS' for battery.
    """
    svc = get_solar_health_service()
    package = await svc.generate_warranty_evidence(site_id, equipment_id)
    if not package:
        raise HTTPException(
            status_code=404,
            detail=f"Equipment '{equipment_id}' not found at site '{site_id}'",
        )
    return package.to_dict()


# === Maintenance scheduling endpoints (34-09) ===


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/maintenance/schedule")
async def get_maintenance_schedule(request: Request, site_id: str):
    """Get 90-day maintenance calendar (PPM + condition-based).

    Returns scheduled preventive maintenance (panel cleaning, inspections,
    thermal imaging) and condition-based entries from equipment health
    evaluation. Each entry includes date, type, priority, duration,
    and estimated cost.
    """
    svc = get_solar_maintenance_service()
    calendar = await svc.get_maintenance_schedule(site_id)
    return calendar.to_dict()


@limiter.limit("30/minute")
@router.get("/solar/sites/{site_id}/maintenance/recommendations")
async def get_maintenance_recommendations(request: Request, site_id: str):
    """Get current maintenance recommendations from condition evaluation.

    Evaluates: panel soiling, inverter service needs (runtime, faults,
    thermal events), BESS maintenance (cycle milestones, cell imbalance),
    and string repairs (persistent underperformance). Returns prioritised
    recommendations with estimated cost and due date.
    """
    svc = get_solar_maintenance_service()
    recs = await svc.evaluate_maintenance_needs(site_id)
    return {
        "site_id": site_id,
        "recommendation_count": len(recs),
        "urgent": sum(1 for r in recs if r.priority.value == "urgent"),
        "soon": sum(1 for r in recs if r.priority.value == "soon"),
        "routine": sum(1 for r in recs if r.priority.value == "routine"),
        "recommendations": [r.to_dict() for r in recs],
    }


@router.post("/solar/sites/{site_id}/maintenance/generate-work-orders")
async def generate_maintenance_work_orders(site_id: str):
    """Create work orders from urgent/soon maintenance recommendations.

    Converts condition-based recommendations with priority 'urgent' or
    'soon' into work orders. Auto-assigns to electrical (solar) team
    following existing work order patterns (Sentry notification ready).
    """
    svc = get_solar_maintenance_service()
    work_orders = await svc.generate_work_orders(site_id)
    return {
        "site_id": site_id,
        "work_orders_created": len(work_orders),
        "work_orders": [wo.to_dict() for wo in work_orders],
    }


# === Financial reporting endpoints (34-09) ===


@router.get("/solar/sites/{site_id}/financial/monthly")
async def get_monthly_financial_report(
    site_id: str,
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    year: int = Query(..., ge=2024, le=2030, description="Year"),
):
    """Get monthly financial report with savings breakdown.

    Returns SENTINEL optimisation value: arbitrage savings (TOU),
    demand charge savings (peak shaving), self-consumption value
    (avoided export), diesel avoidance (generator hours saved).
    Includes counterfactual comparison (cost with vs without SENTINEL).
    """
    svc = get_solar_financial_service()
    report = svc.generate_monthly_report(site_id, month, year)
    return report.to_dict()


@router.get("/solar/sites/{site_id}/financial/summary")
async def get_financial_summary(
    site_id: str,
    period: str = Query("ytd", description="Period: ytd (year-to-date)"),
):
    """Get YTD financial summary with ROI calculation.

    Returns cumulative savings, monthly breakdown, average monthly
    savings, SENTINEL licence fee, ROI percentage, and payback period.
    """
    svc = get_solar_financial_service()
    summary = svc.get_financial_summary(site_id, period=period)
    return summary.to_dict()


@router.get("/solar/sites/{site_id}/financial/carbon")
async def get_carbon_offset(
    site_id: str,
    period: str = Query("month", description="Period: month or ytd"),
):
    """Get carbon offset report.

    Calculates CO2 avoided from solar generation (Eskom emission factor
    0.95 kg/kWh) and diesel avoidance (2.68 kg/L). Returns total CO2
    in kg and tonnes, with tree-equivalent for context.
    """
    svc = get_solar_financial_service()
    if period not in ("month", "ytd"):
        raise HTTPException(
            status_code=400,
            detail="Period must be 'month' or 'ytd'",
        )
    carbon = svc.get_carbon_offset(site_id, period=period)
    return carbon.to_dict()
