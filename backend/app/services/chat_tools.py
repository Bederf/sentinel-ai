"""Chat tool handlers for Claude AI BMS intelligence.

This module implements the tool functions that Claude can call to:
- Query real-time device status and readings
- Control building devices with safety validation
- Get optimization recommendations
- Access alerts, anomalies, and maintenance status
- Provide intelligent suggestions for building operations
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.device_abstraction import device_manager
from app.models.device import DeviceStatus

logger = logging.getLogger(__name__)

# Sandton building - the one with DALI integration
SANDTON_SITE_ID = "site-002"  # Sandton City in sites.json

# Data directory for building data
DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(filename: str) -> list | dict:
    """Load JSON data file."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


async def list_devices(
    device_type: str | None = None,
    site_id: str | None = None
) -> dict[str, Any]:
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
            device_list.append({
                "id": device.id,
                "name": device.name,
                "type": device.device_type.value,
                "status": device.status.value,
                "location": device.location,
                "site_id": device.site_id,
            })

        return {
            "success": True,
            "count": len(device_list),
            "devices": device_list
        }
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        return {
            "success": False,
            "error": str(e),
            "devices": []
        }


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
            return {
                "success": False,
                "error": f"Device '{device_id}' not found"
            }

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
                        "quality": value.quality
                    }
                except Exception as e:
                    point_values[point_name] = {"error": str(e)}

        # Get safety status
        try:
            safety_status = await device_manager.get_device_safety_status(device_id)
        except Exception as e:
            safety_status = {"error": str(e)}

        # Build point definitions
        points_info = {}
        for name, point in device.points.items():
            points_info[name] = {
                "description": point.description,
                "unit": point.unit,
                "writable": point.writable,
                "min_value": point.min_value,
                "max_value": point.max_value,
                "current_value": point_values.get(name, {}).get("value")
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
            "safety_status": safety_status
        }
    except Exception as e:
        logger.error(f"Error getting device details for {device_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def control_device(
    device_id: str,
    point: str,
    value: Any,
    reason: str = "AI assistant control"
) -> dict[str, Any]:
    """
    Execute a control action on a device.

    All control actions go through safety validation and are logged
    to the audit trail with user="ai-assistant".

    Args:
        device_id: The device ID to control
        point: The point name to write (e.g., "setpoint", "state")
        value: The value to write
        reason: Reason for the control action (for audit log)

    Returns:
        Dictionary with success/failure and details
    """
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            return {
                "success": False,
                "error": f"Device '{device_id}' not found"
            }

        # Check device is online
        if device.status not in [DeviceStatus.ONLINE, DeviceStatus.STANDBY]:
            return {
                "success": False,
                "error": f"Device '{device.name}' is {device.status.value} and cannot be controlled"
            }

        # Check point exists and is writable
        device_point = device.get_point(point)
        if not device_point:
            available_points = [p for p in device.points.keys()]
            return {
                "success": False,
                "error": f"Point '{point}' not found on device '{device.name}'. Available points: {available_points}"
            }

        if not device_point.writable:
            return {
                "success": False,
                "error": f"Point '{point}' is read-only and cannot be controlled"
            }

        # Get current value for response
        old_value = None
        try:
            current = await device_manager.read_device_value(device_id, point)
            old_value = current.value
        except Exception:
            pass  # Continue even if we can't read current value

        # Execute control with safety validation (uses user="ai-assistant")
        # The write_device_value method handles safety validation and audit logging
        success = await device_manager.write_device_value(
            device_id=device_id,
            point_name=point,
            value=value,
            user="ai-assistant"
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
                "reason": reason
            }
        else:
            return {
                "success": False,
                "error": f"Failed to write value to device. The device may be unresponsive."
            }

    except ValueError as e:
        # Safety validation failures come as ValueError
        error_msg = str(e)
        logger.warning(f"Control blocked for {device_id}.{point}={value}: {error_msg}")
        return {
            "success": False,
            "blocked": True,
            "error": error_msg,
            "device_id": device_id,
            "point": point,
            "attempted_value": value
        }
    except Exception as e:
        logger.error(f"Error controlling device {device_id}.{point}={value}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def get_system_status(site_id: str | None = None) -> dict[str, Any]:
    """
    Get overall BMS system status including alerts, anomalies, and equipment health.

    Args:
        site_id: Optional site ID to filter status

    Returns:
        Dictionary with system status, active alerts, predicted issues, and recommendations
    """
    try:
        sites = load_json("sites.json")
        equipment = load_json("equipment.json")
        alerts = load_json("alerts.json")
        anomalies = load_json("anomalies.json")
        predictions = load_json("predictions.json")

        # Filter by site if provided
        if site_id:
            sites = [s for s in sites if s["id"] == site_id]
            equipment = [e for e in equipment if e.get("site_id") == site_id]
            alerts = [a for a in alerts if a.get("site_id") == site_id]
            anomalies = [a for a in anomalies if a.get("site_id") == site_id]
            predictions = [p for p in predictions if p.get("site_id") == site_id]

        # Active alerts summary
        active_alerts = [a for a in alerts if a.get("status") == "active"]
        critical_alerts = [a for a in active_alerts if a.get("severity") == "critical"]
        warning_alerts = [a for a in active_alerts if a.get("severity") == "warning"]

        # Equipment health summary
        healthy_equipment = [e for e in equipment if e.get("health_score", 0) >= 80]
        degraded_equipment = [e for e in equipment if 50 <= e.get("health_score", 0) < 80]
        critical_equipment = [e for e in equipment if e.get("health_score", 0) < 50]

        # High-priority predictions
        urgent_predictions = [p for p in predictions if p.get("probability_percent", 0) >= 70]

        # Build status response
        status = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_sites": len(sites),
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
            "recommendations": [],
        }

        # Add critical issues
        for alert in critical_alerts[:5]:
            status["critical_issues"].append({
                "type": "alert",
                "id": alert["id"],
                "severity": "critical",
                "title": alert.get("title", "Unknown"),
                "site": alert.get("site_id"),
                "equipment": alert.get("equipment_id"),
                "estimated_cost": alert.get("estimated_cost_zar", 0),
            })

        for eq in critical_equipment[:5]:
            status["critical_issues"].append({
                "type": "equipment_health",
                "id": eq["id"],
                "name": eq["name"],
                "health_score": eq.get("health_score", 0),
                "status": eq.get("status"),
                "last_service": eq.get("last_service"),
            })

        # Add proactive recommendations based on system state
        if len(critical_alerts) > 0:
            status["recommendations"].append({
                "priority": "high",
                "action": "Address critical alerts immediately",
                "details": f"{len(critical_alerts)} critical alerts require immediate attention",
            })

        if len(critical_equipment) > 0:
            status["recommendations"].append({
                "priority": "high",
                "action": "Schedule maintenance for degraded equipment",
                "details": f"{len(critical_equipment)} equipment items below 50% health",
            })

        for pred in urgent_predictions[:3]:
            status["recommendations"].append({
                "priority": "medium",
                "action": f"Preventive maintenance: {pred.get('equipment_name', 'Unknown')}",
                "details": f"{pred.get('probability_percent', 0)}% failure probability within {pred.get('timeframe_days', 0)} days",
                "potential_savings": pred.get("financial_impact", {}).get("potential_loss_zar", 0) - pred.get("financial_impact", {}).get("repair_cost_zar", 0),
            })

        return status

    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {"success": False, "error": str(e)}


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
        from app.services.ai_optimizer import ai_optimizer_service

        recommendation = await ai_optimizer_service.analyze_building(site_id)

        return {
            "success": True,
            "site_id": site_id,
            "timestamp": recommendation.timestamp,
            "recommendations": recommendation.recommendations,
            "projected_savings": recommendation.projected_savings,
            "confidence": recommendation.confidence,
            "reasoning": recommendation.reasoning,
            "note": "These are AI-generated recommendations. Use control_device to apply them after review."
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {e}")
        return {"success": False, "error": str(e)}


async def get_equipment_health(
    site_id: str | None = None,
    equipment_id: str | None = None,
    status_filter: str | None = None
) -> dict[str, Any]:
    """
    Get equipment health status and maintenance information.

    Args:
        site_id: Optional site ID to filter
        equipment_id: Optional specific equipment ID
        status_filter: Filter by status (critical, warning, normal)

    Returns:
        Dictionary with equipment health details and maintenance recommendations
    """
    try:
        equipment = load_json("equipment.json")
        predictions = load_json("predictions.json")

        # Filter equipment
        if equipment_id:
            equipment = [e for e in equipment if e["id"] == equipment_id]
        elif site_id:
            equipment = [e for e in equipment if e.get("site_id") == site_id]

        if status_filter:
            if status_filter == "critical":
                equipment = [e for e in equipment if e.get("health_score", 100) < 50]
            elif status_filter == "warning":
                equipment = [e for e in equipment if 50 <= e.get("health_score", 100) < 80]
            elif status_filter == "normal":
                equipment = [e for e in equipment if e.get("health_score", 100) >= 80]

        # Build predictions lookup
        pred_by_equipment = {}
        for pred in predictions:
            eq_id = pred.get("equipment_id")
            if eq_id:
                if eq_id not in pred_by_equipment:
                    pred_by_equipment[eq_id] = []
                pred_by_equipment[eq_id].append(pred)

        # Build response
        equipment_list = []
        for eq in equipment:
            eq_preds = pred_by_equipment.get(eq["id"], [])
            highest_risk = max([p.get("probability_percent", 0) for p in eq_preds], default=0)

            item = {
                "id": eq["id"],
                "name": eq["name"],
                "type": eq["type"],
                "site_id": eq.get("site_id"),
                "health_score": eq.get("health_score", 100),
                "status": eq.get("status", "unknown"),
                "last_service": eq.get("last_service"),
                "failure_risk_percent": highest_risk,
                "maintenance_due": eq.get("health_score", 100) < 70 or highest_risk > 60,
            }

            # Add recommendation if needed
            if item["health_score"] < 50:
                item["recommendation"] = "Schedule immediate maintenance - equipment health critical"
            elif item["health_score"] < 70:
                item["recommendation"] = "Plan preventive maintenance within 2 weeks"
            elif highest_risk > 70:
                item["recommendation"] = f"High failure risk ({highest_risk}%) - schedule inspection"

            equipment_list.append(item)

        # Sort by health score (worst first)
        equipment_list.sort(key=lambda x: x["health_score"])

        return {
            "success": True,
            "count": len(equipment_list),
            "equipment": equipment_list,
            "summary": {
                "critical_count": len([e for e in equipment_list if e["health_score"] < 50]),
                "warning_count": len([e for e in equipment_list if 50 <= e["health_score"] < 80]),
                "healthy_count": len([e for e in equipment_list if e["health_score"] >= 80]),
                "maintenance_due_count": len([e for e in equipment_list if e.get("maintenance_due")]),
            }
        }
    except Exception as e:
        logger.error(f"Error getting equipment health: {e}")
        return {"success": False, "error": str(e)}


async def get_alerts_and_anomalies(
    site_id: str | None = None,
    severity: str | None = None,
    include_resolved: bool = False
) -> dict[str, Any]:
    """
    Get active alerts and detected anomalies.

    Args:
        site_id: Optional site ID to filter
        severity: Filter by severity (critical, warning, info)
        include_resolved: Include resolved/acknowledged alerts

    Returns:
        Dictionary with alerts and anomalies
    """
    try:
        alerts = load_json("alerts.json")
        anomalies = load_json("anomalies.json")

        # Filter alerts
        if not include_resolved:
            alerts = [a for a in alerts if a.get("status") == "active"]
        if site_id:
            alerts = [a for a in alerts if a.get("site_id") == site_id]
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]

        # Filter anomalies
        if site_id:
            anomalies = [a for a in anomalies if a.get("site_id") == site_id]

        # Sort by priority/urgency
        alerts.sort(key=lambda a: a.get("priority", 99))
        anomalies.sort(key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a.get("urgency", "low"), 4))

        # Format alerts
        formatted_alerts = []
        for alert in alerts[:20]:
            formatted_alerts.append({
                "id": alert["id"],
                "severity": alert.get("severity"),
                "title": alert.get("title"),
                "description": alert.get("description"),
                "site_id": alert.get("site_id"),
                "equipment_id": alert.get("equipment_id"),
                "estimated_cost_zar": alert.get("estimated_cost_zar", 0),
                "created_at": alert.get("created_at"),
            })

        # Format anomalies
        formatted_anomalies = []
        for anomaly in anomalies[:10]:
            formatted_anomalies.append({
                "id": anomaly["id"],
                "type": anomaly.get("type"),
                "urgency": anomaly.get("urgency"),
                "site_id": anomaly.get("site_id"),
                "equipment_id": anomaly.get("equipment_id"),
                "predicted_failure": anomaly.get("predicted_failure"),
                "confidence": anomaly.get("confidence"),
                "repair_cost_zar": anomaly.get("repair_cost_zar", 0),
                "damage_cost_zar": anomaly.get("damage_cost_zar", 0),
            })

        return {
            "success": True,
            "alerts": {
                "count": len(formatted_alerts),
                "items": formatted_alerts,
            },
            "anomalies": {
                "count": len(formatted_anomalies),
                "items": formatted_anomalies,
            },
            "summary": {
                "total_active_alerts": len([a for a in alerts if a.get("status") == "active"]),
                "critical_alerts": len([a for a in alerts if a.get("severity") == "critical"]),
                "total_estimated_cost": sum(a.get("estimated_cost_zar", 0) for a in alerts),
                "total_potential_damage": sum(a.get("damage_cost_zar", 0) for a in anomalies),
            }
        }
    except Exception as e:
        logger.error(f"Error getting alerts and anomalies: {e}")
        return {"success": False, "error": str(e)}


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
                        device_readings[point_name] = {
                            "value": value.value,
                            "unit": value.unit
                        }
                    except Exception:
                        pass
                if device_readings:
                    readings[device.id] = {
                        "device_name": device.name,
                        "type": device.device_type.value,
                        "readings": device_readings
                    }

        # Generate energy insights based on readings
        insights = []
        suggestions = []

        # Check HVAC efficiency
        for device_id, data in readings.items():
            if data["type"] == "hvac":
                r = data["readings"]
                # Check temperature differential
                if "supply_temp" in r and "return_temp" in r:
                    diff = r["return_temp"]["value"] - r["supply_temp"]["value"]
                    if diff < 4:
                        insights.append(f"{data['device_name']}: Low temperature differential ({diff:.1f}°C) indicates reduced cooling efficiency")
                        suggestions.append(f"Check {data['device_name']} for coil fouling or low refrigerant")

                # Check setpoints
                if "setpoint" in r:
                    setpoint = r["setpoint"]["value"]
                    if setpoint < 22:
                        suggestions.append(f"Consider raising {data['device_name']} setpoint from {setpoint}°C to 23°C for energy savings")

        # Check lighting usage
        for device_id, data in readings.items():
            if data["type"] == "lighting":
                r = data["readings"]
                if "brightness" in r and r["brightness"]["value"] > 80:
                    suggestions.append(f"Consider reducing {data['device_name']} brightness from {r['brightness']['value']}% during off-peak hours")

        return {
            "success": True,
            "site_id": site_id,
            "site_name": site["name"],
            "timestamp": datetime.now().isoformat(),
            "current_readings": readings,
            "insights": insights if insights else ["System operating within normal parameters"],
            "efficiency_suggestions": suggestions if suggestions else ["No immediate efficiency improvements identified"],
            "tip": "Use get_optimization_recommendations for AI-powered setpoint optimization"
        }
    except Exception as e:
        logger.error(f"Error getting energy analysis: {e}")
        return {"success": False, "error": str(e)}


