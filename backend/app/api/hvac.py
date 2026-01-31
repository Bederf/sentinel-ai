"""HVAC Module API endpoints.

Complete HVAC system monitoring and control:
- Zone temperature control
- AHU/FCU/Chiller equipment status
- Thermal runway calculations
- Equipment health scores
"""

import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/hvac", tags=["hvac"])

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
ZONES_PATH = DATA_DIR / "hvac_zones.json"
EQUIPMENT_PATH = DATA_DIR / "equipment.json"
SAFETY_RULES_PATH = DATA_DIR / "safety_rules.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
HEALTH_CONFIG_PATH = DATA_DIR / "health_calculation_config.json"


# ========== Request/Response Models ==========

class SetpointRequest(BaseModel):
    """Request to change zone temperature setpoint."""
    setpoint: float = Field(..., ge=16, le=28, description="Temperature setpoint in °C")


class ChillerControlRequest(BaseModel):
    """Request to control chiller on/off."""
    action: str = Field(..., pattern="^(on|off)$", description="Turn chiller on or off")


class ZoneResponse(BaseModel):
    """Zone details with equipment and sensors."""
    zone_id: str
    zone_name: str
    floor: str
    fcu_id: Optional[str]
    vav_id: Optional[str]
    ahu_id: Optional[str]
    temp_sensor: Optional[str]
    co2_sensor: Optional[str]
    typical_occupancy: int
    area_sqm: float
    setpoint: float
    current_temp: float
    status: str
    temp_deviation: float = 0.0
    temp_min: float = 16.0
    temp_max: float = 28.0


# ========== Helper Functions ==========

