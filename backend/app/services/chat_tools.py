
"""Chat tool handlers for Claude AI BMS intelligence.

This module implements the tool functions that Claude can call to:
- Query real-time device status and readings
- Control building devices with safety validation
- Get optimization recommendations
- Access alerts, anomalies, and maintenance status
- Provide intelligent suggestions for building operations
- Create work orders, approve/reject recommendations (operator+)
- Adjust setpoints and reset equipment faults (operator+)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.site_resolver import get_primary_site_code
from app.database.repositories.module_access_repository import get_module_access_repository
from app.database.supabase_client import get_supabase_client
from app.models.auth import ROLE_HIERARCHY, SentinelRole
from app.models.device import DeviceStatus
from app.models.module_registry import ModuleType
from app.services.chat_tools_service_history import get_equipment_service_history
from app.services.device_abstraction import device_manager
from app.services.health_threshold_service import get_health_thresholds
from app.services.module_registry_service import module_registry
from app.utils.calm_harness import calm_error_legacy

logger = logging.getLogger(__name__)


def _default_site_id() -> str:
    """Resolve the default site from the registered building list."""
    return get_primary_site_code() or "unknown"


# Data directory for building data
DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(filename: str) -> list | dict:
    """Load JSON data file."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


async def list_devices(device_type: str | None = None, site_id: str | None = None) -> dict[str, Any]:
    """
    List available devices with optional filtering.

    Args:
        device_type: Filter by device type (hvac, lighting, security, etc.)
        site_id: Filter by site ID

    Returns:
        Dictionary with list of devices
    """
    try:
        devices = await device_manager.list_devices()

        # Apply filters
        if device_type:
            devices = [d for d in devices if d.device_type.value == device_type.lower()]
        if site_id:
            devices = [d for d in devices if d.site_id == site_id]

        # Convert to simplified format for Claude
        device_list = []
        for device in devices:
            device_list.append(
                {
                    "id": device.id,
                    "name": device.name,
                    "type": device.device_type.value,
                    "status": device.status.value,
                    "location": device.location,
                    "site_id": device.site_id,
                }
            )

        return {"success": True, "count": len(device_list), "devices": device_list}
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="list_devices")


async def get_device_details(device_id: str) -> dict[str, Any]:
    """
    Get detailed information about a specific device.

    Args:
        device_id: The device ID to look up

    Returns:
        Dictionary with device details, current values, and safety status
    """
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            return {"success": False, "error": f"Device '{device_id}' not found"}

        # Get adapter for reading current values
        adapter = await device_manager.get_adapter(device_id)

        # Read current values for all points
        point_values = {}
        if adapter and adapter._connected:
            for point_name in device.points:
                try:
                    value = await adapter.read_value(point_name)
                    point_values[point_name] = {
                        "value": value.value,
                        "unit": value.unit,
                        "timestamp": value.timestamp,
                        "quality": value.quality,
                    }
                except Exception as e:
                    point_values[point_name] = {"error": calm_error_legacy(e, tool_name="get_device_details")["error"]}

        # Get safety status
        try:
            safety_status = await device_manager.get_device_safety_status(device_id)
        except Exception as e:
            safety_status = {"error": calm_error_legacy(e, tool_name="get_device_details")["error"]}

        # Build point definitions
        points_info = {}
        for name, point in device.points.items():
            points_info[name] = {
                "description": point.description,
                "unit": point.unit,
                "writable": point.writable,
                "min_value": point.min_value,
                "max_value": point.max_value,
                "current_value": point_values.get(name, {}).get("value"),
            }

        return {
            "success": True,
            "device": {
                "id": device.id,
                "name": device.name,
                "type": device.device_type.value,
                "status": device.status.value,
                "location": device.location,
                "site_id": device.site_id,
                "description": device.description,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "last_seen": device.last_seen,
            },
            "points": points_info,
            "safety_status": safety_status,
        }
    except Exception as e:
        logger.error(f"Error getting device details for {device_id}: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="get_device_details")


async def control_device(
    device_id: str,
    point: str,
    value: Any,
    reason: str = "AI assistant control",
    _user_email: str | None = None,
) -> dict[str, Any]:
    """
    Execute a control action on a device.

    All control actions go through safety validation and are logged
    to the audit trail with the authenticated user's identity.

    Args:
        device_id: The device ID to control
        point: The point name to write (e.g., "setpoint", "state")
        value: The value to write
        reason: Reason for the control action (for audit log)
        _user_email: Authenticated user email (injected by execute_tool)

    Returns:
        Dictionary with success/failure and details
    """
    # User attribution: use real user identity, not generic label
    audit_user = _user_email or "ai-assistant"

    try:
        device = await device_manager.get_device(device_id)
        if not device:
            return {"success": False, "error": f"Device '{device_id}' not found"}

        # Check device is online
        if device.status not in [DeviceStatus.ONLINE, DeviceStatus.STANDBY]:
            return {
                "success": False,
                "error": f"Device '{device.name}' is {device.status.value} and cannot be controlled",
            }

        # Check point exists and is writable
        device_point = device.get_point(point)
        if not device_point:
            available_points = list(device.points.keys())
            return {
                "success": False,
                "error": f"Point '{point}' not found on device '{device.name}'. Available points: {available_points}",
            }

        if not device_point.writable:
            return {"success": False, "error": f"Point '{point}' is read-only and cannot be controlled"}

        # Get current value for response
        old_value = None
        try:
            current = await device_manager.read_device_value(device_id, point)
            old_value = current.value
        except Exception as e:
            logger.warning(f"write_device_value: could not read old value for {device_id}/{point}: {e}", exc_info=True)

        # Execute control with safety validation — audit with real user identity
        success = await device_manager.write_device_value(
            device_id=device_id, point_name=point, value=value, user=audit_user
        )

        if success:
            return {
                "success": True,
                "device_name": device.name,
                "device_id": device_id,
                "point": point,
                "old_value": old_value,
                "new_value": value,
                "unit": device_point.unit,
                "message": f"Successfully set {point} to {value}{device_point.unit} on {device.name}",
                "reason": reason,
            }
        else:
            return {"success": False, "error": "Failed to write value to device. The device may be unresponsive."}

    except ValueError as e:
        # Safety validation failures come as ValueError
        error_msg = calm_error_legacy(e, tool_name="control_device")["error"]
        logger.warning(f"Control blocked for {device_id}.{point}={value}: {e}")
        return {
            "success": False,
            "blocked": True,
            "error": error_msg,
            "device_id": device_id,
            "point": point,
            "attempted_value": value,
        }
    except Exception as e:
        logger.error(f"Error controlling device {device_id}.{point}={value}: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="control_device")


async def get_system_status(site_id: str | None = None) -> dict[str, Any]:
    """
    Get overall BMS system status including alerts, anomalies, and equipment health from Supabase.

    Args:
        site_id: Optional site ID/code to filter status (e.g., the registered building code)

    Returns:
        Dictionary with system status, active alerts, predicted issues, and recommendations
    """
    try:
        client = get_supabase_client()
        thresholds = get_health_thresholds()

        # Get building info
        site_uuid = None
        site_name = None
        if site_id:
            building_resp = client.table("sites").select("id, name, code").eq("code", site_id).execute()
            if building_resp.data:
                site_uuid = building_resp.data[0]["id"]
                site_name = building_resp.data[0]["name"]
            else:
                return {
                    "success": False,
                    "error": f"Site '{site_id}' not found in the system",
                    "available_sites": "Use get_equipment_health without site_id to see all sites",
                }

        # Get equipment for site
        eq_query = client.table("equipment").select("id, code, name, type, health_score, status, last_service")
        if site_uuid:
            eq_query = eq_query.eq("site_id", site_uuid)
        eq_resp = eq_query.execute()
        equipment = eq_resp.data if eq_resp.data else []

        # Get active alerts for site
        alerts_query = (
            client.table("alerts")
            .select("id, type, severity, message, status, created_at, equipment_id")
            .eq("status", "active")
        )
        if site_uuid:
            alerts_query = alerts_query.eq("site_id", site_uuid)
        alerts_resp = alerts_query.execute()
        alerts = alerts_resp.data if alerts_resp.data else []

        # Get predictions for site
        pred_query = (
            client.table("predictions")
            .select("id, equipment_id, prediction_type, probability_percent, status, equipment(code, name, site_id)")
            .eq("status", "active")
        )
        pred_resp = pred_query.execute()
        predictions = pred_resp.data if pred_resp.data else []
        if site_uuid:
            predictions = [p for p in predictions if p.get("equipment", {}).get("site_id") == site_uuid]

        # Count sites
        sites_resp = client.table("sites").select("id").execute()
        total_sites = len(sites_resp.data) if sites_resp.data else 0

        # Active alerts summary
        active_alerts = [a for a in alerts if a.get("status") == "active"]
        critical_alerts = [a for a in active_alerts if a.get("severity") == "critical"]
        warning_alerts = [a for a in active_alerts if a.get("severity") == "warning"]

        # Equipment health summary
        healthy_equipment = [e for e in equipment if (e.get("health_score") or 100) >= thresholds["healthy"]]
        degraded_equipment = [
            e for e in equipment if thresholds["warning"] <= (e.get("health_score") or 100) < thresholds["healthy"]
        ]
        critical_equipment = [e for e in equipment if (e.get("health_score") or 100) < thresholds["warning"]]

        # High-priority predictions
        urgent_predictions = [p for p in predictions if p.get("probability_percent", 0) >= 70]

        # Build alerts lookup by equipment_id for enrichment
        alerts_by_equipment = {}
        for a in active_alerts:
            eq_id = a.get("equipment_id")
            if eq_id:
                alerts_by_equipment.setdefault(eq_id, []).append(a)

        # Build predictions lookup by equipment_id for enrichment
        preds_by_equipment = {}
        for p in predictions:
            eq_id = p.get("equipment_id")
            if eq_id:
                preds_by_equipment.setdefault(eq_id, []).append(p)

        # Build status response
        status = {
            "success": True,
            "site_id": site_id,
            "site_name": site_name,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_sites": total_sites if not site_id else 1,
                "total_equipment": len(equipment),
                "equipment_healthy": len(healthy_equipment),
                "equipment_degraded": len(degraded_equipment),
                "equipment_critical": len(critical_equipment),
                "active_alerts": len(active_alerts),
                "critical_alerts": len(critical_alerts),
                "warning_alerts": len(warning_alerts),
                "urgent_predictions": len(urgent_predictions),
            },
            "critical_issues": [],
            "degraded_equipment": [],
            "active_predictions": [],
            "recommendations": [],
        }

        # Add critical issues
        for alert in critical_alerts[:5]:
            status["critical_issues"].append(
                {
                    "type": "alert",
                    "id": alert["id"],
                    "severity": "critical",
                    "title": alert.get("type", "Alert"),
                    "message": alert.get("message"),
                    "equipment_id": alert.get("equipment_id"),
                }
            )

        for eq in critical_equipment[:5]:
            eq_id = eq.get("id")
            eq_alerts = alerts_by_equipment.get(eq_id, [])
            eq_preds = preds_by_equipment.get(eq_id, [])
            status["critical_issues"].append(
                {
                    "type": "equipment_health",
                    "id": eq.get("code") or eq["id"],
                    "name": eq["name"],
                    "health_score": eq.get("health_score", 0),
                    "status": eq.get("status"),
                    "last_service": eq.get("last_service"),
                    "active_alerts": [
                        {"severity": a.get("severity"), "message": a.get("message")} for a in eq_alerts[:3]
                    ],
                    "predictions": [
                        {
                            "id": p.get("id"),
                            "type": p.get("prediction_type"),
                            "probability_percent": p.get("probability_percent"),
                        }
                        for p in eq_preds[:2]
                    ],
                }
            )

        # Add degraded equipment details so Claude has full context
        for eq in degraded_equipment[:10]:
            eq_id = eq.get("id")
            eq_alerts = alerts_by_equipment.get(eq_id, [])
            eq_preds = preds_by_equipment.get(eq_id, [])
            status["degraded_equipment"].append(
                {
                    "id": eq.get("code") or eq["id"],
                    "name": eq.get("name"),
                    "type": eq.get("type"),
                    "health_score": eq.get("health_score", 0),
                    "status": eq.get("status"),
                    "last_service": eq.get("last_service"),
                    "active_alerts": [
                        {"severity": a.get("severity"), "message": a.get("message")} for a in eq_alerts[:3]
                    ],
                    "predictions": [
                        {
                            "id": p.get("id"),
                            "type": p.get("prediction_type"),
                            "probability_percent": p.get("probability_percent"),
                        }
                        for p in eq_preds[:2]
                    ],
                }
            )

        # Add active predictions with equipment context
        for pred in predictions[:10]:
            eq_info = pred.get("equipment", {}) or {}
            status["active_predictions"].append(
                {
                    "id": pred.get("id"),
                    "equipment_code": eq_info.get("code"),
                    "equipment_name": eq_info.get("name"),
                    "prediction_type": pred.get("prediction_type"),
                    "probability_percent": pred.get("probability_percent", 0),
                }
            )

        # Add proactive recommendations based on system state
        if len(critical_alerts) > 0:
            status["recommendations"].append(
                {
                    "priority": "high",
                    "action": "Address critical alerts immediately",
                    "details": f"{len(critical_alerts)} critical alerts require immediate attention",
                }
            )

        if len(critical_equipment) > 0:
            status["recommendations"].append(
                {
                    "priority": "high",
                    "action": "Schedule maintenance for critical equipment",
                    "details": f"{len(critical_equipment)} equipment items below {thresholds['warning']}% health",
                }
            )

        if len(degraded_equipment) > 0:
            status["recommendations"].append(
                {
                    "priority": "medium",
                    "action": "Plan preventive maintenance",
                    "details": (
                        f"{len(degraded_equipment)} equipment items showing degradation "
                        f"({thresholds['warning']}-{thresholds['healthy']}% health)"
                    ),
                }
            )

        for pred in urgent_predictions[:3]:
            eq_info = pred.get("equipment", {}) or {}
            status["recommendations"].append(
                {
                    "priority": "medium",
                    "action": f"Preventive maintenance: {eq_info.get('name', 'Unknown')}",
                    "details": f"{pred.get('probability_percent', 0)}% failure probability predicted",
                }
            )

        return status

    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="get_system_status")


async def get_optimization_recommendations(site_id: str) -> dict[str, Any]:
    """
    Get AI-powered optimization recommendations for a site.

    Analyzes current conditions, weather, and energy pricing to suggest
    optimal HVAC setpoints for energy efficiency and comfort.

    Args:
        site_id: Site ID to analyze

    Returns:
        Dictionary with optimization recommendations and projected savings
    """
    try:
        from app.services.ai_optimizer import get_ai_optimizer

        recommendation = await get_ai_optimizer().analyze_building(site_id)

        return {
            "success": True,
            "site_id": site_id,
            "timestamp": recommendation.timestamp,
            "recommendations": recommendation.recommendations,
            "projected_savings": recommendation.projected_savings,
            "confidence": recommendation.confidence,
            "reasoning": recommendation.reasoning,
            "note": "These are AI-generated recommendations. Use control_device to apply them after review.",
        }
    except ValueError as e:
        return {"success": False} | calm_error_legacy(e, tool_name="get_optimization_recommendations")
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="get_optimization_recommendations")