async def lookup_desk(desk_id: str, building: str | None = None) -> dict[str, Any]:
    """
    Look up a desk and return its zone, HVAC, and sensor context.

    For Sandton which has DALI integration, this returns
    detailed occupancy and lighting data from PIR sensors.

    Args:
        desk_id: Desk identifier (e.g., "201", "L12-25", "Desk 25")
        building: Optional building name. If not provided and multiple buildings
                  have desks, will return a prompt asking for clarification.

    Returns:
        Dictionary with desk info, zone, HVAC status, and DALI sensor data
    """
    try:
        # Load desk and zone data
        desks = load_json("desks.json")
        zones = load_json("hvac_zones.json")

        if not desks:
            return {
                "success": False,
                "error": "Desk data not available",
                "prompt_user": "I don't have desk mapping data loaded. Which building and zone is the user in?"
            }

        # Normalize desk ID - extract number from various formats
        import re
        desk_num = re.sub(r'[^0-9]', '', str(desk_id))
        if not desk_num:
            return {
                "success": False,
                "error": f"Invalid desk ID format: {desk_id}",
                "prompt_user": f"I couldn't parse desk ID '{desk_id}'. Can you provide just the desk number (e.g., 201, 25)?"
            }

        # Find desk - try exact match first, then partial
        desk = None
        for d in desks:
            d_num = re.sub(r'[^0-9]', '', str(d.get('desk_id', '')))
            if d_num == desk_num:
                desk = d
                break

        if not desk:
            # Desk not found - prompt for more info
            available_desks = [d.get('desk_id') for d in desks[:10]]
            return {
                "success": False,
                "error": f"Desk {desk_id} not found in mapping",
                "prompt_user": f"I don't have desk {desk_id} in my database. Can you confirm the desk number? Available desks include: {', '.join(available_desks)}...",
                "available_sample": available_desks
            }

        # Get zone info
        zone_id = desk.get('zone_id')
        zone = next((z for z in zones if z.get('zone_id') == zone_id), None)

        # Get DALI/occupancy context for Sandton
        dali_context = {}
        try:
            from app.services.cross_system_analyzer import get_cross_system_analyzer
            analyzer = get_cross_system_analyzer()

            # Get zone occupancy from DALI sensors
            if zone_id:
                zone_analysis = analyzer.dali.get_zone_analysis(zone_id)
                dali_context = {
                    "occupancy_percent": zone_analysis.get('occupancy_percent', 0),
                    "avg_lux": zone_analysis.get('average_lux', 0),
                    "sensors_active": zone_analysis.get('occupied_count', 0),
                    "total_sensors": zone_analysis.get('total_sensors', 0),
                    "high_daylight": zone_analysis.get('average_lux', 0) > 800,
                }
        except Exception as e:
            logger.warning(f"Could not get DALI context: {e}")
            dali_context = {"available": False, "reason": str(e)}

        # Build response
        response = {
            "success": True,
            "desk": {
                "desk_id": desk.get('desk_id'),
                "floor": desk.get('floor'),
                "building": desk.get('building', 'Sandton'),
                "zone_id": zone_id,
                "near_window": desk.get('near_window', False),
                "near_diffuser": desk.get('near_diffuser', False),
                "near_printer": desk.get('near_printer', False),
            },
            "zone": None,
            "hvac": None,
            "dali": dali_context,
            "context_flags": []
        }

        # Add context flags for diagnosis
        if desk.get('near_window'):
            response["context_flags"].append("NEAR_WINDOW - Check for solar heat gain")
        if desk.get('near_diffuser'):
            response["context_flags"].append("NEAR_DIFFUSER - May experience direct airflow")
        if desk.get('near_printer'):
            response["context_flags"].append("NEAR_PRINTER - Local heat source")
        if dali_context.get('high_daylight'):
            response["context_flags"].append("HIGH_DAYLIGHT - Solar gain likely")

        # Add zone info if available
        if zone:
            response["zone"] = {
                "zone_id": zone.get('zone_id'),
                "zone_name": zone.get('zone_name'),
                "floor": zone.get('floor'),
                "setpoint": zone.get('setpoint'),
                "current_temp": zone.get('current_temp'),
                "status": zone.get('status'),
            }
            response["hvac"] = {
                "fcu_id": zone.get('fcu_id'),
                "vav_id": zone.get('vav_id'),
                "sensors": zone.get('sensors', []),
            }

        return response

    except Exception as e:
        logger.error(f"Error looking up desk {desk_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "prompt_user": "I encountered an error looking up that desk. Can you provide more details about the location?"
        }