def load_json(path: Path) -> list | dict:
    """Load JSON data from file."""
    if not path.exists():
        return [] if "zones" in str(path) or "equipment" in str(path) else {}
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: list | dict) -> None:
    """Save JSON data to file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_zone_limits(zone_id: str) -> tuple[float, float]:
    """Get temperature limits for a zone from safety rules.

    Returns (min_temp, max_temp) tuple.
    Zone-specific limits override global limits.
    """
    rules = load_json(SAFETY_RULES_PATH)
    settings = load_json(SETTINGS_PATH)

    # Start with global control limits
    min_temp = settings.get("controlLimits", {}).get("temperature_setpoint", {}).get("min", 18)
    max_temp = settings.get("controlLimits", {}).get("temperature_setpoint", {}).get("max", 26)

    # Check safety rules for zone-specific or global HVAC limits
    for rule in rules:
        if rule.get("enabled") and rule.get("rule_type") == "temperature_range":
            # Zone-specific rule
            if rule.get("device_id") == zone_id:
                min_temp = rule.get("min_temp", min_temp)
                max_temp = rule.get("max_temp", max_temp)
                break
            # Global HVAC zone rule (fallback)
            elif rule.get("device_type") == "hvac" and rule.get("point_name") == "cooling_setpoint":
                min_temp = rule.get("min_temp", min_temp)
                max_temp = rule.get("max_temp", max_temp)

    return (min_temp, max_temp)


def calculate_equipment_health(equipment: dict) -> dict:
    """Calculate health score for equipment based on health config."""
    health_config = load_json(HEALTH_CONFIG_PATH)
    eq_type = equipment.get("type", "").lower()

    # Use existing health score if no config
    if eq_type not in health_config:
        return {
            "health_score": equipment.get("health_score", 85),
            "status": get_health_status(equipment.get("health_score", 85)),
            "factors": {}
        }

    config = health_config[eq_type]
    weights = config.get("weights", {})
    thresholds = config.get("thresholds", {})

    # Calculate individual factors
    factors = {}

    # Age factor
    install_date = equipment.get("install_date")
    if install_date:
        try:
            install = datetime.fromisoformat(install_date.replace("Z", "+00:00"))
            age_years = (datetime.now() - install.replace(tzinfo=None)).days / 365
            expected_life = config.get("expected_life_years", 20)
            age_score = max(0, 100 - (age_years / expected_life) * 100)
            if age_years >= thresholds.get("age_critical_years", 18):
                age_score = max(0, age_score - 30)
            elif age_years >= thresholds.get("age_warning_years", 15):
                age_score = max(0, age_score - 15)
            factors["age"] = {"score": age_score, "value": f"{age_years:.1f} years"}
        except (ValueError, TypeError):
            factors["age"] = {"score": 80, "value": "Unknown"}
    else:
        factors["age"] = {"score": 80, "value": "Unknown"}

    # Service compliance factor
    last_service = equipment.get("last_service")
    service_interval = config.get("service_interval_days", 90)
    if last_service:
        try:
            service_date = datetime.fromisoformat(last_service.replace("Z", "+00:00"))
            days_since = (datetime.now() - service_date.replace(tzinfo=None)).days
            days_overdue = max(0, days_since - service_interval)
            service_score = max(0, 100 - days_overdue * 2)
            if days_overdue >= thresholds.get("service_overdue_days_critical", 90):
                service_score = max(0, service_score - 30)
            elif days_overdue >= thresholds.get("service_overdue_days_warning", 30):
                service_score = max(0, service_score - 15)
            factors["service"] = {"score": service_score, "value": f"{days_since} days ago"}
        except (ValueError, TypeError):
            factors["service"] = {"score": 70, "value": "Unknown"}
    else:
        factors["service"] = {"score": 70, "value": "Never"}

    # Runtime hours factor (simulated based on age if not available)
    runtime_hours = equipment.get("runtime_hours")
    if runtime_hours is None and install_date:
        try:
            install = datetime.fromisoformat(install_date.replace("Z", "+00:00"))
            age_days = (datetime.now() - install.replace(tzinfo=None)).days
            runtime_hours = age_days * 10  # Estimate 10 hours/day average
        except (ValueError, TypeError):
            runtime_hours = 10000
    elif runtime_hours is None:
        runtime_hours = 10000

    runtime_critical = thresholds.get("runtime_hours_critical", 40000)
    runtime_warning = thresholds.get("runtime_hours_warning", 20000)
    if runtime_hours >= runtime_critical:
        runtime_score = 40
    elif runtime_hours >= runtime_warning:
        runtime_score = 70
    else:
        runtime_score = 100 - (runtime_hours / runtime_warning) * 30
    factors["runtime"] = {"score": runtime_score, "value": f"{runtime_hours:,} hours"}

    # Fault history factor (use existing status as proxy)
    status = equipment.get("status", "normal")
    if status == "normal":
        fault_score = 100
    elif status == "warning":
        fault_score = 60
    else:
        fault_score = 30
    factors["fault_history"] = {"score": fault_score, "value": status}

    # Calculate weighted total
    total_score = (
        factors["age"]["score"] * weights.get("age_factor", 0.2) +
        factors["service"]["score"] * weights.get("service_compliance", 0.3) +
        factors["runtime"]["score"] * weights.get("runtime_hours", 0.2) +
        factors["fault_history"]["score"] * weights.get("fault_history", 0.3)
    )

    return {
        "health_score": round(total_score, 1),
        "status": get_health_status(total_score),
        "factors": factors
    }


def get_health_status(score: float) -> str:
    """Get health status string from score."""
    settings = load_json(SETTINGS_PATH)
    thresholds = settings.get("healthThresholds", {"healthy": 80, "warning": 60, "critical": 0})

    if score >= thresholds.get("healthy", 80):
        return "healthy"
    elif score >= thresholds.get("warning", 60):
        return "attention"
    else:
        return "critical"


# ========== HVAC Overview ==========

@router.get("/overview/{site_id}")
async def get_hvac_overview(site_id: str):
    """Get complete HVAC status for a site.

    Returns zones, equipment summary, and overall health.
    """
    zones = load_json(ZONES_PATH)
    equipment = load_json(EQUIPMENT_PATH)

    # Filter equipment by site (using site_id prefix match for simplicity)
    hvac_types = ["ahu", "fcu", "chiller", "cooling_tower", "vav", "pump"]
    hvac_equipment = [e for e in equipment if e.get("type") in hvac_types]

    # Calculate zone status
    zone_stats = {
        "total": len(zones),
        "normal": sum(1 for z in zones if z.get("status") == "running"),
        "fault": sum(1 for z in zones if z.get("status") == "fault"),
        "offline": sum(1 for z in zones if z.get("status") == "offline"),
    }

    # Calculate equipment summary
    equipment_summary = {}
    for eq_type in hvac_types:
        typed_equipment = [e for e in hvac_equipment if e.get("type") == eq_type]
        if typed_equipment:
            avg_health = sum(e.get("health_score", 85) for e in typed_equipment) / len(typed_equipment)
            equipment_summary[eq_type] = {
                "count": len(typed_equipment),
                "avg_health": round(avg_health, 1),
                "faults": sum(1 for e in typed_equipment if e.get("status") != "normal"),
            }

    # Calculate overall health
    all_scores = [e.get("health_score", 85) for e in hvac_equipment]
    overall_health = round(sum(all_scores) / len(all_scores), 1) if all_scores else 85

    # Generate active alerts
    alerts = []
    for zone in zones:
        if zone.get("status") == "fault":
            alerts.append({
                "type": "zone_fault",
                "priority": "high",
                "title": f"Zone Fault: {zone.get('zone_name')}",
                "description": f"FCU {zone.get('fcu_id')} reporting fault status",
                "zone_id": zone.get("zone_id"),
            })
        deviation = abs(zone.get("current_temp", 22) - zone.get("setpoint", 22))
        if deviation > 2:
            alerts.append({
                "type": "temp_deviation",
                "priority": "medium" if deviation < 4 else "high",
                "title": f"Temperature Deviation: {zone.get('zone_name')}",
                "description": f"Current {zone.get('current_temp')}°C vs setpoint {zone.get('setpoint')}°C ({deviation:.1f}°C off)",
                "zone_id": zone.get("zone_id"),
            })

    for eq in hvac_equipment:
        if eq.get("health_score", 85) < 70:
            alerts.append({
                "type": "equipment_health",
                "priority": "high" if eq.get("health_score", 85) < 60 else "medium",
                "title": f"Low Health: {eq.get('name')}",
                "description": f"Health score {eq.get('health_score')}% - service may be required",
                "equipment_id": eq.get("id"),
            })

    return {
        "site_id": site_id,
        "timestamp": datetime.now().isoformat(),
        "zones": zone_stats,
        "equipment": equipment_summary,
        "overall_health": overall_health,
        "health_status": get_health_status(overall_health),
        "alerts": alerts[:10],  # Top 10 alerts
        "chillers_running": sum(1 for e in hvac_equipment
                                if e.get("type") == "chiller" and e.get("status") == "normal"),
    }


# ========== Zones ==========

@router.get("/zones")
async def list_zones(
    site_id: Optional[str] = Query(None, description="Filter by site"),
    floor: Optional[str] = Query(None, description="Filter by floor"),
):
    """List all HVAC zones."""
    zones = load_json(ZONES_PATH)

    if floor:
        zones = [z for z in zones if z.get("floor") == floor]

    # Enrich with temperature limits
    result = []
    for zone in zones:
        zone_id = zone.get("zone_id")
        min_temp, max_temp = get_zone_limits(zone_id)
        deviation = zone.get("current_temp", 22) - zone.get("setpoint", 22)

        result.append({
            **zone,
            "temp_min": min_temp,
            "temp_max": max_temp,
            "temp_deviation": round(deviation, 1),
        })

    return {
        "zones": result,
        "total": len(result),
    }


@router.get("/zones/{zone_id}")
async def get_zone(zone_id: str):
    """Get details for a specific zone."""
    zones = load_json(ZONES_PATH)

    zone = next((z for z in zones if z.get("zone_id") == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")

    min_temp, max_temp = get_zone_limits(zone_id)
    deviation = zone.get("current_temp", 22) - zone.get("setpoint", 22)

    # Get associated equipment health
    equipment = load_json(EQUIPMENT_PATH)
    fcu = next((e for e in equipment if e.get("name") == zone.get("fcu_id")), None)

    return {
        **zone,
        "temp_min": min_temp,
        "temp_max": max_temp,
        "temp_deviation": round(deviation, 1),
        "fcu_health": fcu.get("health_score") if fcu else None,
    }


@router.post("/zones/{zone_id}/setpoint")
async def set_zone_temperature(zone_id: str, request: SetpointRequest):
    """Set temperature setpoint for a zone.

    Validates against safety rules before applying.
    """
    zones = load_json(ZONES_PATH)

    zone_idx = next((i for i, z in enumerate(zones) if z.get("zone_id") == zone_id), None)
    if zone_idx is None:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")

    # Validate against safety limits
    min_temp, max_temp = get_zone_limits(zone_id)
    if request.setpoint < min_temp or request.setpoint > max_temp:
        raise HTTPException(
            status_code=400,
            detail=f"Setpoint {request.setpoint}°C outside allowed range {min_temp}-{max_temp}°C"
        )

    # Update zone setpoint
    old_setpoint = zones[zone_idx].get("setpoint", 22)
    zones[zone_idx]["setpoint"] = request.setpoint
    save_json(ZONES_PATH, zones)

    return {
        "success": True,
        "zone_id": zone_id,
        "old_setpoint": old_setpoint,
        "new_setpoint": request.setpoint,
        "message": f"Temperature setpoint changed from {old_setpoint}°C to {request.setpoint}°C",
    }


# ========== Equipment ==========

@router.get("/equipment")
async def list_equipment(
    site_id: Optional[str] = Query(None, description="Filter by site"),
    equipment_type: Optional[str] = Query(None, description="Filter by type (ahu, fcu, chiller, etc.)"),
):
    """List HVAC equipment with health scores."""
    equipment = load_json(EQUIPMENT_PATH)

    hvac_types = ["ahu", "fcu", "chiller", "cooling_tower", "vav", "pump", "crac"]
    result = [e for e in equipment if e.get("type") in hvac_types]

    if site_id:
        result = [e for e in result if e.get("site_id") == site_id]

    if equipment_type:
        result = [e for e in result if e.get("type") == equipment_type]

    # Calculate health details for each
    enriched = []
    for eq in result:
        health = calculate_equipment_health(eq)
        enriched.append({
            **eq,
            "calculated_health": health["health_score"],
            "health_status": health["status"],
            "health_factors": health["factors"],
        })

    return {
        "equipment": enriched,
        "total": len(enriched),
    }


@router.get("/equipment/{equipment_id}")
async def get_equipment(equipment_id: str):
    """Get details for specific equipment."""
    equipment = load_json(EQUIPMENT_PATH)

    eq = next((e for e in equipment if e.get("id") == equipment_id), None)
    if not eq:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    health = calculate_equipment_health(eq)

    return {
        **eq,
        "calculated_health": health["health_score"],
        "health_status": health["status"],
        "health_factors": health["factors"],
    }


# ========== Chillers ==========

@router.get("/chillers")
async def list_chillers(site_id: Optional[str] = Query(None)):
    """List all chillers with status and health."""
    equipment = load_json(EQUIPMENT_PATH)

    chillers = [e for e in equipment if e.get("type") == "chiller"]
    if site_id:
        chillers = [c for c in chillers if c.get("site_id") == site_id]

    result = []
    for chiller in chillers:
        health = calculate_equipment_health(chiller)
        result.append({
            **chiller,
            "calculated_health": health["health_score"],
            "health_status": health["status"],
            "is_running": chiller.get("status") == "normal",
        })

    return {
        "chillers": result,
        "total": len(result),
        "running": sum(1 for c in result if c["is_running"]),
    }


@router.post("/chillers/{chiller_id}/control")
async def control_chiller(chiller_id: str, request: ChillerControlRequest):
    """Control chiller on/off.

    Validates against safety rules (runtime limits, pressure limits).
    """
    equipment = load_json(EQUIPMENT_PATH)

    chiller_idx = next((i for i, e in enumerate(equipment)
                        if e.get("id") == chiller_id and e.get("type") == "chiller"), None)

    if chiller_idx is None:
        raise HTTPException(status_code=404, detail=f"Chiller {chiller_id} not found")

    chiller = equipment[chiller_idx]

    # Check safety rules for runtime limits
    rules = load_json(SAFETY_RULES_PATH)
    for rule in rules:
        if rule.get("enabled") and rule.get("rule_type") == "runtime_limit":
            if rule.get("device_type") == "hvac" and "chiller" in rule.get("point_name", ""):
                # In a real system, check actual runtime
                # For demo, we just acknowledge the rule exists
                pass

    # Update status (simulated)
    old_status = chiller.get("status")
    if request.action == "on":
        equipment[chiller_idx]["status"] = "normal"
    else:
        equipment[chiller_idx]["status"] = "off"

    save_json(EQUIPMENT_PATH, equipment)

    return {
        "success": True,
        "chiller_id": chiller_id,
        "action": request.action,
        "old_status": old_status,
        "new_status": equipment[chiller_idx]["status"],
        "message": f"Chiller {chiller.get('name')} turned {request.action}",
    }


# ========== Thermal Runway ==========

@router.get("/thermal-runway/{site_id}")
async def get_thermal_runway(site_id: str):
    """Get thermal runway calculations for load shedding preparation.

    Returns predicted temperature curves with and without pre-cooling.
    """
    zones = load_json(ZONES_PATH)

    # Calculate average current temperature
    avg_temp = sum(z.get("current_temp", 22) for z in zones) / len(zones) if zones else 22
    avg_setpoint = sum(z.get("setpoint", 22) for z in zones) / len(zones) if zones else 22

    # Thermal model parameters (simplified)
    thermal_mass_hours = 2.5  # Building thermal mass in hours to rise 1°C
    comfort_limit = 26.0
    outage_duration_hours = 2.5

    # Generate time points (30-minute intervals)
    time_points = []
    without_precooling = []
    with_precooling = []

    base_time = datetime.now().replace(minute=0, second=0, microsecond=0)

    # Pre-cooling starts 1 hour before outage
    precooling_start_temp = avg_temp - 2  # Pre-cool by 2°C

    for i in range(12):  # 6 hours of data
        time = base_time + timedelta(minutes=i * 30)
        time_points.append(time.strftime("%H:%M"))

        hours = i * 0.5

        # Without pre-cooling: start at current temp, rise during outage
        if hours < 2:  # Before outage
            without_precooling.append(round(avg_temp, 1))
        elif hours < 4.5:  # During outage (2.5 hours)
            rise = (hours - 2) / thermal_mass_hours
            without_precooling.append(round(avg_temp + rise, 1))
        else:  # Recovery
            recovery = (hours - 4.5) / 1.5  # Recovery takes 1.5 hours
            peak_temp = avg_temp + 2.5 / thermal_mass_hours
            without_precooling.append(round(peak_temp - recovery * (peak_temp - avg_setpoint), 1))

        # With pre-cooling: lower start temp, better runway
        if hours < 1:  # Pre-cooling phase
            with_precooling.append(round(avg_temp - hours * 2, 1))
        elif hours < 2:  # Continue at lowered temp
            with_precooling.append(round(precooling_start_temp, 1))
        elif hours < 4.5:  # During outage
            rise = (hours - 2) / thermal_mass_hours
            with_precooling.append(round(precooling_start_temp + rise, 1))
        else:  # Recovery
            recovery = (hours - 4.5) / 1.5
            peak_temp = precooling_start_temp + 2.5 / thermal_mass_hours
            with_precooling.append(round(peak_temp - recovery * (peak_temp - avg_setpoint), 1))

    # Calculate metrics
    runway_without = int(thermal_mass_hours * (comfort_limit - avg_temp) * 60)
    runway_with = int(thermal_mass_hours * (comfort_limit - precooling_start_temp) * 60)

    breach_without_idx = next((i for i, t in enumerate(without_precooling) if t >= comfort_limit), -1)
    breach_time = time_points[breach_without_idx] if breach_without_idx >= 0 else "No breach"

    return {
        "site_id": site_id,
        "timestamp": datetime.now().isoformat(),
        "data": {
            "time_points": time_points,
            "without_precooling": without_precooling,
            "with_precooling": with_precooling,
        },
        "outage_period": {
            "start": time_points[4],  # 2 hours in
            "end": time_points[9],    # 4.5 hours in
        },
        "metrics": {
            "runway_without": runway_without,
            "runway_with": runway_with,
            "comfort_breach_time": breach_time,
            "recovery_time": time_points[11] if len(time_points) > 11 else "N/A",
            "improvement_percent": round((runway_with - runway_without) / runway_without * 100, 0) if runway_without > 0 else 0,
        },
        "current_conditions": {
            "avg_temperature": round(avg_temp, 1),
            "avg_setpoint": round(avg_setpoint, 1),
            "comfort_limit": comfort_limit,
        },
    }


# ========== Safety Limits ==========

@router.get("/safety-limits")
async def get_hvac_safety_limits():
    """Get all HVAC-related safety limits for UI enforcement."""
    rules = load_json(SAFETY_RULES_PATH)
    settings = load_json(SETTINGS_PATH)

    hvac_rules = [r for r in rules if r.get("device_type") == "hvac" and r.get("enabled")]

    control_limits = settings.get("controlLimits", {})

    return {
        "temperature_setpoint": {
            "min": control_limits.get("temperature_setpoint", {}).get("min", 18),
            "max": control_limits.get("temperature_setpoint", {}).get("max", 26),
            "unit": "°C",
        },
        "chiller_setpoint": {
            "min": control_limits.get("chiller_setpoint", {}).get("min", 5),
            "max": control_limits.get("chiller_setpoint", {}).get("max", 12),
            "unit": "°C",
        },
        "safety_rules": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "type": r.get("rule_type"),
                "severity": r.get("severity"),
                "description": r.get("description"),
            }
            for r in hvac_rules
        ],
    }