async def get_equipment_health(
    site_id: str | None = None, equipment_id: str | None = None, status_filter: str | None = None
) -> dict[str, Any]:
    """
    Get equipment health status and maintenance information from Supabase.

    Args:
        site_id: Optional site ID/code to filter (e.g., the registered building code)
        equipment_id: Optional specific equipment ID
        status_filter: Filter by status (critical, warning, normal)

    Returns:
        Dictionary with equipment health details and maintenance recommendations
    """
    try:
        client = get_supabase_client()
        thresholds = get_health_thresholds()

        # Build equipment query from Supabase
        query = client.table("equipment").select(
            "id, code, name, type, health_score, status, last_service, "
            "install_date, manufacturer, model, location, device_info, site_id, buildings(code, name, floors, sqm)"
        )

        # Filter by site if provided
        if site_id:
            # First get building UUID from site code
            building_resp = client.table("sites").select("id").eq("code", site_id).execute()
            if building_resp.data:
                site_uuid = building_resp.data[0]["id"]
                query = query.eq("site_id", site_uuid)
            else:
                return {"success": False, "error": f"Site '{site_id}' not found", "count": 0, "equipment": []}

        # Filter by equipment ID if provided
        if equipment_id:
            query = query.eq("code", equipment_id)

        # Filter by health status
        if status_filter:
            if status_filter == "critical":
                query = query.lt("health_score", thresholds["critical"])
            elif status_filter == "warning":
                query = query.gte("health_score", thresholds["critical"]).lt("health_score", thresholds["healthy"])
            elif status_filter == "normal":
                query = query.gte("health_score", thresholds["healthy"])

        # Execute query
        equipment_resp = query.order("health_score").execute()
        equipment_data = equipment_resp.data if equipment_resp.data else []

        # Get predictions from Supabase
        pred_query = (
            client.table("predictions").select("equipment_id, probability_percent, status").eq("status", "active")
        )
        pred_resp = pred_query.execute()
        predictions = pred_resp.data if pred_resp.data else []

        # Build predictions lookup by equipment_id
        pred_by_equipment = {}
        for pred in predictions:
            eq_id = pred.get("equipment_id")
            if eq_id:
                if eq_id not in pred_by_equipment:
                    pred_by_equipment[eq_id] = []
                pred_by_equipment[eq_id].append(pred)

        # Build response
        equipment_list = []
        for eq in equipment_data:
            eq_id = eq.get("id")
            eq_preds = pred_by_equipment.get(eq_id, [])
            highest_risk = max([p.get("probability_percent", 0) for p in eq_preds], default=0)
            health_score = eq.get("health_score", 100) or 100

            # Get site code from joined building
            site_info = eq.get("sites", {}) or {}
            eq_site_id = site_info.get("code", "unknown")

            # Extract sensor reading from device_info if available
            device_info = eq.get("device_info") or {}
            current_reading = device_info.get("current_reading")
            reading_unit = device_info.get("unit")
            setpoint = device_info.get("setpoint")

            item = {
                "id": eq.get("code") or eq.get("id"),
                "name": eq.get("name"),
                "type": eq.get("type"),
                "site_id": eq_site_id,
                "location": eq.get("location"),
                "health_score": health_score,
                "status": eq.get("status", "unknown"),
                "last_service": eq.get("last_service"),
                "manufacturer": eq.get("manufacturer"),
                "model": eq.get("model"),
                "failure_risk_percent": highest_risk,
                "maintenance_due": health_score < thresholds["warning"] or highest_risk > 60,
            }

            # Add all device_info readings based on equipment type
            if device_info:
                # Common readings
                if current_reading is not None:
                    item["current_reading"] = current_reading
                    item["unit"] = reading_unit
                if setpoint is not None:
                    item["setpoint"] = setpoint

                # CO2 sensors
                if "co2" in item["name"].lower():
                    item["unit"] = "ppm"

                # Occupancy sensors
                if device_info.get("occupied") is not None:
                    item["occupied"] = device_info.get("occupied")
                    item["occupant_count"] = device_info.get("occupant_count", 0)

                # Lighting
                if device_info.get("brightness_percent") is not None:
                    item["brightness_percent"] = device_info.get("brightness_percent")
                    item["is_on"] = device_info.get("is_on", False)
                    item["power_watts"] = device_info.get("power_watts", 0)

                # Daylight sensors
                if device_info.get("current_lux") is not None:
                    item["current_lux"] = device_info.get("current_lux")
                    item["lux_setpoint"] = device_info.get("lux_setpoint")

                # HVAC (VAV, FCU, AHU)
                if device_info.get("supply_temp") is not None:
                    item["supply_temp"] = device_info.get("supply_temp")
                    item["return_temp"] = device_info.get("return_temp")
                if device_info.get("airflow_cfm") is not None:
                    item["airflow_cfm"] = device_info.get("airflow_cfm")
                    item["damper_position_percent"] = device_info.get("damper_position_percent")
                if device_info.get("fan_speed") is not None:
                    item["fan_speed"] = device_info.get("fan_speed")

                # Chillers
                if device_info.get("chw_supply_temp") is not None:
                    item["chw_supply_temp"] = device_info.get("chw_supply_temp")
                    item["chw_return_temp"] = device_info.get("chw_return_temp")
                    item["load_percent"] = device_info.get("load_percent")
                    item["power_kw"] = device_info.get("power_kw")

                # Generators (DSE8610 controller data)
                if device_info.get("fuel_level_percent") is not None:
                    item["generator_status"] = device_info.get("status")
                    item["control_mode"] = device_info.get("control_mode")
                    item["fuel_level_percent"] = device_info.get("fuel_level_percent")
                    item["runtime_hours"] = device_info.get("runtime_hours")
                    item["kwh_total"] = device_info.get("kwh_total")
                    # Engine
                    item["engine_rpm"] = device_info.get("engine_rpm")
                    item["engine_temp_c"] = device_info.get("engine_temp_c")
                    item["coolant_temp_c"] = device_info.get("coolant_temp")
                    item["oil_temp_c"] = device_info.get("oil_temp_c")
                    item["oil_pressure_kpa"] = device_info.get("oil_pressure_kpa")
                    item["battery_voltage"] = device_info.get("battery_voltage")
                    # Output (when running)
                    item["output_kw"] = device_info.get("output_kw")
                    item["output_kva"] = device_info.get("output_kva")
                    item["frequency_hz"] = device_info.get("frequency_hz")
                    # Mains monitoring
                    item["mains_healthy"] = device_info.get("mains_healthy")
                    item["load_transfer_status"] = device_info.get("load_transfer_status")
                    # Alarms
                    item["alarm_active"] = device_info.get("alarm_active")
                    item["alarm_count"] = device_info.get("alarm_count")
                    item["comms_status"] = device_info.get("comms_status")

                # Power meters
                if device_info.get("kw") is not None:
                    item["kw"] = device_info.get("kw")
                    item["kwh_today"] = device_info.get("kwh_today")
                    item["power_factor"] = device_info.get("power_factor")

                # UPS
                if device_info.get("battery_percent") is not None:
                    item["battery_percent"] = device_info.get("battery_percent")
                    item["load_percent"] = device_info.get("load_percent")
                    item["runtime_minutes"] = device_info.get("runtime_minutes")

                # BMS/SCADA (Desigo CC)
                if device_info.get("total_data_points") is not None:
                    item["total_data_points"] = device_info.get("total_data_points")
                    item["online_devices"] = device_info.get("online_devices")
                    item["offline_devices"] = device_info.get("offline_devices")
                    item["active_alarms"] = device_info.get("active_alarms")
                    item["unacknowledged_alarms"] = device_info.get("unacknowledged_alarms")
                    item["alarms_today"] = device_info.get("alarms_today")
                    item["subsystems"] = device_info.get("subsystems")
                    item["protocols"] = device_info.get("protocols")
                    # Energy
                    item["current_demand_kw"] = device_info.get("current_demand_kw")
                    item["peak_demand_kw"] = device_info.get("peak_demand_kw")
                    item["energy_today_kwh"] = device_info.get("energy_today_kwh")
                    item["cost_today_zar"] = device_info.get("cost_today_zar")
                    item["load_shedding_stage"] = device_info.get("load_shedding_stage")
                    # System
                    item["active_users"] = device_info.get("active_users")
                    item["historian_status"] = device_info.get("historian_status")
                    item["trend_logs_active"] = device_info.get("trend_logs_active")
                    item["active_schedules"] = device_info.get("active_schedules")
                    item["uptime_days"] = device_info.get("uptime_days")

                # BMS Controllers (Desigo PXC)
                if device_info.get("points_configured") is not None:
                    item["points_configured"] = device_info.get("points_configured")
                    item["points_online"] = device_info.get("points_online")
                    item["communication_status"] = device_info.get("communication_status")
                    item["firmware"] = device_info.get("firmware")
                    item["uptime_hours"] = device_info.get("uptime_hours")

            # Add recommendation if needed
            if health_score < thresholds["critical"]:
                item["recommendation"] = "Schedule immediate maintenance - equipment health critical"
            elif health_score < thresholds["warning"]:
                item["recommendation"] = "Plan preventive maintenance within 2 weeks"
            elif highest_risk > 70:
                item["recommendation"] = f"High failure risk ({highest_risk}%) - schedule inspection"

            equipment_list.append(item)

        # Get building info for site summary
        site_info = {}
        if site_id:
            building_resp = (
                client.table("sites").select("name, code, floors, sqm, address").eq("code", site_id).execute()
            )
            if building_resp.data:
                b = building_resp.data[0]
                site_info = {
                    "name": b.get("name"),
                    "code": b.get("code"),
                    "floors": b.get("floors"),
                    "sqm": b.get("sqm"),
                    "address": b.get("address"),
                }

        # Calculate summaries for different sensor/equipment types

        # Temperature sensors
        temp_readings = [
            e.get("current_reading")
            for e in equipment_list
            if e.get("current_reading") is not None and "temperature" in e.get("name", "").lower()
        ]
        temp_summary = {}
        if temp_readings:
            temp_summary = {
                "average": round(sum(temp_readings) / len(temp_readings), 1),
                "min": min(temp_readings),
                "max": max(temp_readings),
                "sensor_count": len(temp_readings),
                "unit": "°C",
            }

        # CO2 sensors
        co2_readings = [
            e.get("current_reading")
            for e in equipment_list
            if e.get("current_reading") is not None and "co2" in e.get("name", "").lower()
        ]
        co2_summary = {}
        if co2_readings:
            co2_summary = {
                "average": round(sum(co2_readings) / len(co2_readings)),
                "min": min(co2_readings),
                "max": max(co2_readings),
                "sensor_count": len(co2_readings),
                "unit": "ppm",
            }

        # Occupancy
        occ_sensors = [e for e in equipment_list if e.get("occupied") is not None]
        occupancy_summary = {}
        if occ_sensors:
            occupied_count = len([e for e in occ_sensors if e.get("occupied")])
            total_occupants = sum(e.get("occupant_count", 0) for e in occ_sensors)
            occupancy_summary = {
                "zones_occupied": occupied_count,
                "zones_vacant": len(occ_sensors) - occupied_count,
                "total_occupants": total_occupants,
                "occupancy_rate_percent": round(occupied_count / len(occ_sensors) * 100),
            }

        # Lighting
        light_groups = [e for e in equipment_list if e.get("brightness_percent") is not None]
        lighting_summary = {}
        if light_groups:
            lights_on = [e for e in light_groups if e.get("is_on")]
            total_power = sum(e.get("power_watts", 0) for e in lights_on)
            avg_brightness = (
                round(sum(e.get("brightness_percent", 0) for e in lights_on) / len(lights_on)) if lights_on else 0
            )
            lighting_summary = {
                "zones_on": len(lights_on),
                "zones_off": len(light_groups) - len(lights_on),
                "average_brightness_percent": avg_brightness,
                "total_power_watts": total_power,
            }

        # Daylight sensors
        lux_readings = [e.get("current_lux") for e in equipment_list if e.get("current_lux") is not None]
        daylight_summary = {}
        if lux_readings:
            daylight_summary = {
                "average_lux": round(sum(lux_readings) / len(lux_readings)),
                "min_lux": min(lux_readings),
                "max_lux": max(lux_readings),
                "sensor_count": len(lux_readings),
            }

        # HVAC (chillers)
        chillers = [e for e in equipment_list if e.get("chw_supply_temp") is not None]
        chiller_summary = {}
        if chillers:
            chiller_summary = {
                "count": len(chillers),
                "avg_load_percent": round(sum(e.get("load_percent", 0) for e in chillers) / len(chillers)),
                "total_power_kw": sum(e.get("power_kw", 0) for e in chillers),
                "avg_chw_supply_temp": round(sum(e.get("chw_supply_temp", 0) for e in chillers) / len(chillers), 1),
            }

        # Energy (power meters)
        meters = [e for e in equipment_list if e.get("kw") is not None]
        energy_summary = {}
        if meters:
            energy_summary = {
                "total_kw": round(sum(e.get("kw", 0) for e in meters), 1),
                "total_kwh_today": sum(e.get("kwh_today", 0) for e in meters),
                "avg_power_factor": round(sum(e.get("power_factor", 0) for e in meters) / len(meters), 2),
            }

        # Generators (DSE8610)
        generators = [e for e in equipment_list if e.get("fuel_level_percent") is not None]
        generator_summary = {}
        if generators:
            running_gens = [g for g in generators if g.get("generator_status") == "running"]
            alarm_gens = [g for g in generators if g.get("alarm_active")]
            generator_summary = {
                "count": len(generators),
                "status": "all_standby" if not running_gens else f"{len(running_gens)}_running",
                "running_count": len(running_gens),
                "avg_fuel_level_percent": round(
                    sum(e.get("fuel_level_percent", 0) for e in generators) / len(generators)
                ),
                "total_kwh": sum(e.get("kwh_total", 0) for e in generators),
                "total_runtime_hours": sum(e.get("runtime_hours", 0) for e in generators),
                "mains_healthy": all(e.get("mains_healthy", True) for e in generators),
                "load_transfer_status": generators[0].get("load_transfer_status") if generators else None,
                "alarms_active": len(alarm_gens),
                "comms_online": len([g for g in generators if g.get("comms_status") == "online"]),
            }
            if running_gens:
                generator_summary["total_output_kw"] = sum(g.get("output_kw", 0) for g in running_gens)
                generator_summary["avg_frequency_hz"] = round(
                    sum(g.get("frequency_hz", 0) for g in running_gens) / len(running_gens), 1
                )

        # BMS/SCADA (Desigo CC)
        bms_systems = [e for e in equipment_list if e.get("total_data_points") is not None]
        bms_controllers = [e for e in equipment_list if e.get("points_configured") is not None]
        bms_summary = {}
        if bms_systems:
            bms = bms_systems[0]  # Main SCADA head-end
            bms_summary = {
                "head_end": bms.get("name"),
                "total_data_points": bms.get("total_data_points"),
                "online_devices": bms.get("online_devices"),
                "offline_devices": bms.get("offline_devices"),
                "active_alarms": bms.get("active_alarms"),
                "unacknowledged_alarms": bms.get("unacknowledged_alarms"),
                "subsystems_count": len(bms.get("subsystems", {})),
                "protocols": bms.get("protocols"),
                "current_demand_kw": bms.get("current_demand_kw"),
                "energy_today_kwh": bms.get("energy_today_kwh"),
                "cost_today_zar": bms.get("cost_today_zar"),
                "load_shedding_stage": bms.get("load_shedding_stage"),
                "active_users": bms.get("active_users"),
                "uptime_days": bms.get("uptime_days"),
                "controllers": len(bms_controllers),
                "total_controller_points": sum(c.get("points_configured", 0) for c in bms_controllers),
            }

        return {
            "success": True,
            "count": len(equipment_list),
            "site_id": site_id,
            "building": site_info,
            "equipment": equipment_list,
            "health_summary": {
                "critical_count": len([e for e in equipment_list if e["health_score"] < thresholds["critical"]]),
                "warning_count": len(
                    [e for e in equipment_list if thresholds["critical"] <= e["health_score"] < thresholds["healthy"]]
                ),
                "healthy_count": len([e for e in equipment_list if e["health_score"] >= thresholds["healthy"]]),
                "maintenance_due_count": len([e for e in equipment_list if e.get("maintenance_due")]),
            },
            "readings": {
                "temperature": temp_summary,
                "co2": co2_summary,
                "occupancy": occupancy_summary,
                "lighting": lighting_summary,
                "daylight": daylight_summary,
                "chillers": chiller_summary,
                "energy": energy_summary,
                "generators": generator_summary,
                "bms_scada": bms_summary,
            },
        }
    except Exception as e:
        logger.error(f"Error getting equipment health: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="get_equipment_health")


async def get_alerts_and_anomalies(
    site_id: str | None = None, severity: str | None = None, include_resolved: bool = False
) -> dict[str, Any]:
    """
    Get active alerts and detected anomalies from Supabase.

    Args:
        site_id: Optional site ID/code to filter (e.g., the registered building code)
        severity: Filter by severity (critical, warning, info)
        include_resolved: Include resolved/acknowledged alerts

    Returns:
        Dictionary with alerts and anomalies
    """
    try:
        client = get_supabase_client()

        # Get building UUID if site_id provided
        site_uuid = None
        if site_id:
            building_resp = client.table("sites").select("id").eq("code", site_id).execute()
            if building_resp.data:
                site_uuid = building_resp.data[0]["id"]

        # Build alerts query
        alerts_query = client.table("alerts").select(
            "id, type, severity, message, status, created_at, acknowledged_at, "
            "equipment_id, site_id, buildings(code, name), equipment(code, name)"
        )

        if not include_resolved:
            alerts_query = alerts_query.eq("status", "active")
        if site_uuid:
            alerts_query = alerts_query.eq("site_id", site_uuid)
        if severity:
            alerts_query = alerts_query.eq("severity", severity)

        alerts_resp = alerts_query.order("created_at", desc=True).limit(100).execute()
        alerts_data = alerts_resp.data if alerts_resp.data else []

        # Build predictions query (as anomalies)
        pred_query = (
            client.table("predictions")
            .select(
                "id, equipment_id, prediction_type, probability_percent, contributing_factors, "
                "recommended_action, status, created_at, equipment(code, name, site_id)"
            )
            .eq("status", "active")
        )

        if site_uuid:
            # Filter by equipment's building
            pred_resp = pred_query.execute()
            predictions_data = [p for p in (pred_resp.data or []) if p.get("equipment", {}).get("site_id") == site_uuid]
        else:
            pred_resp = pred_query.limit(10).execute()
            predictions_data = pred_resp.data if pred_resp.data else []

        # Format alerts
        formatted_alerts = []
        for alert in alerts_data:
            site_info = alert.get("sites", {}) or {}
            equipment_info = alert.get("equipment", {}) or {}
            formatted_alerts.append(
                {
                    "id": alert["id"],
                    "severity": alert.get("severity"),
                    "title": alert.get("type", "Alert"),
                    "description": alert.get("message"),
                    "site_id": site_info.get("code"),
                    "site_name": site_info.get("name"),
                    "equipment_id": equipment_info.get("code"),
                    "equipment_name": equipment_info.get("name"),
                    "status": alert.get("status"),
                    "created_at": alert.get("created_at"),
                }
            )

        # Format predictions as anomalies
        formatted_anomalies = []
        for pred in predictions_data[:10]:
            equipment_info = pred.get("equipment", {}) or {}
            formatted_anomalies.append(
                {
                    "id": pred["id"],
                    "type": pred.get("prediction_type"),
                    "urgency": "critical"
                    if pred.get("probability_percent", 0) > 80
                    else "high"
                    if pred.get("probability_percent", 0) > 60
                    else "medium",
                    "equipment_id": equipment_info.get("code"),
                    "equipment_name": equipment_info.get("name"),
                    "predicted_failure": pred.get("prediction_type"),
                    "probability_percent": pred.get("probability_percent"),
                    "contributing_factors": pred.get("contributing_factors"),
                    "recommended_action": pred.get("recommended_action"),
                }
            )

        return {
            "success": True,
            "site_id": site_id,
            "alerts": {
                "count": len(formatted_alerts),
                "items": formatted_alerts,
            },
            "anomalies": {
                "count": len(formatted_anomalies),
                "items": formatted_anomalies,
            },
            "summary": {
                "total_active_alerts": len([a for a in formatted_alerts if a.get("status") == "active"]),
                "critical_alerts": len([a for a in formatted_alerts if a.get("severity") == "critical"]),
                "warning_alerts": len([a for a in formatted_alerts if a.get("severity") == "warning"]),
                "high_risk_predictions": len([a for a in formatted_anomalies if a.get("probability_percent", 0) > 70]),
            },
        }
    except Exception as e:
        logger.error(f"Error getting alerts and anomalies: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="get_alerts_and_anomalies")


async def get_energy_analysis(site_id: str) -> dict[str, Any]:
    """
    Get energy consumption analysis and efficiency recommendations.

    Args:
        site_id: Site ID to analyze

    Returns:
        Dictionary with energy data and efficiency suggestions
    """
    try:
        sites = load_json("sites.json")
        site = next((s for s in sites if s["id"] == site_id), None)
        if not site:
            return {"success": False, "error": f"Site '{site_id}' not found"}

        # Get device readings for energy analysis
        devices = await device_manager.list_devices_by_site(site_id)

        # Gather current readings
        readings = {}
        for device in devices:
            adapter = await device_manager.get_adapter(device.id)
            if adapter and adapter._connected:
                device_readings = {}
                for point_name in device.points:
                    try:
                        value = await adapter.read_value(point_name)
                        device_readings[point_name] = {"value": value.value, "unit": value.unit}
                    except Exception as e:
                        logger.warning(
                            f"get_device_readings_batch: failed to read {point_name} on {device.id}: {e}", exc_info=True
                        )
                if device_readings:
                    readings[device.id] = {
                        "device_name": device.name,
                        "type": device.device_type.value,
                        "readings": device_readings,
                    }

        # Generate energy insights based on readings
        insights = []
        suggestions = []

        # Check HVAC efficiency
        for _device_id, data in readings.items():
            if data["type"] == "hvac":
                r = data["readings"]
                # Check temperature differential
                if "supply_temp" in r and "return_temp" in r:
                    diff = r["return_temp"]["value"] - r["supply_temp"]["value"]
                    if diff < 4:
                        insights.append(
                            f"{data['device_name']}: Low temperature differential"
                            f" ({diff:.1f}°C) indicates reduced cooling efficiency"
                        )
                        suggestions.append(f"Check {data['device_name']} for coil fouling or low refrigerant")

                # Check setpoints
                if "setpoint" in r:
                    setpoint = r["setpoint"]["value"]
                    if setpoint < 22:
                        suggestions.append(
                            f"Consider raising {data['device_name']} setpoint"
                            f" from {setpoint}°C to 23°C for energy savings"
                        )

        # Check lighting usage
        for _device_id, data in readings.items():
            if data["type"] == "lighting":
                r = data["readings"]
                if "brightness" in r and r["brightness"]["value"] > 80:
                    suggestions.append(
                        f"Consider reducing {data['device_name']} brightness"
                        f" from {r['brightness']['value']}%"
                        " during off-peak hours"
                    )

        return {
            "success": True,
            "site_id": site_id,
            "site_name": site["name"],
            "timestamp": datetime.now().isoformat(),
            "current_readings": readings,
            "insights": insights if insights else ["System operating within normal parameters"],
            "efficiency_suggestions": suggestions
            if suggestions
            else ["No immediate efficiency improvements identified"],
            "tip": "Use get_optimization_recommendations for AI-powered setpoint optimization",
        }
    except Exception as e:
        logger.error(f"Error getting energy analysis: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="get_energy_analysis")


async def get_floor_temperatures(floor: str | None = None, site_id: str | None = None) -> dict:
    """Get zone temperatures filtered by floor. Called when user asks about floor temps.

    Args:
        floor: Floor level to filter by: 'L0', 'L1', 'L2'. Omit for all floors.
        site_id: Site ID (resolved from registered building)

    Returns:
        Dictionary with zone temperatures, setpoints, and status
    """
    try:
        zones = load_json("hvac_zones.json")

        if floor:
            zones = [z for z in zones if z.get("floor", "").upper() == floor.upper()]

        return {
            "success": True,
            "site_id": site_id or _default_site_id(),
            "floor_filter": floor,
            "zone_count": len(zones),
            "zones": [
                {
                    "zone_id": z.get("zone_id"),
                    "zone_name": z.get("zone_name"),
                    "floor": z.get("floor"),
                    "current_temp": z.get("current_temp"),
                    "setpoint": z.get("setpoint"),
                    "status": z.get("status"),
                }
                for z in zones
            ],
        }
    except Exception as e:
        logger.error(f"Error getting floor temperatures: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="get_floor_temperatures")


async def lookup_desk(desk_id: str, building: str | None = None) -> dict[str, Any]:
    """
    Look up a desk and return its zone, HVAC, and sensor context.

    Queries Supabase for desk and zone data. Desk IDs encode the floor:
    L0=001-100, L1=101-200, L2=201-300. Each zone has 20 desks and
    linked HVAC equipment (FCU, VAV, AHU).

    Args:
        desk_id: Desk identifier (e.g., "205", "desk 205", "25")
        building: Optional building code (defaults to the primary registered building).

    Returns:
        Dictionary with desk info, zone, HVAC status, and DALI sensor data
    """
    try:
        import re

        # Normalize desk ID - extract number from various formats
        raw = str(desk_id).strip().lower().replace("desk", "").strip()
        desk_num = re.sub(r"[^0-9]", "", raw)
        if not desk_num:
            return {
                "success": False,
                "error": f"Invalid desk ID format: {desk_id}",
                "prompt_user": (
                    f"I couldn't parse desk ID '{desk_id}'. "
                    "Please provide the desk number (e.g., 205 for Level 2 desk 5)."
                ),
            }

        # Zero-pad to 3 digits to match Supabase format
        desk_num_padded = desk_num.zfill(3)

        # Query Supabase for desk
        client = get_supabase_client()

        if building:
            # Specific building requested — filter by site
            bld_resp = client.table("sites").select("id").eq("code", building).execute()
            if not bld_resp.data:
                return {
                    "success": False,
                    "error": f"Building {building} not found",
                    "prompt_user": f"Building '{building}' not found in the database.",
                }
            site_uuid = bld_resp.data[0]["id"]
            desk_resp = (
                client.table("desks").select("*").eq("site_id", site_uuid).eq("desk_id", desk_num_padded).execute()
            )
        else:
            # No building specified — search across all sites
            desk_resp = client.table("desks").select("*").eq("desk_id", desk_num_padded).limit(1).execute()

        desk = desk_resp.data[0] if desk_resp.data else None
        site_uuid = desk.get("site_id") if desk else None

        # Resolve site_code from the desk's site_id for zone lookups
        site_code = building
        if desk and not site_code and site_uuid:
            code_resp = client.table("sites").select("code").eq("id", site_uuid).execute()
            site_code = code_resp.data[0]["code"] if code_resp.data else _default_site_id()

        if not desk:
            # Show nearby desks from the same floor for guidance
            floor_prefix = desk_num_padded[0] if len(desk_num_padded) >= 2 else "0"
            floor_map = {"0": "L0", "1": "L1", "2": "L2", "3": "L3"}
            floor = floor_map.get(floor_prefix, "L0")

            nearby_query = client.table("desks").select("desk_id, zone_id")
            if site_uuid:
                nearby_query = nearby_query.eq("site_id", site_uuid)
            nearby_resp = nearby_query.eq("floor", floor).order("desk_id").limit(10).execute()
            nearby = [d["desk_id"] for d in (nearby_resp.data or [])]

            return {
                "success": False,
                "error": f"Desk {desk_num_padded} not found",
                "prompt_user": (
                    f"Desk {desk_num_padded} not found on {floor}."
                    f" Available desks on {floor} include: {', '.join(nearby)}..."
                    if nearby
                    else (
                        f"Desk {desk_num_padded} not found. "
                        f"Desks are numbered 001-100 (L0), 101-200 (L1), 201-300 (L2)."
                    )
                ),
                "available_sample": nearby,
            }

        # Get zone info from zones table
        zone_id = desk.get("zone_id")
        zone = None
        if zone_id:
            zone_resp = client.table("zones").select("*").eq("site_id", site_uuid).eq("zone_id", zone_id).execute()
            zone = zone_resp.data[0] if zone_resp.data else None

        # Get DALI/occupancy context
        dali_context = {}
        try:
            from app.services.cross_system_analyzer import get_cross_system_analyzer

            analyzer = get_cross_system_analyzer()
            if zone_id:
                zone_analysis = analyzer.dali.get_zone_analysis(zone_id)
                dali_context = {
                    "occupancy_percent": zone_analysis.get("occupancy_percent", 0),
                    "avg_lux": zone_analysis.get("average_lux", 0),
                    "sensors_active": zone_analysis.get("occupied_count", 0),
                    "total_sensors": zone_analysis.get("total_sensors", 0),
                    "high_daylight": zone_analysis.get("average_lux", 0) > 800,
                }
        except Exception as e:
            logger.warning(f"Could not get DALI context: {e}")
            dali_context = {"available": False, "reason": calm_error_legacy(e, tool_name="lookup_desk")["error"]}

        # Build response
        response = {
            "success": True,
            "desk": {
                "desk_id": desk.get("desk_id"),
                "floor": desk.get("floor"),
                "building": site_code,
                "zone_id": zone_id,
                "context": desk.get("context"),
                "near_window": desk.get("near_window", False),
                "near_diffuser": desk.get("near_diffuser", False),
                "near_printer": desk.get("near_printer", False),
                "orientation": desk.get("orientation"),
            },
            "zone": None,
            "hvac": None,
            "dali": dali_context,
            "context_flags": [],
        }

        # Add context flags for diagnosis
        if desk.get("near_window"):
            response["context_flags"].append("NEAR_WINDOW - Check for solar heat gain")
        if desk.get("near_diffuser"):
            response["context_flags"].append("NEAR_DIFFUSER - May experience direct airflow")
        if desk.get("near_printer"):
            response["context_flags"].append("NEAR_PRINTER - Local heat source")
        if dali_context.get("high_daylight"):
            response["context_flags"].append("HIGH_DAYLIGHT - Solar gain likely")

        # Add zone info with HVAC equipment
        if zone:
            response["zone"] = {
                "zone_id": zone.get("zone_id"),
                "zone_name": zone.get("zone_name"),
                "floor": zone.get("floor"),
                "zone_type": zone.get("zone_type"),
                "typical_occupancy": zone.get("typical_occupancy"),
                "setpoint": zone.get("setpoint"),
                "current_temp": zone.get("current_temp"),
                "status": zone.get("status"),
            }
            response["hvac"] = {
                "fcu_id": zone.get("fcu_id"),
                "vav_id": zone.get("vav_id"),
                "ahu_id": zone.get("ahu_id"),
                "temp_sensor": zone.get("temp_sensor"),
                "co2_sensor": zone.get("co2_sensor"),
                "humidity_sensor": zone.get("humidity_sensor"),
            }

        return response

    except Exception as e:
        logger.error(f"Error looking up desk {desk_id}: {e}")
        return {
            "success": False,
            "error": calm_error_legacy(e, tool_name="lookup_desk")["error"],
            "prompt_user": (
                "I encountered an error looking up that desk. Can you provide more details about the location?"
            ),
        }


async def _get_zone_equipment_status(zone: dict, site_code: str) -> dict[str, Any]:
    """Query all equipment in a zone and return their status/health.

    Derives equipment codes from the zone-code naming convention:
    S002-{TYPE}-{ZONE_CODE}. Falls back to reading equipment operating_data
    for live readings when hvac_zone_history is unavailable.
    """
    client = get_supabase_client()
    zone_id = zone.get("zone_id", "")
    zone_code = zone_id.replace("Zone-", "")

    # Derive equipment codes from zone-code naming convention
    equip_candidates = [
        f"S002-FCU-{zone_code}",
        f"S002-VAV-{zone_code}",
    ]
    # Also check for legacy zone-record fields
    for key in ("fcu_id", "vav_id", "ahu_id", "temp_sensor", "co2_sensor", "humidity_sensor"):
        val = zone.get(key)
        if val and val not in equip_candidates:
            equip_candidates.append(val)

    equipment_status = {}
    if equip_candidates:
        resp = client.table("equipment").select("code, type, status, health_score").in_("code", equip_candidates).execute()
        for e in resp.data or []:
            equipment_status[e["code"]] = e

    # Also try zone-matching VAV and AHU by zone-code pattern
    for eq_type in ("VAV", "AHU"):
        candidate = f"S002-{eq_type}-{zone_code}"
        if candidate not in equipment_status:
            try:
                eq_resp = client.table("equipment").select("code, type, status, health_score").eq("code", candidate).limit(1).execute()
                if eq_resp.data:
                    equipment_status[eq_resp.data[0]["code"]] = eq_resp.data[0]
            except Exception:
                pass

    # Get live readings from FCU operating_data (most recent source)
    live_readings = {}
    fcu_code = f"S002-FCU-{zone_code}"
    if fcu_code in equipment_status:
        try:
            fcu_resp = client.table("equipment").select("operating_data").eq("code", fcu_code).limit(1).execute()
            if fcu_resp.data:
                op = fcu_resp.data[0].get("operating_data", {})
                for point_name, point_data in op.items():
                    if isinstance(point_data, dict):
                        live_readings[point_name] = point_data.get("value")
                    else:
                        live_readings[point_name] = point_data
        except Exception:
            pass

    # Also try hvac_zone_history if it exists (graceful fallback)
    try:
        bld_resp = client.table("sites").select("id").eq("code", site_code).execute()
        site_uuid = bld_resp.data[0]["id"] if bld_resp.data else None
        if site_uuid:
            hist_resp = (
                client.table("hvac_zone_history")
                .select("temp, humidity, co2, setpoint, status, occupancy, time")
                .eq("zone_id", zone_id)
                .eq("site_id", site_uuid)
                .order("time", desc=True)
                .limit(1)
                .execute()
            )
            if hist_resp.data:
                live_readings = {**live_readings, **hist_resp.data[0]}
    except Exception:
        pass  # hvac_zone_history may not exist — readings from operating_data are sufficient

    return {
        "equipment": equipment_status,
        "diffusers": [],
        "live_readings": live_readings,
        "equipment_count": len(equipment_status),
    }


async def diagnose_comfort_complaint(
    desk_id: str, complaint_type: str, building: str | None = None, additional_info: str | None = None
) -> dict[str, Any]:
    """
    Diagnose a comfort complaint for a specific desk.

    Queries ALL zone equipment (FCU, VAV, AHU, temp/CO2/humidity sensors,
    diffusers) and uses their status + readings for diagnosis.

    Args:
        desk_id: Desk identifier (e.g., "205")
        complaint_type: Type of complaint: "too_hot", "too_cold", "stuffy", "drafty"
        building: Optional building code (defaults to the primary registered building)
        additional_info: Any additional context from the technician

    Returns:
        Dictionary with diagnosis, root cause, confidence, and suggested actions
    """
    try:
        # First look up the desk
        desk_info = await lookup_desk(desk_id, building)

        if not desk_info.get("success"):
            return desk_info  # Pass through the error/prompt

        zone = desk_info.get("zone", {}) or {}
        hvac = desk_info.get("hvac", {}) or {}
        dali = desk_info.get("dali", {}) or {}
        desk = desk_info.get("desk", {}) or {}

        # Get ALL equipment status for this zone — use the site resolved from the desk
        site_code = desk.get("building") or building or _default_site_id()
        zone_equip = await _get_zone_equipment_status(zone, site_code)
        equipment = zone_equip["equipment"]
        live = zone_equip["live_readings"]
        diffusers = zone_equip["diffusers"]

        # Use live readings if available, fall back to zone table values
        current_temp = live.get("temp") or zone.get("current_temp") or 22
        current_humidity = live.get("humidity")
        current_co2 = live.get("co2")
        setpoint = live.get("setpoint") or zone.get("setpoint") or 22
        occupancy = live.get("occupancy")
        current_temp = float(current_temp)
        setpoint = float(setpoint)
        temp_diff = current_temp - setpoint

        # Get current time for solar analysis
        current_hour = datetime.now().hour
        is_afternoon = 12 <= current_hour <= 18
        is_morning = 6 <= current_hour <= 11

        # Check equipment health — any faulted equipment?
        faulted = [e for e in equipment.values() if e.get("status") == "fault" or (e.get("health_score") or 100) < 50]
        degraded = [e for e in equipment.values() if 50 <= (e.get("health_score") or 100) < 80]

        # Build equipment summary for the response
        equip_summary = {}
        for code, e in equipment.items():
            equip_summary[code] = {
                "type": e.get("type"),
                "status": e.get("status"),
                "health": e.get("health_score"),
            }

        # Build diagnosis
        diagnosis = {
            "success": True,
            "desk_id": desk_id,
            "complaint_type": complaint_type,
            "desk_info": desk,
            "zone_info": zone,
            "hvac_info": hvac,
            "dali_info": dali,
            "readings": {
                "temperature": current_temp,
                "setpoint": setpoint,
                "temp_diff": round(temp_diff, 1),
                "humidity": current_humidity,
                "co2_ppm": current_co2,
                "occupancy": occupancy,
            },
            "zone_equipment": equip_summary,
            "equipment_count": zone_equip["equipment_count"],
            "faulted_equipment": [
                k for k, e in equipment.items() if e.get("status") == "fault" or (e.get("health_score") or 100) < 50
            ],
            "diagnosis": None,
            "root_cause": None,
            "confidence": "medium",
            "suggested_actions": [],
            "auto_actions_taken": [],
            "dispatch_required": False,
        }

        # If any equipment is faulted, that's the likely cause regardless of complaint type
        if faulted:
            fault_codes = [f"{e.get('type')} {k}" for k, e in equipment.items() if e in faulted]
            diagnosis["root_cause"] = f"Equipment fault detected: {', '.join(fault_codes)}"
            diagnosis["confidence"] = "high"
            diagnosis["diagnosis"] = (
                f"Zone {zone.get('zone_id')} has {len(faulted)} faulted equipment: "
                f"{', '.join(fault_codes)}. This is the most likely cause of the {complaint_type} complaint."
            )
            diagnosis["suggested_actions"] = [
                f"Inspect faulted equipment: {', '.join(fault_codes)}",
                "Check equipment alerts for error codes",
                "Dispatch technician for repair",
            ]
            diagnosis["dispatch_required"] = True
            return diagnosis

        # Diagnose based on complaint type + full equipment context
        fcu_id = hvac.get("fcu_id", "unknown")
        vav_id = hvac.get("vav_id", "unknown")
        ahu_id = hvac.get("ahu_id", "unknown")
        ts_id = hvac.get("temp_sensor", "unknown")
        co2_id = hvac.get("co2_sensor", "unknown")
        rh_id = hvac.get("humidity_sensor", "unknown")
        diffuser_id = desk.get("diffuser_id") or (diffusers[0]["code"] if diffusers else "unknown")

        if complaint_type in ["too_hot", "hot"]:
            if desk.get("near_window") and is_afternoon:
                orientation = desk.get("orientation", "")
                solar_note = ""
                if orientation == "N":
                    solar_note = " North-facing window receives direct sun most of the day (southern hemisphere)."
                elif orientation == "E" and is_morning:
                    solar_note = " East-facing window receiving morning sun."
                elif orientation == "W" and is_afternoon:
                    solar_note = " West-facing window receiving afternoon sun."
                diagnosis["root_cause"] = "Solar heat gain from window"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = (
                    f"Desk {desk_id} is near a {orientation}-facing window at {current_hour}:00.{solar_note}"
                    f" Zone temp: {current_temp}°C (setpoint {setpoint}°C)."
                    f" Sensor {ts_id} reading confirmed."
                )
                diagnosis["suggested_actions"] = [
                    "Close blinds/shades near the desk",
                    f"Temporarily lower {fcu_id} setpoint by 2°C for 2 hours",
                    f"Verify {vav_id} damper is open to increase airflow",
                    "Offer to relocate user to shaded desk",
                ]
            elif dali.get("high_daylight"):
                diagnosis["root_cause"] = "High daylight/solar gain detected by DALI sensors"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = (
                    f"DALI sensors show {dali.get('avg_lux', 0)} lux at this location."
                    f" Zone temp: {current_temp}°C. Direct sunlight causing heat gain."
                )
                diagnosis["suggested_actions"] = [
                    "Reduce lighting levels (daylight harvesting)",
                    "Close blinds to reduce solar load",
                    f"Boost cooling via {fcu_id} temporarily",
                ]
            elif temp_diff > 1.5:
                diagnosis["root_cause"] = "Zone temperature above setpoint"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = (
                    f"Sensor {ts_id} reads {current_temp}°C — {temp_diff:.1f}°C above"
                    f" setpoint ({setpoint}°C). FCU {fcu_id} may be undersized or struggling."
                )
                if current_humidity and current_humidity > 60:
                    diagnosis["diagnosis"] += f" Humidity is high ({current_humidity}% via {rh_id})."
                if current_co2 and current_co2 > 800:
                    diagnosis["diagnosis"] += f" CO2 elevated ({current_co2}ppm via {co2_id}) — high occupancy."
                diagnosis["suggested_actions"] = [
                    f"Check FCU {fcu_id} — verify fan running and coil valve open",
                    f"Check VAV {vav_id} damper position — should be >70% open",
                    f"Verify temp sensor {ts_id} calibration",
                    f"Check AHU {ahu_id} supply air temperature",
                ]
                if degraded:
                    degraded_info = ", ".join(
                        e.get("type", "?") + " " + k for k, e in equipment.items() if e in degraded
                    )
                    diagnosis["suggested_actions"].append(f"Degraded equipment detected: {degraded_info}")
                diagnosis["dispatch_required"] = True
            elif desk.get("near_printer"):
                diagnosis["root_cause"] = "Local heat source (printer/equipment)"
                diagnosis["confidence"] = "medium"
                diagnosis["diagnosis"] = (
                    f"Desk {desk_id} is near a printer/heat source."
                    f" Zone temp: {current_temp}°C (setpoint {setpoint}°C) — zone HVAC is OK."
                    " Localized hot spot from equipment."
                )
                diagnosis["suggested_actions"] = [
                    "Relocate printer or add local extraction",
                    f"Open nearest diffuser {diffuser_id} wider for more airflow",
                    "Consider desk relocation",
                ]
            else:
                diagnosis["root_cause"] = "Unknown — requires investigation"
                diagnosis["confidence"] = "low"
                diag_parts = [f"Zone temp: {current_temp}°C (setpoint {setpoint}°C)."]
                if current_humidity:
                    diag_parts.append(f"Humidity: {current_humidity}% ({rh_id}).")
                if current_co2:
                    diag_parts.append(f"CO2: {current_co2}ppm ({co2_id}).")
                diag_parts.append("No obvious cause — needs on-site inspection.")
                diagnosis["diagnosis"] = " ".join(diag_parts)
                diagnosis["suggested_actions"] = [
                    f"Check diffusers near desk {desk_id} for blockages",
                    f"Verify VAV {vav_id} damper position",
                    f"Check CO2 sensor {co2_id} — high occupancy?",
                    f"Inspect FCU {fcu_id} filter condition",
                ]
                diagnosis["dispatch_required"] = True

        elif complaint_type in ["too_cold", "cold", "freezing"]:
            if desk.get("near_diffuser"):
                diagnosis["root_cause"] = "Direct airflow from supply diffuser"
                diagnosis["confidence"] = "high"
                diff_code = desk.get("diffuser_id") or diffuser_id
                diagnosis["diagnosis"] = (
                    f"Desk {desk_id} is near diffuser {diff_code}."
                    f" Cold supply air causing discomfort."
                    f" Zone temp: {current_temp}°C (setpoint {setpoint}°C)."
                )
                diagnosis["suggested_actions"] = [
                    f"Adjust VAV {vav_id} damper to reduce airflow to this area",
                    f"Install deflector on diffuser {diff_code}",
                    "Relocate user away from direct airflow",
                ]
                diagnosis["dispatch_required"] = True
            elif temp_diff < -1.5:
                diagnosis["root_cause"] = "Zone overcooling"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = (
                    f"Sensor {ts_id} reads {current_temp}°C — {abs(temp_diff):.1f}°C below"
                    f" setpoint ({setpoint}°C). Possible control issue."
                )
                diagnosis["suggested_actions"] = [
                    f"Raise {fcu_id} setpoint by 1-2°C",
                    f"Check {fcu_id} cooling valve — may be stuck open",
                    f"Verify temp sensor {ts_id} calibration",
                ]
            else:
                diagnosis["root_cause"] = "Personal comfort preference"
                diagnosis["confidence"] = "medium"
                diagnosis["diagnosis"] = (
                    f"Zone temp ({current_temp}°C) is close to setpoint ({setpoint}°C)."
                    " May be personal preference or localized draft."
                )
                if current_humidity and current_humidity < 30:
                    diagnosis["diagnosis"] += f" Low humidity ({current_humidity}%) can increase cold sensation."
                    diagnosis["suggested_actions"].append("Consider portable humidifier")
                diagnosis["suggested_actions"].extend(
                    [
                        "Offer desk heater (temporary)",
                        f"Check diffusers near desk for draft — closest: {diffuser_id}",
                        "Consider desk relocation to warmer area",
                    ]
                )

        elif complaint_type in ["stuffy", "poor_air", "stale"]:
            co2_high = current_co2 and current_co2 > 800
            humidity_high = current_humidity and current_humidity > 60
            occ_high = dali.get("occupancy_percent", 0) > 70 or (occupancy and occupancy > 15)

            if co2_high:
                diagnosis["root_cause"] = f"High CO2 ({current_co2}ppm) — poor ventilation"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = (
                    f"CO2 sensor {co2_id} reads {current_co2}ppm (>800ppm threshold). Fresh air intake insufficient."
                )
                if humidity_high:
                    diagnosis["diagnosis"] += f" Humidity also elevated: {current_humidity}% ({rh_id})."
                diagnosis["suggested_actions"] = [
                    f"Increase fresh air damper on AHU {ahu_id}",
                    f"Check VAV {vav_id} minimum airflow setting",
                    f"Verify CO2 sensor {co2_id} calibration",
                ]
            elif occ_high:
                diagnosis["root_cause"] = "High occupancy causing CO2 buildup"
                diagnosis["confidence"] = "high"
                occ_pct = dali.get("occupancy_percent", occupancy or 0)
                diagnosis["diagnosis"] = (
                    f"Zone occupancy ~{occ_pct}% — high density causing poor air quality."
                    f" CO2: {current_co2 or 'no reading'}ppm. Humidity: {current_humidity or 'no reading'}%."
                )
                diagnosis["suggested_actions"] = [
                    f"Increase fresh air damper on AHU {ahu_id}",
                    f"Boost VAV {vav_id} minimum airflow",
                    "Consider temporary portable air purifier",
                ]
            else:
                diagnosis["root_cause"] = "Insufficient ventilation"
                diagnosis["confidence"] = "medium"
                diagnosis["diagnosis"] = (
                    f"Air quality complaint. CO2: {current_co2 or 'no reading'}ppm ({co2_id})."
                    f" Humidity: {current_humidity or 'no reading'}% ({rh_id})."
                    " May be ventilation equipment issue."
                )
                diagnosis["suggested_actions"] = [
                    f"Check FCU {fcu_id} fan status — may be off or on low speed",
                    f"Verify AHU {ahu_id} fresh air damper position",
                    "Check for blocked return air grilles near desk",
                    f"Read CO2 sensor {co2_id} and humidity sensor {rh_id} directly",
                ]
                diagnosis["dispatch_required"] = True

        elif complaint_type in ["drafty", "draft", "windy"]:
            diff_code = desk.get("diffuser_id") or diffuser_id
            if desk.get("near_diffuser"):
                diagnosis["root_cause"] = f"Supply diffuser {diff_code} causing draft"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = (
                    f"Desk {desk_id} is near diffuser {diff_code}. VAV {vav_id} airflow may be too high."
                )
                diagnosis["suggested_actions"] = [
                    f"Reduce VAV {vav_id} maximum airflow setting",
                    f"Install deflector on diffuser {diff_code}",
                    f"Check {vav_id} damper — may be fully open",
                ]
            elif desk.get("near_window"):
                diagnosis["root_cause"] = "Window infiltration or poor seals"
                diagnosis["confidence"] = "medium"
                diagnosis["diagnosis"] = (
                    f"Desk {desk_id} is near a window. Draft may be from window seals. Zone temp: {current_temp}°C."
                )
                diagnosis["suggested_actions"] = [
                    "Inspect window seals for gaps",
                    "Check if window is slightly open",
                    f"Verify nearest diffuser {diff_code} direction",
                ]
            else:
                diagnosis["root_cause"] = "Excessive airflow or infiltration"
                diagnosis["confidence"] = "medium"
                diagnosis["diagnosis"] = (
                    f"Draft complaint at desk {desk_id}."
                    f" Could be diffuser, window seals, or door proximity."
                    f" Nearest diffuser: {diff_code}."
                )
                diagnosis["suggested_actions"] = [
                    f"Check diffuser {diff_code} airflow direction",
                    "Inspect window seals for gaps",
                    f"Verify VAV {vav_id} damper position",
                ]
            diagnosis["dispatch_required"] = True

        # Add degraded equipment warning if any
        if degraded:
            deg_list = [
                f"{e.get('type')} {k} (health: {e.get('health_score')}%)" for k, e in equipment.items() if e in degraded
            ]
            diagnosis["suggested_actions"].append(f"Note: degraded equipment in zone: {', '.join(deg_list)}")

        return diagnosis

    except Exception as e:
        logger.error(f"Error diagnosing comfort complaint for desk {desk_id}: {e}")
        return {
            "success": False,
            "error": calm_error_legacy(e, tool_name="diagnose_complaint")["error"],
            "prompt_user": "I encountered an error during diagnosis. Can you provide more details about the complaint?",
        }


# ---------------------------------------------------------------------------
# Niagara point discovery chat tools (Phase 60-03)
# ---------------------------------------------------------------------------


async def discover_niagara_points(
    device_ip: str,
    site_id: str | None = None,
) -> dict[str, Any]:
    """
    Trigger Niagara BACnet point discovery and AI classification.

    Scans a BACnet device for all points, classifies them using
    Haystack/Brick ontology, and groups into equipment entities.

    SSRF protection: validates IP against known BMS subnets and blocks
    loopback, link-local, and multicast addresses (137-07).

    Args:
        device_ip: IP address of the BACnet device (JACE/Supervisor)
        site_id: SENTINEL site ID for mapping

    Returns:
        Discovery summary with equipment counts and confidence breakdown
    """
    site_id = site_id or _default_site_id()

    # --- SSRF Protection (137-07) ---
    from app.security.tool_policy import validate_bms_ip

    ip_ok, ip_reason = validate_bms_ip(device_ip)
    if not ip_ok:
        logger.warning("SSRF blocked: discover_niagara_points(%s) — %s", device_ip, ip_reason)
        return {"success": False, "error": ip_reason}

    try:
        from app.services.niagara.mapping_service import get_mapping_service
        from app.services.niagara.point_classifier import get_point_classifier
        from app.services.niagara.point_discovery import get_point_discovery_service

        discovery_service = get_point_discovery_service()
        mapping_service = get_mapping_service()
        classifier = get_point_classifier()

        # Run discovery
        result = await discovery_service.discover_and_classify(
            device_ip=device_ip,
            site_id=site_id,
        )

        if result.status == "error":
            return {
                "success": False,
                "error": f"Discovery failed: {result.error}",
            }

        # Auto-generate mappings
        classified_points = classifier.classify_points(result.raw_points)
        mappings = mapping_service.map_points_to_equipment(classified_points, site_id)
        mapping_service.save_mappings(result.discovery_id, mappings, site_id)

        # Build summary
        summary = result.summary
        equipment_ids = summary.get("equipment_ids", {})
        equipment_list = []
        for eq_type, ids in equipment_ids.items():
            equipment_list.append(f"{len(ids)} {eq_type}(s): {', '.join(ids)}")

        confidence = summary.get("confidence_counts", {})

        return {
            "success": True,
            "discovery_id": result.discovery_id,
            "device_ip": device_ip,
            "site_id": site_id,
            "points_discovered": summary.get("total_points", 0),
            "equipment_identified": equipment_list,
            "confidence_breakdown": {
                "high": confidence.get("high", 0),
                "medium": confidence.get("medium", 0),
                "low": confidence.get("low", 0),
                "unknown": confidence.get("unknown", 0),
            },
            "needs_review": summary.get("needs_review", 0),
            "message": (
                f"Discovered {summary.get('total_points', 0)} points on {device_ip}. "
                f"Grouped into {len(equipment_ids)} equipment types. "
                f"{summary.get('needs_review', 0)} points need manual review."
            ),
        }

    except Exception as e:
        logger.error(f"Error in discover_niagara_points: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="discover_niagara_points")


async def review_point_mapping(
    discovery_id: str,
) -> dict[str, Any]:
    """
    Get mapping summary for FM team review.

    Returns equipment list with classified points, confidence scores,
    and items needing review.

    Args:
        discovery_id: Discovery identifier from discover_niagara_points

    Returns:
        Mapping summary with equipment, confidence, and review checklist
    """
    try:
        from app.services.niagara.mapping_service import get_mapping_service

        mapping_service = get_mapping_service()
        mappings = mapping_service.get_mappings(discovery_id)

        if mappings is None:
            return {
                "success": False,
                "error": f"Discovery '{discovery_id}' not found. Run discover_niagara_points first.",
            }

        # Build review summary
        equipment_summary = []
        total_points = 0
        low_confidence_items = []

        for eid, mapping in mappings.items():
            if eid == "UNASSIGNED":
                for p in mapping.points:
                    low_confidence_items.append(f"  - {p.get('original_name', 'unknown')}: unclassified")
                continue

            point_count = len(mapping.points)
            total_points += point_count
            equipment_summary.append(
                f"  {eid} ({mapping.equipment_type}): {point_count} points [{mapping.confidence} confidence]"
            )

            # Flag low confidence points
            for p in mapping.points:
                if p.get("confidence") in ("low", "unknown"):
                    low_confidence_items.append(
                        f"  - {p.get('original_name', 'unknown')} in {eid}: {p.get('confidence', 'unknown')} confidence"
                    )

        # Run validation
        validation = mapping_service.validate_mappings(mappings)

        return {
            "success": True,
            "discovery_id": discovery_id,
            "equipment_count": len([e for e in mappings if e != "UNASSIGNED"]),
            "total_points": total_points,
            "equipment_summary": equipment_summary,
            "needs_review": low_confidence_items,
            "validation_warnings": validation.warnings[:10],
            "orphan_count": len(validation.orphan_points),
            "message": (
                f"Mapping for discovery {discovery_id}: "
                f"{len(equipment_summary)} equipment entities, {total_points} points. "
                f"{len(low_confidence_items)} items need review."
            ),
        }

    except Exception as e:
        logger.error(f"Error in review_point_mapping: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="review_point_mapping")


async def approve_point_mapping(
    discovery_id: str,
    approved_by: str = "chat_user",
) -> dict[str, Any]:
    """
    Approve and activate a point mapping.

    Creates equipment models from approved mappings and integrates
    them into SENTINEL for monitoring and control.

    Args:
        discovery_id: Discovery identifier to approve
        approved_by: Name of the approver

    Returns:
        Approval result with equipment created count
    """
    try:
        from app.services.niagara.mapping_service import get_mapping_service

        mapping_service = get_mapping_service()
        mappings = mapping_service.get_mappings(discovery_id)

        if mappings is None:
            return {
                "success": False,
                "error": f"Discovery '{discovery_id}' not found.",
            }

        result = mapping_service.approve_mappings(discovery_id, approved_by)

        if result.get("success"):
            return {
                "success": True,
                "discovery_id": discovery_id,
                "equipment_created": result.get("equipment_created", 0),
                "approved_by": approved_by,
                "message": (
                    f"Approved! Created {result['equipment_created']} equipment models. "
                    f"Equipment is now active in SENTINEL for monitoring and control."
                ),
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Approval failed"),
            }

    except Exception as e:
        logger.error(f"Error in approve_point_mapping: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="approve_point_mapping")


async def correct_point_classification(
    discovery_id: str,
    point_name: str,
    correct_equipment_id: str | None = None,
    correct_point_type: str | None = None,
    correct_equipment_type: str | None = None,
) -> dict[str, Any]:
    """
    Manually correct a point classification.

    Use this when the AI classification is wrong. You can reassign
    a point to a different equipment, change its type, or update
    the equipment type.

    Args:
        discovery_id: Discovery identifier containing the point
        point_name: Original BACnet point name to correct
        correct_equipment_id: New equipment to assign point to
        correct_point_type: Corrected point type (sensor/setpoint/command/status/alarm)
        correct_equipment_type: Corrected equipment type (chiller/ahu/fcu/etc.)

    Returns:
        Correction result with changes applied
    """
    try:
        from app.services.niagara.mapping_service import get_mapping_service

        mapping_service = get_mapping_service()
        result = mapping_service.correct_point(
            discovery_id=discovery_id,
            point_name=point_name,
            new_equipment_id=correct_equipment_id,
            new_point_type=correct_point_type,
            new_equipment_type=correct_equipment_type,
        )

        if result.get("success"):
            return {
                "success": True,
                "point_name": point_name,
                "corrections": result.get("corrections", []),
                "message": (
                    f"Point '{point_name}' corrected: {', '.join(result.get('corrections', []))}. "
                    f"Confidence set to 'manual' (verified by human)."
                ),
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Correction failed"),
            }

    except Exception as e:
        logger.error(f"Error in correct_point_classification: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="correct_point_classification")


# Methodology access is now gated by DEVELOPER role (Phase 137-02)
# No hardcoded password — role check happens via TOOL_ROLE_REQUIREMENTS

# System methodology documentation (proprietary)
SYSTEM_METHODOLOGY = """
## SENTINEL System Methodology

### Equipment Health Score Calculation (0-100%)

SENTINEL calculates equipment health using a **weighted multi-factor model**:

| Factor | Weight | Data Sources |
|--------|--------|--------------|
| **Operational Performance** | 35% | Real-time sensor readings vs design specs, efficiency ratios, runtime hours |
| **Maintenance History** | 25% | Work order frequency, repeat failures, parts replacement cycles |
| **Asset Age & Lifecycle** | 20% | Installation date vs expected lifespan, manufacturer degradation curves |
| **Anomaly Indicators** | 20% | Vibration, temperature trends, pressure deviations, power patterns |

**Health Score Thresholds:**
- **80-100%**: Healthy - Normal operation, no action needed
- **50-79%**: Degraded - Schedule preventive maintenance within 2-4 weeks
- **Below 50%**: Critical - Immediate attention required, high failure risk

### Failure Prediction Methodology

SENTINEL uses **machine learning models** trained on historical failure data:

1. **Pattern Recognition**: Analyzes sensor trends (temperature, vibration, pressure) against pre-failure signatures
2. **Historical Correlation**: Compares current equipment behavior to similar assets that have failed
3. **Contributing Factors**: Weights multiple indicators:
   - Repeat work orders (same issue recurring)
   - Asset age vs expected life
   - Operating conditions (load, environment)
   - Maintenance compliance
4. **Confidence Score**: Based on data quality and pattern match strength (higher % = more certain)

### Optimization Recommendations

SENTINEL's AI optimizer considers:

1. **Current Conditions**: Indoor/outdoor temperature, humidity, occupancy
2. **Weather Forecast**: 4-hour lookahead for proactive adjustments
3. **Energy Pricing**: Time-of-use rates (peak/off-peak/standard)
4. **Safety Constraints**: Never exceeds equipment safety limits
5. **Comfort Bounds**: Maintains occupant comfort (typically 20-26°C)

**Savings Calculation**: (Current consumption - Optimized consumption) × Energy rate (ZAR/kWh)

### Safety Validation

All control actions are validated against:
- **Temperature limits**: Equipment-specific safe operating ranges
- **Interlock rules**: Dependencies between systems (e.g., fire alarm → HVAC shutdown)
- **Rate limits**: Maximum change rates to prevent equipment stress
- **Occupancy rules**: Comfort requirements during occupied hours

### Data Sources

SENTINEL integrates data from:
- BACnet/Modbus device protocols
- IoT sensors (temperature, humidity, pressure, vibration)
- Maintenance management systems (work orders, service history)
- Energy meters and utility feeds
- Weather APIs for forecast data
- Eskom load shedding schedules (South Africa specific)
"""


async def get_system_methodology(topic: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """
    Get proprietary SENTINEL system methodology documentation.

    Access is gated by DEVELOPER role via TOOL_ROLE_REQUIREMENTS (Phase 137-02).
    The password parameter was removed — role check replaces it.

    Args:
        topic: Optional specific topic (health_score, predictions, optimization, safety)

    Returns:
        System methodology documentation
    """
    logger.info(f"Methodology access granted for topic: {topic or 'all'}")

    # Return full or topic-specific documentation
    if topic:
        topic_lower = topic.lower()
        sections = SYSTEM_METHODOLOGY.split("### ")

        for section in sections:
            if topic_lower in section.lower():
                return {"success": True, "topic": topic, "documentation": "### " + section.strip()}

        return {
            "success": True,
            "topic": topic,
            "documentation": (
                f"Topic '{topic}' not found. Available topics: health_score, predictions, optimization, safety"
            ),
            "full_documentation": SYSTEM_METHODOLOGY,
        }

    return {"success": True, "documentation": SYSTEM_METHODOLOGY}


async def get_fire_system_status() -> dict[str, Any]:
    """
    Get fire and life safety system status including active alarms,
    damper positions, pressurization, and system health.

    Returns:
        Structured fire system status report
    """
    try:
        from app.services.fire_system_service import get_fire_system_service

        svc = get_fire_system_service()

        status = svc.get_system_status()
        health = svc.get_system_health()
        zones = svc.get_zones()
        dampers = svc.get_damper_status()
        press = svc.get_pressurization_status()

        # Build structured response
        sections = []

        # Panel status
        panel_st = status.panel_status.value.upper()
        last_test = status.last_test_date or "Unknown"
        sections.append(
            f"## Fire Alarm Panel\n- Status: {panel_st}\n- Battery: {status.battery_voltage}V\n- Last Test: {last_test}"
        )

        # Active alarms
        if status.active_alarms:
            alarm_lines = []
            for a in status.active_alarms:
                alarm_lines.append(
                    f"  - [{a.severity.value.upper()}] {a.alarm_type.value}: {a.description} (Zone: {a.zone_id})"
                )
            alarm_count = len(status.active_alarms)
            alarm_text = "\n".join(alarm_lines)
            sections.append(f"## Active Alarms ({alarm_count})\n" + alarm_text)
        else:
            sections.append("## Active Alarms\nNone - all zones normal")

        # Zones summary
        zones_with_alarms = sum(1 for z in zones if any(a.zone_id == z.zone_id for a in status.active_alarms))
        total_detectors = sum(
            z.smoke_detectors + z.heat_detectors + z.beam_detectors + z.manual_call_points for z in zones
        )
        sections.append(
            f"## Zones\n- Total: {len(zones)} zones"
            " across 3 floors"
            f"\n- With active alarms: {zones_with_alarms}"
            f"\n- Total detectors: {total_detectors}"
        )

        # Dampers
        fault_dampers = [d for d in dampers if d.status.value == "fault"]
        if fault_dampers:
            damper_lines = [
                f"  - {d.damper_id}: STUCK at {d.position}% (target {d.target_position}%)" for d in fault_dampers
            ]
            damper_text = "\n".join(damper_lines)
            sections.append(
                f"## Smoke Dampers\n- Total: {len(dampers)}\n- Faults: {len(fault_dampers)}\n" + damper_text
            )
        else:
            sections.append(f"## Smoke Dampers\n- Total: {len(dampers)}\n- All healthy (open position)")

        # Pressurization
        all_standby = all(p.fan_status.value == "off" for p in press)
        press_status = "All standby" if all_standby else "Active"
        sections.append(f"## Stairwell Pressurization\n- Fans: {len(press)}\n- Status: {press_status}")

        # Health
        overall = health.overall_health.value.upper()
        sections.append(
            f"## System Health\n- Overall: {overall}"
            f"\n- Panel Comms: {health.panel_comms}"
            f"\n- Battery: {health.battery_status}"
            f"\n- Detector Faults: {health.detector_faults}"
            f"\n- Damper Faults: {health.damper_faults}"
        )

        return {
            "success": True,
            "report": "\n\n".join(sections),
            "panel_status": status.panel_status.value,
            "active_alarm_count": len(status.active_alarms),
            "overall_health": health.overall_health.value,
            "battery_voltage": status.battery_voltage,
            "damper_faults": health.damper_faults,
            "detector_faults": health.detector_faults,
        }

    except Exception as e:
        logger.error(f"Error getting fire system status: {e}")
        return {"error": calm_error_legacy(e, tool_name="get_fire_system_status")["error"]}


async def get_security_status() -> dict[str, Any]:
    """
    Get security system status including access control, cameras,
    alarm zones, occupancy, and recent badge events.

    Returns:
        Structured security system status report
    """
    try:
        from app.services.security_occupancy_service import get_security_occupancy_service
        from app.services.security_service import get_security_service

        svc = get_security_service()
        occ_svc = get_security_occupancy_service()

        status = svc.get_system_status()
        zones = svc.get_access_zones()
        cameras = svc.get_cameras()
        alarm_zones = svc.get_alarm_zones()
        denied = svc.get_denied_access_events()
        after_hours = svc.get_after_hours_events()
        building_occ = occ_svc.get_building_occupancy()

        # Build structured response
        sections = []

        # System overview
        sections.append(
            f"## Security System Overview\n"
            f"- Doors: {status.doors_secure}/{status.total_doors} secure\n"
            f"- Cameras: {status.cameras_online}/{status.cameras_total} online\n"
            f"- Alarm zones: {status.alarm_zones_armed}/{status.alarm_zones_total} armed\n"
            f"- Active alerts: {status.active_alerts}\n"
            f"- Building occupancy: {status.occupancy_total} people"
        )

        # Access zones
        zone_lines = []
        for z in zones:
            zone_lines.append(f"  - {z.name} ({z.floor}) - {z.access_level.value}")
        sections.append(f"## Access Zones ({len(zones)})\n" + "\n".join(zone_lines))

        # Camera status
        offline_cams = [c for c in cameras if c.status.value != "online"]
        if offline_cams:
            cam_lines = [f"  - {c.name}: {c.status.value}" for c in offline_cams]
            sections.append("## Camera Alerts\n" + "\n".join(cam_lines))
        else:
            sections.append(f"## Cameras\nAll {len(cameras)} cameras online")

        # Alarm zones
        alarm_lines = [f"  - {az.name}: {az.status.value} ({az.arm_type.value})" for az in alarm_zones]
        sections.append("## Alarm Zones\n" + "\n".join(alarm_lines))

        # Denied access
        if denied:
            deny_lines = [f"  - {e.person_name} at {e.door_id}: {e.reason}" for e in denied[:5]]
            sections.append(f"## Denied Access ({len(denied)})\n" + "\n".join(deny_lines))

        # After-hours access
        if after_hours:
            ah_lines = [f"  - {e.person_name} at {e.door_id} ({e.timestamp})" for e in after_hours[:5]]
            sections.append(f"## After-Hours Access ({len(after_hours)})\n" + "\n".join(ah_lines))

        # Occupancy summary
        occ_lines = []
        for zone_occ in building_occ.get("zones", []):
            if zone_occ.get("occupancy_count", 0) > 0:
                occ_lines.append(f"  - {zone_occ['zone_name']}: {zone_occ['occupancy_count']} people")
        if occ_lines:
            sections.append(
                f"## Occupancy\nTotal: {building_occ.get('total_occupancy', 0)} people\n" + "\n".join(occ_lines)
            )
        else:
            sections.append(f"## Occupancy\nTotal: {building_occ.get('total_occupancy', 0)} people")

        return {
            "success": True,
            "report": "\n\n".join(sections),
            "doors_secure": status.doors_secure,
            "total_doors": status.total_doors,
            "cameras_online": status.cameras_online,
            "cameras_total": status.cameras_total,
            "alarm_zones_armed": status.alarm_zones_armed,
            "active_alerts": status.active_alerts,
            "occupancy_total": status.occupancy_total,
            "denied_events": len(denied),
            "after_hours_events": len(after_hours),
        }

    except Exception as e:
        logger.error(f"Error getting security status: {e}")
        return {"error": calm_error_legacy(e, tool_name="get_security_status")["error"]}


# Tool definitions for Claude API
# ============================================================================
# Solar Chat Tool Handlers (34-09)
# ============================================================================


async def get_solar_overview(site_id: str | None = None) -> dict[str, Any]:
    """Get solar site overview — generation, BESS, grid, savings."""
    site_id = site_id or _default_site_id()
    try:
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()
        overview = await svc.get_site_overview(site_id)
        if not overview:
            return {"error": f"Solar site '{site_id}' not found"}
        return {"success": True, **overview}
    except Exception as e:
        logger.error(f"get_solar_overview error: {e}")
        return {"error": calm_error_legacy(e, tool_name="get_solar_overview")["error"]}


async def get_bess_status_chat(site_id: str | None = None) -> dict[str, Any]:
    """Get BESS battery status — SOC, mode, health."""
    site_id = site_id or _default_site_id()
    try:
        from app.services.solar_ingestion_service import get_solar_ingestion_service

        svc = get_solar_ingestion_service()
        bess = await svc.get_bess_status(site_id)
        if not bess:
            return {"error": f"No BESS found at site '{site_id}'"}
        return {"success": True, **bess.to_dict()}
    except Exception as e:
        logger.error(f"get_bess_status error: {e}")
        return {"error": calm_error_legacy(e, tool_name="get_bess_status_chat")["error"]}


async def get_solar_savings(
    site_id: str | None = None,
    period: str = "ytd",
) -> dict[str, Any]:
    """Get solar savings — monthly/YTD financial summary."""
    site_id = site_id or _default_site_id()
    try:
        from app.services.solar_financial_service import get_solar_financial_service

        svc = get_solar_financial_service()
        summary = svc.get_financial_summary(site_id, period=period)
        return {"success": True, **summary.to_dict()}
    except Exception as e:
        logger.error(f"get_solar_savings error: {e}")
        return {"error": calm_error_legacy(e, tool_name="get_solar_savings")["error"]}


async def get_solar_diagnostics(site_id: str | None = None) -> dict[str, Any]:
    """Get solar diagnostics — underperformers, issues, maintenance."""
    site_id = site_id or _default_site_id()
    try:
        from app.services.solar_performance_service import get_solar_performance_service

        perf = get_solar_performance_service()
        report = await perf.get_diagnostic_summary(site_id)
        if not report:
            return {"error": f"No diagnostics for site '{site_id}'"}
        result = {"success": True, **report.to_dict()}
        # Add maintenance recommendations
        try:
            from app.services.solar_maintenance_service import get_solar_maintenance_service

            maint = get_solar_maintenance_service()
            recs = await maint.evaluate_maintenance_needs(site_id)
            result["maintenance_recommendations"] = [r.to_dict() for r in recs[:5]]
        except Exception as e:
            logger.warning(f"get_solar_diagnostics: failed to fetch maintenance recs: {e}", exc_info=True)
        return result
    except Exception as e:
        logger.error(f"get_solar_diagnostics error: {e}")
        return {"error": calm_error_legacy(e, tool_name="get_solar_diagnostics")["error"]}


async def get_solar_forecast(
    site_id: str | None = None,
    hours: int = 24,
) -> dict[str, Any]:
    """Get solar generation forecast — next 24h with confidence."""
    site_id = site_id or _default_site_id()
    try:
        from app.services.solar_forecast_service import get_solar_forecast_service

        svc = get_solar_forecast_service()
        forecast = svc.get_forecast(site_id, hours_ahead=hours)
        return {"success": True, **forecast.to_dict()}
    except Exception as e:
        logger.error(f"get_solar_forecast error: {e}")
        return {"error": calm_error_legacy(e, tool_name="get_solar_forecast")["error"]}


async def handle_comfort_complaint(
    user_message: str,
    user_id: str = "chat_user",
    channel: str = "chat",
) -> dict[str, Any]:
    """
    Route a free-text comfort complaint to the LangGraph desk complaint agent.

    Handles multi-turn conversations via checkpointed state.
    Returns response text and whether further input is needed.
    """
    try:
        from langchain_core.messages import HumanMessage

        from app.agents import get_desk_complaint_graph

        agent = get_desk_complaint_graph()
        config = {"configurable": {"thread_id": f"{user_id}_{channel}"}}
        result = agent.invoke(
            {
                "messages": [HumanMessage(content=user_message)],
                "user_id": user_id,
                "channel": channel,
            },
            config=config,
        )
        return {
            "success": True,
            "response": result.get("response", ""),
            "needs_input": result.get("needs_input", False),
        }
    except Exception as e:
        logger.error(f"handle_comfort_complaint error: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="handle_comfort_complaint")


CHAT_TOOLS = [
    {
        "name": "list_devices",
        "description": (
            "List available building devices. Use this to discover"
            " what devices can be controlled or monitored."
            " You can filter by device type"
            " (hvac, lighting, security, power) or site ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_type": {
                    "type": "string",
                    "description": (
                        "Filter by device type: hvac, lighting, security, fire_safety, access_control, power, other"
                    ),
                    "enum": [
                        "hvac",
                        "lighting",
                        "security",
                        "fire_safety",
                        "access_control",
                        "power",
                        "other",
                    ],
                },
                "site_id": {"type": "string", "description": "Filter by site ID (e.g., 'site-001')"},
            },
            "required": [],
        },
    },
    {
        "name": "get_device_details",
        "description": (
            "Get detailed information about a specific device"
            " including its current values, available control"
            " points, and safety status. Use this before"
            " controlling a device to understand its"
            " current state."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": ("The device ID to look up (e.g., 'S002-CHILLER-B1-001')"),
                }
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "control_device",
        "description": (
            "Execute a control action on a building device."
            " This will set a value on a device point"
            " (like temperature setpoint or on/off state)."
            " All actions are validated against safety rules"
            " and logged to the audit trail. If safety"
            " validation fails, the action will be blocked"
            " and you'll receive an error explaining why."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID to control (e.g., 'S002-CHILLER-B1-001')",
                },
                "point": {
                    "type": "string",
                    "description": "The point name to control (e.g., 'setpoint', 'state', 'mode')",
                },
                "value": {
                    "description": (
                        "The value to set. For temperature"
                        " setpoints use a number. For on/off"
                        " states use true/false or 1/0."
                    )
                },
                "reason": {
                    "type": "string",
                    "description": "Brief explanation of why this control action is being performed",
                    "default": "User requested via AI assistant",
                },
            },
            "required": ["device_id", "point", "value"],
        },
        "safety_profiles": {
            # SETPOINT — temperature, humidity, pressure setpoints
            "SETPOINT": {
                "is_dangerous": False,
                "is_reversible": True,
                "approval_hint": (
                    "Auto-approved if confidence >= 0.85 and risk_level is low or medium; "
                    "human approval required if risk_level is high or critical."
                ),
                "bacnet_priority": 8,
            },
            # LIGHTING — DALI, 0-10V dimming
            "LIGHTING": {
                "is_dangerous": False,
                "is_reversible": True,
                "approval_hint": (
                    "Auto-approved if confidence >= 0.85 and risk_level is low or medium; "
                    "human approval required if risk_level is high or critical."
                ),
                "bacnet_priority": 8,
            },
            # STAGING — chiller/boiler/AHU staging, binary on/off overrides
            # is_dangerous=True: binary overrides can cause oscillations or comfort events
            "STAGING": {
                "is_dangerous": True,
                "is_reversible": True,
                "approval_hint": (
                    "Human approval required for staging actions; "
                    "they affect equipment state and can cause oscillations if misapplied."
                ),
                "bacnet_priority": 3,
            },
            # BESS — battery dispatch (charge/discharge), genset start/stop
            # is_dangerous=True: writes to power hardware; is_reversible=False: dispatch commits to grid
            "BESS": {
                "is_dangerous": True,
                "is_reversible": False,
                "approval_hint": (
                    "Human approval always required for BESS dispatch and genset operations; "
                    "these affect power hardware and grid commitments."
                ),
                "bacnet_priority": 2,
            },
            # LIFE_SAFETY — fire, access control, CCTV, emergency overrides
            "LIFE_SAFETY": {
                "is_dangerous": True,
                "is_reversible": False,
                "approval_hint": (
                    "Human approval always required for life safety actions regardless of confidence; "
                    "these affect emergency systems."
                ),
                "bacnet_priority": 1,
            },
            # UNKNOWN — fallback for unrecognized action types
            "UNKNOWN": {
                "is_dangerous": False,
                "is_reversible": False,
                "approval_hint": "Human approval required for any unrecognized action type.",
                "bacnet_priority": 8,
            },
        },
    },
    {
        "name": "get_system_status",
        "description": (
            "Get overall BMS system status including active"
            " alerts, equipment health summary, predicted"
            " failures, and prioritized recommendations."
            " Use this to understand the current state of"
            " the building and identify issues that need"
            " attention."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": (
                        "Optional site ID to filter status"
                        " (e.g., 'site-001'). If not provided,"
                        " returns status for all sites."
                    ),
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_optimization_recommendations",
        "description": (
            "Get AI-powered optimization recommendations"
            " for HVAC setpoints based on current conditions,"
            " weather forecast, and energy pricing. Returns"
            " specific setpoint changes with projected"
            " energy and cost savings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "The site ID to analyze for optimization (e.g., 'site-001')",
                }
            },
            "required": ["site_id"],
        },
    },
    {
        "name": "get_equipment_health",
        "description": (
            "Get equipment health status, maintenance"
            " history, and failure predictions. Helps"
            " identify equipment that needs attention"
            " and prioritize maintenance activities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string", "description": "Filter by site ID"},
                "equipment_id": {"type": "string", "description": "Get details for specific equipment"},
                "status_filter": {
                    "type": "string",
                    "description": "Filter by health status",
                    "enum": ["critical", "warning", "normal"],
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_equipment_service_history",
        "description": (
            "Get maintenance and service records for a"
            " specific piece of equipment. Returns service"
            " history, repair records, and knowledge base"
            " entries for the asset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": ("Equipment UUID (equipment.id from database)"),
                },
                "knowledge_type": {
                    "type": "string",
                    "description": ("Optional filter on knowledge type (e.g. 'service', 'repair')"),
                },
                "limit": {
                    "type": "integer",
                    "description": ("Maximum number of records to return (default 10, max 50)"),
                    "default": 10,
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "get_alerts_and_anomalies",
        "description": (
            "Get active alerts and detected"
            " anomalies/predicted failures. Alerts are"
            " current issues, anomalies are AI-predicted"
            " future problems. Includes cost estimates"
            " for repairs and potential damage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string", "description": "Filter by site ID"},
                "severity": {
                    "type": "string",
                    "description": "Filter alerts by severity",
                    "enum": ["critical", "warning", "info"],
                },
                "include_resolved": {
                    "type": "boolean",
                    "description": "Include resolved/acknowledged alerts (default: false)",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_energy_analysis",
        "description": (
            "Get energy consumption analysis for a site"
            " including current device readings, efficiency"
            " insights, and suggestions for reducing"
            " energy costs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": ("The site ID to analyze (e.g., 'site-001')"),
                }
            },
            "required": ["site_id"],
        },
    },
    {
        "name": "get_system_methodology",
        "description": (
            "Get proprietary SENTINEL system methodology"
            " documentation explaining how health scores"
            " are calculated, how failure predictions work,"
            " optimization algorithms, and safety"
            " validation. Requires DEVELOPER role or higher."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "Optional specific topic:"
                        " health_score, predictions,"
                        " optimization, safety,"
                        " or leave empty for all"
                    ),
                    "enum": ["health_score", "predictions", "optimization", "safety"],
                },
            },
        },
    },
    {
        "name": "lookup_desk",
        "description": (
            "Look up a desk location and get its HVAC zone,"
            " temperature, and sensor data. Use this when a"
            " technician reports a comfort complaint from a"
            " user at a specific desk. Returns zone info,"
            " HVAC equipment IDs, and DALI sensor data"
            " (Sandton has DALI integration). If the desk"
            " isn't found, ask the technician for"
            " clarification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "desk_id": {
                    "type": "string",
                    "description": "The desk identifier. Can be formats like '201', 'L12-25', 'Desk 25', or just '25'",
                },
                "building": {
                    "type": "string",
                    "description": (
                        "Optional building name if working"
                        " across multiple sites. For Sandton"
                        " (which has DALI), this is automatic."
                    ),
                },
            },
            "required": ["desk_id"],
        },
    },
    {
        "name": "diagnose_comfort_complaint",
        "description": (
            "Diagnose a comfort complaint (too hot, too cold,"
            " stuffy, drafty) for a specific desk. Analyzes"
            " desk location, HVAC zone, DALI sensors"
            " (occupancy, daylight), and context (near"
            " window, diffuser, printer) to determine root"
            " cause and suggest actions. Use this when a"
            " technician says something like 'user at desk"
            " 201 says it's too hot'. Returns diagnosis"
            " with confidence level and recommended actions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "desk_id": {"type": "string", "description": "The desk identifier (e.g., '201', 'L12-25', 'Desk 25')"},
                "complaint_type": {
                    "type": "string",
                    "description": "Type of comfort complaint",
                    "enum": ["too_hot", "too_cold", "stuffy", "drafty"],
                },
                "building": {
                    "type": "string",
                    "description": "Optional building name if technician is working across multiple sites",
                },
                "additional_info": {
                    "type": "string",
                    "description": (
                        "Any additional context from the technician (e.g., 'user says it's been like this all morning')"
                    ),
                },
            },
            "required": ["desk_id", "complaint_type"],
        },
    },
    {
        "name": "handle_comfort_complaint",
        "description": (
            "Handle a free-text comfort complaint using the multi-turn desk complaint agent. "
            "Unlike diagnose_comfort_complaint (which needs structured desk_id + complaint_type), "
            "this tool accepts natural language like 'it's freezing at desk 25' and extracts the "
            "desk and complaint type automatically. If info is missing, it returns a follow-up "
            "question (needs_input=true). Use this for user-reported complaints in chat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_message": {
                    "type": "string",
                    "description": ("The user's free-text comfort complaint message"),
                }
            },
            "required": ["user_message"],
        },
    },
    {
        "name": "discover_niagara_points",
        "description": (
            "Scan a Niagara BACnet device to discover all"
            " BMS points. Uses AI classification with"
            " Haystack/Brick ontology to identify equipment"
            " types (chiller, AHU, FCU, VAV, pump, etc.)"
            " and point types (sensor, setpoint, command,"
            " status). Returns a discovery_id for reviewing"
            " and approving the mapping. Use this when an"
            " FM team needs to onboard a new building or"
            " BMS controller."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_ip": {
                    "type": "string",
                    "description": "IP address of the BACnet device to scan (e.g., '192.168.1.100')",
                },
                "site_id": {
                    "type": "string",
                    "description": "Site ID (resolved from registered building)",
                },
            },
            "required": ["device_ip"],
        },
    },
    {
        "name": "review_point_mapping",
        "description": (
            "Get a summary of discovered Niagara points"
            " and their AI classification for review."
            " Shows equipment groupings, confidence levels,"
            " and items needing manual review. Use this"
            " after discover_niagara_points to let the FM"
            " team verify the auto-classification before"
            " approving."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "discovery_id": {
                    "type": "string",
                    "description": ("Discovery ID returned from discover_niagara_points"),
                }
            },
            "required": ["discovery_id"],
        },
    },
    {
        "name": "approve_point_mapping",
        "description": (
            "Approve a Niagara point mapping after review."
            " This activates the auto-generated equipment"
            " models in SENTINEL for monitoring and"
            " control. Only use after reviewing the"
            " mapping with review_point_mapping."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "discovery_id": {"type": "string", "description": "Discovery ID to approve"},
                "approved_by": {
                    "type": "string",
                    "description": "Name of the person approving (defaults to 'chat_user')",
                    "default": "chat_user",
                },
            },
            "required": ["discovery_id"],
        },
    },
    {
        "name": "correct_point_classification",
        "description": (
            "Manually correct a point that was misclassified"
            " by the AI. Use this when reviewing a mapping"
            " and finding incorrect equipment assignment or"
            " point type. You can move a point to a"
            " different equipment, change its type, or fix"
            " the equipment type."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "discovery_id": {"type": "string", "description": "Discovery ID containing the point"},
                "point_name": {
                    "type": "string",
                    "description": ("Original BACnet point name to correct (e.g., 'CH-1_CHW_Supply_Temp')"),
                },
                "correct_equipment_id": {
                    "type": "string",
                    "description": "New equipment ID to assign the point to (optional)",
                },
                "correct_point_type": {
                    "type": "string",
                    "description": "Corrected point type",
                    "enum": ["sensor", "setpoint", "command", "status", "alarm"],
                },
                "correct_equipment_type": {
                    "type": "string",
                    "description": ("Corrected equipment type (chiller, ahu, fcu, vav, pump, boiler, etc.)"),
                },
            },
            "required": ["discovery_id", "point_name"],
        },
    },
    {
        "name": "get_fire_system_status",
        "description": (
            "Get fire and life safety system status"
            " including active alarms, damper positions,"
            " stairwell pressurization, and system health."
            " Use this when someone asks about fire safety,"
            " fire alarms, smoke dampers, or life safety"
            " systems. Returns panel status, active alarm"
            " count, zone summary, damper health,"
            " pressurization status, and battery voltage."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_security_status",
        "description": (
            "Get security system status including access"
            " control doors, CCTV cameras, alarm zones,"
            " building occupancy from badge events, denied"
            " access events, and after-hours access. Use"
            " this when someone asks about security, access"
            " control, cameras, CCTV, who is in the"
            " building, occupancy, or alarm zones."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # Solar chat tools (34-09)
    {
        "name": "get_solar_overview",
        "description": (
            "Get solar site overview including current"
            " generation (kW), daily yield (kWh), BESS"
            " State of Charge, grid import/export,"
            " performance ratio, and estimated savings."
            " Use this when someone asks 'How much solar"
            " did we generate today?', about solar output,"
            " PV panels, or the solar dashboard."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Site ID (resolved from registered building)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_bess_status",
        "description": (
            "Get BESS (Battery) status including State of"
            " Charge (SOC%), current mode"
            " (charging/discharging/idle), health, power"
            " flow, and cycle count. Use this when someone"
            " asks 'What is the battery level?', about"
            " BESS, battery storage, or energy storage"
            " status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Site ID (resolved from registered building)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_solar_savings",
        "description": (
            "Get solar and BESS financial savings summary"
            " including arbitrage, demand charge,"
            " self-consumption, and diesel avoidance"
            " savings. Returns YTD totals, monthly"
            " breakdown, and ROI. Use this when someone"
            " asks 'How much have we saved this month?',"
            " about solar ROI, financial performance,"
            " or cost savings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Site ID (resolved from registered building)",
                },
                "period": {"type": "string", "description": "Period: ytd or month", "default": "ytd"},
            },
            "required": [],
        },
    },
    {
        "name": "get_solar_diagnostics",
        "description": (
            "Get solar diagnostics including"
            " underperforming inverters, string anomalies,"
            " maintenance recommendations, and cost"
            " impact. Use this when someone asks 'Which"
            " inverters are underperforming?', about solar"
            " problems, faults, or maintenance needs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Site ID (resolved from registered building)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_solar_forecast",
        "description": (
            "Get solar generation forecast for the next"
            " 24-72 hours with confidence bands. Returns"
            " hourly predicted output in kW. Use this when"
            " someone asks 'What is tomorrow's generation"
            " forecast?', about expected solar production,"
            " or upcoming generation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Site ID (resolved from registered building)",
                },
                "hours": {
                    "type": "integer",
                    "description": ("Forecast horizon in hours (default: 24)"),
                    "default": 24,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_floor_temperatures",
        "description": (
            "Get current HVAC zone temperatures, optionally filtered by floor. "
            "Use when asked 'what is the temperature on floor 1?', 'floor 2 temp', "
            "or 'show me all zone temperatures'. Returns current_temp, setpoint, status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "floor": {
                    "type": "string",
                    "description": "Floor level to filter by: 'L0', 'L1', or 'L2'. Omit for all floors.",
                    "enum": ["L0", "L1", "L2"],
                },
                "site_id": {"type": "string", "description": "Site ID (resolved from registered building)"},
            },
            "required": [],
        },
    },
    # ================================================================
    # Documentation / Knowledge Base Search
    # ================================================================
    {
        "name": "search_documents",
        "description": (
            "Search operational documentation: equipment manuals, fault codes, "
            "maintenance procedures, and troubleshooting guides. Use this for "
            "equipment-specific questions and operational knowledge. Returns "
            "relevant document excerpts ranked by relevance. Do NOT use this "
            "for live building data — use the other tools for real-time equipment status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — natural language question or keywords",
                },
                "n_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 5, max: 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_system_documents",
        "description": (
            "Search SENTINEL platform documentation: architecture, security design, "
            "compliance controls, FSR gap analysis, ISO 42001 AI governance, EU AI Act, "
            "NIST AI RMF, POPIA compliance, vulnerability management, penetration testing, "
            "onboarding instructions, building upload procedures, and configuration guides. "
            "For questions about SENTINEL's standards, compliance posture, or security "
            "certifications: include keywords like 'FSR', 'ISO', 'NIST', 'POPIA', 'EU AI Act', "
            "'gap analysis', 'control mapping', 'assessment scores' in your query to retrieve "
            "the detailed compliance documents. Only use when the user asks about how the "
            "SENTINEL platform itself works, NOT for operational/equipment questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Platform documentation search query",
                },
                "n_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 8, max: 10)",
                    "default": 8,
                },
            },
            "required": ["query"],
        },
    },
    # ================================================================
    # Hybrid Context — Brick + RAG + Telemetry + ML in one call
    # ================================================================
    {
        "name": "get_hybrid_context",
        "description": (
            "Get merged context for an asset combining Brick graph metadata, "
            "live telemetry, ML predictions, and document search results. "
            "Use this BEFORE answering fault diagnosis, maintenance planning, "
            "SLA compliance, inspection history, or vendor questions about a "
            "specific piece of equipment. Provide either equipment_id or "
            "bacnet_ref. Returns structured data plus a prompt-ready text block."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "equipment_id": {
                    "type": "string",
                    "description": "Equipment code (e.g., 'S002-CHILLER-B1-001'). Provide this or bacnet_ref.",
                },
                "bacnet_ref": {
                    "type": "string",
                    "description": "BMS-native point reference (e.g., 'CH-1.ChwSupplyTemp').",
                },
                "question": {
                    "type": "string",
                    "description": "Optional question to tailor document retrieval and context formatting.",
                },
                "include_documents": {
                    "type": "boolean",
                    "description": "Include document RAG results (default: true).",
                    "default": True,
                },
                "include_telemetry": {
                    "type": "boolean",
                    "description": "Include live telemetry data (default: true).",
                    "default": True,
                },
                "include_ml": {
                    "type": "boolean",
                    "description": "Include ML context — anomalies, forecasts, health trends (default: true).",
                    "default": True,
                },
            },
            "required": [],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "equipment_id": {"type": ["string", "null"]},
                "equipment_type": {"type": ["string", "null"]},
                "site_id": {"type": "string"},
                "sources_used": {"type": "array", "items": {"type": "string"}},
                "retrievalTelemetry": {
                    "type": ["object", "null"],
                    "properties": {
                        "trace_id": {"type": "string"},
                        "retrieval_path": {"type": "string"},
                        "query_time_ms": {"type": "integer"},
                        "top_k_requested": {"type": "integer"},
                        "hit_count": {"type": "integer"},
                        "used_fallback": {"type": ["string", "null"]},
                        "fallback_reason": {"type": ["string", "null"]},
                    },
                    "required": [
                        "trace_id",
                        "retrieval_path",
                        "query_time_ms",
                        "top_k_requested",
                        "hit_count",
                        "used_fallback",
                    ],
                },
                "context": {"type": "object"},
                "prompt_context": {"type": "string"},
            },
            "required": [
                "success",
                "equipment_id",
                "equipment_type",
                "site_id",
                "sources_used",
                "retrievalTelemetry",
                "context",
                "prompt_context",
            ],
        },
    },
    # ================================================================
    # Write/Action Tools — Operator+ only (role-gated)
    # ================================================================
    {
        "name": "adjust_setpoint",
        "description": (
            "Adjust a temperature setpoint on HVAC equipment. "
            "WRITE action — restricted to operators and admins. "
            "Safety boundaries enforced: zone_temp 16-28°C, "
            "supply_temp 4-25°C, supply_air_temp 12-22°C, "
            "chw_supply_temp 5-12°C. "
            "ALWAYS check the current reading with get_device_details "
            "before adjusting. All changes are audit-logged."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "equipment_code": {
                    "type": "string",
                    "description": "Equipment code (e.g., 'S002-VAV-101', 'S002-AHU-L1-001')",
                },
                "setpoint_type": {
                    "type": "string",
                    "description": "Type of setpoint to adjust",
                    "enum": ["zone_temp", "supply_temp", "supply_air_temp", "chw_supply_temp"],
                },
                "value": {
                    "type": "number",
                    "description": "New setpoint value in °C",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for adjustment (e.g., 'comfort complaint', 'energy optimization')",
                },
            },
            "required": ["equipment_code", "setpoint_type", "value", "reason"],
        },
    },
    {
        "name": "create_work_order",
        "description": (
            "Create a maintenance work order for equipment issues. "
            "WRITE action — restricted to operators and admins. "
            "IMPORTANT: Before calling this tool, ALWAYS guide the user through "
            "the FM workflow first. Present clickable slash commands in this order:\n"
            "1. `/info_{CODE}` — show equipment diagnostics first\n"
            "2. `/inspect_{CODE}` — schedule inspection with technician notification\n"
            "3. `/WO_{CODE}` — create general work order\n"
            "Only call this tool directly if the user explicitly confirms they want "
            "to skip diagnostics and create a work order immediately. "
            "Replace {CODE} with the equipment code using underscores (e.g., S002_FCU_301)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Clear description of the issue or maintenance needed",
                },
                "equipment_code": {
                    "type": "string",
                    "description": "Equipment code if known (e.g., 'S002-AHU-L1-001')",
                },
                "priority": {
                    "type": "string",
                    "description": "Work order priority",
                    "enum": ["critical", "high", "medium", "low"],
                },
                "category": {
                    "type": "string",
                    "description": "Work order category",
                    "enum": ["hvac", "electrical", "plumbing", "maintenance", "other"],
                },
                "assigned_to": {
                    "type": "string",
                    "description": "Technician name to assign the WO to. Auto-assigns if omitted.",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "close_work_order",
        "description": (
            "Close (complete) an existing work order by code. "
            "WRITE action — restricted to operators and admins. "
            "Used by the technician /done flow to mark a work order as completed "
            "and record resolution notes and actual time spent. "
            "Requires the work order code (e.g. 'WO-2026-0044')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_order_code": {
                    "type": "string",
                    "description": "Work order code (e.g. 'WO-2026-0044')",
                },
                "resolution": {
                    "type": "string",
                    "description": "Resolution notes — what was done to close the work order",
                },
                "actual_duration_hours": {
                    "type": "number",
                    "description": "Actual hours spent on the work order",
                },
            },
            "required": ["work_order_code"],
        },
    },
    {
        "name": "approve_recommendation",
        "description": (
            "Approve a pending AI recommendation for execution. "
            "WRITE action — restricted to operators and admins. "
            "The recommendation will be executed through the "
            "safety-validated approval pipeline. Use get_system_status "
            "or get_optimization_recommendations first to see pending items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "description": "The recommendation ID to approve (e.g., 'rec-...')",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional approval notes",
                },
            },
            "required": ["recommendation_id"],
        },
    },
    {
        "name": "reject_recommendation",
        "description": (
            "Reject a pending AI recommendation. "
            "WRITE action — restricted to operators and admins. "
            "Provide a clear reason for rejection."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "description": "The recommendation ID to reject",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for rejecting the recommendation",
                },
            },
            "required": ["recommendation_id", "reason"],
        },
    },
    {
        "name": "reset_equipment_fault",
        "description": (
            "Reset a fault condition on equipment, restoring it to "
            "operational status. WRITE action — restricted to operators "
            "and admins. Safety-critical equipment (FIRE, GEN) cannot "
            "be remotely reset — create a work order instead. Resets "
            "health score, clears active predictions, and logs the action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "equipment_code": {
                    "type": "string",
                    "description": "Equipment code to reset (e.g., 'S002-FCU-L1-A')",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the fault reset",
                },
            },
            "required": ["equipment_code"],
        },
    },
    # ---------------------------------------------------------------------------
    # ServiceNow Integration Tools (Phase 138-02)
    # ---------------------------------------------------------------------------
    {
        "name": "check_servicenow_status",
        "description": (
            "Check the ServiceNow integration status. Returns whether "
            "ServiceNow is configured, connected, and what data tables "
            "are available. Use this to verify integration health."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_servicenow_incidents",
        "description": (
            "Query open incidents from ServiceNow. Returns a list of "
            "active incidents with their priority, state, description, "
            "and assignment details. Filter by location, assignment group, "
            "or priority level."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Filter by location or building name",
                },
                "assignment_group": {
                    "type": "string",
                    "description": "Filter by assignment group name",
                },
                "priority_max": {
                    "type": "integer",
                    "description": (
                        "Maximum priority level to include (1=critical, 2=high, 3=medium, 4=low). Default: 4"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of incidents to return (default: 10, max: 50)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "query_servicenow_work_orders",
        "description": (
            "Query work orders from ServiceNow. Returns a list of "
            "work orders with their state, priority, assigned technician, "
            "and task details. Requires MAINTENANCE module. Filter by "
            "location, state, or assigned technician."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Filter by location or building name",
                },
                "state": {
                    "type": "string",
                    "description": "Filter by work order state (e.g., 'open', 'in_progress', 'closed')",
                },
                "assigned_to": {
                    "type": "string",
                    "description": "Filter by assigned technician name",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of work orders to return (default: 10, max: 50)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_servicenow_incident_summary",
        "description": (
            "Get a summary breakdown of ServiceNow incidents by priority "
            "and state. Returns counts of open, in-progress, and resolved "
            "incidents at each priority level. Useful for dashboard views "
            "and operational overview."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Filter summary by location or building name",
                },
            },
            "required": [],
        },
    },
]


# Tool-level module requirements for site-aware access control.
TOOL_MODULE_REQUIREMENTS: dict[str, ModuleType] = {
    # Control/automation tools (per-discipline control modules)
    "control_device": ModuleType.HVAC_CONTROL,
    # Maintenance/work order tools
    "create_work_order": ModuleType.MAINTENANCE,
    "close_work_order": ModuleType.MAINTENANCE,
    # SIMBIOT / onboarding workflows
    "discover_niagara_points": ModuleType.SIMBIOT,
    "review_point_mapping": ModuleType.SIMBIOT,
    "approve_point_mapping": ModuleType.SIMBIOT,
    "correct_point_classification": ModuleType.SIMBIOT,
    # Security & life safety workflows
    "get_security_status": ModuleType.SECURITY,
    "get_fire_system_status": ModuleType.FIRE,
    # Solar / BESS workflows
    "get_solar_overview": ModuleType.SOLAR,
    "get_bess_status": ModuleType.SOLAR,
    "get_solar_savings": ModuleType.SOLAR,
    "get_solar_diagnostics": ModuleType.SOLAR,
    "get_solar_forecast": ModuleType.SOLAR,
    # Write/action tools — per-discipline control gating
    "adjust_setpoint": ModuleType.HVAC_CONTROL,
    "approve_recommendation": ModuleType.ENERGY_CONTROL,
    "reject_recommendation": ModuleType.ENERGY_CONTROL,
    "reset_equipment_fault": ModuleType.HVAC_CONTROL,
    # ServiceNow work orders gated by MAINTENANCE module (138-02)
    "query_servicenow_work_orders": ModuleType.MAINTENANCE,
}


# Tool-level minimum role requirements.
# Tools NOT listed here are available to any authenticated user.
TOOL_ROLE_REQUIREMENTS: dict[str, SentinelRole] = {
    # Existing write tools — now role-gated
    "control_device": SentinelRole.OPERATOR,
    "approve_point_mapping": SentinelRole.OPERATOR,
    "correct_point_classification": SentinelRole.OPERATOR,
    # New write/action tools
    "adjust_setpoint": SentinelRole.OPERATOR,
    "create_work_order": SentinelRole.OPERATOR,
    "close_work_order": SentinelRole.OPERATOR,
    "approve_recommendation": SentinelRole.OPERATOR,
    "reject_recommendation": SentinelRole.OPERATOR,
    "reset_equipment_fault": SentinelRole.OPERATOR,
    # Methodology access gated by role instead of password (Phase 137-02)
    "get_system_methodology": SentinelRole.DEVELOPER,
    # Niagara discovery SSRF-sensitive — restrict to DEVELOPER+ (137-07)
    "discover_niagara_points": SentinelRole.DEVELOPER,
}


def _has_required_role(user_role: SentinelRole | None, required_role: SentinelRole) -> bool:
    """Check if user role meets the minimum required role."""
    if user_role is None:
        return False
    # Handle string role values from auth middleware
    if isinstance(user_role, str):
        try:
            user_role = SentinelRole(user_role)
        except ValueError:
            return False
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 999)
    return user_level >= required_level


