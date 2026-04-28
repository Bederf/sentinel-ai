"""HVAC API endpoints.

Provides HVAC zone management, equipment monitoring, thermal runway,
and health calculation for building climate systems.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.hvac_zone_repository import HVACZoneRepository
from app.middleware.auth_middleware import require_query_site_access
from app.models.auth import AuthContext

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
HEALTH_CONFIG_PATH = DATA_DIR / "health_config.json"

router = APIRouter(prefix="/hvac", tags=["hvac"])

# Repositories
_zone_repo = HVACZoneRepository()
_equip_repo = EquipmentRepository()

FORMULA_VERSION_STATIC = "2.0.0"


# === Pydantic models ===


class EquipmentHealthResponse(BaseModel):
    health_score: float
    status: str
    factors: dict
    formula_version: str


class HVACZoneResponse(BaseModel):
    zone_id: str
    zone_name: str
    floor: str
    fcu_id: str | None = None
    vav_id: str | None = None
    ahu_id: str | None = None
    temp_sensor: str | None = None
    co2_sensor: str | None = None
    typical_occupancy: int
    area_sqm: float
    setpoint: float
    current_temp: float | None = None
    status: str
    temp_deviation: float
    temp_min: float
    temp_max: float
    fcu_health: float | None = None


class HVACEquipmentResponse(BaseModel):
    id: str
    site_id: str
    type: str
    name: str
    manufacturer: str
    model: str
    capacity: str
    install_date: str
    last_service: str
    status: str
    health_score: int
    location: str
    serial_number: str | None = None


class ChillerResponse(BaseModel):
    id: str
    site_id: str
    type: str = "chiller"
    name: str
    manufacturer: str
    model: str
    capacity: str
    install_date: str
    last_service: str
    status: str
    health_score: int
    location: str
    serial_number: str | None = None
    is_running: bool
    metadata: dict | None = None


class HVACOverviewResponse(BaseModel):
    site_id: str
    timestamp: str
    zones: dict
    equipment: dict
    overall_health: float
    health_status: str
    alerts: list
    chillers_running: int
    raw_telemetry: dict | None = None
    sentinel_intelligence: dict | None = None


# === Health calculation ===


def get_health_status(score: float) -> str:
    if score >= 80:
        return "healthy"
    elif score >= 50:
        return "attention"
    return "critical"


def load_json(path: Path) -> dict:
    try:
        import json

        return json.loads(path.read_text())
    except Exception:
        return {}


def calculate_equipment_health(equipment: dict) -> dict:
    """Calculate health score for equipment based on health config."""
    health_config = load_json(HEALTH_CONFIG_PATH)
    eq_type = equipment.get("type", "").lower()

    if eq_type not in health_config:
        return {
            "health_score": equipment.get("health_score") or 85,
            "status": get_health_status(equipment.get("health_score") or 85),
            "factors": {},
            "formula_version": FORMULA_VERSION_STATIC,
        }

    config = health_config[eq_type]
    weights = config.get("weights", {})
    thresholds = config.get("thresholds", {})

    factors = {}
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
            factors["age"] = {"score": 80, "value": None}
    else:
        factors["age"] = {"score": 80, "value": None}

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
            factors["service"] = {"score": 70, "value": None}
    else:
        factors["service"] = {"score": 70, "value": None}

    runtime_hours = equipment.get("runtime_hours")
    if runtime_hours is None and install_date:
        try:
            install = datetime.fromisoformat(install_date.replace("Z", "+00:00"))
            age_days = (datetime.now() - install.replace(tzinfo=None)).days
            runtime_hours = age_days * 10
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

    status = equipment.get("status", "normal")
    if status == "normal":
        fault_score = 100
    elif status == "warning":
        fault_score = 60
    else:
        fault_score = 30
    factors["fault_history"] = {"score": fault_score, "value": status}

    total_score = (
        factors["age"]["score"] * weights.get("age_factor", 0.2)
        + factors["service"]["score"] * weights.get("service_compliance", 0.3)
        + factors["runtime"]["score"] * weights.get("runtime_hours", 0.2)
        + factors["fault_history"]["score"] * weights.get("fault_history", 0.3)
    )

    return {
        "health_score": round(total_score, 1),
        "status": get_health_status(total_score),
        "factors": factors,
        "formula_version": FORMULA_VERSION_STATIC,
    }


# === Helpers ===


def _get_site_uuid(site_code: str) -> str | None:
    """Resolve site code (e.g. 'site-002') to site UUID."""
    result = _zone_repo.get_site_uuid(site_code)
    if result:
        return result
    # Try as direct site code
    from app.database.supabase_client import get_supabase_client

    sb = get_supabase_client()
    resp = sb.table("sites").select("id").eq("code", site_code).execute()
    if resp.data:
        return resp.data[0]["id"]
    return None


# === Routes ===


@router.get("/overview/{site_id}", response_model=HVACOverviewResponse)
async def get_hvac_overview(
    site_id: str,
    auth: AuthContext = Depends(require_query_site_access("site_id")),
) -> HVACOverviewResponse:
    """Get HVAC overview for a site — zones, equipment, health, alerts."""
    site_uuid = _get_site_uuid(site_id)
    if not site_uuid:
        raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

    zones = _zone_repo.get_all(site_uuid)
    equipment_rows = _equip_repo.get_all(site_uuid)

    # Zone counts — "idle" with active temp control counts as running (chillers are active)
    normal = sum(1 for z in zones if z.get("status") in ("running", "normal", "idle", None))
    fault = sum(1 for z in zones if z.get("status") in ("fault", "warning"))
    offline = sum(1 for z in zones if z.get("status") in ("offline", "off"))

    # Equipment by type
    equip_by_type: dict[str, list] = {}
    for eq in equipment_rows:
        t = eq.get("type", "unknown")
        if t not in equip_by_type:
            equip_by_type[t] = []
        equip_by_type[t].append(eq)

    # Equipment summaries
    equip_summary = {}
    for eq_type, items in equip_by_type.items():
        scores = [item.get("health_score") or 85 for item in items]
        avg_health = sum(scores) / len(scores) if scores else 85
        faults = sum(1 for item in items if item.get("status") in ("fault", "critical", "warning"))
        equip_summary[eq_type] = {"count": len(items), "avg_health": round(avg_health, 1), "faults": faults}

    # Overall health
    zone_scores = [z.get("health_score") or 85 for z in zones]
    equip_scores = [item.get("health_score") or 85 for item in equipment_rows]
    all_scores = zone_scores + equip_scores
    overall_health = round(sum(all_scores) / len(all_scores), 1) if all_scores else 85

    # Chillers running — status "normal" means actively cooling (no is_running column in equipment table)
    chillers = [eq for eq in equipment_rows if eq.get("type", "").lower() in ("chiller", "hvac_chiller")]
    chillers_running = sum(1 for c in chillers if c.get("status") in ("running", "normal"))

    # Fetch live site power from ML feeder bridge buffers (bridge data, not DB)
    site_power = None
    try:
        from app.services.sentinel_data_sync import get_sentinel_data_sync

        sync = get_sentinel_data_sync(site_id=site_id)
        site_power = sync.ml_feeder.get_latest_site_power()
    except Exception:
        pass

    if site_power:
        hvac_kw = site_power["hvac_kw"]
        lighting_kw = site_power["lighting_kw"]
        total_kw = site_power["total_kw"]
        raw_telemetry_status = "live"
    else:
        hvac_kw = 0.0
        lighting_kw = 0.0
        total_kw = 0.0
        raw_telemetry_status = "unavailable"

    # Fetch alerts for this site
    from app.database.supabase_client import get_supabase_client

    sb = get_supabase_client()
    alert_resp = sb.table("alerts").select("*").eq("site_id", site_uuid).eq("status", "active").execute()
    active_alerts = [
        {
            "type": a.get("type", "unknown"),
            "priority": a.get("severity", "medium"),
            "title": a.get("title", ""),
            "description": a.get("message", ""),
            "zone_id": a.get("zone_id"),
            "equipment_id": a.get("equipment_id"),
        }
        for a in (alert_resp.data or [])
        if a.get("type") in ("zone_fault", "temp_deviation", "equipment_health", "co2_warning")
    ]

    return HVACOverviewResponse(
        site_id=site_id,
        timestamp=datetime.now(UTC).isoformat(),
        zones={"total": len(zones), "normal": normal, "fault": fault, "offline": offline},
        equipment=equip_summary,
        overall_health=overall_health,
        health_status=get_health_status(overall_health),
        alerts=active_alerts,
        chillers_running=chillers_running,
        raw_telemetry={
            "status": raw_telemetry_status,
            "zone_count": len(zones),
            "power": {
                "hvac_kw": hvac_kw,
                "lighting_kw": lighting_kw,
                "total_kw": total_kw,
            },
            "equipment_summary": {
                "total": len(equipment_rows),
                "online": sum(1 for eq in equipment_rows if eq.get("status") not in ("offline", "fault", "off")),
            },
        },
        sentinel_intelligence=None,
    )


@router.get("/zones")
async def get_hvac_zones(
    site_id: str | None = Query(None, description="Filter by site ID"),
    floor: str | None = Query(None, description="Filter by floor"),
    auth: AuthContext = Depends(require_query_site_access("site_id")),
) -> dict:
    """Get all HVAC zones, optionally filtered by site and floor."""
    if site_id:
        site_uuid = _get_site_uuid(site_id)
        if not site_uuid:
            return {"zones": [], "total": 0}
        all_zones = _zone_repo.get_all(site_uuid)
    else:
        # Fallback: fetch from equipment if no site
        all_zones = []

    if floor:
        all_zones = [z for z in all_zones if z.get("floor") == floor]

    zone_responses = []
    for z in all_zones:
        # Derive FCU code when fcu_id is null — zone_id pattern: Zone-{num} or Zone-{letter}
        raw_fcu_id = z.get("fcu_id")
        if not raw_fcu_id:
            zone_id_str = z.get("zone_id", "")
            # Numeric zone: Zone-001 → S002-FCU-001, Zone-101 → S002-FCU-101, Zone-201 → S002-FCU-201
            if zone_id_str.startswith("Zone-"):
                suffix = zone_id_str[5:]  # e.g. "001", "101", "B", "R"
                if suffix.isdigit():
                    raw_fcu_id = f"S002-FCU-{suffix}"
                elif suffix in ("B", "R"):
                    raw_fcu_id = "S002-FCU-BASEMENT" if suffix == "B" else "S002-FCU-ROOF"

        zone_responses.append(
            HVACZoneResponse(
                zone_id=z.get("zone_id", ""),
                zone_name=z.get("zone_name", z.get("name", "")),
                floor=z.get("floor", ""),
                fcu_id=raw_fcu_id,
                vav_id=z.get("vav_id"),
                ahu_id=z.get("ahu_id"),
                temp_sensor=z.get("temp_sensor"),
                co2_sensor=z.get("co2_sensor"),
                typical_occupancy=z.get("typical_occupancy", 0),
                area_sqm=z.get("area_sqm", 0),
                setpoint=z.get("setpoint", 22),
                current_temp=z.get("current_temp"),
                status=z.get("status", "unknown"),
                temp_deviation=z.get("temp_deviation", 0),
                temp_min=z.get("temp_min", 18),
                temp_max=z.get("temp_max", 28),
                fcu_health=z.get("fcu_health"),
            )
        )

    return {"zones": zone_responses, "total": len(zone_responses)}


@router.get("/zones/{zone_id}")
async def get_hvac_zone(
    zone_id: str,
    auth: AuthContext = Depends(require_query_site_access("zone_id")),
) -> HVACZoneResponse:
    """Get single HVAC zone by zone_id."""
    zone = _zone_repo.get_by_zone_id(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")

    return HVACZoneResponse(
        zone_id=zone.get("zone_id", zone_id),
        zone_name=zone.get("zone_name", zone.get("name", "")),
        floor=zone.get("floor", ""),
        fcu_id=zone.get("fcu_id"),
        vav_id=zone.get("vav_id"),
        ahu_id=zone.get("ahu_id"),
        temp_sensor=zone.get("temp_sensor"),
        co2_sensor=zone.get("co2_sensor"),
        typical_occupancy=zone.get("typical_occupancy", 0),
        area_sqm=zone.get("area_sqm", 0),
        setpoint=zone.get("setpoint", 22),
        current_temp=zone.get("current_temp"),
        status=zone.get("status", "unknown"),
        temp_deviation=zone.get("temp_deviation", 0),
        temp_min=zone.get("temp_min", 18),
        temp_max=zone.get("temp_max", 28),
        fcu_health=zone.get("fcu_health"),
    )


@router.post("/zones/{zone_id}/setpoint")
async def set_zone_setpoint(
    zone_id: str,
    setpoint: float,
    auth: AuthContext = Depends(require_query_site_access("zone_id")),
) -> dict:
    """Update zone temperature setpoint."""
    zone = _zone_repo.get_by_zone_id(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")

    _zone_repo.update_setpoint(zone_id, setpoint)
    return {
        "success": True,
        "zone_id": zone_id,
        "old_setpoint": zone.get("setpoint", 22),
        "new_setpoint": setpoint,
        "message": f"Setpoint updated to {setpoint}°C",
    }


@router.get("/equipment")
async def get_hvac_equipment(
    site_id: str | None = Query(None, description="Filter by site ID"),
    equipment_type: str | None = Query(None, alias="type", description="Filter by equipment type"),
    auth: AuthContext = Depends(require_query_site_access("site_id")),
) -> dict:
    """Get HVAC equipment filtered by site and/or type."""
    if site_id:
        site_uuid = _get_site_uuid(site_id)
        if not site_uuid:
            return {"equipment": [], "total": 0}
        rows = _equip_repo.get_all(site_uuid)
    else:
        rows = []

    # Filter HVAC types
    hvac_types = {
        "ahu",
        "fcu",
        "chiller",
        "cooling_tower",
        "vav",
        "pump",
        "crac",
        "hvac_ahu",
        "hvac_fcu",
        "hvac_chiller",
        "hvac_vav",
        "hvac_pump",
    }
    if equipment_type:
        rows = [r for r in rows if equipment_type.lower() in r.get("type", "").lower()]
    else:
        rows = [
            r
            for r in rows
            if r.get("type", "").lower() in hvac_types or any(t in r.get("type", "").lower() for t in hvac_types)
        ]

    equip_responses = []
    for eq in rows:
        equip_responses.append(
            HVACEquipmentResponse(
                id=eq.get("id", eq.get("code", "")),
                site_id=eq.get("site_id", site_id or ""),
                type=eq.get("type") or "unknown",
                name=eq.get("name") or "Unknown",
                manufacturer=eq.get("manufacturer") or "Unknown",
                model=eq.get("model") or "Unknown",
                capacity=eq.get("capacity") or "N/A",
                install_date=eq.get("install_date") or "",
                last_service=eq.get("last_service") or "",
                status=eq.get("status") or "normal",
                health_score=int(eq.get("health_score") or 85),
                location=eq.get("location") or "",
                serial_number=eq.get("serial_number"),
            )
        )

    return {"equipment": equip_responses, "total": len(equip_responses)}


@router.get("/equipment/{equipment_id}")
async def get_hvac_equipment_detail(
    equipment_id: str,
    auth: AuthContext = Depends(require_query_site_access("equipment_id")),
) -> HVACEquipmentResponse:
    """Get single HVAC equipment by ID."""
    from app.database.supabase_client import get_supabase_client

    sb = get_supabase_client()
    resp = sb.table("equipment").select("*").eq("id", equipment_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    eq = resp.data[0]
    return HVACEquipmentResponse(
        id=eq.get("id", ""),
        site_id=eq.get("site_id", ""),
        type=eq.get("type") or "unknown",
        name=eq.get("name") or "Unknown",
        manufacturer=eq.get("manufacturer") or "Unknown",
        model=eq.get("model") or "Unknown",
        capacity=eq.get("capacity") or "N/A",
        install_date=eq.get("install_date") or "",
        last_service=eq.get("last_service") or "",
        status=eq.get("status") or "normal",
        health_score=int(eq.get("health_score") or 85),
        location=eq.get("location") or "",
        serial_number=eq.get("serial_number"),
    )


@router.get("/chillers")
async def get_chillers(
    site_id: str | None = Query(None, description="Filter by site ID"),
    auth: AuthContext = Depends(require_query_site_access("site_id")),
) -> dict:
    """Get all chillers for a site."""
    if site_id:
        site_uuid = _get_site_uuid(site_id)
        if not site_uuid:
            return {"chillers": [], "total": 0, "running": 0}
        rows = _equip_repo.get_all(site_uuid)
    else:
        rows = []

    chillers = [r for r in rows if "chiller" in r.get("type", "").lower() or r.get("type", "") == "hvac_chiller"]
    running = sum(1 for c in chillers if c.get("status") == "running" or c.get("is_running"))

    chillers_response = []
    for c in chillers:
        chillers_response.append(
            {
                "id": c.get("id", c.get("code", "")),
                "site_id": c.get("site_id", site_id or ""),
                "type": "chiller",
                "name": c.get("name") or "Unknown Chiller",
                "manufacturer": c.get("manufacturer") or "Unknown",
                "model": c.get("model") or "Unknown",
                "capacity": c.get("capacity") or "N/A",
                "install_date": c.get("install_date") or "",
                "last_service": c.get("last_service") or "",
                "status": c.get("status") or "unknown",
                "health_score": int(c.get("health_score") or 85),
                "location": c.get("location") or "",
                "serial_number": c.get("serial_number"),
                "is_running": c.get("status") == "running" or c.get("is_running", False),
                "metadata": c.get("operating_data") or c.get("metadata") or {},
            }
        )

    return {"chillers": chillers_response, "total": len(chillers_response), "running": running}


@router.get("/equipment-health/{equipment_id}")
async def get_equipment_health(
    equipment_id: str,
    auth: AuthContext = Depends(require_query_site_access("equipment_id")),
) -> dict:
    """Get calculated health score for equipment."""
    from app.database.supabase_client import get_supabase_client

    sb = get_supabase_client()
    resp = sb.table("equipment").select("*").eq("id", equipment_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    eq = resp.data[0]
    return calculate_equipment_health(eq)
