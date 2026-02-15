"""Equipment API endpoints."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

import httpx

from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.sensor_repository import SensorRepository
from app.services.csv_loader import AssetData, AlarmData as CSVAlarmData
from app.services.health_threshold_service import get_health_thresholds

logger = logging.getLogger(__name__)
router = APIRouter()

# Simulation API endpoint (already running)
SIMULATION_API = "http://localhost:9095/api/simulation"

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"

# Initialize Supabase repositories
equipment_repo = EquipmentRepository()
sensor_repo = SensorRepository()


def _derive_health_score(condition: str, age_years: int, expected_life: int) -> int:
    """
    Derive health score from condition, age, and expected life.

    Returns a score 0-100 based on:
    - Base score from condition (good=85, fair=65, poor=35)
    - Age penalty (subtract points as asset approaches end of life)
    """
    # Base score from condition
    condition_scores = {
        "good": 85,
        "fair": 65,
        "poor": 35,
    }
    base_score = condition_scores.get(condition.lower(), 70)

    # Age penalty: lose up to 15 points as remaining life decreases
    if expected_life > 0:
        remaining_ratio = max(0, (expected_life - age_years) / expected_life)
        age_penalty = int((1 - remaining_ratio) * 15)
    else:
        age_penalty = 0

    return max(0, min(100, base_score - age_penalty))


def _derive_status(condition: str, health_score: int) -> str:
    """Derive status from condition and health score using configured thresholds."""
    thresholds = get_health_thresholds()

    # Poor condition always critical, otherwise use health score
    if condition.lower() == "poor":
        return "critical"
    elif health_score < thresholds["critical"]:
        return "critical"
    elif condition.lower() == "fair" or health_score < thresholds["warning"]:
        return "warning"
    return "normal"


async def load_equipment() -> list[dict]:
    """Load equipment from Supabase (primary source), fallback to CSV/JSON."""
    try:
        # Primary source: Load from Supabase
        equipment_data = await equipment_repo.get_all()

        if equipment_data:
            equipment_list = []
            for eq in equipment_data:
                # Transform Supabase equipment to API response format
                # Ensure all string fields have non-null defaults
                # Extract site_id from code (e.g., S002-GEN-B1-005 → site-002)
                code = eq.get("code", "")
                extracted_site = ""
                if code:
                    # Handle both S002 and site-002 formats
                    first_part = code.split("-")[0].lower()
                    if first_part.startswith("s"):
                        # S002 → site-002
                        extracted_site = f"site-{first_part[1:]}"
                    elif first_part.startswith("site"):
                        # site-002 → site-002
                        extracted_site = first_part

                equipment_list.append({
                    "id": eq.get("id") or "",
                    "site_id": extracted_site or "unknown",
                    "site_name": eq.get("site_name") or "",
                    "type": eq.get("type") or "unknown",
                    "name": eq.get("name") or "Unknown Equipment",
                    "code": eq.get("code") or "",
                    "manufacturer": eq.get("manufacturer") or "Unknown",
                    "model": eq.get("model") or "Unknown",
                    "capacity": eq.get("capacity") or "N/A",
                    "install_date": eq.get("install_date") or "",
                    "last_service": eq.get("last_service") or "",
                    "status": eq.get("status") or "normal",
                    "health_score": int(eq.get("health_score") or 100),
                    "location": eq.get("location") or "",
                    "serial_number": eq.get("serial_number") or "",
                    "building_id": eq.get("building_id") or "",
                })

            logger.info(f"Loaded {len(equipment_list)} equipment items from Supabase")
            return equipment_list
    except Exception as e:
        logger.error(f"Failed to load from Supabase: {e}")

    # Fallback to CSV/JSON if Supabase fails
    try:
        # Load from CSV using the csv_loader service
        assets = AssetData.load()

        if assets:
            equipment_list = []
            for asset in assets:
                # Format dates as strings
                install_date = ""
                if asset.get("install_date"):
                    if isinstance(asset["install_date"], datetime):
                        install_date = asset["install_date"].strftime("%Y-%m-%d")
                    else:
                        install_date = str(asset["install_date"])

                last_service = ""
                if asset.get("last_service_date"):
                    if isinstance(asset["last_service_date"], datetime):
                        last_service = asset["last_service_date"].strftime("%Y-%m-%d")
                    else:
                        last_service = str(asset["last_service_date"])

                # Calculate health score from condition and age
                health_score = _derive_health_score(
                    asset.get("condition", "fair"),
                    asset.get("age_years", 0),
                    asset.get("expected_life_years", 20)
                )

                # Derive status from condition
                status = _derive_status(asset.get("condition", "fair"), health_score)

                # Derive capacity from asset category (approximate)
                capacity_map = {
                    "hvac-chiller": "300 tons",
                    "hvac-ahu": "10,000 CFM",
                    "hvac-cooling-tower": "500 tons",
                    "hvac-split": "24 kW",
                    "hvac-fcu": "6 kW",
                    "generator": "500 kVA",
                    "ups": "200 kVA",
                    "lift-passenger": "1600 kg",
                    "db-board": "3200A",
                }
                asset_category = asset.get("asset_category", "").lower()
                capacity = capacity_map.get(asset_category, "N/A")

                equipment_list.append({
                    "id": asset.get("asset_id", ""),
                    "site_id": asset.get("site_id", "").lower(),  # Normalize to lowercase
                    "site_name": asset.get("site_name", ""),
                    "type": asset.get("asset_category", "unknown"),
                    "name": asset.get("asset_tag", "Unknown Equipment"),
                    "manufacturer": asset.get("make", "Unknown"),
                    "model": asset.get("model", "Unknown"),
                    "capacity": capacity,
                    "install_date": install_date,
                    "last_service": last_service,
                    "status": status,
                    "health_score": health_score,
                    "location": asset.get("site_name", ""),
                    "serial_number": asset.get("serial_number", ""),
                    "condition": asset.get("condition", "fair"),
                    "criticality": asset.get("criticality", "standard"),
                    "notes": asset.get("notes", ""),
                    "age_years": asset.get("age_years", 0),
                    "expected_life_years": asset.get("expected_life_years", 20),
                    "remaining_life_years": asset.get("remaining_life_years", 0),
                })

            logger.info(f"Loaded {len(equipment_list)} equipment items from assets.csv (Supabase unavailable)")
            return equipment_list
    except Exception as e:
        logger.error(f"Failed to load from assets.csv: {e}")

    # Fallback to equipment.json if CSV loading fails
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        try:
            with open(equipment_file) as f:
                equipment_list = json.load(f)
                logger.info(f"Loaded {len(equipment_list)} equipment items from equipment.json (fallback)")
                return equipment_list
        except Exception as e:
            logger.error(f"Failed to load equipment.json: {e}")

    # Final fallback to simulation API
    logger.warning("No local data found, falling back to simulation API")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SIMULATION_API}/equipment", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                equipment_list = data.get("equipment", [])
                logger.info(f"Loaded {len(equipment_list)} equipment items from simulation API")
                return equipment_list
            else:
                logger.error(f"Simulation API returned {response.status_code}")
                return []
    except Exception as e:
        logger.error(f"Failed to load equipment from simulation API: {e}")
        return []


async def load_sensors() -> list[dict]:
    """Load sensors from sensors.json file (primary source)."""
    sensors_file = DATA_DIR / "sensors.json"
    if sensors_file.exists():
        try:
            with open(sensors_file) as f:
                sensors_list = json.load(f)
                logger.info(f"Loaded {len(sensors_list)} sensors from sensors.json")
                return sensors_list
        except Exception as e:
            logger.error(f"Failed to load sensors.json: {e}")

    # Fallback to simulation API only if JSON not available
    logger.warning("sensors.json not found, falling back to simulation API")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SIMULATION_API}/equipment", timeout=5.0)
            if response.status_code != 200:
                return []

            equipment_list = response.json().get("equipment", [])
            all_sensors = []

            for eq in equipment_list:
                # Convert sensor readings to sensor format
                for sensor_name, value in eq.get("sensor_readings", {}).items():
                    if isinstance(value, (int, float)):
                        sensor = {
                            "id": f"{eq['id']}_{sensor_name.upper()}",
                            "equipment_id": eq["id"],
                            "name": f"{eq['name']} {sensor_name.replace('_', ' ').title()}",
                            "type": "temperature" if "temp" in sensor_name.lower() else "pressure" if "press" in sensor_name.lower() else "generic",
                            "unit": "°C" if "temp" in sensor_name.lower() else "bar" if "press" in sensor_name.lower() else "-",
                            "current_value": value,
                            "timestamp": eq.get("timestamp", ""),
                            "quality": "good"
                        }
                        all_sensors.append(sensor)

            logger.info(f"Loaded {len(all_sensors)} sensors from simulation API")
            return all_sensors
    except Exception as e:
        logger.error(f"Failed to load sensors from simulation API: {e}")
        return []


async def load_alerts() -> list[dict]:
    """Load alerts from alarms.csv via csv_loader (primary source)."""
    try:
        # Load from CSV using the csv_loader service
        alarms = CSVAlarmData.load()

        if alarms:
            alerts_list = []
            for alarm in alarms:
                # Map severity to priority
                severity = alarm.get("severity", "minor").lower()
                priority_map = {"critical": 5, "major": 4, "minor": 2, "warning": 1}
                priority = priority_map.get(severity, 2)

                # Format timestamp
                triggered_at = ""
                if alarm.get("triggered_at"):
                    if isinstance(alarm["triggered_at"], datetime):
                        triggered_at = alarm["triggered_at"].isoformat()
                    else:
                        triggered_at = str(alarm["triggered_at"])

                alerts_list.append({
                    "id": alarm.get("alarm_id", ""),
                    "equipment_id": alarm.get("asset_id", ""),
                    "type": "alarm",
                    "severity": severity,
                    "title": f"{alarm.get('asset_tag', '')} - {alarm.get('alarm_code', '')}",
                    "description": alarm.get("alarm_description", ""),
                    "status": "cleared" if alarm.get("cleared_at") else "active",
                    "created_at": triggered_at,
                    "acknowledged": bool(alarm.get("acknowledged_at")),
                    "acknowledged_by": alarm.get("acknowledged_by", None),
                    "assigned_to": None,
                    "priority": priority,
                    "tags": ["alarm", alarm.get("source", "bms")],
                    "site_id": alarm.get("site_id", ""),
                    "site_name": alarm.get("site_name", ""),
                    "notes": alarm.get("notes", ""),
                })

            logger.info(f"Loaded {len(alerts_list)} alerts from alarms.csv")
            return alerts_list
    except Exception as e:
        logger.error(f"Failed to load from alarms.csv: {e}")

    # Fallback to alerts.json if CSV loading fails
    alerts_file = DATA_DIR / "alerts.json"
    if alerts_file.exists():
        try:
            with open(alerts_file) as f:
                alerts_list = json.load(f)
                logger.info(f"Loaded {len(alerts_list)} alerts from alerts.json (fallback)")
                return alerts_list
        except Exception as e:
            logger.error(f"Failed to load alerts.json: {e}")

    # Final fallback to simulation API
    logger.warning("No local alert data found, falling back to simulation API")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SIMULATION_API}/equipment", timeout=5.0)
            if response.status_code != 200:
                return []

            equipment_list = response.json().get("equipment", [])
            all_alerts = []

            for eq in equipment_list:
                for fault_code in eq.get("fault_codes", []):
                    alert = {
                        "id": f"ALERT_{eq['id']}_{fault_code}",
                        "equipment_id": eq["id"],
                        "type": "fault",
                        "severity": "major" if "E14" in fault_code or "F21" in fault_code else "minor",
                        "title": f"{eq['name']} - Fault {fault_code}",
                        "description": f"Fault {fault_code} detected on {eq['name']}",
                        "status": "active",
                        "created_at": eq.get("timestamp", ""),
                        "acknowledged": False,
                        "assigned_to": None,
                        "priority": 4 if "E14" in fault_code or "F21" in fault_code else 2,
                        "tags": ["fault", "simulated"]
                    }
                    all_alerts.append(alert)

            logger.info(f"Loaded {len(all_alerts)} alerts from simulation API")
            return all_alerts
    except Exception as e:
        logger.error(f"Failed to load alerts from simulation API: {e}")
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
    raw_equipment = await load_equipment()
    sensors = await load_sensors()
    alerts = await load_alerts()

    # Data is already transformed by load_equipment(), just ensure required fields exist
    equipment = []
    for eq in raw_equipment:
        transformed = {
            "id": eq.get("id", ""),
            "site_id": eq.get("site_id", "site-001"),
            "type": eq.get("type", "unknown"),
            "name": eq.get("name", "Unknown Equipment"),
            "manufacturer": eq.get("manufacturer", "Unknown"),
            "model": eq.get("model", "Unknown"),
            "capacity": eq.get("capacity", "N/A"),
            "install_date": eq.get("install_date", ""),
            "last_service": eq.get("last_service", ""),
            "status": eq.get("status", "normal"),
            "health_score": int(eq.get("health_score", 100)),
            "location": eq.get("location", ""),
            "serial_number": eq.get("serial_number", ""),
        }
        equipment.append(transformed)

    # Apply filters - normalize site_id comparison (handle both SITE-001 and site-001 formats)
    if site_id:
        site_id_lower = site_id.lower()
        equipment = [e for e in equipment if e["site_id"].lower() == site_id_lower]
    if equipment_type:
        # Match equipment type (handle hvac-chiller, hvac-ahu etc.)
        type_lower = equipment_type.lower()
        equipment = [e for e in equipment if type_lower in e["type"].lower() or e["type"].lower() == type_lower]
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
    raw_equipment = await load_equipment()
    sensors = await load_sensors()
    alerts = await load_alerts()

    raw_eq = next((e for e in raw_equipment if e["id"] == equipment_id), None)
    if not raw_eq:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    # Data is already transformed by load_equipment()
    eq = {
        "id": raw_eq.get("id", ""),
        "site_id": raw_eq.get("site_id", "site-001"),
        "type": raw_eq.get("type", "unknown"),
        "name": raw_eq.get("name", "Unknown Equipment"),
        "manufacturer": raw_eq.get("manufacturer", "Unknown"),
        "model": raw_eq.get("model", "Unknown"),
        "capacity": raw_eq.get("capacity", "N/A"),
        "install_date": raw_eq.get("install_date", ""),
        "last_service": raw_eq.get("last_service", ""),
        "status": raw_eq.get("status", "normal"),
        "health_score": int(raw_eq.get("health_score", 100)),
        "location": raw_eq.get("location", ""),
        "serial_number": raw_eq.get("serial_number", ""),
    }

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
            equipment_list = await load_equipment()
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
            all_sensors = await load_sensors()
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
            equipment_list = await load_equipment()
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
                all_sensors = await load_sensors()
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
    equipment = await load_equipment()

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