async def diagnose_comfort_complaint(
    desk_id: str,
    complaint_type: str,
    building: str | None = None,
    additional_info: str | None = None
) -> dict[str, Any]:
    """
    Diagnose a comfort complaint for a specific desk.

    Uses desk location, HVAC zone data, and DALI sensors to determine
    the root cause and suggest actions.

    Args:
        desk_id: Desk identifier (e.g., "201", "L12-25")
        complaint_type: Type of complaint: "too_hot", "too_cold", "stuffy", "drafty"
        building: Optional building name for disambiguation
        additional_info: Any additional context from the technician

    Returns:
        Dictionary with diagnosis, root cause, confidence, and suggested actions
    """
    try:
        # First look up the desk
        desk_info = await lookup_desk(desk_id, building)

        if not desk_info.get("success"):
            return desk_info  # Pass through the error/prompt

        # Get current time for solar analysis
        from datetime import datetime
        current_hour = datetime.now().hour
        is_afternoon = 12 <= current_hour <= 18

        # Analyze based on complaint type and context
        diagnosis = {
            "success": True,
            "desk_id": desk_id,
            "complaint_type": complaint_type,
            "desk_info": desk_info.get("desk"),
            "zone_info": desk_info.get("zone"),
            "hvac_info": desk_info.get("hvac"),
            "dali_info": desk_info.get("dali"),
            "diagnosis": None,
            "root_cause": None,
            "confidence": "medium",
            "suggested_actions": [],
            "auto_actions_taken": [],
            "dispatch_required": False,
        }

        context_flags = desk_info.get("context_flags", [])
        zone = desk_info.get("zone", {}) or {}
        dali = desk_info.get("dali", {}) or {}
        desk = desk_info.get("desk", {}) or {}

        current_temp = zone.get("current_temp", 22)
        setpoint = zone.get("setpoint", 22)
        temp_diff = current_temp - setpoint if current_temp and setpoint else 0

        # Diagnose based on complaint type
        if complaint_type in ["too_hot", "hot"]:
            if desk.get("near_window") and is_afternoon:
                diagnosis["root_cause"] = "Solar heat gain from window"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = f"Desk {desk_id} is near a window and it's {current_hour}:00 (afternoon). Solar radiation is likely causing localized heating despite HVAC working correctly."
                diagnosis["suggested_actions"] = [
                    "Close blinds/shades near the desk",
                    "Temporarily boost zone cooling by 2°C for 2 hours",
                    f"Offer to relocate user to shaded desk (away from windows)",
                ]
            elif dali.get("high_daylight"):
                diagnosis["root_cause"] = "High daylight/solar gain detected by DALI sensors"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = f"DALI sensors show {dali.get('avg_lux', 0)} lux at this location - significantly above normal. This indicates direct sunlight causing heat gain."
                diagnosis["suggested_actions"] = [
                    "Reduce lighting levels (daylight harvesting)",
                    "Close blinds to reduce solar load",
                    "Boost cooling temporarily",
                ]
            elif temp_diff > 1.5:
                diagnosis["root_cause"] = "Zone temperature above setpoint"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = f"Zone is {temp_diff:.1f}°C above setpoint ({current_temp}°C vs {setpoint}°C target). HVAC may be undersized or equipment fault."
                diagnosis["suggested_actions"] = [
                    f"Check FCU {zone.get('fcu_id', 'unknown')} for faults",
                    "Verify supply air temperature",
                    "Check if zone is overcrowded",
                ]
                diagnosis["dispatch_required"] = True
            elif desk.get("near_printer"):
                diagnosis["root_cause"] = "Local heat source (printer/equipment)"
                diagnosis["confidence"] = "medium"
                diagnosis["diagnosis"] = f"Desk {desk_id} is near a printer or other heat-generating equipment. This creates a localized hot spot."
                diagnosis["suggested_actions"] = [
                    "Relocate printer or add local extraction",
                    "Consider desk relocation",
                    "Add small desk fan as temporary measure",
                ]
            else:
                diagnosis["root_cause"] = "Unknown - requires investigation"
                diagnosis["confidence"] = "low"
                diagnosis["diagnosis"] = f"No obvious cause found. Zone temp is {current_temp}°C (setpoint {setpoint}°C). May need on-site inspection."
                diagnosis["suggested_actions"] = [
                    "Check for blocked diffusers near desk",
                    "Verify VAV damper position",
                    "Check occupancy levels in zone",
                ]
                diagnosis["dispatch_required"] = True

        elif complaint_type in ["too_cold", "cold", "freezing"]:
            if desk.get("near_diffuser"):
                diagnosis["root_cause"] = "Direct airflow from supply diffuser"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = f"Desk {desk_id} is directly under or near a supply diffuser. Cold supply air is causing discomfort."
                diagnosis["suggested_actions"] = [
                    f"Adjust VAV damper {zone.get('vav_id', 'unknown')} to reduce airflow",
                    "Install diffuser deflector",
                    "Relocate user away from direct airflow",
                ]
                diagnosis["dispatch_required"] = True
            elif temp_diff < -1.5:
                diagnosis["root_cause"] = "Zone overcooling"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = f"Zone is {abs(temp_diff):.1f}°C below setpoint ({current_temp}°C vs {setpoint}°C). Possible control issue."
                diagnosis["suggested_actions"] = [
                    "Raise zone setpoint by 1-2°C",
                    "Check cooling valve position",
                    "Verify temperature sensor calibration",
                ]
            else:
                diagnosis["root_cause"] = "Personal comfort preference"
                diagnosis["confidence"] = "medium"
                diagnosis["diagnosis"] = f"Zone temperature ({current_temp}°C) is close to setpoint ({setpoint}°C). May be personal preference."
                diagnosis["suggested_actions"] = [
                    "Offer desk heater (temporary)",
                    "Check for drafts from windows/doors",
                    "Consider desk relocation to warmer area",
                ]

        elif complaint_type in ["stuffy", "poor_air", "stale"]:
            if dali.get("occupancy_percent", 0) > 70:
                diagnosis["root_cause"] = "High occupancy causing CO2 buildup"
                diagnosis["confidence"] = "high"
                diagnosis["diagnosis"] = f"Zone occupancy is {dali.get('occupancy_percent', 0):.0f}% - high density is likely causing poor air quality."
                diagnosis["suggested_actions"] = [
                    "Increase fresh air damper on AHU",
                    "Check CO2 sensor readings",
                    "Consider temporary portable air purifier",
                ]
            else:
                diagnosis["root_cause"] = "Insufficient ventilation"
                diagnosis["confidence"] = "medium"
                diagnosis["diagnosis"] = "Air quality complaint despite normal occupancy. May be ventilation equipment issue."
                diagnosis["suggested_actions"] = [
                    f"Check FCU {zone.get('fcu_id', 'unknown')} fan status",
                    "Verify fresh air damper position",
                    "Check for blocked return air grilles",
                ]
                diagnosis["dispatch_required"] = True

        elif complaint_type in ["drafty", "draft", "windy"]:
            diagnosis["root_cause"] = "Excessive airflow or infiltration"
            diagnosis["confidence"] = "medium"
            diagnosis["diagnosis"] = f"Draft complaint at desk {desk_id}. Could be supply diffuser, window seals, or door proximity."
            diagnosis["suggested_actions"] = [
                "Check nearby diffuser airflow direction",
                "Inspect window seals for gaps",
                "Install draft deflector if near diffuser",
            ]
            if desk.get("near_diffuser"):
                diagnosis["confidence"] = "high"
                diagnosis["root_cause"] = "Supply diffuser causing draft"

        return diagnosis

    except Exception as e:
        logger.error(f"Error diagnosing comfort complaint for desk {desk_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "prompt_user": "I encountered an error during diagnosis. Can you provide more details about the complaint?"
        }