def _filter_tools_by_role(tools: list[dict], user_role: SentinelRole | None) -> list[dict]:
    """Filter tool list by role requirements (no module check)."""
    result = []
    for tool in tools:
        required_role = TOOL_ROLE_REQUIREMENTS.get(tool.get("name"))
        if required_role and not _has_required_role(user_role, required_role):
            continue
        result.append(tool)
    return result


# Tools that require the system docs toggle to be enabled
_SYSTEM_DOCS_GATED_TOOLS = {"search_system_documents"}


def get_chat_tools(
    site_id: str | None = None,
    *,
    user_email: str | None = None,
    user_role: SentinelRole | None = None,
    include_system_docs: bool = False,
) -> list[dict[str, Any]]:
    """Return chat tools filtered by active modules, user role, and system docs toggle.

    When include_system_docs is False (default), the search_system_documents tool
    is excluded to prevent platform documentation from polluting operational answers.
    """
    # Pre-filter system docs tools
    base_tools = CHAT_TOOLS
    if not include_system_docs:
        base_tools = [t for t in CHAT_TOOLS if t.get("name") not in _SYSTEM_DOCS_GATED_TOOLS]

    if not site_id:
        return _filter_tools_by_role(base_tools, user_role)

    filtered: list[dict[str, Any]] = []
    for tool in base_tools:
        tool_name = tool.get("name")

        # Role check — hide write tools from users below required role
        required_role = TOOL_ROLE_REQUIREMENTS.get(tool_name)
        if required_role and not _has_required_role(user_role, required_role):
            continue

        # Module check — existing behavior
        required_module = TOOL_MODULE_REQUIREMENTS.get(tool_name)
        if required_module is None:
            filtered.append(tool)
            continue

        if not module_registry.is_module_active(site_id, required_module):
            continue

        if user_email and user_role:
            repo = get_module_access_repository()
            if not repo.has_module_access(
                user_email=user_email,
                user_role=user_role,
                site_code=site_id,
                module_type=required_module,
            ):
                continue

        filtered.append(tool)
    return filtered


