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


def load_safety_rules() -> list[dict]:
    """Load safety rules from JSON file."""
    rules_file = DATA_DIR / "safety_rules.json"
    if rules_file.exists():
        with open(rules_file) as f:
            return json.load(f)
    return []


def get_safety_limits_for_point(
    device_type: str, point_name: str, safety_rules: list[dict]
) -> dict | None:
    """
    Find applicable safety rule limits for a device type and point name.

    Args:
        device_type: The equipment type (e.g., "hvac", "lighting", "ahu")
        point_name: The point/sensor name (e.g., "setpoint_temp", "brightness")
        safety_rules: List of safety rules

    Returns:
        Dict with min_value and max_value if found, None otherwise
    """
    # Normalize device type for matching
    normalized_type = device_type.lower()
    hvac_types = ["hvac", "ahu", "chiller", "split_unit", "ac", "vav"]

    for rule in safety_rules:
        if not rule.get("enabled", True):
            continue

        rule_device_type = rule.get("device_type", "").lower()
        rule_point_name = rule.get("point_name")

        # Check device type match (or rule applies to all)
        device_match = (
            not rule_device_type or
            rule_device_type == normalized_type or
            (rule_device_type == "hvac" and normalized_type in hvac_types)
        )

        # Check point name match (flexible matching)
        point_match = False
        if rule_point_name:
            # Direct match
            if rule_point_name.lower() == point_name.lower():
                point_match = True
            # Partial match for setpoints
            elif "setpoint" in point_name.lower() and "setpoint" in rule_point_name.lower():
                point_match = True
            # Temperature setpoint matching
            elif "temp" in point_name.lower() and "temp" in rule_point_name.lower():
                point_match = True
        elif rule.get("rule_type") == "temperature_range" and "temp" in point_name.lower():
            # Generic temperature rule without specific point applies to temp setpoints
            point_match = True

        if device_match and point_match:
            # Extract limits based on rule type
            rule_type = rule.get("rule_type", "")

            if rule_type == "temperature_range":
                return {
                    "min_value": rule.get("min_temp", 16.0),
                    "max_value": rule.get("max_temp", 28.0),
                    "unit": rule.get("unit", "°C"),
                }
            elif rule_type == "brightness_limit":
                return {
                    "min_value": rule.get("min_brightness", 0),
                    "max_value": rule.get("max_brightness", 100),
                    "unit": "%",
                }
            elif rule_type == "pressure_limit":
                return {
                    "min_value": rule.get("min_pressure", 0),
                    "max_value": rule.get("max_pressure", 1200),
                    "unit": rule.get("unit", "kPa"),
                }

    return None


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

        # Load safety rules for limit enforcement
        safety_rules = load_safety_rules()

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

            # Generate realistic default values based on sensor type
            default_value = sensor.get("current_value")
            if default_value is None:
                sensor_defaults = {
                    "temperature": 22.0,
                    "humidity": 55.0,
                    "pressure": 101.3,
                    "flow": 150.0,
                    "power": 45.0,
                    "energy": 120.0,
                    "vibration": 0.5,
                    "battery_voltage": 54.0,
                    "battery_runtime": 30.0,
                }
                default_value = sensor_defaults.get(sensor_type.lower(), 0)

            # Determine if sensor is writable (controllable) or read-only (monitoring)
            # Most sensors are read-only monitoring values
            # Only setpoints and control outputs are writable
            read_only_types = [
                "temperature", "humidity", "pressure", "flow", "power", "energy",
                "vibration", "battery_voltage", "battery_runtime", "current",
                "voltage", "frequency", "speed", "level", "status"
            ]
            is_writable = sensor_type.lower() not in read_only_types
            # Check sensor name/location for setpoint indicators
            sensor_name = sensor.get("name", "").lower()
            sensor_location = sensor.get("location", "").lower()
            if "setpoint" in sensor_name or "setpoint" in sensor_location:
                is_writable = True

            # Determine min/max values
            min_val = float(sensor.get("min_value", 0)) if sensor.get("min_value") else 0
            max_val = float(sensor.get("max_value", 100)) if sensor.get("max_value") else 100
            point_unit = sensor.get("unit", "")

            # For writable points, apply safety rule limits if available
            if is_writable:
                eq_type = eq.get("type", "")
                safety_limits = get_safety_limits_for_point(eq_type, point_name, safety_rules)
                if safety_limits:
                    min_val = safety_limits["min_value"]
                    max_val = safety_limits["max_value"]
                    if safety_limits.get("unit"):
                        point_unit = safety_limits["unit"]
                    logger.debug(f"Applied safety limits to {point_name}: {min_val}-{max_val}")

            points[point_name] = {
                "point_type": point_type,
                "description": f"{sensor_type.title()} - {sensor.get('location', 'Main')}",
                "unit": point_unit,
                "min_value": min_val,
                "max_value": max_val,
                "default_value": float(default_value),
                "writable": is_writable,
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
                # Get safety limits for temperature setpoint
                temp_limits = get_safety_limits_for_point(eq_type, "setpoint_temp", safety_rules)
                temp_min = temp_limits["min_value"] if temp_limits else 16
                temp_max = temp_limits["max_value"] if temp_limits else 28
                temp_unit = temp_limits.get("unit", "°C") if temp_limits else "°C"

                points["setpoint_temp"] = {
                    "point_type": "analog_value",
                    "description": "Temperature Setpoint",
                    "unit": temp_unit,
                    "min_value": temp_min,
                    "max_value": temp_max,
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

        # Load safety rules for validation
        safety_rules = load_safety_rules()

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

        # Validate value against safety rules for writable points
        eq_type = eq.get("type", "")
        safety_limits = get_safety_limits_for_point(eq_type, point, safety_rules)
        if safety_limits and isinstance(value, (int, float)):
            min_val = safety_limits["min_value"]
            max_val = safety_limits["max_value"]
            if value < min_val or value > max_val:
                raise HTTPException(
                    status_code=400,
                    detail=f"Value {value} is outside safety limits ({min_val}-{max_val}). "
                           f"Please adjust within the allowed range."
                )

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