# Password for accessing proprietary system methodology
METHODOLOGY_PASSWORD = "Open says me"

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
| **Anomaly Indicators** | 20% | Vibration analysis, temperature trends, pressure deviations, power consumption patterns |

**Health Score Thresholds:**
- **80-100%**: Healthy - Normal operation, no action needed
- **50-79%**: Degraded - Schedule preventive maintenance within 2-4 weeks
- **Below 50%**: Critical - Immediate attention required, high failure risk

### Failure Prediction Methodology

SENTINEL uses **machine learning models** trained on historical failure data:

1. **Pattern Recognition**: Analyzes sensor trends (temperature, vibration, pressure) against known pre-failure signatures
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


async def get_system_methodology(password: str, topic: str | None = None) -> dict[str, Any]:
    """
    Get proprietary SENTINEL system methodology documentation.

    Requires admin password to access.

    Args:
        password: Admin password to access methodology
        topic: Optional specific topic (health_score, predictions, optimization, safety)

    Returns:
        System methodology documentation or access denied message
    """
    if password != METHODOLOGY_PASSWORD:
        logger.warning(f"Failed methodology access attempt with password: {password[:3]}***")
        return {
            "success": False,
            "access_denied": True,
            "message": "Access denied. Incorrect password. Please contact your system administrator for access to proprietary methodology documentation."
        }

    logger.info(f"Methodology access granted for topic: {topic or 'all'}")

    # Return full or topic-specific documentation
    if topic:
        topic_lower = topic.lower()
        sections = SYSTEM_METHODOLOGY.split("### ")

        for section in sections:
            if topic_lower in section.lower():
                return {
                    "success": True,
                    "topic": topic,
                    "documentation": "### " + section.strip()
                }

        return {
            "success": True,
            "topic": topic,
            "documentation": f"Topic '{topic}' not found. Available topics: health_score, predictions, optimization, safety",
            "full_documentation": SYSTEM_METHODOLOGY
        }

    return {
        "success": True,
        "documentation": SYSTEM_METHODOLOGY
    }