def _is_tool_allowed_for_site(
    tool_name: str,
    site_id: str | None,
    *,
    user_email: str | None = None,
    user_role: SentinelRole | None = None,
) -> bool:
    """Check whether a tool is allowed for the given site/module state."""
    if not site_id:
        return True

    required_module = TOOL_MODULE_REQUIREMENTS.get(tool_name)
    if required_module is None:
        return True

    if not module_registry.is_module_active(site_id, required_module):
        return False

    if user_email and user_role:
        repo = get_module_access_repository()
        return repo.has_module_access(
            user_email=user_email,
            user_role=user_role,
            site_code=site_id,
            module_type=required_module,
        )

    return True


async def process_recommendation(
    site_id: str | None = None,
    recommendation_id: str | None = None,
    channel: str = "chat",
) -> dict[str, Any]:
    """
    Trigger the recommendation agent to process pending recommendations.

    Uses the LangGraph recommendation agent to validate, assess impact,
    route through tier engine, and execute/request approval.

    Args:
        site_id: Building identifier (e.g., "S002")
        recommendation_id: Optional specific recommendation to process
        channel: Output channel ("chat", "system", "whatsapp", "telegram")

    Returns:
        Dictionary with processing result
    """
    try:
        from langchain_core.messages import HumanMessage

        from app.agents import get_recommendation_graph

        agent = get_recommendation_graph()
        thread_id = f"rec_{site_id}_{recommendation_id or 'batch'}"
        config = {"configurable": {"thread_id": thread_id}}

        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="process")],
                "site_id": site_id or "site-002",
                "channel": channel,
                "trigger": "manual",
            },
            config=config,
        )

        return {
            "success": True,
            "response": result.get("response", ""),
            "tier": result.get("tier"),
            "needs_input": result.get("needs_input", False),
            "processing_complete": result.get("processing_complete", False),
        }

    except ImportError:
        return {
            "success": False,
            "error": "LangGraph not available. Install langgraph to use the recommendation agent.",
        }
    except Exception as e:
        logger.error(f"Error processing recommendation: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="process_recommendation")


# ================================================================
# Write/Action Tool Handlers — Operator+ only
# ================================================================

# Maps setpoint type to device point name
SETPOINT_TYPE_TO_POINT = {
    "zone_temp": "setpoint",
    "supply_temp": "supply_temp_setpoint",
    "supply_air_temp": "supply_air_temp_setpoint",
    "chw_supply_temp": "chw_supply_temp_setpoint",
    "humidity": "humidity_setpoint",
}

# Fallback limits only used if settings.json cannot be loaded
_FALLBACK_LIMITS = {
    "zone_temp": {"min": 18.0, "max": 26.0, "unit": "°C"},
    "supply_temp": {"min": 4.0, "max": 26.0, "unit": "°C"},
    "supply_air_temp": {"min": 12.0, "max": 26.0, "unit": "°C"},
    "chw_supply_temp": {"min": 5.0, "max": 12.0, "unit": "°C"},
    "humidity": {"min": 40.0, "max": 60.0, "unit": "%RH"},
}


def _get_setpoint_safety_limits() -> dict:
    """Load setpoint safety limits from settings.json (Settings page)."""
    try:
        from app.api.settings import load_settings

        settings = load_settings()
        control_limits = settings.get("controlLimits", {})
        temp = control_limits.get("temperature_setpoint", {})
        chiller = control_limits.get("chiller_setpoint", {})
        humidity = control_limits.get("humidity_setpoint", {})
        return {
            "zone_temp": {
                "min": float(temp.get("min", 18)),
                "max": float(temp.get("max", 26)),
                "unit": temp.get("unit", "°C"),
            },
            "supply_temp": {
                "min": 4.0,
                "max": float(temp.get("max", 26)),
                "unit": "°C",
            },
            "supply_air_temp": {
                "min": 12.0,
                "max": float(temp.get("max", 26)),
                "unit": "°C",
            },
            "chw_supply_temp": {
                "min": float(chiller.get("min", 5)),
                "max": float(chiller.get("max", 12)),
                "unit": chiller.get("unit", "°C"),
            },
            "humidity": {
                "min": float(humidity.get("min", 40)),
                "max": float(humidity.get("max", 60)),
                "unit": humidity.get("unit", "%RH"),
            },
        }
    except Exception as e:
        logger.warning(f"_get_default_control_limits failed, returning fallback: {e}", exc_info=True)
        return _FALLBACK_LIMITS.copy()


async def adjust_setpoint(
    equipment_code: str,
    setpoint_type: str,
    value: float,
    reason: str = "Operator adjustment via chat",
) -> dict[str, Any]:
    """Adjust a setpoint within safety boundaries from settings."""
    safety_limits = _get_setpoint_safety_limits()
    limits = safety_limits.get(setpoint_type)
    if not limits:
        return {
            "success": False,
            "error": (f"Unknown setpoint type '{setpoint_type}'. Valid types: {list(safety_limits.keys())}"),
        }

    try:
        value = float(value)
    except (ValueError, TypeError):
        return {"success": False, "error": f"Value must be a number, got: {value}"}

    if value < limits["min"] or value > limits["max"]:
        return {
            "success": False,
            "blocked": True,
            "error": (
                f"Value {value}{limits['unit']} is outside safe range "
                f"({limits['min']}-{limits['max']}{limits['unit']}) for {setpoint_type}."
            ),
            "safety_limits": limits,
        }

    point_name = SETPOINT_TYPE_TO_POINT.get(setpoint_type, "setpoint")
    return await control_device(
        device_id=equipment_code,
        point=point_name,
        value=value,
        reason=reason,
    )


def _get_template_requirements(equipment_type: str | None) -> dict[str, Any] | None:
    """Get ML data collection template for an equipment type.

    Returns the 'breakdown' template first (most common for WOs), falling
    back to 'minor', then 'callout'.  Returns None if no template found.
    """
    if not equipment_type:
        return None
    try:
        from app.services.ml_template_service import MLTemplateService

        svc = MLTemplateService()
        # Try breakdown first (most relevant for work orders), then minor
        for service_type in ("breakdown", "callout", "minor"):
            template = svc.get_template(equipment_type, service_type)
            if template:
                return template
        return None
    except Exception as e:
        logger.warning(f"_get_template_requirements({equipment_type}) failed, returning None: {e}", exc_info=True)
        return None


async def _build_wo_email_body(wo, description: str, reported_by: str, equipment_code: str | None) -> str:
    """Build detailed WO email body with equipment diagnostics from Supabase.

    Matches the format of WorkOrderNotifier._build_email_body():
    WORK ORDER REFERENCES, EQUIPMENT & SITE, DIAGNOSTIC CONTEXT,
    FIELD INSTRUCTIONS, NEXT STEPS.
    """
    wo_dict = wo.to_dict()
    lines = [
        f"Hi {reported_by},",
        "",
        "A new work order has been created via SENTINEL AI Chat.",
        "",
        "WORK ORDER REFERENCES",
        f"- Work Order: {wo.id}",
        f"- Priority: {wo.priority.upper()}",
        f"- Category: {wo.category}",
        f"- Created: {wo_dict.get('created_at', 'now')[:16].replace('T', ' ')}",
        "- Status: OPEN",
        "",
        "EQUIPMENT & SITE",
        f"- Site: {wo.site_name} [{wo.site_id}]",
        f"- Equipment: {wo.equipment_name or 'Not specified'}",
        f"- Equipment Code: {wo.equipment_id or 'N/A'}",
        "",
        "ISSUE DESCRIPTION",
        description,
    ]

    # Pull equipment diagnostics from Supabase if equipment_code provided
    if equipment_code:
        try:
            diag = await _fetch_equipment_diagnostics(equipment_code)
            if diag:
                lines.extend(["", "DIAGNOSTIC CONTEXT"])
                lines.append(f"- Health Score: {diag['health_score']}%")
                lines.append(f"- Equipment Status: {diag['status']}")
                if diag.get("type"):
                    lines.append(f"- Equipment Type: {diag['type']}")
                if diag.get("manufacturer"):
                    lines.append(f"- Manufacturer: {diag['manufacturer']}")
                if diag.get("model"):
                    lines.append(f"- Model: {diag['model']}")
                if diag.get("last_service"):
                    lines.append(f"- Last Service: {diag['last_service']}")

                # Active alerts for this equipment
                if diag.get("active_alerts"):
                    lines.append("")
                    lines.append(f"Active Alerts ({len(diag['active_alerts'])}):")
                    for alert in diag["active_alerts"][:5]:
                        sev = alert.get("severity", "info").upper()
                        msg = alert.get("message", "No details")
                        lines.append(f"  [{sev}] {msg}")

                # Active predictions/anomalies
                if diag.get("predictions"):
                    lines.append("")
                    lines.append(f"ML Predictions ({len(diag['predictions'])}):")
                    for pred in diag["predictions"][:3]:
                        ptype = pred.get("prediction_type", "unknown")
                        prob = pred.get("probability_percent", 0)
                        action = pred.get("recommended_action", "")
                        lines.append(f"  - {ptype}: {prob}% probability")
                        if action:
                            lines.append(f"    Recommended: {action}")

                # Current sensor readings
                if diag.get("readings"):
                    lines.append("")
                    lines.append("Current Readings:")
                    for key, val in diag["readings"].items():
                        lines.append(f"  - {key}: {val}")
        except Exception as diag_err:
            logger.warning(f"Could not fetch equipment diagnostics for WO email: {diag_err}")

    # Pull equipment-specific template for field instructions & required feedback
    eq_type_for_template = None
    if equipment_code:
        # Extract type from equipment code: S002-AHU-L1-001 → ahu
        parts = equipment_code.split("-")
        if len(parts) >= 2:
            eq_type_for_template = parts[1].lower()

    template_items = _get_template_requirements(eq_type_for_template)

    # Field instructions
    lines.extend(
        [
            "",
            "FIELD INSTRUCTIONS",
            "1. Verify site safety controls before touching equipment.",
        ]
    )
    if template_items:
        # Equipment-specific prompts from ML template
        step = 2
        for _item_name, prompt in template_items["prompts"].items():
            lines.append(f"{step}. {prompt}")
            step += 1
        lines.append(f"{step}. Document all findings with photos, measurements, and notes.")
    else:
        lines.extend(
            [
                "2. Inspect the faulted subsystem and capture photos/readings.",
                "3. Run diagnostics and record measured values.",
                "4. Identify likely root cause and required corrective action.",
                "5. Document all findings with photos, measurements, and notes.",
            ]
        )

    # Next steps
    lines.extend(
        [
            "",
            "NEXT STEPS",
            "1. Perform inspection and diagnostics per instructions above.",
            "2. Capture required photos and meter readings for the service record.",
            "3. Record root cause analysis and corrective action taken.",
            "4. Update work order status when complete.",
        ]
    )

    # Required feedback — equipment-specific or generic
    lines.append("")
    lines.append("REQUIRED FEEDBACK")
    if template_items and template_items.get("required"):
        for item in template_items["required"]:
            label = item.replace("_", " ").title()
            lines.append(f"- {label}")
        if template_items.get("optional"):
            lines.append("")
            lines.append("Optional (if available):")
            for item in template_items["optional"]:
                label = item.replace("_", " ").title()
                lines.append(f"- {label}")
        if template_items.get("validation_rules"):
            lines.append("")
            lines.append("Expected Ranges:")
            for field, rule in template_items["validation_rules"].items():
                label = field.replace("_", " ").title()
                unit = rule.get("unit", "")
                lines.append(f"- {label}: {rule['min']}-{rule['max']} {unit}".rstrip())
    else:
        lines.extend(
            [
                "- Before/after photos of affected equipment",
                "- Measured values (temperature, pressure, voltage as applicable)",
                "- Root cause identified",
                "- Corrective action taken or parts replaced",
                "- Estimated time to next scheduled maintenance",
            ]
        )

    lines.extend(
        [
            "",
            "---",
            "SENTINEL BMS Intelligence / Sentry",
        ]
    )

    return "\n".join(lines)


async def _fetch_equipment_diagnostics(equipment_code: str) -> dict[str, Any] | None:
    """Fetch equipment health, alerts, and predictions from Supabase for WO context."""
    try:
        client = get_supabase_client()

        # Get equipment details
        eq_resp = (
            client.table("equipment")
            .select(
                "id, code, name, type, health_score, status, last_service, "
                "manufacturer, model, location, device_info, site_id"
            )
            .eq("code", equipment_code)
            .execute()
        )

        if not eq_resp.data:
            return None

        eq = eq_resp.data[0]
        eq_uuid = eq["id"]

        # Get active alerts for this equipment
        alerts_resp = (
            client.table("alerts")
            .select("severity, message, type, created_at")
            .eq("equipment_id", eq_uuid)
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        # Get active predictions for this equipment
        pred_resp = (
            client.table("predictions")
            .select("prediction_type, probability_percent, recommended_action, contributing_factors")
            .eq("equipment_id", eq_uuid)
            .eq("status", "active")
            .order("probability_percent", desc=True)
            .limit(3)
            .execute()
        )

        # Extract current readings from device_info
        device_info = eq.get("device_info") or {}
        readings = {}
        if device_info.get("current_reading") is not None:
            unit = device_info.get("unit", "")
            readings["Current Reading"] = f"{device_info['current_reading']}{' ' + unit if unit else ''}"
        if device_info.get("setpoint") is not None:
            readings["Setpoint"] = f"{device_info['setpoint']}"
        if device_info.get("supply_temp") is not None:
            readings["Supply Temp"] = f"{device_info['supply_temp']}°C"
        if device_info.get("return_temp") is not None:
            readings["Return Temp"] = f"{device_info['return_temp']}°C"
        if device_info.get("power_kw") is not None:
            readings["Power"] = f"{device_info['power_kw']} kW"
        if device_info.get("brightness_percent") is not None:
            readings["Brightness"] = f"{device_info['brightness_percent']}%"

        return {
            "health_score": eq.get("health_score", 100) or 100,
            "status": eq.get("status", "unknown"),
            "type": eq.get("type"),
            "manufacturer": eq.get("manufacturer"),
            "model": eq.get("model"),
            "last_service": eq.get("last_service"),
            "active_alerts": alerts_resp.data or [],
            "predictions": pred_resp.data or [],
            "readings": readings if readings else None,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch equipment diagnostics for {equipment_code}: {e}")
        return None


async def close_work_order_chat(
    work_order_code: str,
    resolution: str | None = None,
    actual_duration_hours: float | None = None,
    _user_email: str | None = None,
) -> dict[str, Any]:
    """Close a work order by code — sets status to completed and records resolution.

    Used by the technician /done flow. Looks up by WO code, updates status
    to 'completed', stamps completed_at, and records resolution notes.
    """
    try:
        from datetime import timezone

        from app.database.repositories.work_order_repository import get_work_order_repository

        repo = get_work_order_repository()
        wo = await repo.get_work_order_by_code(work_order_code)

        if not wo:
            return {"success": False, "error": f"Work order '{work_order_code}' not found"}

        if wo.get("status") == "completed":
            return {
                "success": True,
                "work_order_code": work_order_code,
                "message": f"Work order {work_order_code} is already completed.",
            }

        updates: dict[str, Any] = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if resolution:
            updates["resolution"] = resolution
        if actual_duration_hours is not None:
            updates["actual_duration_hours"] = actual_duration_hours

        updated = await repo.update_work_order(wo["id"], updates)

        if not updated:
            return {"success": False, "error": f"Failed to update work order {work_order_code}"}

        logger.info("close_work_order: %s closed by %s", work_order_code, _user_email or "technician")
        return {
            "success": True,
            "work_order_code": work_order_code,
            "status": "completed",
            "message": f"Work order {work_order_code} closed successfully.",
            "resolution": resolution,
        }

    except Exception as e:
        logger.warning(f"close_work_order_chat failed for {work_order_code}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def create_work_order_chat(
    description: str,
    equipment_code: str | None = None,
    priority: str = "medium",
    category: str = "other",
    assigned_to: str | None = None,
    site_id: str | None = None,
    _user_email: str | None = None,
) -> dict[str, Any]:
    """Create a work order from chat via the Sentry work-order API.

    Uses the same POST /api/sentry/create-work-order endpoint as the /WO_
    slash command, ensuring work orders are persisted to Supabase and
    technicians are auto-assigned.

    Falls back to the in-memory work_order_service only if the Sentry API
    is unreachable.
    """
    try:
        import httpx

        from app.config.settings import settings

        reported_by = _user_email or "AI Chat (operator)"
        title = description[:120] if description else "Work order from chat"
        port = settings.port if hasattr(settings, "port") else 9095
        base_url = f"http://127.0.0.1:{port}"

        payload: dict[str, Any] = {
            "equipment_code": equipment_code or "GENERAL",
            "title": title,
            "description": description,
            "priority": priority,
            "created_by": reported_by,
        }
        if assigned_to:
            payload["assigned_to"] = assigned_to

        # Use the Sentry create-work-order endpoint (same as /WO_ slash command)
        headers: dict[str, str] = {
            "X-Sentry-Secret": settings.sentry_webhook_secret,
            "Content-Type": "application/json",
        }
        if settings.sentry_bot_api_key:
            headers["X-Sentry-API-Key"] = settings.sentry_bot_api_key

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{base_url}/api/sentry/create-work-order",
                json=payload,
                headers=headers,
            )

        if resp.status_code == 200:
            wo_data = resp.json()
            wo_code = wo_data.get("code", "N/A")
            assigned = wo_data.get("assigned_to", "Unassigned")

            confirmation = (
                f"**Work Order Created:** `{wo_code}`\n"
                f"**Equipment:** `{equipment_code or 'General'}`\n"
                f"**Priority:** {priority}\n"
                f"**Assigned To:** {assigned}\n"
                f"**Status:** scheduled"
            )

            # Send email confirmation if user email available
            if _user_email and "@" in _user_email:
                try:
                    from app.services.sentry_integration.work_order_notifier import WorkOrderNotifier

                    notifier = WorkOrderNotifier()
                    email_body = f"Work Order {wo_code} created for {equipment_code or 'General'}.\n\n{description}"
                    await notifier._send_email_via_local_gmail_helper(
                        to_email=_user_email,
                        subject=f"Work Order Created: {wo_code} — {equipment_code or 'General'}",
                        body=email_body,
                    )
                    logger.info(f"WO email confirmation sent to {_user_email} for {wo_code}")
                except Exception as email_err:
                    logger.warning(f"Could not send WO email to {_user_email}: {email_err}")

            return {
                "success": True,
                "work_order": wo_data,
                "message": confirmation,
                "email_sent_to": _user_email if _user_email and "@" in _user_email else None,
            }

        # Sentry API returned an error — log and fall back
        logger.warning(f"Sentry create-work-order returned {resp.status_code}, falling back to in-memory")

    except Exception as e:
        logger.warning(f"Sentry WO API unreachable, falling back to in-memory: {e}")

    # Fallback: in-memory work order service (for local/offline scenarios)
    try:
        from app.services.work_order_service import work_order_service

        wo = work_order_service.create_work_order(
            description=description,
            site_id=site_id or _default_site_id(),
            equipment_ref=equipment_code,
            category=category,
            priority=priority,
            reported_by=_user_email or "AI Chat (operator)",
        )
        return {
            "success": True,
            "work_order": wo.to_dict(),
            "message": wo.format_confirmation() + "\n\n*Note: Saved in-memory only (Sentry API unavailable)*",
        }
    except Exception as e:
        logger.error(f"Error creating work order: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="create_work_order_chat")


async def approve_recommendation_chat(
    recommendation_id: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Approve a Tier 2 recommendation from chat."""
    try:
        from app.agents.recommendation_tools import execute_approved_recommendation

        result = await execute_approved_recommendation(
            recommendation_id=recommendation_id,
            approved_by="chat:operator",
            notes=notes or "Approved via AI Chat",
        )
        return result
    except ImportError:
        return {"success": False, "error": "Recommendation agent not available"}
    except Exception as e:
        logger.error(f"Error approving recommendation: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="approve_recommendation_chat")


async def reject_recommendation_chat(
    recommendation_id: str,
    reason: str,
) -> dict[str, Any]:
    """Reject a Tier 2 recommendation from chat."""
    try:
        from app.agents.recommendation_tools import reject_recommendation

        result = await reject_recommendation(
            recommendation_id=recommendation_id,
            rejected_by="chat:operator",
            reason=reason,
        )
        return result
    except ImportError:
        return {"success": False, "error": "Recommendation agent not available"}
    except Exception as e:
        logger.error(f"Error rejecting recommendation: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="reject_recommendation_chat")


_RESET_BLOCKED_TYPES = {"FIRE", "GEN"}


async def reset_equipment_fault_chat(
    equipment_code: str,
    reason: str = "Operator reset via chat",
) -> dict[str, Any]:
    """Reset equipment fault from chat."""
    parts = equipment_code.split("-")
    eq_type = parts[1].upper() if len(parts) >= 2 else ""

    if eq_type in _RESET_BLOCKED_TYPES:
        return {
            "success": False,
            "blocked": True,
            "error": (
                f"{eq_type} equipment cannot be remotely reset for safety reasons. Please create a work order instead."
            ),
            "equipment_code": equipment_code,
        }

    try:
        from app.services.remote_command_service import RemoteCommandService

        service = RemoteCommandService()
        result = await service.execute_remote_command(
            user_id="chat:operator",
            user_role="operator",
            device_id=equipment_code,
            command_type="fault_reset",
            reason=reason,
        )
        reset_data = result.get("data", {})
        return {
            "success": result.get("success", False),
            "equipment_code": equipment_code,
            "message": result.get("message", ""),
            "previous_health": reset_data.get("previous_health"),
            "new_health": reset_data.get("new_health"),
            "predictions_resolved": reset_data.get("predictions_resolved", 0),
            "error": result.get("error") if not result.get("success") else None,
        }
    except Exception as e:
        logger.error(f"Error resetting equipment fault: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="reset_equipment_fault_chat")


def _format_doc_results(results: list[dict], query: str) -> dict[str, Any]:
    """Format RAG search results into a standardized response."""
    if not results:
        return {
            "success": True,
            "results": [],
            "message": f"No documentation found matching '{query}'.",
        }

    formatted = []
    citations: list[dict[str, Any]] = []
    for r in results:
        grounding = r.get("grounding") if isinstance(r.get("grounding"), dict) else {}
        citation = {
            "document_id": grounding.get("document_id") or r.get("document_id"),
            "chunk_id": grounding.get("chunk_id") or r.get("chunk_id") or r.get("id"),
            "document_title": grounding.get("document_title") or r.get("document_title", "Unknown"),
            "section_title": grounding.get("section_title") or r.get("section_title"),
            "page_number": grounding.get("page_number") if grounding else r.get("page_number"),
            "source": grounding.get("source") or r.get("source") or r.get("document_source"),
        }
        formatted.append(
            {
                "title": r.get("document_title", "Unknown"),
                "content": r.get("content", "")[:1500],
                "source": r.get("source", ""),
                "relevance": round(r.get("similarity", r.get("hybrid_score", 0)), 3),
                "citation": citation,
            }
        )
        citations.append(citation)

    return {
        "success": True,
        "results": formatted,
        "citations": citations,
        "count": len(formatted),
        "query": query,
    }


async def search_documents(
    query: str,
    n_results: int = 5,
) -> dict[str, Any]:
    """Search operational documentation and knowledge base via hybrid search.

    This searches building-scoped documents, equipment manuals, fault codes,
    and procedures. It does NOT search SENTINEL platform/system documentation
    unless search_system_documents is also enabled.
    """
    try:
        from app.services.doc_rag_service import search_documentation

        results = await search_documentation(
            query=query,
            n_results=min(n_results, 10),
        )
        return _format_doc_results(results, query)
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="search_documents") | {"results": []}


async def search_system_documents(
    query: str,
    n_results: int = 5,
) -> dict[str, Any]:
    """Search SENTINEL platform documentation (architecture, security, compliance, onboarding).

    This tool is only available when the user enables the 'Include SENTINEL platform
    documentation' toggle. Results are weighted at 30% relative to operational RAG (70%).
    """
    try:
        from app.services.doc_rag_service import search_documentation

        # System docs are not building-scoped — search without site_id filter
        results = await search_documentation(
            query=query,
            n_results=min(n_results, 10),
            site_id=None,  # Global platform docs
        )
        return _format_doc_results(results, query)
    except Exception as e:
        logger.error(f"Error searching system documents: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="search_system_documents") | {"results": []}


# ---------------------------------------------------------------------------
# Hybrid Context Tool (wires hybrid_query_service into chat)
# ---------------------------------------------------------------------------


async def get_hybrid_context(
    site_id: str | None = None,
    equipment_id: str | None = None,
    bacnet_ref: str | None = None,
    question: str | None = None,
    include_documents: bool = True,
    include_telemetry: bool = True,
    include_ml: bool = True,
) -> dict[str, Any]:
    """Merge Brick graph + telemetry + ML + document context for one asset.

    Read-only. Returns structured dict plus prompt-formatted text.
    """
    if not equipment_id and not bacnet_ref:
        return {
            "success": False,
            "error": "Provide either equipment_id or bacnet_ref.",
        }

    try:
        from app.core.site_resolver import get_primary_site_code
        from app.services.hybrid_query_service import get_hybrid_query_service

        effective_site = site_id or get_primary_site_code()
        if not effective_site:
            return {
                "success": False,
                "error": "No registered site available. Provide site_id explicitly.",
            }
        svc = get_hybrid_query_service(effective_site)

        ctx = await svc.query(
            equipment_id=equipment_id,
            bacnet_ref=bacnet_ref,
            question=question,
            include_documents=bool(include_documents),
            include_telemetry=bool(include_telemetry),
            include_ml=bool(include_ml),
        )

        result: dict[str, Any] = {
            "success": True,
            "equipment_id": ctx.equipment_id,
            "equipment_type": ctx.equipment_type,
            "site_id": effective_site,
            "sources_used": ctx.sources_used,
            "retrievalTelemetry": ctx.retrieval_telemetry,
            "context": ctx.to_dict(),
            "prompt_context": ctx.format_for_prompt(),
        }

        # Cap points in returned dict to avoid bloating tool response
        if result["context"].get("points") and len(result["context"]["points"]) > 10:
            result["context"]["points"] = result["context"]["points"][:10]
            result["context"]["points_truncated"] = True

        return result
    except Exception as e:
        logger.error(f"Error fetching hybrid context: {e}")
        return {"success": False} | calm_error_legacy(e, tool_name="get_hybrid_context")


# ---------------------------------------------------------------------------
# ServiceNow Integration Tools (Phase 138-02)
# ---------------------------------------------------------------------------


async def check_servicenow_status(site_id: str | None = None) -> dict[str, Any]:
    """Check ServiceNow connection status and available data.

    Args:
        site_id: Site identifier (unused, for consistency)

    Returns:
        Dictionary with connection status and discovered tables
    """
    try:
        from app.services.servicenow_service import get_servicenow_service

        service = get_servicenow_service()
        if not service.is_configured:
            return {
                "success": True,
                "configured": False,
                "message": (
                    "ServiceNow integration is not configured. "
                    "Set SERVICENOW_INSTANCE, SERVICENOW_USERNAME, "
                    "and SERVICENOW_PASSWORD environment variables."
                ),
            }
        status = service.status
        return {"success": True, "configured": True, **status.to_dict()}
    except ImportError:
        return {
            "success": False,
            "error": "ServiceNow service module not available",
        }
    except Exception as e:
        logger.error(f"check_servicenow_status error: {e}")
        return {"success": False, "error": "Failed to check ServiceNow status"}


async def query_servicenow_incidents(
    location: str | None = None,
    assignment_group: str | None = None,
    priority_max: int = 4,
    limit: int = 10,
) -> dict[str, Any]:
    """Query open incidents from ServiceNow.

    Args:
        location: Filter by location/building
        assignment_group: Filter by assignment group
        priority_max: Maximum priority level (1=critical, 4=low)
        limit: Maximum number of results

    Returns:
        Dictionary with incident list
    """
    try:
        from app.services.servicenow_service import get_servicenow_service

        service = get_servicenow_service()
        if not service.is_configured:
            return {
                "success": True,
                "configured": False,
                "message": "ServiceNow not configured",
                "incidents": [],
            }
        incidents = await service.query_incidents(
            location=location,
            assignment_group=assignment_group,
            priority_max=priority_max,
            limit=min(limit, 50),
        )
        return {
            "success": True,
            "incidents": incidents,
            "count": len(incidents),
        }
    except ImportError:
        return {
            "success": False,
            "error": "ServiceNow service module not available",
            "incidents": [],
        }
    except Exception as e:
        logger.error(f"query_servicenow_incidents error: {e}")
        return {"success": False, "error": "Failed to query incidents", "incidents": []}


async def query_servicenow_work_orders(
    location: str | None = None,
    state: str | None = None,
    assigned_to: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Query work orders from ServiceNow.

    Args:
        location: Filter by location/building
        state: Filter by work order state (e.g., 'open', 'in_progress', 'closed')
        assigned_to: Filter by assigned technician
        limit: Maximum number of results

    Returns:
        Dictionary with work order list
    """
    try:
        from app.services.servicenow_service import get_servicenow_service

        service = get_servicenow_service()
        if not service.is_configured:
            return {
                "success": True,
                "configured": False,
                "message": "ServiceNow not configured",
                "work_orders": [],
            }
        work_orders = await service.query_work_orders(
            location=location,
            state=state,
            assigned_to=assigned_to,
            limit=min(limit, 50),
        )
        return {
            "success": True,
            "work_orders": work_orders,
            "count": len(work_orders),
        }
    except ImportError:
        return {
            "success": False,
            "error": "ServiceNow service module not available",
            "work_orders": [],
        }
    except Exception as e:
        logger.error(f"query_servicenow_work_orders error: {e}")
        return {
            "success": False,
            "error": "Failed to query work orders",
            "work_orders": [],
        }


async def get_servicenow_incident_summary(
    location: str | None = None,
) -> dict[str, Any]:
    """Get incident count breakdown by priority and state.

    Args:
        location: Filter by location/building

    Returns:
        Dictionary with incident summary breakdown
    """
    try:
        from app.services.servicenow_service import get_servicenow_service

        service = get_servicenow_service()
        if not service.is_configured:
            return {
                "success": True,
                "configured": False,
                "message": "ServiceNow not configured",
            }
        summary = await service.get_incident_summary(location=location)
        return {"success": True, **summary}
    except ImportError:
        return {
            "success": False,
            "error": "ServiceNow service module not available",
        }
    except Exception as e:
        logger.error(f"get_servicenow_incident_summary error: {e}")
        return {"success": False, "error": "Failed to get incident summary"}


# Tool handler dispatch
TOOL_HANDLERS = {
    "list_devices": list_devices,
    "get_device_details": get_device_details,
    "control_device": control_device,
    "get_system_status": get_system_status,
    "get_optimization_recommendations": get_optimization_recommendations,
    "get_equipment_health": get_equipment_health,
    "get_equipment_service_history": get_equipment_service_history,
    "get_alerts_and_anomalies": get_alerts_and_anomalies,
    "get_energy_analysis": get_energy_analysis,
    "get_system_methodology": get_system_methodology,
    "lookup_desk": lookup_desk,
    "diagnose_comfort_complaint": diagnose_comfort_complaint,
    "handle_comfort_complaint": handle_comfort_complaint,
    "discover_niagara_points": discover_niagara_points,
    "review_point_mapping": review_point_mapping,
    "approve_point_mapping": approve_point_mapping,
    "correct_point_classification": correct_point_classification,
    "get_fire_system_status": get_fire_system_status,
    "get_security_status": get_security_status,
    # Solar tools (34-09)
    "get_solar_overview": get_solar_overview,
    "get_bess_status": get_bess_status_chat,
    "get_solar_savings": get_solar_savings,
    "get_solar_diagnostics": get_solar_diagnostics,
    "get_solar_forecast": get_solar_forecast,
    "get_floor_temperatures": get_floor_temperatures,
    "process_recommendation": process_recommendation,
    # Write/action tools (role-gated to operator+)
    "adjust_setpoint": adjust_setpoint,
    "close_work_order": close_work_order_chat,
    "create_work_order": create_work_order_chat,
    "approve_recommendation": approve_recommendation_chat,
    "reject_recommendation": reject_recommendation_chat,
    "reset_equipment_fault": reset_equipment_fault_chat,
    "search_documents": search_documents,
    "search_system_documents": search_system_documents,
    "get_hybrid_context": get_hybrid_context,
    # ServiceNow integration tools (Phase 138-02)
    "check_servicenow_status": check_servicenow_status,
    "query_servicenow_incidents": query_servicenow_incidents,
    "query_servicenow_work_orders": query_servicenow_work_orders,
    "get_servicenow_incident_summary": get_servicenow_incident_summary,
}


async def execute_tool(
    tool_name: str,
    tool_input: dict,
    site_id: str | None = None,
    user_email: str | None = None,
    user_role: SentinelRole | None = None,
) -> dict[str, Any]:
    """
    Execute a tool by name with given input.

    Enforces tool policy (137-07):
        1. Default deny — unregistered tools are rejected
        2. Tier enforcement — control tools require step-up
        3. Result sanitization — secrets/injection scanned, non-safe tools summarized

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        Tool execution result (sanitized)
    """
    from app.security.tool_policy import (
        REGISTERED_TOOLS,
        get_tool_tier,
        sanitize_tool_result,
    )

    # --- Default deny: reject unregistered tools ---
    if tool_name not in REGISTERED_TOOLS:
        logger.warning("TOOL_POLICY: unregistered tool requested: %s", tool_name)
        # Audit: TOOL_DENIED (Phase 137-09)
        try:
            from app.security.audit_events import audit_tool_denied

            audit_tool_denied(tool_name, reason="unregistered_tool")
        except Exception as e:
            logger.warning(f"audit_tool_denied injection failed for {tool_name}: {e}", exc_info=True)
        return {"error": "Unknown tool", "tool": tool_name}

    # --- Tier enforcement ---
    tier = get_tool_tier(tool_name)
    if tier == "unknown":
        return {"error": "Tool not registered in security policy", "tool": tool_name}

    # Role enforcement (defence in depth — tools are also filtered in get_chat_tools)
    required_role = TOOL_ROLE_REQUIREMENTS.get(tool_name)
    if required_role and not _has_required_role(user_role, required_role):
        return {
            "error": (f"Insufficient permissions: '{tool_name}' requires '{required_role.value}' role or higher."),
            "required_role": required_role.value,
            "current_role": user_role.value if user_role else "none",
        }

    effective_site_id = site_id or tool_input.get("site_id")
    if not _is_tool_allowed_for_site(
        tool_name,
        effective_site_id,
        user_email=user_email,
        user_role=user_role,
    ):
        required_module = TOOL_MODULE_REQUIREMENTS.get(tool_name)
        return {
            "error": (
                f"Tool '{tool_name}' is unavailable because module "
                f"'{required_module.value if required_module else 'unknown'}' "
                f"is not active for site '{effective_site_id}'"
            )
        }

    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    # Auto-inject site_id from chat context when Claude didn't pass it explicitly.
    # This ensures the user's building selector always scopes tool queries.
    if site_id and "site_id" not in tool_input:
        import inspect as _inspect

        sig = _inspect.signature(handler)
        if "site_id" in sig.parameters:
            tool_input["site_id"] = site_id

    # Inject user context into tools that accept it (137-07: real user attribution)
    if user_email and tool_name in ("create_work_order", "control_device"):
        tool_input["_user_email"] = user_email

    # --- Credential scanning on inputs (Gap 7: tool input scanning) ---
    try:
        from app.security.credential_scanner import redact_credentials, scan_tool_input

        findings = scan_tool_input(tool_name, tool_input)
        if findings:
            logger.warning(
                "CREDENTIAL_DETECTED in tool input for '%s': %s",
                tool_name,
                [f"{f['field']}={f['pattern']}" for f in findings],
            )
            # Audit the detection
            try:
                from app.security.audit_events import audit_secret_detected

                for f in findings:
                    audit_secret_detected(f"tool_input:{tool_name}:{f['field']}")
            except Exception as e:
                logger.warning(f"audit_secret_detected injection failed: {e}", exc_info=True)
            # Redact credentials from arguments before passing to handler
            tool_input = redact_credentials(tool_input)
    except Exception as e:
        logger.warning(f"credential_scan guard failed for {tool_name}: {e}", exc_info=True)

    import time as _time

    _t0 = _time.perf_counter()
    _outcome = "success"
    try:
        result = await handler(**tool_input)
        if isinstance(result, dict) and "error" in result:
            _outcome = "error"
        # --- Result sanitization (137-07) ---
        return sanitize_tool_result(result, tool_name)
    except TypeError as e:
        _outcome = "error"
        logger.error("Tool %s parameter error: %s", tool_name, e, exc_info=True)
        try:
            from app.services.governance_metrics_collector import governance_metrics

            governance_metrics.record_tool_error(tool_name, "param_validation")
        except Exception as e:
            logger.warning(f"governance_metrics.record_tool_error failed for {tool_name}: {e}", exc_info=True)
        return {"error": f"Invalid parameters for {tool_name}.", "tool": tool_name}
    except TimeoutError as e:
        _outcome = "error"
        logger.error("Tool %s timeout: %s", tool_name, e, exc_info=True)
        try:
            from app.services.governance_metrics_collector import governance_metrics

            governance_metrics.record_tool_error(tool_name, "timeout")
        except Exception as e:
            logger.warning(f"governance_metrics.record_tool_error failed for {tool_name}: {e}", exc_info=True)
        return {"error": "This operation timed out.", "tool": tool_name}
    except PermissionError as e:
        _outcome = "error"
        logger.error("Tool %s permission error: %s", tool_name, e, exc_info=True)
        try:
            from app.services.governance_metrics_collector import governance_metrics

            governance_metrics.record_tool_error(tool_name, "permission")
        except Exception as e:
            logger.warning(f"governance_metrics.record_tool_error failed for {tool_name}: {e}", exc_info=True)
        return {"error": "This operation could not be completed.", "tool": tool_name}
    except Exception as e:
        _outcome = "error"
        _error_type = "execution"
        if isinstance(e, RuntimeError) and "module" in str(e).lower():
            _error_type = "module_inactive"
        try:
            from app.services.governance_metrics_collector import governance_metrics

            governance_metrics.record_tool_error(tool_name, _error_type)
        except Exception as e:
            logger.warning(f"governance_metrics.record_tool_error failed for {tool_name}: {e}", exc_info=True)
        logger.error("Tool %s execution error: %s", tool_name, e, exc_info=True)
        return {"error": "This operation could not be completed.", "tool": tool_name}
    finally:
        _duration = _time.perf_counter() - _t0
        try:
            from app.api.metrics import (
                sentinel_tool_call_duration_seconds,
                sentinel_tool_calls_total,
            )

            sentinel_tool_calls_total.labels(tool_name=tool_name, outcome=_outcome).inc()
            sentinel_tool_call_duration_seconds.labels(tool_name=tool_name).observe(_duration)
        except Exception as e:
            logger.warning(f"metrics recording failed for {tool_name}: {e}", exc_info=True)
