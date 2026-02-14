"""Solar Performance Monitoring & Diagnostics API.

Endpoints for:
  - Inverter performance baseline and peer comparison
  - String-level MPPT tracking and anomaly detection
  - Soiling and degradation analysis
  - Performance alerts and recommendations
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.middleware.rate_limiter import limiter

from app.api.dependencies.module_access import require_active_module
from app.models.module_registry import ModuleType
from app.models.solar import SolarInverter, SolarString
from app.services.solar_ingestion_service import get_solar_ingestion_service
from app.services.solar_performance_analyzer import get_solar_performance_analyzer
from app.ml.solar_anomaly_detector import get_string_analyzer

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


# === Performance Summary ===


@limiter.limit("30/minute")
@router.get("/solar/performance/{system_id}/summary")
async def get_performance_summary(request: Request, system_id: str):
    """
    Get performance summary for a solar system/plant.

    Includes: Efficiency, capacity factor, availability, peer comparison status.

    Args:
        system_id: Plant or site identifier

    Returns:
        Performance summary with key metrics and status
    """
    analyzer = get_solar_performance_analyzer()
    ingestion = get_solar_ingestion_service()

    # Parse system_id (could be site_id or plant_id)
    # For now, treat as site_id
    site_id = system_id

    # Get inverters for this site
    inverters = await ingestion.get_inverters(site_id)
    if not inverters:
        raise HTTPException(
            status_code=404,
            detail=f"No inverters found for system '{system_id}'",
        )

    # Calculate aggregate efficiency
    total_ac_power = sum(inv.ac_power_kw for inv in inverters)
    total_dc_power = sum(inv.dc_power_kw for inv in inverters)

    # Estimate total installed capacity from first inverter
    total_capacity_kwp = len(inverters) * (inverters[0].rated_power_kva * 0.85)

    # Average efficiency across fleet
    avg_efficiency = 0.90
    if total_ac_power > 0 and total_dc_power > 0:
        avg_efficiency = total_ac_power / total_dc_power

    # Availability (simplified: count online inverters)
    online_count = sum(1 for inv in inverters if inv.status == "online")
    availability = online_count / len(inverters) if inverters else 0.0

    # Get recent baseline
    baseline = analyzer.get_peer_baseline(
        f"{inverters[0].manufacturer} {inverters[0].model}",
        inverters[0].rated_power_kva,
    )

    return {
        "system_id": system_id,
        "summary": {
            "efficiency": round(avg_efficiency, 4),
            "capacity_factor": round(analyzer.calculate_capacity_factor(total_ac_power, total_capacity_kwp), 4),
            "availability": round(availability, 4),
            "status": "good" if avg_efficiency > 0.85 and availability > 0.95 else "attention",
        },
        "fleet": {
            "inverter_count": len(inverters),
            "online_count": online_count,
            "total_ac_power_kw": round(total_ac_power, 2),
            "total_dc_power_kw": round(total_dc_power, 2),
            "installed_capacity_kwp": round(total_capacity_kwp, 1),
        },
        "baseline": baseline.to_dict(),
    }


# === Peer Comparison ===


@limiter.limit("30/minute")
@router.get("/solar/performance/{inverter_id}/vs-peers")
async def get_peer_comparison(request: Request, inverter_id: str):
    """
    Get detailed peer comparison for an inverter.

    Shows percentiles (p10, p25, p50, p75, p90) for same model fleet.

    Args:
        inverter_id: Inverter identifier

    Returns:
        Peer comparison report with deviation analysis
    """
    analyzer = get_solar_performance_analyzer()
    ingestion = get_solar_ingestion_service()

    # Lookup inverter (need to search across all sites)
    target_inverter = None
    all_inverters = []

    # Get all registered sites
    sites = ingestion.get_registered_sites()
    for site in sites:
        site_inverters = await ingestion.get_inverters(site["site_id"])
        all_inverters.extend(site_inverters)
        target_inv = next(
            (inv for inv in site_inverters if inv.inverter_id == inverter_id),
            None,
        )
        if target_inv:
            target_inverter = target_inv

    if not target_inverter:
        raise HTTPException(
            status_code=404,
            detail=f"Inverter '{inverter_id}' not found",
        )

    # Get peer inverters (same manufacturer + model)
    peers = [
        inv for inv in all_inverters
        if inv.manufacturer == target_inverter.manufacturer
        and inv.model == target_inverter.model
        and inv.inverter_id != inverter_id
    ]

    if not peers:
        peers = [target_inverter]  # Include self if no other peers

    # Calculate current efficiency for target inverter
    current_efficiency = (
        target_inverter.ac_power_kw / target_inverter.dc_power_kw
        if target_inverter.dc_power_kw > 0
        else 0.90
    )

    # Get comparison report
    report = analyzer.compare_to_peers(
        target_inverter,
        peers,
        current_efficiency=current_efficiency,
        current_availability=0.99,
        current_temp_rise_c=target_inverter.temp_c - 25.0,
    )

    return report.to_dict()


# === String Health ===


@limiter.limit("30/minute")
@router.get("/solar/performance/{system_id}/strings")
async def get_string_health(request: Request, system_id: str):
    """
    Get string-level health scores for a system.

    Returns health score (0-100), failure type, and recommendations for each string.

    Args:
        system_id: Plant or site identifier

    Returns:
        List of string health reports
    """
    string_analyzer = get_string_analyzer()
    ingestion = get_solar_ingestion_service()

    # Get inverters for this site
    inverters = await ingestion.get_inverters(system_id)
    if not inverters:
        raise HTTPException(
            status_code=404,
            detail=f"No inverters found for system '{system_id}'",
        )

    # Analyze each string
    string_health_reports = []

    for inverter in inverters:
        # Get strings for this inverter
        inverter_detail = await ingestion.get_inverter_detail(system_id, inverter.inverter_id)
        if not inverter_detail or "strings" not in inverter_detail:
            continue

        for string_data in inverter_detail.get("strings", []):
            # Convert to SolarString object if needed
            if isinstance(string_data, dict):
                string = SolarString(
                    string_id=string_data.get("string_id", f"S{len(string_health_reports)}"),
                    inverter_id=inverter.inverter_id,
                    mppt_tracker=string_data.get("mppt_tracker", 0),
                    panel_count=string_data.get("panel_count", 20),
                    dc_voltage_v=string_data.get("dc_voltage_v", 45.0),
                    dc_current_a=string_data.get("dc_current_a", 5.0),
                    dc_power_kw=string_data.get("dc_power_kw", 0.2),
                    irradiance_w_m2=string_data.get("irradiance_w_m2", 500.0),
                )
            else:
                string = string_data

            # Analyze string health
            health_score = string_analyzer.analyze_string_health(string)
            string_health_reports.append(health_score.to_dict())

    # Sort by health score (worst first)
    string_health_reports.sort(key=lambda x: x["health"]["score"], reverse=True)

    return {
        "system_id": system_id,
        "string_count": len(string_health_reports),
        "strings": string_health_reports,
        "summary": {
            "healthy_count": sum(1 for s in string_health_reports if s["health"]["status"] == "healthy"),
            "warning_count": sum(1 for s in string_health_reports if s["health"]["status"] == "warning"),
            "critical_count": sum(1 for s in string_health_reports if s["health"]["status"] == "critical"),
        },
    }


# === Soiling Analysis ===


@limiter.limit("30/minute")
@router.get("/solar/performance/{system_id}/soiling")
async def get_soiling_analysis(request: Request, system_id: str):
    """
    Get soiling and cleaning recommendations.

    Returns: Soiling loss %, cleaning recommendation, estimated recovery.

    Args:
        system_id: Plant or site identifier

    Returns:
        Soiling analysis with recommendations
    """
    analyzer = get_solar_performance_analyzer()
    ingestion = get_solar_ingestion_service()

    # Get site overview for generation data
    overview = await ingestion.get_site_overview(system_id)
    if not overview:
        raise HTTPException(
            status_code=404,
            detail=f"Solar site '{system_id}' not found",
        )

    # Extract generation data
    actual_generation_kwh = overview.get("current_generation_kw", 100.0)  # Simplified
    installed_capacity_kwp = overview.get("installed_capacity_kwp", 500.0)

    # Analyze soiling
    soiling_analysis = analyzer.analyze_soiling(
        site_id=system_id,
        plant_id=system_id,
        actual_generation_kwh=actual_generation_kwh,
        installed_capacity_kwp=installed_capacity_kwp,
        temperature_c=25.0,
    )

    return soiling_analysis.to_dict()


# === Degradation Analysis ===


@limiter.limit("30/minute")
@router.get("/solar/performance/{system_id}/degradation")
async def get_degradation_analysis(request: Request, system_id: str):
    """
    Get annual degradation rate and warranty evidence.

    Returns: Degradation trend, warranty eligibility, recommendations.

    Args:
        system_id: Plant or site identifier

    Returns:
        Degradation analysis
    """
    analyzer = get_solar_performance_analyzer()

    # Estimate current PR (would use historical data in production)
    current_pr = 0.80
    last_year_pr = 0.805  # Assumed previous year

    degradation_analysis = analyzer.track_annual_degradation(
        site_id=system_id,
        current_pr=current_pr,
        last_year_pr=last_year_pr,
    )

    return degradation_analysis


# === Site Anomalies ===


@limiter.limit("30/minute")
@router.get("/solar/anomalies/{site_id}")
async def get_site_anomalies(request: Request, site_id: str):
    """
    Get all active anomalies across a site.

    Returns: Prioritized list of issues with cost impact and recommendations.

    Args:
        site_id: Site identifier

    Returns:
        List of active anomalies
    """
    string_analyzer = get_string_analyzer()
    ingestion = get_solar_ingestion_service()

    # Get all inverters for site
    inverters = await ingestion.get_inverters(site_id)
    if not inverters:
        raise HTTPException(
            status_code=404,
            detail=f"No inverters found for site '{site_id}'",
        )

    # Collect all anomalies
    anomalies = []

    for inverter in inverters:
        inverter_detail = await ingestion.get_inverter_detail(site_id, inverter.inverter_id)
        if not inverter_detail or "strings" not in inverter_detail:
            continue

        for string_data in inverter_detail.get("strings", []):
            if isinstance(string_data, dict):
                string = SolarString(
                    string_id=string_data.get("string_id", f"S{len(anomalies)}"),
                    inverter_id=inverter.inverter_id,
                    mppt_tracker=string_data.get("mppt_tracker", 0),
                    panel_count=string_data.get("panel_count", 20),
                    dc_voltage_v=string_data.get("dc_voltage_v", 45.0),
                    dc_current_a=string_data.get("dc_current_a", 5.0),
                    dc_power_kw=string_data.get("dc_power_kw", 0.2),
                    irradiance_w_m2=string_data.get("irradiance_w_m2", 500.0),
                )
            else:
                string = string_data

            # Analyze string
            health = string_analyzer.analyze_string_health(string)

            # Only include non-healthy strings
            if health.health_status != "healthy":
                anomalies.append(
                    {
                        "string_id": health.string_id,
                        "health_score": round(health.health_score, 1),
                        "status": health.health_status,
                        "failure_type": health.failure_type,
                        "confidence": round(health.failure_confidence, 3),
                        "estimated_loss_kw": round(health.power_kw, 3),
                        "recommendation": health.recommendation,
                    }
                )

    # Add persistent anomalies
    persistent = string_analyzer.get_persistent_anomalies()
    for string_id, anomaly_data in persistent.items():
        if not any(a["string_id"] == string_id for a in anomalies):
            anomalies.append(
                {
                    "string_id": string_id,
                    "health_score": anomaly_data["health_score"],
                    "status": "critical",
                    "failure_type": anomaly_data["failure_type"],
                    "persistence_hours": round(anomaly_data["persistent_hours"], 1),
                    "recommendation": anomaly_data["recommendation"],
                }
            )

    # Sort by health score (worst first)
    anomalies.sort(key=lambda x: x.get("health_score", 0), reverse=True)

    return {
        "site_id": site_id,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "summary": {
            "critical_count": sum(1 for a in anomalies if a["status"] == "critical"),
            "warning_count": sum(1 for a in anomalies if a["status"] == "warning"),
        },
    }


# === Baseline Management ===


@limiter.limit("10/minute")
@router.post("/solar/performance/{inverter_id}/baseline")
async def reset_baseline(
    request: Request,
    inverter_id: str,
    baseline_efficiency: float = Query(0.90, ge=0.0, le=1.0),
    baseline_availability: float = Query(0.99, ge=0.0, le=1.0),
):
    """
    Manually reset baseline for an inverter (testing/maintenance).

    Args:
        inverter_id: Inverter identifier
        baseline_efficiency: New efficiency baseline (0-1)
        baseline_availability: New availability baseline (0-1)

    Returns:
        Updated baseline
    """
    analyzer = get_solar_performance_analyzer()

    # This is a simplified version for testing
    # In production, would need to lookup inverter type
    baseline = analyzer.track_baseline_changes(
        inverter_id=inverter_id,
        inverter_type="test-inverter",
        capacity_kva=100.0,
        new_efficiency=baseline_efficiency,
        new_availability=baseline_availability,
    )

    return {
        "inverter_id": inverter_id,
        "baseline": baseline.to_dict(),
        "message": "Baseline reset successfully",
    }