# Tool definitions for Claude API
CHAT_TOOLS = [
    {
        "name": "list_devices",
        "description": "List available building devices. Use this to discover what devices can be controlled or monitored. You can filter by device type (hvac, lighting, security, power) or site ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_type": {
                    "type": "string",
                    "description": "Filter by device type: hvac, lighting, security, fire_safety, access_control, power, other",
                    "enum": ["hvac", "lighting", "security", "fire_safety", "access_control", "power", "other"]
                },
                "site_id": {
                    "type": "string",
                    "description": "Filter by site ID (e.g., 'site-001')"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_device_details",
        "description": "Get detailed information about a specific device including its current values, available control points, and safety status. Use this before controlling a device to understand its current state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID to look up (e.g., '001-chiller-001')"
                }
            },
            "required": ["device_id"]
        }
    },
    {
        "name": "control_device",
        "description": "Execute a control action on a building device. This will set a value on a device point (like temperature setpoint or on/off state). All actions are validated against safety rules and logged to the audit trail. If safety validation fails, the action will be blocked and you'll receive an error explaining why.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID to control (e.g., '001-chiller-001')"
                },
                "point": {
                    "type": "string",
                    "description": "The point name to control (e.g., 'setpoint', 'state', 'mode')"
                },
                "value": {
                    "description": "The value to set. For temperature setpoints use a number. For on/off states use true/false or 1/0."
                },
                "reason": {
                    "type": "string",
                    "description": "Brief explanation of why this control action is being performed",
                    "default": "User requested via AI assistant"
                }
            },
            "required": ["device_id", "point", "value"]
        }
    },
    {
        "name": "get_system_status",
        "description": "Get overall BMS system status including active alerts, equipment health summary, predicted failures, and prioritized recommendations. Use this to understand the current state of the building and identify issues that need attention.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Optional site ID to filter status (e.g., 'site-001'). If not provided, returns status for all sites."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_optimization_recommendations",
        "description": "Get AI-powered optimization recommendations for HVAC setpoints based on current conditions, weather forecast, and energy pricing. Returns specific setpoint changes with projected energy and cost savings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "The site ID to analyze for optimization (e.g., 'site-001')"
                }
            },
            "required": ["site_id"]
        }
    },
    {
        "name": "get_equipment_health",
        "description": "Get equipment health status, maintenance history, and failure predictions. Helps identify equipment that needs attention and prioritize maintenance activities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Filter by site ID"
                },
                "equipment_id": {
                    "type": "string",
                    "description": "Get details for specific equipment"
                },
                "status_filter": {
                    "type": "string",
                    "description": "Filter by health status",
                    "enum": ["critical", "warning", "normal"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_alerts_and_anomalies",
        "description": "Get active alerts and detected anomalies/predicted failures. Alerts are current issues, anomalies are AI-predicted future problems. Includes cost estimates for repairs and potential damage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Filter by site ID"
                },
                "severity": {
                    "type": "string",
                    "description": "Filter alerts by severity",
                    "enum": ["critical", "warning", "info"]
                },
                "include_resolved": {
                    "type": "boolean",
                    "description": "Include resolved/acknowledged alerts (default: false)",
                    "default": False
                }
            },
            "required": []
        }
    },
    {
        "name": "get_energy_analysis",
        "description": "Get energy consumption analysis for a site including current device readings, efficiency insights, and suggestions for reducing energy costs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "The site ID to analyze (e.g., 'site-001')"
                }
            },
            "required": ["site_id"]
        }
    },
    {
        "name": "get_system_methodology",
        "description": "Get proprietary SENTINEL system methodology documentation explaining how health scores are calculated, how failure predictions work, optimization algorithms, and safety validation. REQUIRES ADMIN PASSWORD. If user asks about methodology without providing password, tell them this is proprietary information and ask for the admin password.",
        "input_schema": {
            "type": "object",
            "properties": {
                "password": {
                    "type": "string",
                    "description": "Admin password required to access proprietary methodology documentation"
                },
                "topic": {
                    "type": "string",
                    "description": "Optional specific topic: health_score, predictions, optimization, safety, or leave empty for all",
                    "enum": ["health_score", "predictions", "optimization", "safety"]
                }
            },
            "required": ["password"]
        }
    },
    {
        "name": "lookup_desk",
        "description": "Look up a desk location and get its HVAC zone, temperature, and sensor data. Use this when a technician reports a comfort complaint from a user at a specific desk. Returns zone info, HVAC equipment IDs, and DALI sensor data (Sandton has DALI integration). If the desk isn't found, ask the technician for clarification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "desk_id": {
                    "type": "string",
                    "description": "The desk identifier. Can be formats like '201', 'L12-25', 'Desk 25', or just '25'"
                },
                "building": {
                    "type": "string",
                    "description": "Optional building name if working across multiple sites. For Sandton (which has DALI), this is automatic."
                }
            },
            "required": ["desk_id"]
        }
    },
    {
        "name": "diagnose_comfort_complaint",
        "description": "Diagnose a comfort complaint (too hot, too cold, stuffy, drafty) for a specific desk. Analyzes desk location, HVAC zone, DALI sensors (occupancy, daylight), and context (near window, diffuser, printer) to determine root cause and suggest actions. Use this when a technician says something like 'user at desk 201 says it's too hot'. Returns diagnosis with confidence level and recommended actions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "desk_id": {
                    "type": "string",
                    "description": "The desk identifier (e.g., '201', 'L12-25', 'Desk 25')"
                },
                "complaint_type": {
                    "type": "string",
                    "description": "Type of comfort complaint",
                    "enum": ["too_hot", "too_cold", "stuffy", "drafty"]
                },
                "building": {
                    "type": "string",
                    "description": "Optional building name if technician is working across multiple sites"
                },
                "additional_info": {
                    "type": "string",
                    "description": "Any additional context from the technician (e.g., 'user says it's been like this all morning')"
                }
            },
            "required": ["desk_id", "complaint_type"]
        }
    }
]


# Tool handler dispatch
TOOL_HANDLERS = {
    "list_devices": list_devices,
    "get_device_details": get_device_details,
    "control_device": control_device,
    "get_system_status": get_system_status,
    "get_optimization_recommendations": get_optimization_recommendations,
    "get_equipment_health": get_equipment_health,
    "get_alerts_and_anomalies": get_alerts_and_anomalies,
    "get_energy_analysis": get_energy_analysis,
    "get_system_methodology": get_system_methodology,
    "lookup_desk": lookup_desk,
    "diagnose_comfort_complaint": diagnose_comfort_complaint,
}


async def execute_tool(tool_name: str, tool_input: dict) -> dict[str, Any]:
    """
    Execute a tool by name with given input.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        Tool execution result
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return await handler(**tool_input)
    except TypeError as e:
        return {"error": f"Invalid parameters for {tool_name}: {e}"}
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return {"error": str(e)}
