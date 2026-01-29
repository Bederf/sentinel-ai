"""Equipment API endpoints."""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.sensor_repository import SensorRepository

logger = logging.getLogger(__name__)
router = APIRouter()

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"

# Initialize Supabase repositories
equipment_repo = EquipmentRepository()
sensor_repo = SensorRepository()


def load_equipment() -> list[dict]:
    """Load equipment from JSON file."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


def load_sensors() -> list[dict]:
    """Load sensors from JSON file."""
    sensors_file = DATA_DIR / "sensors.json"
    if sensors_file.exists():
        with open(sensors_file) as f:
            return json.load(f)
    return []


def load_alerts() -> list[dict]:
    """Load alerts from JSON file."""
    alerts_file = DATA_DIR / "alerts.json"
    if alerts_file.exists():
        with open(alerts_file) as f:
            return json.load(f)
    return []


class EquipmentBase(BaseModel):
    """Base equipment model."""

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
    serial_number: str


class EquipmentResponse(EquipmentBase):
    """Equipment response with computed fields."""

    sensor_count: int = 0
    active_alerts: int = 0


class EquipmentListResponse(BaseModel):
    """Response for equipment list."""

    total: int
    equipment: list[EquipmentResponse]


@router.get("/equipment", response_model=EquipmentListResponse)
async def list_equipment(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    equipment_type: Optional[str] = Query(None, alias="type", description="Filter by equipment type"),
    status: Optional[str] = Query(None, description="Filter by status (normal, warning, critical)"),
    min_health: Optional[int] = Query(None, ge=0, le=100, description="Minimum health score"),
    max_health: Optional[int] = Query(None, ge=0, le=100, description="Maximum health score"),
) -> EquipmentListResponse:
    """
    List all equipment with optional filtering.

    Args:
        site_id: Filter by site ID
        equipment_type: Filter by type (ahu, chiller, ups, generator, etc.)
        status: Filter by status (normal, warning, critical)
        min_health: Minimum health score (0-100)
        max_health: Maximum health score (0-100)

    Returns:
        EquipmentListResponse with total count and list of equipment.
    """
    equipment = load_equipment()
    sensors = load_sensors()
    alerts = load_alerts()

    # Apply filters
    if site_id:
        equipment = [e for e in equipment if e["site_id"] == site_id]
    if equipment_type:
        equipment = [e for e in equipment if e["type"].lower() == equipment_type.lower()]
    if status:
        equipment = [e for e in equipment if e["status"].lower() == status.lower()]
    if min_health is not None:
        equipment = [e for e in equipment if e["health_score"] >= min_health]
    if max_health is not None:
        equipment = [e for e in equipment if e["health_score"] <= max_health]

    # Enrich with counts
    result = []
    for eq in equipment:
        eq_sensors = [s for s in sensors if s.get("equipment_id") == eq["id"]]
        eq_alerts = [
            a for a in alerts
            if a.get("equipment_id") == eq["id"] and a.get("status") == "active"
        ]
        result.append(
            EquipmentResponse(
                **eq,
                sensor_count=len(eq_sensors),
                active_alerts=len(eq_alerts),
            )
        )

    return EquipmentListResponse(total=len(result), equipment=result)


@router.get("/equipment/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(equipment_id: str) -> EquipmentResponse:
    """
    Get a single equipment item by ID.

    Args:
        equipment_id: The equipment identifier.

    Returns:
        EquipmentResponse with equipment details.

    Raises:
        HTTPException: If equipment not found.
    """
    equipment = load_equipment()
    sensors = load_sensors()
    alerts = load_alerts()

    eq = next((e for e in equipment if e["id"] == equipment_id), None)
    if not eq:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    eq_sensors = [s for s in sensors if s.get("equipment_id") == equipment_id]
    eq_alerts = [
        a for a in alerts
        if a.get("equipment_id") == equipment_id and a.get("status") == "active"
    ]

    return EquipmentResponse(
        **eq,
        sensor_count=len(eq_sensors),
        active_alerts=len(eq_alerts),
    )


@router.get("/equipment/{equipment_id}/controls")
async def get_equipment_controls(equipment_id: str):
    """
    Get equipment with control points from Supabase or JSON fallback.

    Args:
        equipment_id: Equipment code (e.g., "eqp-079")

    Returns:
        Device-like structure with control points for ControlPanel.
    """
    try:
        # Try to get from Supabase first
        eq = None
        try:
            eq = equipment_repo.get_by_id(equipment_id)
        except Exception as supabase_err:
            logger.debug(f"Supabase lookup failed for {equipment_id}: {supabase_err}")

        # Fallback to JSON if not in Supabase or Supabase errored
        if not eq:
            equipment_list = load_equipment()
            eq = next((e for e in equipment_list if e.get("id") == equipment_id), None)
            # Map JSON fields to expected format
            if eq:
                eq["building_id"] = eq.get("site_id", "")

        if not eq:
            raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

        # Get sensors for this equipment
        sensors = []
        try:
            sensors = sensor_repo.get_by_equipment(eq["id"])
        except Exception as sensor_err:
            logger.debug(f"Supabase sensor lookup failed for {eq['id']}: {sensor_err}")

        # Fallback to JSON sensors if none from Supabase
        if not sensors:
            all_sensors = load_sensors()
            sensors = [s for s in all_sensors if s.get("equipment_id") == equipment_id]

        # Convert sensors to control points format
        points = {}
        for sensor in sensors:
            point_name = sensor.get("code", sensor.get("id"))
            sensor_type = sensor.get("type", "temperature")

            # Map sensor type to point type
            point_type = "analog_value"  # default
            if sensor_type in ["temperature", "pressure", "flow", "energy"]:
                point_type = "analog_value"
            elif sensor_type in ["vibration"]:
                point_type = "binary_value"

            points[point_name] = {
                "point_type": point_type,
                "description": f"{sensor_type.title()} - {sensor.get('location', 'Main')}",
                "unit": sensor.get("unit", ""),
                "min_value": float(sensor.get("min_value", 0)) if sensor.get("min_value") else 0,
                "max_value": float(sensor.get("max_value", 100)) if sensor.get("max_value") else 100,
                "default_value": float(sensor.get("current_value", 0)) if sensor.get("current_value") else 0,
                "writable": True,
            }

        # Add common control points for HVAC equipment
        eq_type = eq.get("type", "").lower()
        if eq_type in ["hvac", "split_unit", "ahu", "chiller", "ac"]:
            if "power" not in points and "power_switch" not in points:
                points["power_switch"] = {
                    "point_type": "binary_value",
                    "description": "Power On/Off",
                    "default_value": True,
                    "writable": True,
                }
            if "setpoint" not in points and "setpoint_temp" not in points:
                points["setpoint_temp"] = {
                    "point_type": "analog_value",
                    "description": "Temperature Setpoint",
                    "unit": "°C",
                    "min_value": 16,
                    "max_value": 30,
                    "default_value": 22,
                    "writable": True,
                }
            if "fan_speed" not in points:
                points["fan_speed"] = {
                    "point_type": "multistate_value",
                    "description": "Fan Speed",
                    "states": ["Auto", "Low", "Medium", "High"],
                    "default_value": 0,
                    "writable": True,
                }

        # Return device-like structure
        return {
            "id": equipment_id,
            "name": eq.get("name", equipment_id),
            "device_type": eq.get("type", "unknown"),
            "type": eq.get("type", "unknown"),
            "protocol": "supabase",
            "location": eq.get("location", ""),
            "site_id": eq.get("building_id", ""),
            "description": f"{eq.get('manufacturer', '')} {eq.get('model', '')}".strip() or eq.get("name", ""),
            "points": points,
            "status": eq.get("status", "normal"),
            "safety_status": "warning" if eq.get("status") == "warning" else "critical" if eq.get("status") == "critical" else "safe",
            "health_score": eq.get("health_score", 100),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching equipment controls for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/equipment/{equipment_id}/control")
async def control_equipment(
    equipment_id: str,
    request: Request,
):
    """
    Control an equipment point (write value to Supabase).

    Args:
        equipment_id: Equipment code (e.g., "eqp-004")
        request body: {"point": "setpoint_temp", "value": 23, "priority": 8}

    Returns:
        Control result with success/failure status
    """
    from datetime import datetime
    from app.database.repositories.audit_repository import AuditRepository

    try:
        body = await request.json()
        point = body.get("point")
        value = body.get("value")
        priority = body.get("priority", 8)

        if not point or value is None:
            raise HTTPException(status_code=400, detail="Missing 'point' or 'value' in request body")

        # Get equipment from Supabase with JSON fallback
        eq = None
        try:
            eq = equipment_repo.get_by_id(equipment_id)
        except Exception as supabase_err:
            logger.debug(f"Supabase lookup failed for {equipment_id}: {supabase_err}")

        # Fallback to JSON if not in Supabase
        if not eq:
            equipment_list = load_equipment()
            eq = next((e for e in equipment_list if e.get("id") == equipment_id), None)
            if eq:
                eq["building_id"] = eq.get("site_id", "")

        if not eq:
            raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

        # Get the sensor if it's a sensor point
        sensor_value = None
        old_value = None
        if point.startswith("sensor-"):
            # Try Supabase first, fallback to JSON
            sensors = []
            try:
                sensors = sensor_repo.get_by_equipment(eq["id"])
            except Exception as sensor_err:
                logger.debug(f"Supabase sensor lookup failed: {sensor_err}")
            if not sensors:
                all_sensors = load_sensors()
                sensors = [s for s in all_sensors if s.get("equipment_id") == equipment_id]
            sensor = next((s for s in sensors if s.get("code") == point), None)
            if sensor:
                old_value = sensor.get("current_value")
                # Update sensor current_value in Supabase
                try:
                    from app.database.supabase_client import get_supabase_client
                    client = get_supabase_client()
                    client.table("sensors").update({
                        "current_value": float(value),
                        "updated_at": datetime.now().isoformat()
                    }).eq("code", point).execute()
                    sensor_value = value
                except Exception as sensor_err:
                    logger.warning(f"Could not update sensor value in Supabase: {sensor_err}")

        # Log the control action to audit trail
        try:
            audit_repo = AuditRepository()
            audit_repo.create({
                "action": "equipment_control",
                "user": body.get("user", "system"),
                "device_id": eq["id"],
                "point_name": point,
                "old_value": old_value,
                "new_value": value,
                "result": "success",
                "metadata": {
                    "equipment_code": equipment_id,
                    "equipment_name": eq.get("name"),
                    "equipment_type": eq.get("type"),
                    "priority": priority,
                }
            })
        except Exception as audit_err:
            logger.warning(f"Could not log audit entry: {audit_err}")

        return {
            "success": True,
            "message": f"Control command sent to {equipment_id}",
            "device_id": equipment_id,
            "point": point,
            "value": value,
            "priority": priority,
            "sensor_updated": sensor_value is not None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error controlling equipment {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class EquipmentTypeStats(BaseModel):
    """Statistics for an equipment type."""

    type: str
    count: int
    avg_health: float
    warning_count: int
    critical_count: int


class EquipmentStatsResponse(BaseModel):
    """Equipment statistics response."""

    total: int
    by_type: list[EquipmentTypeStats]
    avg_health: float
    warning_count: int
    critical_count: int


@router.get("/equipment-stats", response_model=EquipmentStatsResponse)
async def get_equipment_stats(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
) -> EquipmentStatsResponse:
    """
    Get equipment statistics.

    Args:
        site_id: Optional site ID to filter by.

    Returns:
        EquipmentStatsResponse with aggregated statistics.
    """
    equipment = load_equipment()

    if site_id:
        equipment = [e for e in equipment if e["site_id"] == site_id]

    if not equipment:
        return EquipmentStatsResponse(
            total=0,
            by_type=[],
            avg_health=0,
            warning_count=0,
            critical_count=0,
        )

    # Calculate stats by type
    type_stats: dict[str, dict] = {}
    for eq in equipment:
        eq_type = eq["type"]
        if eq_type not in type_stats:
            type_stats[eq_type] = {
                "type": eq_type,
                "count": 0,
                "total_health": 0,
                "warning_count": 0,
                "critical_count": 0,
            }
        type_stats[eq_type]["count"] += 1
        type_stats[eq_type]["total_health"] += eq["health_score"]
        if eq["status"] == "warning":
            type_stats[eq_type]["warning_count"] += 1
        elif eq["status"] == "critical":
            type_stats[eq_type]["critical_count"] += 1

    by_type = [
        EquipmentTypeStats(
            type=stats["type"],
            count=stats["count"],
            avg_health=round(stats["total_health"] / stats["count"], 1),
            warning_count=stats["warning_count"],
            critical_count=stats["critical_count"],
        )
        for stats in type_stats.values()
    ]

    total_health = sum(eq["health_score"] for eq in equipment)
    warning_count = sum(1 for eq in equipment if eq["status"] == "warning")
    critical_count = sum(1 for eq in equipment if eq["status"] == "critical")

    return EquipmentStatsResponse(
        total=len(equipment),
        by_type=sorted(by_type, key=lambda x: -x.count),
        avg_health=round(total_health / len(equipment), 1),
        warning_count=warning_count,
        critical_count=critical_count,
    )
