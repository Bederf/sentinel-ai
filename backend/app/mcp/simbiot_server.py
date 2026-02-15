"""
SIMBIOT MCP Server for Building Data and Device Control

Provides tools for AI chat integration with building data, asset management,
and BMS device control through a standardized MCP interface.

Usage:
    from app.mcp import SIMBIOTMCPServer

    server = SIMBIOTMCPServer()
    result = await server.call_tool("get_buildings")
    result = await server.call_tool("read_device_point", device_id="S001-CHILLER-B1-001", point_name="chw_supply_temp")
"""

from typing import Optional, Dict, List, Any
import logging
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

from app.services.device_abstraction import device_manager
from app.models.device import DeviceStatus
from app.services.building_loader import get_building_loader

logger = logging.getLogger(__name__)

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
SITES_FILE = DATA_DIR / "sites.json"
DEVICES_FILE = DATA_DIR / "mock_devices.json"
ALERTS_FILE = DATA_DIR / "alerts.json"


def _load_sites() -> List[Dict[str, Any]]:
    """Load sites from JSON file."""
    try:
        with open(SITES_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load sites: {e}")
        return []


def _load_devices() -> List[Dict[str, Any]]:
    """Load devices from JSON file."""
    try:
        with open(DEVICES_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load devices: {e}")
        return []


def _load_alerts() -> List[Dict[str, Any]]:
    """Load alerts from JSON file."""
    try:
        with open(ALERTS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load alerts: {e}")
        return []


def _calculate_building_health(devices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate building health metrics from devices."""
    if not devices:
        return {"health_score": 100, "critical_alarms": 0, "warnings": 0}

    health_scores = []
    critical_count = 0
    warning_count = 0

    for device in devices:
        metadata = device.get("metadata", {})
        safety_status = metadata.get("safety_status", "safe")

        if safety_status == "critical" or safety_status == "alarm":
            health_scores.append(30)
            critical_count += 1
        elif safety_status == "warning":
            health_scores.append(70)
            warning_count += 1
        else:
            health_scores.append(100)

    avg_health = sum(health_scores) / len(health_scores) if health_scores else 100

    return {
        "health_score": round(avg_health, 1),
        "critical_alarms": critical_count,
        "warnings": warning_count
    }


# ============================================================================
# MCP Tool Functions
# ============================================================================

async def get_buildings_tool(
    status_filter: str = "all",
    region: Optional[str] = None
) -> Dict[str, Any]:
    """
    List buildings with status summary.

    MCP Tool: get_buildings

    Args:
        status_filter: Filter by status - "all", "critical", "warning", "healthy"
        region: Filter by region (e.g., "Gauteng", "Western Cape", "KwaZulu-Natal")

    Returns:
        Dictionary with:
        - buildings: Array of building objects with id, name, address, asset_count, health_score, critical_alarms
        - total: Total number of buildings
        - filtered: Number of buildings after filtering
    """
    sites = _load_sites()
    devices = _load_devices()

    # Group devices by site
    devices_by_site: Dict[str, List[Dict[str, Any]]] = {}
    for device in devices:
        site_id = device.get("site_id", "unknown")
        if site_id not in devices_by_site:
            devices_by_site[site_id] = []
        devices_by_site[site_id].append(device)

    buildings = []
    for site in sites:
        site_id = site.get("id")
        site_devices = devices_by_site.get(site_id, [])
        health_metrics = _calculate_building_health(site_devices)

        building = {
            "id": site_id,
            "name": site.get("name"),
            "address": site.get("address"),
            "region": site.get("region"),
            "type": site.get("type"),
            "sqm": site.get("sqm"),
            "floors": site.get("floors"),
            "asset_count": len(site_devices),
            "health_score": health_metrics["health_score"],
            "critical_alarms": health_metrics["critical_alarms"],
            "warnings": health_metrics["warnings"],
            "control_enabled": site.get("control_enabled", False),
            "optimization_enabled": site.get("optimization_enabled", False)
        }

        # Apply region filter
        if region and site.get("region", "").lower() != region.lower():
            continue

        # Apply status filter
        if status_filter == "critical" and health_metrics["critical_alarms"] == 0:
            continue
        elif status_filter == "warning" and health_metrics["warnings"] == 0 and health_metrics["critical_alarms"] == 0:
            continue
        elif status_filter == "healthy" and (health_metrics["critical_alarms"] > 0 or health_metrics["warnings"] > 0):
            continue

        buildings.append(building)

    return {
        "buildings": buildings,
        "total": len(sites),
        "filtered": len(buildings)
    }


async def get_assets_tool(
    building_id: str,
    asset_type: Optional[str] = None,
    criticality: Optional[str] = None
) -> Dict[str, Any]:
    """
    List assets for a building.

    MCP Tool: get_assets

    Args:
        building_id: Building/site ID (required)
        asset_type: Filter by asset type (AHU, Chiller, FCU, VAV, etc.)
        criticality: Filter by criticality level

    Returns:
        Dictionary with:
        - assets: Array of asset objects with id, name, type, location, health_score, status, active_alarms
        - building_id: The building ID queried
        - total: Total number of assets for the building
    """
    devices = _load_devices()

    # Filter devices by site_id (building_id)
    building_devices = [d for d in devices if d.get("site_id") == building_id]

    assets = []
    for device in building_devices:
        hvac_type = device.get("hvac_type", device.get("device_type", "unknown"))
        metadata = device.get("metadata", {})
        safety_status = metadata.get("safety_status", "safe")
        location = device.get("device_location", {})
        equipment = device.get("equipment", {})

        # Calculate health score based on safety status
        if safety_status == "critical" or safety_status == "alarm":
            health_score = 30
            active_alarms = 1
        elif safety_status == "warning":
            health_score = 70
            active_alarms = 0
        else:
            health_score = 100
            active_alarms = 0

        asset = {
            "id": device.get("id"),
            "name": device.get("name"),
            "tag": device.get("id"),
            "type": hvac_type.upper() if hvac_type else device.get("device_type", "unknown").upper(),
            "device_type": device.get("device_type"),
            "location": {
                "building": location.get("building"),
                "floor": location.get("floor"),
                "zone": location.get("zone"),
                "room": location.get("room"),
                "description": location.get("description")
            },
            "manufacturer": equipment.get("manufacturer"),
            "model": equipment.get("model"),
            "health_score": health_score,
            "status": safety_status,
            "active_alarms": active_alarms,
            "critical": metadata.get("critical", False),
            "safety_note": metadata.get("safety_note")
        }

        # Apply asset_type filter
        if asset_type and hvac_type and hvac_type.lower() != asset_type.lower():
            continue

        # Apply criticality filter
        if criticality == "critical" and not metadata.get("critical", False):
            continue

        assets.append(asset)

    return {
        "assets": assets,
        "building_id": building_id,
        "total": len(assets)
    }


async def get_asset_detail_tool(
    asset_id: str,
    include: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get comprehensive asset details.

    MCP Tool: get_asset_detail

    Args:
        asset_id: Asset/device ID (required)
        include: Optional list of sections to include: "health_breakdown", "recent_alarms", "current_readings"

    Returns:
        Dictionary with full asset information:
        - asset: Basic asset info (id, name, type, location, equipment)
        - current_readings: Current point values (if requested or default)
        - health_breakdown: Health score breakdown (if requested)
        - recent_alarms: Recent alarm history (if requested)
    """
    if include is None:
        include = ["current_readings"]

    devices = _load_devices()

    # Find the device
    device_data = None
    for d in devices:
        if d.get("id") == asset_id:
            device_data = d
            break

    if not device_data:
        return {"error": f"Asset {asset_id} not found", "asset": None}

    metadata = device_data.get("metadata", {})
    location = device_data.get("device_location", {})
    equipment = device_data.get("equipment", {})
    points = device_data.get("points", {})
    safety_status = metadata.get("safety_status", "safe")

    # Calculate health score
    if safety_status == "critical" or safety_status == "alarm":
        health_score = 30
    elif safety_status == "warning":
        health_score = 70
    else:
        health_score = 100

    result = {
        "asset": {
            "id": device_data.get("id"),
            "name": device_data.get("name"),
            "type": device_data.get("hvac_type", device_data.get("device_type")),
            "device_type": device_data.get("device_type"),
            "protocol": device_data.get("protocol"),
            "site_id": device_data.get("site_id"),
            "location": location,
            "equipment": equipment,
            "health_score": health_score,
            "safety_status": safety_status,
            "safety_note": metadata.get("safety_note")
        }
    }

    # Include current readings
    if "current_readings" in include:
        readings = {}
        for point_name, point_data in points.items():
            readings[point_name] = {
                "value": point_data.get("default_value"),
                "unit": point_data.get("unit", ""),
                "description": point_data.get("description"),
                "writable": point_data.get("writable", False),
                "point_type": point_data.get("point_type")
            }
        result["current_readings"] = readings

    # Include health breakdown
    if "health_breakdown" in include:
        result["health_breakdown"] = {
            "overall_score": health_score,
            "safety_status": safety_status,
            "factors": [
                {"name": "Safety Status", "score": health_score, "weight": 0.4},
                {"name": "Equipment Age", "score": 85 if equipment.get("installation_year", 2020) > 2015 else 65, "weight": 0.2},
                {"name": "Maintenance Status", "score": 90, "weight": 0.2},
                {"name": "Performance", "score": 95, "weight": 0.2}
            ]
        }

    # Include recent alarms
    if "recent_alarms" in include:
        # Mock recent alarms based on safety status
        alarms = []
        if safety_status == "warning":
            alarms.append({
                "timestamp": datetime.now().isoformat(),
                "severity": "warning",
                "message": metadata.get("safety_note", "Warning condition detected"),
                "acknowledged": False
            })
        elif safety_status == "critical" or safety_status == "alarm":
            alarms.append({
                "timestamp": datetime.now().isoformat(),
                "severity": "critical",
                "message": metadata.get("safety_note", "Critical condition detected"),
                "acknowledged": False
            })
        result["recent_alarms"] = alarms

    return result


async def get_devices_tool(
    site_id: Optional[str] = None,
    device_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    List BMS devices.

    MCP Tool: get_devices

    Wraps device_manager.discover_devices() functionality.

    Args:
        site_id: Filter by site ID (optional)
        device_type: Filter by device type - "hvac", "lighting", "security", "fire_safety" (optional)

    Returns:
        Dictionary with:
        - devices: Array of device objects with id, name, type, protocol, status
        - total: Total number of devices
    """
    try:
        # Try to get devices from device_manager if initialized
        if device_manager._initialized:
            all_devices = await device_manager.list_devices()
            device_list = []

            for device in all_devices:
                # Apply filters
                if site_id and device.site_id != site_id:
                    continue
                if device_type and device.device_type.value != device_type:
                    continue

                device_list.append({
                    "id": device.id,
                    "name": device.name,
                    "type": device.device_type.value,
                    "hvac_type": getattr(device, 'hvac_type', None),
                    "protocol": device.protocol.value,
                    "status": device.status.value if device.status else "unknown",
                    "site_id": device.site_id,
                    "point_count": len(device.points) if device.points else 0
                })

            return {
                "devices": device_list,
                "total": len(device_list),
                "source": "device_manager"
            }
    except Exception as e:
        logger.warning(f"Device manager not available, falling back to JSON: {e}")

    # Fallback to JSON file
    devices = _load_devices()
    device_list = []

    for device in devices:
        # Apply filters
        if site_id and device.get("site_id") != site_id:
            continue
        if device_type and device.get("device_type") != device_type:
            continue

        device_list.append({
            "id": device.get("id"),
            "name": device.get("name"),
            "type": device.get("device_type"),
            "hvac_type": device.get("hvac_type"),
            "protocol": device.get("protocol"),
            "status": device.get("metadata", {}).get("safety_status", "unknown"),
            "site_id": device.get("site_id"),
            "point_count": len(device.get("points", {}))
        })

    return {
        "devices": device_list,
        "total": len(device_list),
        "source": "json_file"
    }


async def read_device_point_tool(
    device_id: str,
    point_name: str
) -> Dict[str, Any]:
    """
    Read a device point value.

    MCP Tool: read_device_point

    Args:
        device_id: Device ID (required)
        point_name: Point name to read (required)

    Returns:
        Dictionary with:
        - value: Current point value
        - unit: Value unit
        - quality: Data quality indicator
        - timestamp: Read timestamp
        - device_id: Device ID
        - point_name: Point name
    """
    try:
        # Try device_manager first
        if device_manager._initialized:
            device_value = await device_manager.read_device_value(device_id, point_name)
            return {
                "value": device_value.value,
                "unit": device_value.unit or "",
                "quality": device_value.quality or "good",
                "timestamp": device_value.timestamp.isoformat() if device_value.timestamp else datetime.now().isoformat(),
                "device_id": device_id,
                "point_name": point_name,
                "source": "device_manager"
            }
    except Exception as e:
        logger.warning(f"Device manager read failed, falling back to JSON: {e}")

    # Fallback to JSON file
    devices = _load_devices()

    for device in devices:
        if device.get("id") == device_id:
            points = device.get("points", {})
            if point_name in points:
                point_data = points[point_name]
                return {
                    "value": point_data.get("default_value"),
                    "unit": point_data.get("unit", ""),
                    "quality": "good",
                    "timestamp": datetime.now().isoformat(),
                    "device_id": device_id,
                    "point_name": point_name,
                    "source": "json_file"
                }
            else:
                return {
                    "error": f"Point {point_name} not found on device {device_id}",
                    "available_points": list(points.keys())
                }

    return {
        "error": f"Device {device_id} not found"
    }


async def write_device_point_tool(
    device_id: str,
    point_name: str,
    value: Any,
    priority: int = 8,
    user: str = "mcp_tool"
) -> Dict[str, Any]:
    """
    Write a device point value (SAFETY CRITICAL).

    MCP Tool: write_device_point

    This operation includes safety validation and audit logging.
    All writes are validated against safety rules before execution.

    Args:
        device_id: Device ID (required)
        point_name: Point name to write (required)
        value: Value to write (required)
        priority: BACnet priority (1-16, default 8)
        user: User identifier for audit logging

    Returns:
        Dictionary with:
        - success: Whether write succeeded
        - previous_value: Value before write
        - new_value: Value after write (if successful)
        - audit_id: Audit log entry ID
        - safety_validation: Safety validation result
        - device_id: Device ID
        - point_name: Point name
    """
    # Read current value first
    current_result = await read_device_point_tool(device_id, point_name)
    previous_value = current_result.get("value") if not current_result.get("error") else None

    try:
        # Try device_manager first (includes safety validation)
        if device_manager._initialized:
            success = await device_manager.write_device_value(
                device_id,
                point_name,
                value,
                priority=priority,
                user=user
            )

            # Read new value to confirm
            new_result = await read_device_point_tool(device_id, point_name)

            return {
                "success": success,
                "previous_value": previous_value,
                "new_value": new_result.get("value") if success else previous_value,
                "device_id": device_id,
                "point_name": point_name,
                "priority": priority,
                "user": user,
                "timestamp": datetime.now().isoformat(),
                "audit_id": f"audit-{datetime.now().strftime('%Y%m%d%H%M%S')}-{device_id}",
                "safety_validation": {
                    "validated": True,
                    "allowed": success,
                    "message": "Write validated through device_manager safety engine"
                },
                "source": "device_manager"
            }
    except ValueError as e:
        # Safety violation or validation error
        return {
            "success": False,
            "previous_value": previous_value,
            "new_value": None,
            "device_id": device_id,
            "point_name": point_name,
            "error": str(e),
            "safety_validation": {
                "validated": True,
                "allowed": False,
                "message": str(e)
            },
            "source": "device_manager"
        }
    except Exception as e:
        logger.warning(f"Device manager write failed: {e}")

    # Fallback: return error since we can't safely write without device_manager
    return {
        "success": False,
        "previous_value": previous_value,
        "new_value": None,
        "device_id": device_id,
        "point_name": point_name,
        "error": "Device manager not available. Cannot perform write without safety validation.",
        "safety_validation": {
            "validated": False,
            "allowed": False,
            "message": "Safety validation unavailable"
        },
        "source": "fallback_blocked"
    }


async def get_alarms_tool(
    building_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    severity: Optional[List[str]] = None,
    state: str = "all",
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Get alarms with filtering.

    MCP Tool: get_alarms

    Args:
        building_id: Filter by building/site ID
        asset_id: Filter by asset/equipment ID
        severity: Filter by severity levels (array of: critical, warning, info)
        state: Filter by alarm state - active, acknowledged, cleared, all (default)
        from_time: Start time (ISO format)
        to_time: End time (ISO format)
        limit: Maximum number of alarms to return (default 50)

    Returns:
        Dictionary with:
        - alarms: Array of alarm objects
        - total: Total alarms matching filters
        - filtered: Number returned (may be limited)
    """
    alerts = _load_alerts()

    # Parse time filters
    from_dt = None
    to_dt = None
    if from_time:
        try:
            from_dt = datetime.fromisoformat(from_time.replace('Z', '+00:00'))
        except ValueError:
            pass
    if to_time:
        try:
            to_dt = datetime.fromisoformat(to_time.replace('Z', '+00:00'))
        except ValueError:
            pass

    filtered_alarms = []
    for alert in alerts:
        # Apply building_id filter
        if building_id and alert.get("site_id") != building_id:
            continue

        # Apply asset_id filter
        if asset_id and alert.get("equipment_id") != asset_id:
            continue

        # Apply severity filter
        if severity and alert.get("severity") not in severity:
            continue

        # Apply state filter
        alert_status = alert.get("status", "active")
        if state == "active" and alert_status != "active":
            continue
        elif state == "acknowledged" and not alert.get("acknowledged", False):
            continue
        elif state == "cleared" and alert_status != "cleared":
            continue

        # Apply time filters
        alert_time = alert.get("created_at")
        if alert_time:
            try:
                alert_dt = datetime.fromisoformat(alert_time.replace('Z', '+00:00'))
                if from_dt and alert_dt < from_dt:
                    continue
                if to_dt and alert_dt > to_dt:
                    continue
            except ValueError:
                pass

        # Map to alarm response format
        alarm = {
            "id": alert.get("id"),
            "timestamp": alert.get("created_at"),
            "asset_tag": alert.get("equipment_id"),
            "asset_name": alert.get("equipment_name"),
            "code": alert.get("type"),
            "title": alert.get("title"),
            "description": alert.get("message"),
            "severity": alert.get("severity"),
            "state": "acknowledged" if alert.get("acknowledged") else alert.get("status", "active"),
            "priority": alert.get("priority"),
            "category": alert.get("category"),
            "site_id": alert.get("site_id"),
            "estimated_cost_zar": alert.get("estimated_cost_zar"),
            "potential_damage_zar": alert.get("potential_damage_zar")
        }
        filtered_alarms.append(alarm)

    # Sort by timestamp (most recent first)
    filtered_alarms.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    total = len(filtered_alarms)
    limited_alarms = filtered_alarms[:limit]

    return {
        "alarms": limited_alarms,
        "total": total,
        "filtered": len(limited_alarms)
    }


async def search_alarms_tool(
    query: str,
    building_id: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Natural language alarm search with pattern analysis.

    MCP Tool: search_alarms

    Parses natural language queries to find relevant alarms and identify patterns.

    Args:
        query: Natural language search query (e.g., "chiller alarms", "temperature issues")
        building_id: Optional building/site ID filter
        limit: Maximum number of results (default 20)

    Returns:
        Dictionary with:
        - interpretation: How the query was interpreted
        - results: Array of matching alarm groups with pattern analysis
        - keywords_matched: Keywords found in query
    """
    alerts = _load_alerts()

    # Define keyword mappings for search
    keyword_mappings = {
        "chiller": ["chiller", "CH-", "refrigerant", "compressor"],
        "ahu": ["ahu", "AHU-", "air handling", "supply air"],
        "temperature": ["temperature", "temp", "hot", "cold", "overheat"],
        "pressure": ["pressure", "high pressure", "low pressure"],
        "trip": ["trip", "tripped", "fault", "failure", "fail"],
        "generator": ["generator", "GEN-", "diesel", "power", "fuel"],
        "battery": ["battery", "UPS", "runtime"],
        "vibration": ["vibration", "bearing", "motor"],
        "maintenance": ["maintenance", "service", "overdue"],
        "hvac": ["hvac", "cooling", "heating", "ventilation"],
        "electrical": ["electrical", "power", "voltage", "current"]
    }

    # Parse query for keywords
    query_lower = query.lower()
    matched_keywords = []
    search_terms = []

    for category, terms in keyword_mappings.items():
        for term in terms:
            if term.lower() in query_lower:
                matched_keywords.append(category)
                search_terms.extend(terms)
                break

    # If no keywords matched, use the whole query
    if not search_terms:
        search_terms = query_lower.split()

    # Build interpretation
    interpretation_parts = []
    if matched_keywords:
        interpretation_parts.append(f"Searching for {', '.join(set(matched_keywords))} alarms")
    else:
        interpretation_parts.append(f"Searching for alarms matching: {query}")

    if building_id:
        interpretation_parts.append(f"in building {building_id}")

    # Time detection
    time_range_days = 14  # Default
    if "today" in query_lower:
        time_range_days = 1
    elif "week" in query_lower:
        time_range_days = 7
    elif "month" in query_lower:
        time_range_days = 30

    interpretation_parts.append(f"in last {time_range_days} days")

    interpretation = " ".join(interpretation_parts)

    # Filter and search alerts
    matched_alerts = []
    for alert in alerts:
        # Apply building filter
        if building_id and alert.get("site_id") != building_id:
            continue

        # Search in title and message
        alert_text = f"{alert.get('title', '')} {alert.get('message', '')} {alert.get('category', '')}".lower()

        # Check if any search term matches
        if any(term.lower() in alert_text for term in search_terms):
            matched_alerts.append(alert)

    # Group by asset for pattern analysis
    asset_groups: Dict[str, List[Dict]] = defaultdict(list)
    for alert in matched_alerts:
        asset_key = alert.get("equipment_id") or alert.get("equipment_name") or "unknown"
        asset_groups[asset_key].append(alert)

    # Build results with pattern analysis
    results = []
    for asset_tag, asset_alerts in asset_groups.items():
        # Sort by date
        asset_alerts.sort(key=lambda x: x.get("created_at") or "", reverse=True)

        # Extract dates
        dates = []
        for a in asset_alerts:
            if a.get("created_at"):
                try:
                    dt = datetime.fromisoformat(a["created_at"].replace('Z', '+00:00'))
                    dates.append(dt.strftime("%Y-%m-%d"))
                except ValueError:
                    pass

        # Detect pattern
        pattern = "Single occurrence"
        if len(asset_alerts) >= 3:
            pattern = f"Recurring - {len(asset_alerts)} occurrences"
            # Calculate average interval if multiple dates
            if len(dates) >= 2:
                try:
                    date_objs = [datetime.strptime(d, "%Y-%m-%d") for d in dates[:5]]
                    if len(date_objs) >= 2:
                        intervals = [(date_objs[i] - date_objs[i+1]).days for i in range(len(date_objs)-1)]
                        avg_interval = sum(intervals) / len(intervals) if intervals else 0
                        if avg_interval > 0:
                            pattern = f"Recurring every {int(avg_interval)} days"
                except ValueError:
                    pass
        elif len(asset_alerts) == 2:
            pattern = "Multiple occurrences"

        result = {
            "asset_tag": asset_tag,
            "asset_name": asset_alerts[0].get("equipment_name"),
            "site_id": asset_alerts[0].get("site_id"),
            "alarm_count": len(asset_alerts),
            "dates": dates[:5],  # Last 5 dates
            "severities": list(set(a.get("severity") for a in asset_alerts if a.get("severity"))),
            "pattern": pattern,
            "latest_alarm": {
                "title": asset_alerts[0].get("title"),
                "severity": asset_alerts[0].get("severity"),
                "timestamp": asset_alerts[0].get("created_at")
            }
        }
        results.append(result)

    # Sort by alarm count (most active first)
    results.sort(key=lambda x: x["alarm_count"], reverse=True)

    return {
        "interpretation": interpretation,
        "results": results[:limit],
        "keywords_matched": list(set(matched_keywords)),
        "total_matches": len(matched_alerts),
        "assets_affected": len(results)
    }


async def get_trends_tool(
    asset_id: str,
    parameter: str,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    interval: str = "1hour"
) -> Dict[str, Any]:
    """
    Get historical trend data for an asset parameter.

    MCP Tool: get_trends

    Args:
        asset_id: Asset/device ID (required)
        parameter: Parameter name to get trends for (required)
        from_time: Start time (ISO format, default: 24 hours ago)
        to_time: End time (ISO format, default: now)
        interval: Data interval - 1min, 5min, 15min, 1hour, 1day (default: 1hour)

    Returns:
        Dictionary with:
        - data_points: Array of {timestamp, value, quality}
        - asset_id: Asset ID
        - parameter: Parameter name
        - interval: Data interval used
        - statistics: min, max, avg, count
    """
    # Parse time range
    if to_time:
        try:
            end_dt = datetime.fromisoformat(to_time.replace('Z', '+00:00'))
        except ValueError:
            end_dt = datetime.now()
    else:
        end_dt = datetime.now()

    if from_time:
        try:
            start_dt = datetime.fromisoformat(from_time.replace('Z', '+00:00'))
        except ValueError:
            start_dt = end_dt - timedelta(hours=24)
    else:
        start_dt = end_dt - timedelta(hours=24)

    # Determine interval in minutes
    interval_minutes = {
        "1min": 1,
        "5min": 5,
        "15min": 15,
        "1hour": 60,
        "1day": 1440
    }.get(interval, 60)

    # Get base value from device
    devices = _load_devices()
    base_value = None
    unit = ""

    for device in devices:
        if device.get("id") == asset_id:
            points = device.get("points", {})
            if parameter in points:
                point_data = points[parameter]
                base_value = point_data.get("default_value")
                unit = point_data.get("unit", "")
                break

    if base_value is None:
        return {
            "error": f"Parameter {parameter} not found for asset {asset_id}",
            "asset_id": asset_id,
            "parameter": parameter
        }

    # Generate synthetic trend data based on base value
    import random
    random.seed(hash(f"{asset_id}{parameter}"))  # Reproducible randomness

    data_points = []
    current_time = start_dt
    values = []

    while current_time <= end_dt:
        # Add realistic variation
        if isinstance(base_value, (int, float)):
            # Temperature-like variation
            variation = random.uniform(-0.15, 0.15) * abs(base_value)
            # Add time-of-day pattern for temperature
            hour = current_time.hour
            if "temp" in parameter.lower():
                # Warmer in afternoon, cooler at night
                if 9 <= hour <= 17:
                    variation += abs(base_value) * 0.05
                elif 0 <= hour <= 6:
                    variation -= abs(base_value) * 0.03

            value = round(base_value + variation, 2)
            values.append(value)
        else:
            value = base_value
            values.append(1 if value else 0)

        quality = "good"
        if random.random() < 0.02:  # 2% chance of questionable data
            quality = "questionable"

        data_points.append({
            "timestamp": current_time.isoformat(),
            "value": value,
            "quality": quality
        })

        current_time += timedelta(minutes=interval_minutes)

    # Calculate statistics
    numeric_values = [v for v in values if isinstance(v, (int, float))]
    statistics = {
        "min": round(min(numeric_values), 2) if numeric_values else None,
        "max": round(max(numeric_values), 2) if numeric_values else None,
        "avg": round(sum(numeric_values) / len(numeric_values), 2) if numeric_values else None,
        "count": len(data_points)
    }

    return {
        "data_points": data_points,
        "asset_id": asset_id,
        "parameter": parameter,
        "unit": unit,
        "interval": interval,
        "from_time": start_dt.isoformat(),
        "to_time": end_dt.isoformat(),
        "statistics": statistics
    }


async def get_health_score_tool(
    asset_id: Optional[str] = None,
    building_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get health score breakdown for an asset or building.

    MCP Tool: get_health_score

    Args:
        asset_id: Asset/device ID (one of asset_id or building_id required)
        building_id: Building/site ID (one of asset_id or building_id required)

    Returns:
        Dictionary with:
        - score: Overall health score (0-100)
        - status: healthy, fair, degrading, critical
        - breakdown: Score breakdown by category
        - trend: improving, stable, declining
        - factors: Contributing factors
    """
    if not asset_id and not building_id:
        return {
            "error": "Either asset_id or building_id is required"
        }

    devices = _load_devices()
    alerts = _load_alerts()

    if asset_id:
        # Single asset health score
        device = None
        for d in devices:
            if d.get("id") == asset_id:
                device = d
                break

        if not device:
            return {"error": f"Asset {asset_id} not found"}

        metadata = device.get("metadata", {})
        safety_status = metadata.get("safety_status", "safe")
        equipment = device.get("equipment", {})

        # Calculate base health from safety status
        if safety_status == "critical" or safety_status == "alarm":
            base_health = 30
        elif safety_status == "warning":
            base_health = 70
        else:
            base_health = 100

        # Calculate breakdown factors
        install_year = equipment.get("installation_year", 2020)
        age_years = datetime.now().year - install_year
        expected_life = 15  # Default expected life

        age_score = max(0, 100 - (age_years / expected_life * 100))
        maintenance_score = 90  # Mock value
        performance_score = 95 if safety_status == "safe" else (70 if safety_status == "warning" else 40)

        # Count relevant alarms
        asset_alarms = [a for a in alerts if a.get("equipment_id") == asset_id]
        alarm_penalty = min(30, len(asset_alarms) * 10)

        overall_score = round((
            base_health * 0.4 +
            age_score * 0.2 +
            maintenance_score * 0.2 +
            performance_score * 0.2
        ) - alarm_penalty)

        overall_score = max(0, min(100, overall_score))

        # Determine status and trend
        if overall_score >= 80:
            status = "healthy"
        elif overall_score >= 60:
            status = "fair"
        elif overall_score >= 40:
            status = "degrading"
        else:
            status = "critical"

        trend = "stable"  # Could be enhanced with historical data
        if safety_status == "warning":
            trend = "declining"

        return {
            "asset_id": asset_id,
            "asset_name": device.get("name"),
            "score": overall_score,
            "status": status,
            "trend": trend,
            "breakdown": {
                "safety_status": {"score": base_health, "weight": 0.4},
                "equipment_age": {"score": round(age_score), "weight": 0.2, "years": age_years},
                "maintenance": {"score": maintenance_score, "weight": 0.2},
                "performance": {"score": performance_score, "weight": 0.2}
            },
            "active_alarms": len(asset_alarms),
            "factors": [
                f"Safety status: {safety_status}",
                f"Equipment age: {age_years} years",
                f"Active alarms: {len(asset_alarms)}"
            ]
        }

    else:
        # Building health score (aggregate)
        building_devices = [d for d in devices if d.get("site_id") == building_id]

        if not building_devices:
            return {"error": f"No devices found for building {building_id}"}

        # Calculate per-device scores
        device_scores = []
        critical_count = 0
        warning_count = 0

        for device in building_devices:
            metadata = device.get("metadata", {})
            safety_status = metadata.get("safety_status", "safe")

            if safety_status == "critical" or safety_status == "alarm":
                device_scores.append(30)
                critical_count += 1
            elif safety_status == "warning":
                device_scores.append(70)
                warning_count += 1
            else:
                device_scores.append(100)

        overall_score = round(sum(device_scores) / len(device_scores)) if device_scores else 100

        # Count building alarms
        building_alarms = [a for a in alerts if a.get("site_id") == building_id]

        # Determine status
        if critical_count > 0 or overall_score < 40:
            status = "critical"
        elif warning_count > 0 or overall_score < 60:
            status = "degrading"
        elif overall_score < 80:
            status = "fair"
        else:
            status = "healthy"

        return {
            "building_id": building_id,
            "score": overall_score,
            "status": status,
            "trend": "stable",
            "breakdown": {
                "device_count": len(building_devices),
                "healthy_devices": len([s for s in device_scores if s >= 80]),
                "warning_devices": warning_count,
                "critical_devices": critical_count
            },
            "active_alarms": len(building_alarms),
            "factors": [
                f"Total devices: {len(building_devices)}",
                f"Critical devices: {critical_count}",
                f"Warning devices: {warning_count}",
                f"Active alarms: {len(building_alarms)}"
            ]
        }


async def get_work_orders_tool(
    building_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    status: str = "all",
    limit: int = 50
) -> Dict[str, Any]:
    """
    Get work orders.

    MCP Tool: get_work_orders

    Args:
        building_id: Filter by building/site ID
        asset_id: Filter by asset ID
        status: Filter by status - open, completed, all (default)
        limit: Maximum number of work orders (default 50)

    Returns:
        Dictionary with:
        - work_orders: Array of work order objects
        - total: Total matching work orders
    """
    # Try to load work orders from the work orders API storage
    try:
        from app.api.work_orders import _technician_work_orders
        technician_wos = list(_technician_work_orders.values())
    except ImportError:
        technician_wos = []

    # Load from CSV data
    try:
        from app.services.csv_loader import WorkOrderData
        csv_work_orders = WorkOrderData.load()
    except Exception:
        csv_work_orders = []

    # Combine and format work orders
    work_orders = []

    # Add technician work orders
    for wo in technician_wos:
        # Apply filters
        if building_id and wo.get("site_id") != building_id:
            continue
        if asset_id and wo.get("equipment_id") != asset_id:
            continue
        if status == "open" and wo.get("status") in ["complete", "completed"]:
            continue
        if status == "completed" and wo.get("status") not in ["complete", "completed"]:
            continue

        work_orders.append({
            "wo_number": wo.get("id"),
            "date": wo.get("created_at").isoformat() if wo.get("created_at") else None,
            "type": "technician",
            "asset_id": wo.get("equipment_id"),
            "site_id": wo.get("site_id"),
            "description": wo.get("fault_description"),
            "diagnosis": wo.get("diagnosis"),
            "status": wo.get("status"),
            "priority": wo.get("priority"),
            "technician_notes": wo.get("technician_notes"),
            "parts_needed": wo.get("parts_needed", []),
            "resolution": wo.get("resolution"),
            "source": "technician_chat"
        })

    # Add CSV work orders
    for wo in csv_work_orders:
        # Apply filters
        if building_id and wo.get("site_id") != building_id:
            continue
        if asset_id and wo.get("asset_id") != asset_id:
            continue
        if status == "open" and wo.get("completed_date"):
            continue
        if status == "completed" and not wo.get("completed_date"):
            continue

        work_orders.append({
            "wo_number": wo.get("work_order_id"),
            "date": wo.get("reported_date").isoformat() if wo.get("reported_date") else None,
            "type": wo.get("type"),
            "asset_id": wo.get("asset_id"),
            "asset_tag": wo.get("asset_tag"),
            "site_id": wo.get("site_id"),
            "site_name": wo.get("site_name"),
            "description": wo.get("description"),
            "fault_code": wo.get("fault_code"),
            "status": "completed" if wo.get("completed_date") else "open",
            "priority": wo.get("priority"),
            "category": wo.get("category"),
            "technician_name": wo.get("technician_name"),
            "technician_notes": wo.get("technician_notes"),
            "resolution": wo.get("resolution"),
            "total_cost": wo.get("total_cost"),
            "sla_met": wo.get("sla_met"),
            "repeat_call": wo.get("repeat_call"),
            "source": "cafm"
        })

    # Sort by date (most recent first)
    work_orders.sort(key=lambda x: x.get("date") or "", reverse=True)

    return {
        "work_orders": work_orders[:limit],
        "total": len(work_orders)
    }


async def create_work_order_tool(
    building_id: str,
    asset_id: str,
    description: str,
    priority: str = "medium",
    suggested_parts: Optional[List[str]] = None,
    user: str = "mcp_tool"
) -> Dict[str, Any]:
    """
    Create a work order (SAFETY CRITICAL - includes audit logging).

    MCP Tool: create_work_order

    This operation creates a work order and logs the action for audit purposes.

    Args:
        building_id: Building/site ID (required)
        asset_id: Asset/device ID (required)
        description: Fault description (required)
        priority: Priority level - low, medium, high, critical (default: medium)
        suggested_parts: List of suggested parts for the repair
        user: User identifier for audit logging

    Returns:
        Dictionary with:
        - wo_number: Work order number
        - status: Created work order status
        - created_at: Creation timestamp
        - audit_id: Audit log entry ID
    """
    import uuid
    from datetime import datetime

    # Generate work order ID
    wo_number = f"MCP-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    # Create work order
    work_order = {
        "id": wo_number,
        "site_id": building_id,
        "equipment_id": asset_id,
        "fault_description": description,
        "diagnosis": f"AI-generated work order for {asset_id}",
        "priority": priority,
        "status": "draft",
        "created_at": datetime.now(),
        "updated_at": None,
        "technician_id": None,
        "technician_notes": f"Created via MCP tool by {user}",
        "parts_needed": suggested_parts or [],
        "estimated_duration": None,
        "resolution": None,
        "parts_used": [],
        "time_spent": None,
    }

    # Store in technician work orders
    try:
        from app.api.work_orders import _technician_work_orders
        _technician_work_orders[wo_number] = work_order
    except ImportError:
        logger.warning("Could not import work order storage - work order created but not persisted")

    # Create audit log entry
    audit_id = f"audit-{datetime.now().strftime('%Y%m%d%H%M%S')}-{wo_number}"

    try:
        from app.services.audit_logger import audit_logger
        await audit_logger.log_action(
            action_type="work_order_create",
            user=user,
            resource_type="work_order",
            resource_id=wo_number,
            details={
                "building_id": building_id,
                "asset_id": asset_id,
                "description": description,
                "priority": priority,
                "suggested_parts": suggested_parts
            }
        )
    except Exception as e:
        logger.warning(f"Could not log to audit logger: {e}")

    return {
        "wo_number": wo_number,
        "status": "draft",
        "created_at": work_order["created_at"].isoformat(),
        "building_id": building_id,
        "asset_id": asset_id,
        "description": description,
        "priority": priority,
        "suggested_parts": suggested_parts or [],
        "audit_id": audit_id,
        "message": f"Work order {wo_number} created successfully"
    }


# ============================================================================
# Contract Management Tools (Phase 48-02)
# ============================================================================


async def get_contracts_tool(
    building_id: Optional[str] = None,
    organization_code: Optional[str] = None,
    status: Optional[str] = None,
    include_sla: bool = False
) -> Dict[str, Any]:
    """
    Get contracts with optional filters.

    MCP Tool: get_contracts

    Args:
        building_id: Filter by building/site ID
        organization_code: Filter by organization code (e.g., ORG-SITE-002)
        status: Filter by status - active, expired, draft
        include_sla: Include SLA terms in response (default false)

    Returns:
        Dictionary with contracts list and total count
    """
    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    contracts = []

    # Scan all building directories for contract.json files
    if buildings_path.exists():
        for building_dir in sorted(buildings_path.iterdir()):
            if not building_dir.is_dir() or building_dir.name.startswith("_"):
                continue

            # Filter by building_id if specified
            if building_id and building_dir.name != building_id:
                continue

            contract_file = building_dir / "contract.json"
            if not contract_file.exists():
                continue

            try:
                with open(contract_file, "r") as f:
                    contract_data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load contract for {building_dir.name}: {e}")
                continue

            # Filter by organization_code
            if organization_code:
                org = contract_data.get("organization", {})
                if org.get("code") != organization_code:
                    continue

            # Filter by status
            contract_info = contract_data.get("contract", {})
            if status and contract_info.get("status") != status:
                continue

            # Build summary
            summary = {
                "building_id": building_dir.name,
                "contract_code": contract_data.get("contract_code"),
                "organization": contract_data.get("organization", {}).get("name"),
                "organization_code": contract_data.get("organization", {}).get("code"),
                "type": contract_info.get("type"),
                "status": contract_info.get("status"),
                "start_date": contract_info.get("start_date"),
                "end_date": contract_info.get("end_date"),
                "monthly_fee_zar": contract_info.get("monthly_fee_zar"),
                "auto_renew": contract_info.get("auto_renew"),
            }

            if include_sla:
                summary["sla_terms"] = contract_data.get("sla_terms", [])

            contracts.append(summary)

    return {
        "contracts": contracts,
        "total": len(contracts)
    }


async def add_building_contract_tool(
    building_code: str,
    organization_name: str,
    organization_code: str,
    contract_type: str,
    monthly_fee_zar: float,
    start_date: str,
    end_date: str,
    sla_terms: Optional[List[Dict[str, Any]]] = None,
    budget: Optional[Dict[str, Any]] = None,
    condition_assessment: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a detailed contract for a building.

    MCP Tool: add_building_contract

    Writes contract.json to the building directory and updates building.json
    with basic contract fields (dual-write pattern).

    Args:
        building_code: Building/site ID (e.g., site-002)
        organization_name: Client organization name
        organization_code: Organization code (e.g., ORG-SITE-002)
        contract_type: Contract type (full_maintenance, preventive_only, ad_hoc, consulting)
        monthly_fee_zar: Monthly fee in ZAR
        start_date: Contract start date (YYYY-MM-DD)
        end_date: Contract end date (YYYY-MM-DD)
        sla_terms: Optional SLA terms array
        budget: Optional budget breakdown object
        condition_assessment: Optional condition assessment object

    Returns:
        Success status with contract code
    """
    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    building_path = buildings_path / building_code

    if not building_path.exists():
        return {
            "success": False,
            "error": f"Building '{building_code}' not found"
        }

    # Generate contract code
    year = start_date[:4] if start_date else str(datetime.now().year)
    org_short = organization_code.replace("ORG-", "") if organization_code.startswith("ORG-") else organization_code
    contract_code = f"CON-{org_short}-{building_code.upper()}-{year}"

    # Build contract data
    contract_data = {
        "contract_code": contract_code,
        "organization": {
            "code": organization_code,
            "name": organization_name,
            "tier": "enterprise",
            "primary_contact_name": "",
            "primary_contact_email": "",
            "primary_contact_phone": ""
        },
        "contract": {
            "type": contract_type,
            "status": "active",
            "start_date": start_date,
            "end_date": end_date,
            "auto_renew": False,
            "monthly_fee_zar": monthly_fee_zar,
            "pricing_basis": "fixed_monthly",
            "payment_terms": "30 days net",
            "billing_cycle_days": 30
        },
        "sla_terms": sla_terms or [],
        "budget": budget or {},
        "condition_assessment": condition_assessment or {},
        "profitability_snapshot": {
            "ytd_revenue_zar": monthly_fee_zar,
            "ytd_direct_costs_zar": 0,
            "ytd_overhead_zar": 0,
            "ytd_penalties_zar": 0,
            "gross_margin_percent": 0,
            "net_margin_percent": 0
        }
    }

    # Write contract.json
    contract_file = building_path / "contract.json"
    with open(contract_file, "w") as f:
        json.dump(contract_data, f, indent=2)

    # Update building.json with basic contract fields
    building_file = building_path / "building.json"
    if building_file.exists():
        try:
            with open(building_file, "r") as f:
                building_data = json.load(f)

            building_data["client_name"] = organization_name
            building_data["organization_code"] = organization_code
            building_data["monthly_fee_zar"] = monthly_fee_zar
            building_data["contract_start"] = start_date
            building_data["contract_end"] = end_date
            building_data["contract_type"] = contract_type

            with open(building_file, "w") as f:
                json.dump(building_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to update building.json for {building_code}: {e}")

    logger.info(f"Created contract {contract_code} for building {building_code}")

    return {
        "success": True,
        "contract_code": contract_code,
        "building_code": building_code,
        "message": f"Contract created for building {building_code}"
    }


async def get_contract_profitability_tool(
    building_code: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get contract profitability snapshot.

    MCP Tool: get_contract_profitability

    Args:
        building_code: Filter by building (all buildings if not specified)
        year: Filter by year (default: current year)
        month: Filter by month (optional)

    Returns:
        Profitability data with portfolio summary
    """
    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    profitability = []
    total_revenue = 0
    total_costs = 0
    at_risk = 0

    target_year = year or datetime.now().year

    if buildings_path.exists():
        for building_dir in sorted(buildings_path.iterdir()):
            if not building_dir.is_dir() or building_dir.name.startswith("_"):
                continue

            if building_code and building_dir.name != building_code:
                continue

            contract_file = building_dir / "contract.json"
            if not contract_file.exists():
                continue

            try:
                with open(contract_file, "r") as f:
                    contract_data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load contract for {building_dir.name}: {e}")
                continue

            snapshot = contract_data.get("profitability_snapshot", {})
            contract_info = contract_data.get("contract", {})
            org = contract_data.get("organization", {})

            revenue = snapshot.get("ytd_revenue_zar", 0)
            direct_costs = snapshot.get("ytd_direct_costs_zar", 0)
            overhead = snapshot.get("ytd_overhead_zar", 0)
            penalties = snapshot.get("ytd_penalties_zar", 0)

            gross_margin = snapshot.get("gross_margin_percent", 0)
            net_margin = snapshot.get("net_margin_percent", 0)

            # Flag at-risk if net margin below 10%
            is_at_risk = net_margin < 10.0

            entry = {
                "building_id": building_dir.name,
                "organization": org.get("name"),
                "contract_code": contract_data.get("contract_code"),
                "contract_type": contract_info.get("type"),
                "monthly_fee_zar": contract_info.get("monthly_fee_zar", 0),
                "ytd_revenue_zar": revenue,
                "ytd_direct_costs_zar": direct_costs,
                "ytd_overhead_zar": overhead,
                "ytd_penalties_zar": penalties,
                "gross_margin_percent": gross_margin,
                "net_margin_percent": net_margin,
                "at_risk": is_at_risk,
                "year": target_year
            }

            profitability.append(entry)
            total_revenue += revenue
            total_costs += direct_costs + overhead + penalties
            if is_at_risk:
                at_risk += 1

    portfolio_margin = round(
        ((total_revenue - total_costs) / total_revenue * 100) if total_revenue > 0 else 0, 1
    )

    return {
        "profitability": profitability,
        "portfolio_summary": {
            "total_revenue_zar": total_revenue,
            "total_costs_zar": total_costs,
            "portfolio_margin_percent": portfolio_margin,
            "total_contracts": len(profitability),
            "at_risk_contracts": at_risk
        }
    }


# ============================================================================
# Municipal Billing Tools (Phase 49)
# ============================================================================

async def process_municipal_bill_tool(
    building_id: str,
    pdf_file_path: str,
    municipality: str,
    utility_type: str,
    account_number: str,
    tariff_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process South African municipal utility bill PDF.

    Supports: Johannesburg, Ekurhuleni, Cape Town, eThekwini

    MCP Tool: process_municipal_bill

    Args:
        building_id: Building/site ID (e.g., "site-002")
        pdf_file_path: Absolute path to PDF file
        municipality: Municipality name (e.g., "city_of_johannesburg")
        utility_type: "electricity" or "water"
        account_number: Municipal account number
        tariff_type: Optional tariff type

    Returns:
        Dictionary with extracted data, invoice ID, confidence score
    """
    from pathlib import Path
    from app.services.municipal_pdf_extraction_service import MunicipalPdfExtractionService

    # Validate PDF exists
    pdf_path = Path(pdf_file_path)
    if not pdf_path.exists():
        return {
            "error": "file_not_found",
            "message": f"PDF file not found: {pdf_file_path}"
        }

    try:
        # Extract data from PDF
        extraction_service = MunicipalPdfExtractionService()
        extracted_data = await extraction_service.parse_invoice(pdf_path)

        # Get or create municipal account
        from app.database.repositories.municipal_invoice_repository import MunicipalInvoiceRepository
        repo = MunicipalInvoiceRepository()

        account = repo.get_or_create_account(
            site_id=building_id,
            municipality=municipality,
            utility_type=utility_type,
            account_number=account_number,
            tariff_type=tariff_type
        )

        if not account:
            logger.error(f"Failed to create municipal account for {building_id}")
            return {
                "error": "account_creation_failed",
                "message": f"Failed to create municipal account for {building_id}",
                "extracted_data": extracted_data
            }

        # Create invoice record
        invoice_payload = {
            "account_id": account.get("id"),
            "site_id": building_id,
            "municipality": municipality,
            "utility_type": utility_type,
            "invoice_number": extracted_data.get("invoice_number"),
            "billing_period_start": extracted_data.get("billing_period_start"),
            "billing_period_end": extracted_data.get("billing_period_end"),
            "consumption_kwh": extracted_data.get("consumption_kwh") if utility_type == "electricity" else None,
            "consumption_kl": extracted_data.get("consumption_kl") if utility_type == "water" else None,
            "total_amount_zar": extracted_data.get("total_amount_zar"),
            "vat_amount_zar": extracted_data.get("vat_amount_zar"),
            "base_amount_zar": extracted_data.get("base_amount_zar"),
            "ocr_confidence": extracted_data.get("confidence", 0.0),
            "raw_text": extracted_data.get("raw_text", "")[:5000],  # Truncate to 5000 chars
            "pdf_file_path": str(pdf_path)
        }

        invoice = repo.create_invoice(invoice_payload)

        # ===== PHASE 081: Update buildings table with extracted NMD =====
        # If electricity bill, extract NMD and update building record
        if utility_type == "electricity" and invoice:
            try:
                from app.database.repositories.building_repository import BuildingRepository
                building_repo = BuildingRepository()
                
                # Extract NMD and demand charge from bill
                extracted_nmd_kva = extracted_data.get("demand_kva")
                billing_start = extracted_data.get("billing_period_start")
                billing_end = extracted_data.get("billing_period_end")
                
                if extracted_nmd_kva:
                    # Update building with real NMD from bill
                    building_update = {
                        "nmd_limit_kva": float(extracted_nmd_kva),
                        "demand_charge_per_kva": 155.50,  # City Power default
                        "electricity_provider": municipality,
                        "bill_last_uploaded_at": invoice.get("created_at") or str(__import__('datetime').datetime.utcnow().isoformat()),
                        "bill_document_path": str(pdf_path),
                        "nmd_extracted_from_bill": True,
                    }
                    
                    # Add billing cycle dates if extracted
                    if billing_start:
                        building_update["billing_cycle_start_date"] = billing_start
                    if billing_end:
                        building_update["billing_cycle_end_date"] = billing_end
                    
                    # Update the building
                    await building_repo.update(building_id, building_update)
                    
                    logger.info(
                        f"Updated building {building_id} NMD from bill: {extracted_nmd_kva} kVA "
                        f"(confidence: {extracted_data.get('confidence', 0.0)})"
                    )
            except Exception as exc:
                logger.warning(f"Failed to update building NMD from bill: {exc}")
        # ===== END PHASE 081 =====

        return {
            "building_id": building_id,
            "municipality": municipality,
            "utility_type": utility_type,
            "account_number": account_number,
            "account_id": account.get("id"),
            "invoice_id": invoice.get("id") if invoice else None,
            "extracted_data": extracted_data,
            "pdf_file": str(pdf_path),
            "nmd_extracted_kva": extracted_data.get("demand_kva"),  # PHASE 081: Show extracted NMD
            "nmd_updated": True if extracted_data.get("demand_kva") else False,  # PHASE 081: Confirm update
            "status": "processed",
            "confidence": extracted_data.get("confidence", 0.0)
        }

    except Exception as exc:
        logger.error(f"Error processing municipal bill: {exc}", exc_info=True)
        return {
            "error": "processing_failed",
            "message": f"Failed to process PDF: {str(exc)}",
            "building_id": building_id,
            "pdf_file": pdf_file_path
        }


async def get_utility_costs_tool(
    building_id: str,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get utility cost analysis for a building from municipal bills.

    Returns total costs, averages, and trends for electricity and water.

    MCP Tool: get_utility_costs

    Args:
        building_id: Building/site ID
        period_start: Period start ISO date (default: current month start)
        period_end: Period end ISO date (default: current month end)

    Returns:
        Cost analysis with totals, averages, and trends
    """
    from datetime import date, timedelta
    from app.database.repositories.municipal_invoice_repository import MunicipalInvoiceRepository

    try:
        repo = MunicipalInvoiceRepository()

        # Default to current month if not specified
        if not period_start:
            today = date.today()
            period_start = today.replace(day=1).isoformat()
            # Get last day of month
            if today.month == 12:
                next_month = date(today.year + 1, 1, 1)
            else:
                next_month = date(today.year, today.month + 1, 1)
            period_end = (next_month - timedelta(days=1)).isoformat()

        # Get invoices for period
        start = date.fromisoformat(period_start) if isinstance(period_start, str) else period_start
        end = date.fromisoformat(period_end) if isinstance(period_end, str) else period_end

        invoices = repo.list_invoices(
            site_id=building_id,
            limit=1000  # Large limit to get all invoices for period
        )

        # Filter by period
        filtered_invoices = []
        for inv in invoices:
            inv_end = inv.get("billing_period_end")
            if inv_end:
                try:
                    inv_date = date.fromisoformat(inv_end.split("T")[0]) if isinstance(inv_end, str) else inv_end
                    if start <= inv_date <= end:
                        filtered_invoices.append(inv)
                except Exception:
                    continue

        # Calculate totals
        electricity_total = sum(
            float(inv.get("total_amount_zar") or 0)
            for inv in filtered_invoices
            if inv.get("utility_type") == "electricity"
        )

        water_total = sum(
            float(inv.get("total_amount_zar") or 0)
            for inv in filtered_invoices
            if inv.get("utility_type") == "water"
        )

        total_zar = electricity_total + water_total

        # Calculate averages
        electricity_count = sum(1 for inv in filtered_invoices if inv.get("utility_type") == "electricity")
        water_count = sum(1 for inv in filtered_invoices if inv.get("utility_type") == "water")

        return {
            "building_id": building_id,
            "period": {"start": period_start, "end": period_end},
            "electricity_cost_zar": round(electricity_total, 2),
            "water_cost_zar": round(water_total, 2),
            "total_cost_zar": round(total_zar, 2),
            "electricity_invoice_count": electricity_count,
            "water_invoice_count": water_count,
            "total_invoice_count": len(filtered_invoices),
            "average_electricity_cost_zar": round(electricity_total / electricity_count, 2) if electricity_count > 0 else 0,
            "average_water_cost_zar": round(water_total / water_count, 2) if water_count > 0 else 0
        }

    except Exception as exc:
        logger.error(f"Error getting utility costs: {exc}", exc_info=True)
        return {
            "error": "query_failed",
            "message": f"Failed to query utility costs: {str(exc)}",
            "building_id": building_id
        }


# ============================================================================
# Building Management Tools (for onboarding)
# ============================================================================

async def list_managed_buildings_tool() -> Dict[str, Any]:
    """List all managed buildings."""
    loader = get_building_loader()
    loader.load(force=True)

    registry = loader.get_registry()
    active_ids = set(registry.get("active_buildings", []))

    buildings = []
    for building in loader.get_all_buildings():
        info = building.to_dict()
        info["is_active"] = building.id in active_ids
        info["desk_count"] = len(loader.get_desks(building.id))
        info["zone_count"] = len(loader.get_zones(building.id))
        buildings.append(info)

    return {
        "buildings": buildings,
        "total": len(buildings),
        "active_count": len(active_ids),
        "default_building": registry.get("default_building"),
    }


async def create_building_tool(
    building_id: str,
    name: str,
    address: str = "",
    floors: List[str] = None,
    features: Dict[str, bool] = None,
    client_name: Optional[str] = None,
    monthly_fee_zar: Optional[float] = None,
    contract_start: Optional[str] = None,
    contract_end: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new building configuration.

    Writes to both Supabase (primary) and JSON files (backup).
    When contract fields (client_name, monthly_fee_zar, contract_start, contract_end)
    are provided, a basic contract.json is also created.
    """
    import json
    import uuid
    from pathlib import Path

    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    building_path = buildings_path / building_id

    if building_path.exists():
        return {
            "success": False,
            "error": f"Building '{building_id}' already exists",
        }

    # Generate deterministic UUID from building_id
    building_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"building-{building_id}"))

    # Prepare building data
    building_data = {
        "id": building_id,
        "name": name,
        "display_name": name,
        "address": address,
        "timezone": "Africa/Johannesburg",
        "floors": floors or [],
        "features": features or {
            "hvac": True,
            "dali": False,
            "desk_diagnosis": True,
        },
        "metadata": {}
    }

    # Add contract fields to building data if provided
    if client_name:
        building_data["client_name"] = client_name
    if monthly_fee_zar is not None:
        building_data["monthly_fee_zar"] = monthly_fee_zar
    if contract_start:
        building_data["contract_start"] = contract_start
    if contract_end:
        building_data["contract_end"] = contract_end

    supabase_written = False

    # 1. Try to write to Supabase first
    try:
        from app.config.settings import settings
        if settings.supabase_url and settings.supabase_service_role_key:
            from app.database.repositories import BuildingRepository
            repo = BuildingRepository()

            # Check if building already exists in Supabase
            existing = repo.get_by_id(building_id)
            if existing:
                return {
                    "success": False,
                    "error": f"Building '{building_id}' already exists in database",
                }

            # Create in Supabase
            supabase_record = {
                "id": building_uuid,
                "code": building_id,
                "name": name,
                "address": address,
                "type": "branch",
                "optimization_enabled": False,
            }
            repo.create(supabase_record)
            supabase_written = True
            logger.info(f"Created building in Supabase: {building_id}")
    except Exception as e:
        logger.warning(f"Supabase write failed, will use JSON only: {e}")

    # 2. Always write to JSON files (backup + offline mode)
    building_path.mkdir(parents=True, exist_ok=True)

    with open(building_path / "building.json", "w") as f:
        json.dump(building_data, f, indent=2)

    # Create empty data files
    with open(building_path / "desks.json", "w") as f:
        json.dump([], f, indent=2)
    with open(building_path / "zones.json", "w") as f:
        json.dump([], f, indent=2)

    # 3. Auto-create contract.json if contract fields provided
    contract_created = False
    if client_name and monthly_fee_zar and contract_start and contract_end:
        year = contract_start[:4]
        contract_data = {
            "contract_code": f"CON-{building_id.upper()}-{year}",
            "organization": {
                "code": "",
                "name": client_name,
                "tier": "standard",
                "primary_contact_name": "",
                "primary_contact_email": "",
                "primary_contact_phone": ""
            },
            "contract": {
                "type": "full_maintenance",
                "status": "active",
                "start_date": contract_start,
                "end_date": contract_end,
                "auto_renew": False,
                "monthly_fee_zar": monthly_fee_zar,
                "pricing_basis": "fixed_monthly",
                "payment_terms": "30 days net",
                "billing_cycle_days": 30
            },
            "sla_terms": [],
            "budget": {},
            "condition_assessment": {},
            "profitability_snapshot": {
                "ytd_revenue_zar": monthly_fee_zar,
                "ytd_direct_costs_zar": 0,
                "ytd_overhead_zar": 0,
                "ytd_penalties_zar": 0,
                "gross_margin_percent": 0,
                "net_margin_percent": 0
            }
        }
        with open(building_path / "contract.json", "w") as f:
            json.dump(contract_data, f, indent=2)
        contract_created = True

    logger.info(f"Created building via MCP: {building_id}")

    result = {
        "success": True,
        "building_id": building_id,
        "name": name,
        "status": "created",
        "storage": "supabase+json" if supabase_written else "json",
        "message": f"Building '{name}' created. Add desks/zones, then activate.",
        "next_steps": [
            "Add desks to the building",
            "Add HVAC zones to the building",
            f"Call activate_building with building_id='{building_id}'"
        ]
    }
    if contract_created:
        result["contract_created"] = True
        result["message"] = f"Building '{name}' created with contract. Add desks/zones, then activate."

    return result


async def activate_building_tool(
    building_id: str,
    set_default: bool = False,
) -> Dict[str, Any]:
    """Activate a building (add to registry)."""
    import json
    from pathlib import Path

    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    building_path = buildings_path / building_id
    registry_path = buildings_path / "_registry.json"

    if not building_path.exists():
        return {
            "success": False,
            "error": f"Building '{building_id}' not found",
        }

    # Load/create registry
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
    else:
        registry = {"active_buildings": [], "default_building": None}

    # Add to active
    if building_id not in registry["active_buildings"]:
        registry["active_buildings"].append(building_id)

    if set_default or not registry.get("default_building"):
        registry["default_building"] = building_id

    # Save registry
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    # Reload
    loader = get_building_loader()
    loader.load(force=True)

    logger.info(f"Activated building via MCP: {building_id}")

    return {
        "success": True,
        "building_id": building_id,
        "status": "active",
        "is_default": registry["default_building"] == building_id,
        "message": f"Building '{building_id}' is now active",
    }


async def get_building_config_tool(building_id: str) -> Dict[str, Any]:
    """Get a building's full configuration."""
    # LOCKED: Clawd only works with site-002 for now
    building_id = "site-002"

    loader = get_building_loader()
    building = loader.get_building(building_id)

    if not building:
        return {
            "success": False,
            "error": f"Building '{building_id}' not found",
        }

    desks = loader.get_desks(building_id)
    zones = loader.get_zones(building_id)

    return {
        "success": True,
        "building": building.to_dict(),
        "is_active": building_id in loader.get_active_building_ids(),
        "desks": {
            "count": len(desks),
            "sample": desks[:5] if desks else [],
        },
        "zones": {
            "count": len(zones),
            "data": zones,
        },
    }


# ============================================================================
# AI-Assisted Onboarding Tools
# ============================================================================

async def add_building_zones_tool(
    building_id: str,
    zones: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Add HVAC zones to a building with equipment mappings.

    Writes to both Supabase (primary) and JSON files (backup).

    Each zone should include:
    - zone_id: Unique zone identifier (e.g., "Zone-L12-N")
    - zone_name: Human-readable name (e.g., "Level 12 North")
    - floor: Floor identifier (e.g., "L12")
    - fcu_id: Fan Coil Unit ID
    - vav_id: Variable Air Volume box ID (optional)
    - ahu_id: Air Handling Unit ID
    - temp_sensor: Temperature sensor ID
    - co2_sensor: CO2 sensor ID
    - setpoint: Temperature setpoint (default 22.0)
    - current_temp: Current temperature (default 22.0)
    - status: Zone status (default "running")
    """
    import json
    import uuid
    from pathlib import Path

    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    building_path = buildings_path / building_id
    zones_file = building_path / "zones.json"

    if not building_path.exists():
        return {
            "success": False,
            "error": f"Building '{building_id}' not found. Create it first with create_building.",
        }

    # Validate and normalize zone data
    normalized_zones = []
    for zone in zones:
        if not zone.get("zone_id"):
            return {
                "success": False,
                "error": "Each zone must have a 'zone_id' field",
            }

        normalized = {
            "zone_id": zone["zone_id"],
            "zone_name": zone.get("zone_name", zone["zone_id"]),
            "floor": zone.get("floor", ""),
            "fcu_id": zone.get("fcu_id", ""),
            "vav_id": zone.get("vav_id"),
            "ahu_id": zone.get("ahu_id", ""),
            "temp_sensor": zone.get("temp_sensor"),
            "co2_sensor": zone.get("co2_sensor"),
            "typical_occupancy": zone.get("typical_occupancy"),
            "area_sqm": zone.get("area_sqm"),
            "setpoint": zone.get("setpoint", 22.0),
            "current_temp": zone.get("current_temp", 22.0),
            "status": zone.get("status", "running"),
            "desk_range": zone.get("desk_range", ""),
        }
        normalized_zones.append(normalized)

    supabase_written = False

    # 1. Try to write to Supabase first
    try:
        from app.config.settings import settings
        if settings.supabase_url and settings.supabase_service_role_key:
            from app.database.repositories import HVACZoneRepository
            repo = HVACZoneRepository()

            # Get building UUID
            building_uuid = repo.get_building_uuid(building_id)
            if building_uuid:
                # Prepare Supabase records
                supabase_zones = []
                for zone in normalized_zones:
                    zone_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"zone-{zone['zone_id']}"))
                    supabase_zone = {
                        "id": zone_uuid,
                        "zone_id": zone["zone_id"],
                        "zone_name": zone["zone_name"],
                        "building_id": building_uuid,
                        "floor": zone["floor"],
                        "fcu_id": zone.get("fcu_id"),
                        "vav_id": zone.get("vav_id"),
                        "ahu_id": zone.get("ahu_id"),
                        "temp_sensor": zone.get("temp_sensor"),
                        "co2_sensor": zone.get("co2_sensor"),
                        "typical_occupancy": zone.get("typical_occupancy"),
                        "area_sqm": zone.get("area_sqm"),
                        "setpoint": zone.get("setpoint", 22.0),
                        "current_temp": zone.get("current_temp"),
                        "status": zone.get("status", "idle"),
                    }
                    supabase_zones.append(supabase_zone)

                repo.upsert_many(supabase_zones)
                supabase_written = True
                logger.info(f"Wrote {len(supabase_zones)} zones to Supabase for {building_id}")
    except Exception as e:
        logger.warning(f"Supabase zone write failed, will use JSON only: {e}")

    # 2. Always write to JSON files (backup + offline mode)
    existing_zones = []
    if zones_file.exists():
        with open(zones_file) as f:
            existing_zones = json.load(f)

    # Merge by zone_id (update existing or add new)
    existing_ids = {z["zone_id"]: i for i, z in enumerate(existing_zones)}
    for zone in normalized_zones:
        if zone["zone_id"] in existing_ids:
            existing_zones[existing_ids[zone["zone_id"]]] = zone
        else:
            existing_zones.append(zone)

    # Save zones
    with open(zones_file, "w") as f:
        json.dump(existing_zones, f, indent=2)

    # Reload building data
    loader = get_building_loader()
    loader.load(force=True)

    logger.info(f"Added {len(normalized_zones)} zones to building {building_id}")

    return {
        "success": True,
        "building_id": building_id,
        "zones_added": len(normalized_zones),
        "total_zones": len(existing_zones),
        "zone_ids": [z["zone_id"] for z in normalized_zones],
        "storage": "supabase+json" if supabase_written else "json",
        "message": f"Added {len(normalized_zones)} zones to '{building_id}'",
    }


async def add_building_desks_tool(
    building_id: str,
    desks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Add desks to a building with zone mappings, DALI lighting, and environmental context.

    Each desk should include:
    - desk_id: Unique desk identifier (e.g., "201", "L12-D001")
    - zone_id: HVAC zone the desk belongs to
    - floor: Floor identifier
    - near_window: Boolean - near exterior window
    - orientation: N/S/E/W/NE/NW/SE/SW - for solar analysis
    - near_diffuser: Diffuser ID if under supply air outlet
    - near_printer: Boolean - near heat source
    - department: Department/team
    - occupant: Occupant name
    - x_coord, y_coord: Floor plan coordinates
    - dali_zone: DALI lighting zone
    - sensor_id: PIR occupancy sensor ID
    - luminaire_ids: List of luminaire IDs serving desk
    - dali_controller: Tridonic Scenecom controller ID
    """
    import json
    from pathlib import Path

    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    building_path = buildings_path / building_id
    desks_file = building_path / "desks.json"

    if not building_path.exists():
        return {
            "success": False,
            "error": f"Building '{building_id}' not found. Create it first with create_building.",
        }

    # Validate and normalize desk data
    normalized_desks = []
    for desk in desks:
        if not desk.get("desk_id"):
            return {
                "success": False,
                "error": "Each desk must have a 'desk_id' field",
            }

        normalized = {
            "desk_id": str(desk["desk_id"]),
            "zone_id": desk.get("zone_id", ""),
            "floor": desk.get("floor", ""),
            # Environmental context
            "near_window": desk.get("near_window", False),
            "orientation": desk.get("orientation"),  # N, S, E, W, NE, NW, SE, SW
            "near_diffuser": desk.get("near_diffuser"),
            "near_printer": desk.get("near_printer", False),
            # Organizational
            "department": desk.get("department"),
            "occupant": desk.get("occupant"),
            # Floor plan
            "x_coord": desk.get("x_coord"),
            "y_coord": desk.get("y_coord"),
            # DALI-2 Scenecom integration
            "dali_zone": desk.get("dali_zone"),
            "sensor_id": desk.get("sensor_id"),
            "luminaire_ids": desk.get("luminaire_ids"),
            "dali_controller": desk.get("dali_controller"),
        }
        normalized_desks.append(normalized)

    supabase_written = False

    # 1. Try to write to Supabase first
    try:
        from app.config.settings import settings
        if settings.supabase_url and settings.supabase_service_role_key:
            from app.database.repositories import DeskRepository
            repo = DeskRepository()

            # Get building UUID
            building_uuid = repo.get_building_uuid(building_id)
            if building_uuid:
                # Prepare Supabase records
                supabase_desks = []
                for desk in normalized_desks:
                    desk_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"desk-{desk['desk_id']}"))

                    # Look up zone UUID if zone_id provided
                    hvac_zone_uuid = None
                    if desk.get("zone_id"):
                        hvac_zone_uuid = repo.get_hvac_zone_uuid(desk["zone_id"])

                    supabase_desk = {
                        "id": desk_uuid,
                        "desk_id": desk["desk_id"],
                        "building_id": building_uuid,
                        "hvac_zone_id": hvac_zone_uuid,
                        "floor": desk.get("floor", ""),
                        "window_facing": desk.get("orientation"),
                        "near_diffuser": bool(desk.get("near_diffuser")),
                        "diffuser_id": desk.get("near_diffuser") if isinstance(desk.get("near_diffuser"), str) else None,
                        "near_printer": desk.get("near_printer", False),
                        "near_kitchen": desk.get("near_kitchen", False),
                        "luminaire_ids": desk.get("luminaire_ids") or [],
                        "sensor_ids": [desk.get("sensor_id")] if desk.get("sensor_id") else [],
                    }
                    supabase_desks.append(supabase_desk)

                repo.upsert_many(supabase_desks)
                supabase_written = True
                logger.info(f"Wrote {len(supabase_desks)} desks to Supabase for {building_id}")
    except Exception as e:
        logger.warning(f"Supabase desk write failed, will use JSON only: {e}")

    # 2. Always write to JSON files (backup + offline mode)
    existing_desks = []
    if desks_file.exists():
        with open(desks_file) as f:
            existing_desks = json.load(f)

    # Merge by desk_id
    existing_ids = {d["desk_id"]: i for i, d in enumerate(existing_desks)}
    for desk in normalized_desks:
        if desk["desk_id"] in existing_ids:
            existing_desks[existing_ids[desk["desk_id"]]] = desk
        else:
            existing_desks.append(desk)

    # Save desks
    with open(desks_file, "w") as f:
        json.dump(existing_desks, f, indent=2)

    # Reload building data
    loader = get_building_loader()
    loader.load(force=True)

    logger.info(f"Added {len(normalized_desks)} desks to building {building_id}")

    return {
        "success": True,
        "building_id": building_id,
        "desks_added": len(normalized_desks),
        "total_desks": len(existing_desks),
        "desk_ids": [d["desk_id"] for d in normalized_desks[:10]],
        "storage": "supabase+json" if supabase_written else "json",
        "message": f"Added {len(normalized_desks)} desks to '{building_id}'",
    }


async def add_building_devices_tool(
    building_id: str,
    devices: List[Dict[str, Any]],
    site_code: str = None,
) -> Dict[str, Any]:
    """
    Add BMS devices to the system for a building.

    Each device should include:
    - device_id: Unique device ID (following naming convention: {site}-{building}-{type}-{seq})
    - device_type: Type (chiller, ahu, fcu, vav, etc.)
    - name: Display name
    - location: Location description
    - protocol: Communication protocol (bacnet, modbus, mock)
    - points: Dict of point names to current values
    - metadata: Additional metadata (manufacturer, model, etc.)

    If device_id is not provided, it will be auto-generated from site_code and device_type.
    """
    import json
    from pathlib import Path

    data_path = Path(__file__).parent.parent / "data"
    devices_file = data_path / "mock_devices.json"

    # Load existing devices
    existing_devices = []
    if devices_file.exists():
        with open(devices_file) as f:
            existing_devices = json.load(f)

    # Track counts by type for auto-generating IDs
    type_counts = defaultdict(int)
    for d in existing_devices:
        dtype = d.get("device_type", "unknown")
        type_counts[dtype] += 1

    # Use site code from building_id if not provided
    if not site_code:
        site_code = building_id[:3] if len(building_id) >= 3 else building_id

    # Normalize devices
    new_devices = []
    for device in devices:
        device_type = device.get("device_type", "unknown")

        # Auto-generate device_id if not provided
        if not device.get("device_id"):
            type_counts[device_type] += 1
            device_id = f"{site_code}-{building_id[:3]}-{device_type}-{type_counts[device_type]:03d}"
        else:
            device_id = device["device_id"]

        normalized = {
            "device_id": device_id,
            "device_type": device_type,
            "name": device.get("name", f"{device_type.upper()} {device_id}"),
            "location": device.get("location", building_id),
            "protocol": device.get("protocol", "mock"),
            "status": device.get("status", "online"),
            "building_id": building_id,
            "points": device.get("points", {}),
            "metadata": device.get("metadata", {}),
        }
        new_devices.append(normalized)

    # Merge with existing (update or add)
    existing_ids = {d["device_id"]: i for i, d in enumerate(existing_devices)}
    for device in new_devices:
        if device["device_id"] in existing_ids:
            existing_devices[existing_ids[device["device_id"]]] = device
        else:
            existing_devices.append(device)

    # Save devices
    with open(devices_file, "w") as f:
        json.dump(existing_devices, f, indent=2)

    logger.info(f"Added {len(new_devices)} devices for building {building_id}")

    return {
        "success": True,
        "building_id": building_id,
        "devices_added": len(new_devices),
        "total_devices": len(existing_devices),
        "device_ids": [d["device_id"] for d in new_devices],
        "message": f"Added {len(new_devices)} devices for '{building_id}'",
    }


async def import_point_list_tool(
    building_id: str,
    point_list: List[Dict[str, Any]],
    site_code: str = None,
    bms_vendor: str = None,
) -> Dict[str, Any]:
    """
    Import BACnet point list and auto-generate device/zone structure.

    This is the primary AI-assisted onboarding tool. It parses BMS point exports
    and automatically creates device and zone structures based on naming patterns.

    Supported BMS vendors (bms_vendor parameter):
    - "desigo" or "siemens": Siemens Desigo CC (e.g., AHU-L12-01.SupplyAirTemp)
    - "metasys" or "jci": Johnson Controls Metasys (e.g., NAE-1/AHU-1.SAT)
    - "ebi" or "honeywell": Honeywell EBI (e.g., AHU_01_SAT)
    - "ecostruxure" or "schneider": Schneider EcoStruxure (e.g., Building/Floor12/AHU01/SAT)
    - "niagara" or "tridium": Tridium Niagara (e.g., station/Drivers/BACnet/AHU_01/SAT)
    - "trend": Trend Controls (e.g., AHU1.SAT)
    - "auto" (default): Auto-detect from naming patterns

    Each point should include:
    - point_name: BACnet object name (e.g., "AHU-L12-01.SupplyAirTemp")
    - object_type: BACnet object type (e.g., "Analog Input", "Binary Output")
    - instance: BACnet object instance number
    - description: Point description
    - units: Engineering units (optional)
    - value: Current value (optional)

    The tool will:
    1. Parse device names from point names (e.g., "AHU-L12-01" from "AHU-L12-01.SupplyAirTemp")
    2. Determine device types (AHU, FCU, VAV, Chiller, etc.)
    3. Group points by device
    4. Create device entries with point mappings
    5. Infer zone structure from device naming patterns
    """
    import json
    import re
    from pathlib import Path

    if not point_list:
        return {
            "success": False,
            "error": "Point list is empty",
        }

    # Use site code from building_id if not provided
    if not site_code:
        site_code = building_id[:3] if len(building_id) >= 3 else building_id

    # Normalize vendor name
    vendor = (bms_vendor or "auto").lower()
    vendor_aliases = {
        "siemens": "desigo", "desigo_cc": "desigo",
        "jci": "metasys", "johnson": "metasys", "johnson_controls": "metasys",
        "honeywell": "ebi",
        "schneider": "ecostruxure", "struxureware": "ecostruxure",
        "tridium": "niagara",
    }
    vendor = vendor_aliases.get(vendor, vendor)

    # BMS vendor-specific device extraction patterns
    # Each returns (device_name, point_suffix) from a full point name
    def extract_desigo(point_name: str) -> tuple:
        """Siemens Desigo CC: AHU-L12-01.SupplyAirTemp, FCU_L11_02.RoomTemp"""
        match = re.match(r"^([A-Za-z0-9\-_]+?)[\._](.+)$", point_name)
        if match:
            return match.group(1), match.group(2)
        return point_name, ""

    def extract_metasys(point_name: str) -> tuple:
        """JCI Metasys: NAE-1/AHU-1.SAT, N2:AHU-1/SA-T, AHU1.SA-T"""
        # Strip NAE/N2 prefix if present
        cleaned = re.sub(r"^(NAE-?\d+[/:]|N\d+:)", "", point_name)
        match = re.match(r"^([A-Za-z0-9\-_]+?)[\./](.+)$", cleaned)
        if match:
            return match.group(1), match.group(2)
        return cleaned.split(".")[0], ""

    def extract_ebi(point_name: str) -> tuple:
        """Honeywell EBI: AHU_01_SAT, FCU_L12_03_ZNT"""
        # EBI uses underscores, device is first 2-3 parts
        parts = point_name.split("_")
        if len(parts) >= 3:
            # Detect if part[1] is a floor or sequence
            if re.match(r"^(L?\d+|B\d+|G|GF)$", parts[1], re.I):
                device_name = "_".join(parts[:3])
                point_suffix = "_".join(parts[3:])
            else:
                device_name = "_".join(parts[:2])
                point_suffix = "_".join(parts[2:])
            return device_name, point_suffix
        return parts[0], "_".join(parts[1:]) if len(parts) > 1 else ""

    def extract_ecostruxure(point_name: str) -> tuple:
        """Schneider EcoStruxure: Building/Floor12/AHU01/SupplyAirTemp"""
        parts = point_name.split("/")
        if len(parts) >= 3:
            # Find the device part (usually contains AHU, FCU, etc.)
            for i, part in enumerate(parts):
                if re.search(r"(AHU|FCU|VAV|CH|CT)", part, re.I):
                    return part, "/".join(parts[i+1:])
            # Fallback: second-to-last is device
            return parts[-2], parts[-1]
        return parts[0], "/".join(parts[1:]) if len(parts) > 1 else ""

    def extract_niagara(point_name: str) -> tuple:
        """Tridium Niagara: station/Drivers/BACnet/AHU_L12_01/SupplyAirTemp"""
        parts = point_name.split("/")
        if len(parts) >= 2:
            # Find device part (usually after BACnet or Drivers)
            for i, part in enumerate(parts):
                if re.search(r"(AHU|FCU|VAV|CH|CT|Chiller)", part, re.I):
                    return part, "/".join(parts[i+1:])
            # Fallback: last two parts
            return parts[-2], parts[-1]
        return point_name, ""

    def extract_trend(point_name: str) -> tuple:
        """Trend Controls: AHU1.SAT, FCU1.RT (short names)"""
        match = re.match(r"^([A-Za-z]+\d+)\.(.+)$", point_name)
        if match:
            return match.group(1), match.group(2)
        return point_name.split(".")[0], ""

    def extract_auto(point_name: str) -> tuple:
        """Auto-detect: try common patterns"""
        # Niagara/EcoStruxure path style
        if point_name.count("/") >= 2:
            return extract_niagara(point_name)
        # EBI underscore style with multiple parts
        if point_name.count("_") >= 3:
            return extract_ebi(point_name)
        # Metasys NAE prefix
        if re.match(r"^(NAE|N\d+)", point_name):
            return extract_metasys(point_name)
        # Default Desigo-style
        return extract_desigo(point_name)

    # Select extraction function
    extractors = {
        "desigo": extract_desigo,
        "metasys": extract_metasys,
        "ebi": extract_ebi,
        "ecostruxure": extract_ecostruxure,
        "niagara": extract_niagara,
        "trend": extract_trend,
        "auto": extract_auto,
    }
    extract_device = extractors.get(vendor, extract_auto)

    # Device type patterns
    device_patterns = {
        "chiller": re.compile(r"(chiller|ch\d|chl)", re.I),
        "ahu": re.compile(r"(ahu|air.?handling|ah\d)", re.I),
        "fcu": re.compile(r"(fcu|fan.?coil|fc\d)", re.I),
        "vav": re.compile(r"(vav|variable.?air)", re.I),
        "pump": re.compile(r"(pump|chw.?p|chwp)", re.I),
        "cooling_tower": re.compile(r"(cooling.?tower|ct\d)", re.I),
        "meter": re.compile(r"(meter|kwh|energy)", re.I),
        "boiler": re.compile(r"(boiler|blr)", re.I),
        "hws": re.compile(r"(hws|hot.?water)", re.I),
    }

    # Parse points and group by device
    devices_map = defaultdict(lambda: {"points": {}, "type": "unknown", "floor": ""})

    for point in point_list:
        point_name = point.get("point_name", "")
        if not point_name:
            continue

        # Extract device name using vendor-specific pattern
        device_name, point_suffix = extract_device(point_name)

        # Determine device type
        device_type = "unknown"
        for dtype, pattern in device_patterns.items():
            if pattern.search(device_name):
                device_type = dtype
                break

        # Extract floor from device name (e.g., L12, L11, Floor12, etc.)
        floor_match = re.search(r"[_\-]?(L\d+|B\d+|G|GF|Floor\d+|[0-9]{1,2}F)[_\-]?", device_name, re.I)
        floor = floor_match.group(1).upper() if floor_match else ""
        # Normalize Floor12 -> L12
        floor = re.sub(r"Floor(\d+)", r"L\1", floor, flags=re.I)

        # Normalize point name for storage
        normalized_point = re.sub(r"[^a-z0-9_]", "_", point_suffix.lower()).strip("_")
        if not normalized_point:
            normalized_point = "value"

        # Store point data
        devices_map[device_name]["type"] = device_type
        devices_map[device_name]["floor"] = floor
        devices_map[device_name]["points"][normalized_point] = {
            "original_name": point_name,
            "object_type": point.get("object_type", ""),
            "instance": point.get("instance"),
            "description": point.get("description", ""),
            "units": point.get("units", ""),
            "value": point.get("value"),
        }

    # Generate devices
    generated_devices = []
    for device_name, data in devices_map.items():
        device_type = data["type"]
        floor = data["floor"]

        # Generate device_id
        seq = len([d for d in generated_devices if d["device_type"] == device_type]) + 1
        device_id = f"{site_code}-{building_id[:3]}-{device_type}-{seq:03d}"

        # Simplify points to just values
        simple_points = {}
        for pname, pdata in data["points"].items():
            if pdata.get("value") is not None:
                simple_points[pname] = pdata["value"]
            else:
                # Use 0 or False as default based on object type
                if "binary" in pdata.get("object_type", "").lower():
                    simple_points[pname] = False
                else:
                    simple_points[pname] = 0.0

        device = {
            "device_id": device_id,
            "device_type": device_type,
            "name": device_name,
            "location": f"{building_id} {floor}".strip(),
            "protocol": "bacnet",
            "status": "online",
            "building_id": building_id,
            "floor": floor,
            "points": simple_points,
            "metadata": {
                "source": "point_list_import",
                "original_name": device_name,
                "point_count": len(data["points"]),
            },
        }
        generated_devices.append(device)

    # Infer zones from FCU/VAV devices
    inferred_zones = []
    fcu_devices = [d for d in generated_devices if d["device_type"] == "fcu"]
    vav_devices = [d for d in generated_devices if d["device_type"] == "vav"]
    ahu_devices = [d for d in generated_devices if d["device_type"] == "ahu"]

    for fcu in fcu_devices:
        floor = fcu.get("floor", "")
        fcu_name = fcu["metadata"]["original_name"]

        # Try to find matching VAV
        matching_vav = None
        for vav in vav_devices:
            if vav.get("floor") == floor:
                matching_vav = vav
                break

        # Try to find matching AHU
        matching_ahu = None
        for ahu in ahu_devices:
            if ahu.get("floor") == floor:
                matching_ahu = ahu
                break

        zone_id = f"Zone-{floor}-{fcu_name[-2:]}" if floor else f"Zone-{fcu_name}"
        zone = {
            "zone_id": zone_id,
            "floor": floor,
            "fcu_id": fcu["device_id"],
            "vav_id": matching_vav["device_id"] if matching_vav else None,
            "ahu_id": matching_ahu["device_id"] if matching_ahu else None,
            "setpoint": 22.0,
            "current_temp": 22.0,
            "status": "running",
        }
        inferred_zones.append(zone)

    # Save the generated structures
    result = {
        "success": True,
        "building_id": building_id,
        "bms_vendor": vendor,
        "analysis": {
            "total_points": len(point_list),
            "unique_devices": len(devices_map),
            "device_types": dict(defaultdict(int)),
        },
        "generated": {
            "devices": len(generated_devices),
            "zones": len(inferred_zones),
        },
        "devices": generated_devices,
        "zones": inferred_zones,
        "message": f"Parsed {len(point_list)} points ({vendor} format) into {len(generated_devices)} devices and {len(inferred_zones)} zones",
        "next_steps": [
            "Review the generated devices and zones",
            "Call add_building_devices to save devices",
            "Call add_building_zones to save zones",
            "Call activate_building to make the building active",
        ],
    }

    # Count by device type
    for d in generated_devices:
        result["analysis"]["device_types"][d["device_type"]] = \
            result["analysis"]["device_types"].get(d["device_type"], 0) + 1

    logger.info(f"Imported point list for {building_id}: {len(point_list)} points -> {len(generated_devices)} devices")

    return result


async def import_controller_list_tool(
    building_id: str,
    controllers: List[Dict[str, Any]],
    site_code: str = None,
) -> Dict[str, Any]:
    """
    Import BMS controller information and create device structure.

    Each controller should include:
    - name: Controller name (e.g., "PXC-L12-01")
    - ip_address: IP address
    - bacnet_device_id: BACnet device instance (optional)
    - area_served: Description of area served (e.g., "Level 12 North")
    - controller_type: Type (e.g., "PXC", "PXA", "DDC")
    - equipment: List of equipment names controlled (optional)

    This tool creates controller devices that can be used as parent references
    for other equipment in the system.
    """
    import json
    from pathlib import Path

    if not controllers:
        return {
            "success": False,
            "error": "Controller list is empty",
        }

    # Use site code from building_id if not provided
    if not site_code:
        site_code = building_id[:3] if len(building_id) >= 3 else building_id

    # Generate controller devices
    generated_controllers = []
    for idx, ctrl in enumerate(controllers):
        name = ctrl.get("name", f"Controller-{idx+1}")

        device = {
            "device_id": f"{site_code}-{building_id[:3]}-ctrl-{idx+1:03d}",
            "device_type": "controller",
            "name": name,
            "location": ctrl.get("area_served", building_id),
            "protocol": "bacnet",
            "status": "online",
            "building_id": building_id,
            "points": {},
            "metadata": {
                "ip_address": ctrl.get("ip_address", ""),
                "bacnet_device_id": ctrl.get("bacnet_device_id"),
                "controller_type": ctrl.get("controller_type", "DDC"),
                "area_served": ctrl.get("area_served", ""),
                "equipment_controlled": ctrl.get("equipment", []),
                "source": "controller_list_import",
            },
        }
        generated_controllers.append(device)

    logger.info(f"Imported {len(generated_controllers)} controllers for {building_id}")

    return {
        "success": True,
        "building_id": building_id,
        "controllers_parsed": len(generated_controllers),
        "controllers": generated_controllers,
        "message": f"Parsed {len(controllers)} controllers for '{building_id}'",
        "next_steps": [
            "Review the generated controller devices",
            "Call add_building_devices to save controllers",
            "Import point list to add equipment under each controller",
        ],
    }



# ============================================================================
# DALI Discovery Tool (Tridonic Gateway Support)
# ============================================================================

async def discover_tridonic_gateway_tool(
    building_id: str,
    gateway_ip: str,
    gateway_type: str = "tridonic",
    username: Optional[str] = None,
    password: Optional[str] = None,
    use_simulated: bool = False,
) -> Dict[str, Any]:
    """
    Discover Tridonic DALI gateway and enumerate all devices.

    MCP Tool: discover_tridonic_gateway

    Queries the DALI gateway for system information and discovers all devices
    across DALI lines. Generates equipment codes following v2.0 naming convention.

    This is a READ-ONLY discovery tool - it does not write to the database.
    Use the returned equipment_list with bulk_discover_equipment to fetch
    full metadata and save to database.

    Args:
        building_id: Building/site ID (e.g., "site-002")
        gateway_ip: IP address of DALI gateway (e.g., "192.168.10.50")
        gateway_type: Gateway type - "tridonic", "philips", "helvar", "generic"
        username: Optional HTTP Basic Auth username for gateway API
        password: Optional HTTP Basic Auth password for gateway API
        use_simulated: Use simulated data if gateway unreachable (for testing)

    Returns:
        Dictionary with:
        - success: Boolean
        - gateway: Gateway info (model, firmware, MAC, lines, device counts)
        - total_devices: Total device count across all lines
        - devices_by_line: Dict of line_number -> device_count
        - equipment_list: Array of discovered devices with suggested equipment codes
        - summary: Device counts by type (controller, luminaire, sensor)
        - next_steps: Array of recommended next actions
        - error: Error message (only if success=False)
    """
    from app.services.dali_discovery_service import DALIDiscoveryService

    result = {
        "success": False,
        "building_id": building_id,
        "gateway_ip": gateway_ip,
        "gateway_type": gateway_type,
        "gateway": None,
        "total_devices": 0,
        "devices_by_line": {},
        "equipment_list": [],
        "summary": {
            "controllers": 0,
            "luminaires": 0,
            "sensors": 0,
            "other": 0,
        },
        "next_steps": [],
        "error": None,
    }

    # Extract site code from building_id (e.g., "site-002" -> "S002")
    match = re.match(r'^site-(\d+)', building_id, re.IGNORECASE)
    if match:
        site_num = match.group(1).zfill(3)
        site_code = f"S{site_num}"
    else:
        site_code = building_id[:3].upper() if len(building_id) >= 3 else building_id.upper()

    try:
        # Initialize discovery service
        service = DALIDiscoveryService(
            gateway_ip=gateway_ip,
            gateway_type=gateway_type,
            username=username,
            password=password,
            timeout=10.0
        )

        # Query gateway info
        gateway_info = await service.get_gateway_info()

        if not gateway_info or not gateway_info.online:
            if use_simulated:
                # Fall back to simulated data
                result["gateway"] = {
                    "ip_address": gateway_ip,
                    "manufacturer": "Tridonic (Simulated)",
                    "model": "Scenecom (Demo)",
                    "firmware_version": "2.1.0",
                    "dali_lines": 2,
                    "total_devices": 24,
                    "online": True,
                    "simulated": True,
                }
                gateway_info = type('obj', (object,), {
                    'dali_lines': 2,
                    'online': True,
                    'manufacturer': 'Tridonic',
                    'model': 'Scenecom'
                })()
                # Generate simulated device list
                simulated_devices = []
                for line in range(1, 3):
                    for addr in range(1, 13):  # 12 devices per line
                        device_type = "led_panel" if addr <= 8 else "emergency"
                        simulated_devices.append({
                            "line": line,
                            "address": addr,
                            "device_type": 6 if device_type == "led_panel" else 1,
                            "device_type_name": "LED Module" if device_type == "led_panel" else "Emergency",
                        })
            else:
                result["error"] = f"DALI gateway at {gateway_ip} is offline or unreachable"
                result["next_steps"] = [
                    "Verify gateway IP address and network connectivity",
                    "Check gateway power and Ethernet connection",
                    "Try with use_simulated=true for testing",
                ]
                return result
        else:
            result["gateway"] = gateway_info.to_dict()

        # Discover devices on each DALI line
        all_devices = []
        devices_by_type = {"controllers": 0, "luminaires": 0, "sensors": 0, "other": 0}
        lum_seq = 0
        sensor_seq = 0

        for line in range(1, gateway_info.dali_lines + 1):
            if use_simulated:
                # Use pre-generated simulated list
                line_devices = [d for d in simulated_devices if d["line"] == line]
            else:
                # Real discovery
                line_devices = await service.discover_devices(dali_line=line)

            result["devices_by_line"][line] = len(line_devices)

            # Generate equipment codes for each device
            for device_data in line_devices:
                if use_simulated:
                    device_type = device_data["device_type"]
                    device_type_name = device_data["device_type_name"]
                    dali_address = device_data["address"]
                    dali_line = device_data["line"]
                    gtin = None
                    serial_number = None
                    manufacturer = None
                else:
                    device_type = device_data.device_type
                    device_type_name = device_data.device_type_name
                    dali_address = device_data.dali_address
                    dali_line = line
                    gtin = device_data.gtin
                    serial_number = device_data.serial_number
                    manufacturer = device_data.manufacturer

                # Classify device and generate equipment code
                if "controller" in device_type_name.lower() or device_type == 0:
                    equip_type = "DALI"
                    category = "controllers"
                    code = f"{site_code}-DALI-L{dali_line}-{dali_address:02d}"
                elif "emergency" in device_type_name.lower() or device_type == 1:
                    equip_type = "LUM"
                    category = "luminaires"
                    lum_seq += 1
                    code = f"{site_code}-LUM-L{dali_line}-{lum_seq:03d}"
                elif "sensor" in device_type_name.lower() or "pir" in device_type_name.lower():
                    equip_type = "PIR"
                    category = "sensors"
                    sensor_seq += 1
                    code = f"{site_code}-PIR-L{dali_line}-{sensor_seq:03d}"
                else:
                    # Default to luminaire for LED modules and others
                    equip_type = "LUM"
                    category = "luminaires"
                    lum_seq += 1
                    code = f"{site_code}-LUM-L{dali_line}-{lum_seq:03d}"

                devices_by_type[category] += 1

                equipment_entry = {
                    "equipment_code": code,
                    "equipment_type": equip_type,
                    "device_type": device_type,
                    "device_type_name": device_type_name,
                    "dali_line": dali_line,
                    "dali_address": dali_address,
                    "category": category,
                }

                # Add GTIN/serial if available
                if gtin:
                    equipment_entry["gtin"] = gtin
                if serial_number:
                    equipment_entry["serial_number"] = serial_number
                if manufacturer:
                    equipment_entry["manufacturer"] = manufacturer

                all_devices.append(equipment_entry)

        # Update result
        result["success"] = True
        result["total_devices"] = len(all_devices)
        result["equipment_list"] = all_devices
        result["summary"] = devices_by_type

        # Generate next steps
        result["next_steps"] = [
            f"Review {len(all_devices)} discovered devices and equipment codes",
            f"Update building features: set dali=true in building.json",
            f"Save gateway IP ({gateway_ip}) to building config",
            f"Call bulk_discover with equipment_list to fetch full metadata",
            f"Call add_building_zones with dali_zone mappings for cross-system coordination",
            f"Register site with DALI service: register_niagara_site('{building_id}', gateway_ip)",
        ]

        logger.info(
            f"Discovered DALI gateway at {gateway_ip}: "
            f"{gateway_info.manufacturer} {gateway_info.model}, "
            f"{len(all_devices)} devices across {gateway_info.dali_lines} lines"
        )

    except Exception as e:
        logger.error(f"Error discovering DALI gateway: {e}")
        result["error"] = str(e)
        result["next_steps"] = [
            "Check gateway IP address and network connectivity",
            "Verify gateway API credentials if required",
            "Check server logs for detailed error information",
        ]

    return result


# ============================================================================
# AI/ML Predictive Maintenance Tools (Asset Metric Configuration)
# ============================================================================

# Asset metric templates library for predictive maintenance
# These templates are used when onboarding a new building to auto-generate
# metric configurations based on equipment types present.

ASSET_METRIC_TEMPLATES = {
    "generator": {
        "category": "Electrical/Mechanical",
        "metrics": [
            {"metric_id": "gen_voltage_ll", "name": "Line-Line Voltage", "unit": "V", "data_source": "bms_sensor", "point_pattern": ["voltage_ll", "volt_ll"], "normal_range": [380, 420], "warning_range": [370, 430], "critical_range": [360, 440], "weight": 0.15},
            {"metric_id": "gen_voltage_ln", "name": "Line-Neutral Voltage", "unit": "V", "data_source": "bms_sensor", "point_pattern": ["voltage_ln", "volt_ln"], "normal_range": [220, 240], "warning_range": [215, 245], "critical_range": [210, 250], "weight": 0.10},
            {"metric_id": "gen_frequency", "name": "Frequency", "unit": "Hz", "data_source": "bms_sensor", "point_pattern": ["frequency", "hz"], "normal_range": [49.5, 50.5], "warning_range": [49.0, 51.0], "critical_range": [48.0, 52.0], "weight": 0.15},
            {"metric_id": "gen_coolant_temp", "name": "Coolant Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["coolant_temp", "engine_temp"], "normal_range": [70, 95], "warning_range": [95, 105], "critical_range": [105, 115], "weight": 0.12},
            {"metric_id": "gen_oil_pressure", "name": "Oil Pressure", "unit": "bar", "data_source": "bms_sensor", "point_pattern": ["oil_pressure", "oil_press"], "normal_range": [3.5, 6.0], "warning_range": [2.5, 3.5], "critical_range": [1.5, 2.5], "weight": 0.12},
            {"metric_id": "gen_engine_hours", "name": "Engine Hours", "unit": "h", "data_source": "bms_sensor", "point_pattern": ["runtime", "hours"], "normal_range": [0, 500], "warning_range": [500, 1000], "critical_range": [1000, 2000], "weight": 0.10},
            {"metric_id": "gen_battery_voltage", "name": "Battery Voltage", "unit": "V", "data_source": "bms_sensor", "point_pattern": ["battery_volt", "batt_v"], "normal_range": [12.6, 13.8], "warning_range": [12.0, 12.6], "critical_range": [11.5, 12.0], "weight": 0.08},
            {"metric_id": "gen_fuel_level", "name": "Fuel Level", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["fuel_level", "fuel_lvl"], "normal_range": [50, 100], "warning_range": [25, 50], "critical_range": [10, 25], "weight": 0.08},
            {"metric_id": "gen_sound_level", "name": "Sound Level", "unit": "dBA", "data_source": "mobile_phone", "measurement_type": "audio", "normal_range": [70, 90], "warning_range": [90, 100], "critical_range": [100, 110], "weight": 0.05, "sampling_notes": "Record 10s at 1m from engine enclosure"},
            {"metric_id": "gen_vibration_rms", "name": "Vibration RMS", "unit": "mm/s", "data_source": "mobile_phone", "measurement_type": "accelerometer", "normal_range": [0, 2.0], "warning_range": [2.0, 4.5], "critical_range": [4.5, 7.0], "weight": 0.05, "sampling_notes": "Phone mounted on engine block, 10s sample"},
        ],
        "manual_inspections": [
            {"inspection_id": "gen_oil_analysis", "name": "Oil Analysis", "frequency_days": 90, "parameters": ["viscosity", "particles", "water", "metals"]},
            {"inspection_id": "gen_fuel_filter", "name": "Fuel Filter Condition", "frequency_days": 180, "parameters": ["visual_inspection", "restriction_check"]},
            {"inspection_id": "gen_belts_hoses", "name": "Belts and Hoses", "frequency_days": 60, "parameters": ["wear", "cracks", "tension"]},
            {"inspection_id": "gen_exhaust", "name": "Exhaust System", "frequency_days": 365, "parameters": ["leaks", "mounting", "insulation"]},
        ]
    },
    "chiller": {
        "category": "HVAC/Refrigeration",
        "metrics": [
            {"metric_id": "chill_suction_press", "name": "Suction Pressure", "unit": "bar", "data_source": "bms_sensor", "point_pattern": ["suction", "low_side"], "normal_range": [3.5, 5.5], "warning_range": [2.5, 3.5], "critical_range": [1.5, 2.5], "weight": 0.15},
            {"metric_id": "chill_discharge_press", "name": "Discharge Pressure", "unit": "bar", "data_source": "bms_sensor", "point_pattern": ["discharge", "high_side"], "normal_range": [12, 18], "warning_range": [18, 22], "critical_range": [22, 26], "weight": 0.15},
            {"metric_id": "chill_superheat", "name": "Superheat", "unit": "K", "data_source": "bms_sensor", "point_pattern": ["superheat", "sh"], "normal_range": [4, 8], "warning_range": [2, 4], "critical_range": [0, 2], "weight": 0.10},
            {"metric_id": "chill_subcooling", "name": "Subcooling", "unit": "K", "data_source": "bms_sensor", "point_pattern": ["subcool", "sc"], "normal_range": [3, 7], "warning_range": [1, 3], "critical_range": [0, 1], "weight": 0.10},
            {"metric_id": "chill_chw_supply_temp", "name": "CHW Supply Temp", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["chw_supply", "chws"], "normal_range": [6, 8], "warning_range": [8, 12], "critical_range": [12, 15], "weight": 0.12},
            {"metric_id": "chill_chw_return_temp", "name": "CHW Return Temp", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["chw_return", "chwr"], "normal_range": [11, 14], "warning_range": [14, 18], "critical_range": [18, 22], "weight": 0.10},
            {"metric_id": "chill_motor_current", "name": "Compressor Motor Current", "unit": "A", "data_source": "bms_sensor", "point_pattern": ["motor_current", "current"], "normal_range": [0, 150], "warning_range": [150, 180], "critical_range": [180, 200], "weight": 0.12},
            {"metric_id": "chill_oil_temp", "name": "Oil Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["oil_temp"], "normal_range": [45, 65], "warning_range": [65, 75], "critical_range": [75, 85], "weight": 0.08},
            {"metric_id": "chill_sound_compressor", "name": "Compressor Sound", "unit": "dBA", "data_source": "mobile_phone", "measurement_type": "audio", "normal_range": [65, 85], "warning_range": [85, 95], "critical_range": [95, 105], "weight": 0.05, "sampling_notes": "Record 10s at 1m from compressor"},
            {"metric_id": "chill_vibration_compressor", "name": "Compressor Vibration", "unit": "mm/s", "data_source": "mobile_phone", "measurement_type": "accelerometer", "normal_range": [0, 1.8], "warning_range": [1.8, 4.0], "critical_range": [4.0, 6.5], "weight": 0.03, "sampling_notes": "Phone on compressor housing, 10s sample"},
        ],
        "manual_inspections": [
            {"inspection_id": "chill_refrigerant_leak", "name": "Refrigerant Leak Check", "frequency_days": 180, "parameters": ["visual_inspection", "electronic_leak_detector"]},
            {"inspection_id": "chill_belt_condition", "name": "Belt Condition (if open drive)", "frequency_days": 90, "parameters": ["tension", "wear", "cracks"]},
            {"inspection_id": "chill_electrical_connections", "name": "Electrical Connections", "frequency_days": 365, "parameters": ["tightness", "discoloration", "torque"]},
            {"inspection_id": "chill_condenser_coils", "name": "Condenser Coil Condition", "frequency_days": 60, "parameters": ["cleanliness", "fins", "airflow"]},
        ]
    },
    "ahu": {
        "category": "HVAC/Air Handling",
        "metrics": [
            {"metric_id": "ahu_supply_air_temp", "name": "Supply Air Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["supply_temp", "sat", "discharge_temp"], "normal_range": [12, 16], "warning_range": [10, 12], "critical_range": [8, 10], "weight": 0.15},
            {"metric_id": "ahu_return_air_temp", "name": "Return Air Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["return_temp", "rat"], "normal_range": [22, 26], "warning_range": [26, 30], "critical_range": [30, 35], "weight": 0.12},
            {"metric_id": "ahu_mixed_air_temp", "name": "Mixed Air Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["mixed_temp", "mat"], "normal_range": [14, 20], "warning_range": [10, 14], "critical_range": [6, 10], "weight": 0.10},
            {"metric_id": "ahu_static_pressure", "name": "Static Pressure", "unit": "Pa", "data_source": "bms_sensor", "point_pattern": ["static_press", "sp"], "normal_range": [200, 500], "warning_range": [100, 200], "critical_range": [50, 100], "weight": 0.12},
            {"metric_id": "ahu_filter_dp", "name": "Filter Differential Pressure", "unit": "Pa", "data_source": "bms_sensor", "point_pattern": ["filter_dp", "filter_pressure"], "normal_range": [50, 125], "warning_range": [125, 200], "critical_range": [200, 250], "weight": 0.12},
            {"metric_id": "ahu_fan_current", "name": "Fan Motor Current", "unit": "A", "data_source": "bms_sensor", "point_pattern": ["fan_current", "fan_amps"], "normal_range": [0, 25], "warning_range": [25, 30], "critical_range": [30, 35], "weight": 0.10},
            {"metric_id": "ahu_outside_air_damper", "name": "Outside Air Damper", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["oa_damper", "economizer"], "normal_range": [10, 100], "warning_range": [0, 10], "critical_range": [0, 5], "weight": 0.08},
            {"metric_id": "ahu_sound_fan", "name": "Fan Sound Level", "unit": "dBA", "data_source": "mobile_phone", "measurement_type": "audio", "normal_range": [55, 75], "warning_range": [75, 85], "critical_range": [85, 95], "weight": 0.10, "sampling_notes": "Record 10s at 2m from fan inlet"},
            {"metric_id": "ahu_vibration_belt", "name": "Belt/Motor Vibration", "unit": "mm/s", "data_source": "mobile_phone", "measurement_type": "accelerometer", "normal_range": [0, 2.5], "warning_range": [2.5, 5.0], "critical_range": [5.0, 8.0], "weight": 0.11, "sampling_notes": "Phone on motor housing, 10s sample"},
        ],
        "manual_inspections": [
            {"inspection_id": "ahu_belt_condition", "name": "Belt Condition", "frequency_days": 60, "parameters": ["tension", "wear", "cracks", "alignment"]},
            {"inspection_id": "ahu_bearing_lubrication", "name": "Bearing Lubrication", "frequency_days": 180, "parameters": ["grease_level", "grease_condition"]},
            {"inspection_id": "ahu_coil_cleanliness", "name": "Coil Cleanliness", "frequency_days": 90, "parameters": ["heating_coil", "cooling_coil", "fins"]},
            {"inspection_id": "ahu_damper_operation", "name": "Damper Operation", "frequency_days": 365, "parameters": ["oa_damper", "exhaust_damper", "linkage"]},
        ]
    },
    "fcu": {
        "category": "HVAC/Fan Coil",
        "metrics": [
            {"metric_id": "fcu_coil_temp", "name": "Coil Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["coil_temp", "leaving_water"], "normal_range": [6, 12], "warning_range": [12, 18], "critical_range": [18, 25], "weight": 0.20},
            {"metric_id": "fcu_fan_speed", "name": "Fan Speed", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["fan_speed", "speed"], "normal_range": [0, 100], "warning_range": [80, 100], "critical_range": [100, 100], "weight": 0.15},
            {"metric_id": "fcu_valve_position", "name": "Control Valve Position", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["valve_pos", "control_valve"], "normal_range": [0, 100], "warning_range": [90, 100], "critical_range": [100, 100], "weight": 0.15},
            {"metric_id": "fcu_room_temp", "name": "Room Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["room_temp", "space_temp"], "normal_range": [20, 24], "warning_range": [24, 27], "critical_range": [27, 30], "weight": 0.20},
            {"metric_id": "fcu_motor_current", "name": "Motor Current", "unit": "A", "data_source": "bms_sensor", "point_pattern": ["motor_current"], "normal_range": [0, 3.5], "warning_range": [3.5, 4.5], "critical_range": [4.5, 5.5], "weight": 0.15},
            {"metric_id": "fcu_sound_fan", "name": "Fan Sound", "unit": "dBA", "data_source": "mobile_phone", "measurement_type": "audio", "normal_range": [35, 50], "warning_range": [50, 65], "critical_range": [65, 75], "weight": 0.10, "sampling_notes": "Record 10s at 1m from FCU"},
            {"metric_id": "fcu_vibration_motor", "name": "Motor Vibration", "unit": "mm/s", "data_source": "mobile_phone", "measurement_type": "accelerometer", "normal_range": [0, 2.0], "warning_range": [2.0, 4.5], "critical_range": [4.5, 7.0], "weight": 0.05, "sampling_notes": "Phone on motor housing, 10s sample"},
        ],
        "manual_inspections": [
            {"inspection_id": "fcu_filter_condition", "name": "Filter Condition", "frequency_days": 90, "parameters": ["cleanliness", "pressure_drop"]},
            {"inspection_id": "fcu_condensate_tray", "name": "Condensate Tray", "frequency_days": 60, "parameters": ["cleanliness", "drainage", "leaks"]},
            {"inspection_id": "fcu_fan_motor", "name": "Fan Motor", "frequency_days": 365, "parameters": ["bearings", "capacitor", "wiring"]},
        ]
    },
    "ups": {
        "category": "Electrical/Power",
        "metrics": [
            {"metric_id": "ups_battery_voltage", "name": "Battery Voltage", "unit": "V", "data_source": "bms_sensor", "point_pattern": ["batt_volt", "battery_voltage"], "normal_range": [12.0, 13.8], "warning_range": [11.0, 12.0], "critical_range": [10.0, 11.0], "weight": 0.20},
            {"metric_id": "ups_load_percent", "name": "Load Percentage", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["load", "load_percent"], "normal_range": [20, 80], "warning_range": [80, 95], "critical_range": [95, 100], "weight": 0.15},
            {"metric_id": "ups_battery_temp", "name": "Battery Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["batt_temp"], "normal_range": [20, 25], "warning_range": [25, 30], "critical_range": [30, 35], "weight": 0.15},
            {"metric_id": "ups_runtime_remaining", "name": "Runtime Remaining", "unit": "min", "data_source": "bms_sensor", "point_pattern": ["runtime", "battery_runtime"], "normal_range": [30, 120], "warning_range": [15, 30], "critical_range": [5, 15], "weight": 0.20},
            {"metric_id": "ups_output_frequency", "name": "Output Frequency", "unit": "Hz", "data_source": "bms_sensor", "point_pattern": ["output_freq"], "normal_range": [49.5, 50.5], "warning_range": [49.0, 49.5], "critical_range": [48.5, 49.0], "weight": 0.10},
            {"metric_id": "ups_battery_impedance", "name": "Battery Impedance", "unit": "mΩ", "data_source": "manual", "measurement_type": "battery_tester", "normal_range": [10, 30], "warning_range": [30, 50], "critical_range": [50, 80], "weight": 0.20, "sampling_notes": "Measured with battery impedance tester"},
        ],
        "manual_inspections": [
            {"inspection_id": "ups_battery_visual", "name": "Battery Visual Inspection", "frequency_days": 30, "parameters": ["swelling", "leaks", "corrosion", "terminals"]},
            {"inspection_id": "ups_fan_operation", "name": "Fan Operation", "frequency_days": 90, "parameters": ["noise", "vibration", "airflow"]},
            {"inspection_id": "ups_capacitors", "name": "DC Capacitors", "frequency_days": 365, "parameters": ["bulging", "leaks", "ESR"]},
        ]
    },
    "transformer": {
        "category": "Electrical/Power",
        "metrics": [
            {"metric_id": "tx_winding_temp", "name": "Winding Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["winding_temp", "hw_temp"], "normal_range": [40, 80], "warning_range": [80, 100], "critical_range": [100, 120], "weight": 0.25},
            {"metric_id": "tx_oil_temp", "name": "Oil Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["oil_temp", "tot"], "normal_range": [30, 70], "warning_range": [70, 90], "critical_range": [90, 110], "weight": 0.25},
            {"metric_id": "tx_load_percent", "name": "Load Percentage", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["load"], "normal_range": [30, 80], "warning_range": [80, 100], "critical_range": [100, 115], "weight": 0.20},
            {"metric_id": "tx_tap_position", "name": "Tap Changer Position", "unit": "", "data_source": "bms_sensor", "point_pattern": ["tap", "oltc"], "normal_range": [-5, 5], "warning_range": [-10, -5], "critical_range": [-15, -10], "weight": 0.10},
            {"metric_id": "tx_gas_analysis", "name": "DGA (Dissolved Gas Analysis)", "unit": "ppm", "data_source": "manual", "measurement_type": "oil_sample", "normal_range": [0, 100], "warning_range": [100, 500], "critical_range": [500, 1000], "weight": 0.20, "sampling_notes": "Annual oil sample lab analysis"},
        ],
        "manual_inspections": [
            {"inspection_id": "tx_oil_quality", "name": "Oil Quality Test", "frequency_days": 365, "parameters": ["dielectric_strength", "acidity", "moisture", "DGA"]},
            {"inspection_id": "tx_bushings", "name": "Bushings Inspection", "frequency_days": 365, "parameters": ["oil_level", "leaks", "tan_delta"]},
            {"inspection_id": "tx_oltc_mechanism", "name": "OLTC Mechanism", "frequency_days": 365, "parameters": ["operation_count", "oil_quality", "mechanical_binding"]},
        ]
    },
    "vav": {
        "category": "HVAC/Air Distribution",
        "metrics": [
            {"metric_id": "vairflow", "name": "Airflow", "unit": "L/s", "data_source": "bms_sensor", "point_pattern": ["airflow", "flow"], "normal_range": [50, 200], "warning_range": [30, 50], "critical_range": [10, 30], "weight": 0.30},
            {"metric_id": "vdamper_position", "name": "Damper Position", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["damper", "position"], "normal_range": [10, 100], "warning_range": [0, 10], "critical_range": [0, 5], "weight": 0.20},
            {"metric_id": "vreheat_valve", "name": "Reheat Valve Position", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["reheat", "heating_valve"], "normal_range": [0, 100], "warning_range": [80, 100], "critical_range": [95, 100], "weight": 0.20},
            {"metric_id": "vroom_temp", "name": "Room Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["room_temp"], "normal_range": [20, 24], "warning_range": [24, 27], "critical_range": [27, 30], "weight": 0.30},
        ],
        "manual_inspections": [
            {"inspection_id": "vactuator", "name": "Damper Actuator", "frequency_days": 365, "parameters": ["calibration", "linkage", "noise"]},
            {"inspection_id": "vflow_sensor", "name": "Airflow Sensor", "frequency_days": 365, "parameters": ["calibration", "cleanliness"]},
        ]
    },
    "cooling_tower": {
        "category": "HVAC/Heat Rejection",
        "metrics": [
            {"metric_id": "ct_basin_temp", "name": "Basin Temperature", "unit": "°C", "data_source": "bms_sensor", "point_pattern": ["basin_temp"], "normal_range": [20, 32], "warning_range": [32, 40], "critical_range": [40, 50], "weight": 0.25},
            {"metric_id": "ct_fan_speed", "name": "Fan Speed", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["fan_speed"], "normal_range": [0, 100], "warning_range": [80, 100], "critical_range": [100, 100], "weight": 0.20},
            {"metric_id": "ct_water_level", "name": "Water Level", "unit": "%", "data_source": "bms_sensor", "point_pattern": ["water_level"], "normal_range": [50, 80], "warning_range": [30, 50], "critical_range": [10, 30], "weight": 0.20},
            {"metric_id": "ct_fan_current", "name": "Fan Motor Current", "unit": "A", "data_source": "bms_sensor", "point_pattern": ["fan_current"], "normal_range": [0, 30], "warning_range": [30, 40], "critical_range": [40, 50], "weight": 0.15},
            {"metric_id": "ct_sound_fan", "name": "Fan Sound Level", "unit": "dBA", "data_source": "mobile_phone", "measurement_type": "audio", "normal_range": [65, 85], "warning_range": [85, 95], "critical_range": [95, 105], "weight": 0.15, "sampling_notes": "Record 10s at 5m from tower"},
            {"metric_id": "ct_vibration_fan", "name": "Fan Vibration", "unit": "mm/s", "data_source": "mobile_phone", "measurement_type": "accelerometer", "normal_range": [0, 3.0], "warning_range": [3.0, 6.0], "critical_range": [6.0, 10], "weight": 0.05, "sampling_notes": "Phone on fan motor, 10s sample"},
        ],
        "manual_inspections": [
            {"inspection_id": "ct_fill_condition", "name": "Fill Condition", "frequency_days": 180, "parameters": ["cleanliness", "degradation", "biofouling"]},
            {"inspection_id": "ct_nozzles", "name": "Distribution Nozzles", "frequency_days": 90, "parameters": ["blockage", "wear", "spray_pattern"]},
            {"inspection_id": "ct_drift_eliminator", "name": "Drift Eliminator", "frequency_days": 365, "parameters": ["cleanliness", "damage"]},
        ]
    }
}


async def get_asset_metrics_template_tool(
    building_id: str,
    equipment_types: List[str] = None,
) -> Dict[str, Any]:
    """
    Get asset metric templates for a building during onboarding.

    Returns metric templates based on equipment types present in the building.
    Engineers can review and configure these templates before activation.

    Args:
        building_id: Building/site ID
        equipment_types: Optional list of equipment types to filter (e.g., ["generator", "chiller", "ahu"])
                      If not provided, will auto-detect from building's devices

    Returns:
        Metric templates for each equipment type with configurable parameters
    """
    import json
    from pathlib import Path

    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    building_path = buildings_path / building_id

    if not building_path.exists():
        return {
            "success": False,
            "error": f"Building '{building_id}' not found. Create it first with create_building.",
        }

    # If equipment_types not provided, detect from building's devices/zones
    if not equipment_types:
        equipment_types = set()

        # Check zones for equipment references
        zones_file = building_path / "zones.json"
        if zones_file.exists():
            with open(zones_file) as f:
                zones = json.load(f)
                for zone in zones:
                    # Equipment IDs often contain type hints
                    for field in ["fcu_id", "ahu_id", "vav_id"]:
                        if zone.get(field):
                            eq_id = zone[field].lower()
                            if "fcu" in eq_id or "fan" in eq_id:
                                equipment_types.add("fcu")
                            elif "ahu" in eq_id:
                                equipment_types.add("ahu")
                            elif "vav" in eq_id:
                                equipment_types.add("vav")

        # Check devices file
        devices_file = Path(__file__).parent.parent / "data" / "mock_devices.json"
        if devices_file.exists():
            with open(devices_file) as f:
                devices = json.load(f)
                for device in devices:
                    if device.get("building_id") == building_id:
                        device_type = device.get("device_type", "").lower()
                        # Map device types to templates
                        for template_type in ASSET_METRIC_TEMPLATES.keys():
                            if template_type in device_type:
                                equipment_types.add(template_type)
                                break

        equipment_types = list(equipment_types)

    # Generate templates for each equipment type
    templates = {}
    for eq_type in equipment_types:
        template_key = eq_type.lower()
        if template_key in ASSET_METRIC_TEMPLATES:
            templates[eq_type] = ASSET_METRIC_TEMPLATES[template_key]

    return {
        "success": True,
        "building_id": building_id,
        "equipment_types_detected": equipment_types,
        "metric_templates": templates,
        "total_metrics": sum(len(t.get("metrics", [])) for t in templates.values()),
        "total_inspections": sum(len(t.get("manual_inspections", [])) for t in templates.values()),
        "message": f"Generated {len(templates)} equipment type templates with {sum(len(t.get('metrics', [])) for t in templates.values())} metrics",
        "next_steps": [
            "Review the generated metric templates",
            "Configure thresholds and weights as needed",
            "Call configure_asset_metrics to save configuration",
        ],
    }


async def configure_asset_metrics_tool(
    building_id: str,
    metric_config: Dict[str, Any],
    save_to_file: bool = True,
) -> Dict[str, Any]:
    """
    Configure asset metrics for a building after onboarding.

    Engineers can customize:
    - Thresholds (normal/warning/critical ranges)
    - Weights (for health score calculation)
    - Measurement intervals
    - Which metrics use mobile phone vs BMS sensors

    Args:
        building_id: Building/site ID
        metric_config: Configuration dictionary with structure:
            {
                "equipment_type": {
                    "metrics": {
                        "metric_id": {
                            "enabled": true/false,
                            "normal_range": [min, max],
                            "warning_range": [min, max],
                            "critical_range": [min, max],
                            "weight": 0.1,
                            "measurement_interval_days": 7,
                            "custom_threshold": "override value"
                        }
                    },
                    "manual_inspections": {
                        "inspection_id": {
                            "enabled": true/false,
                            "frequency_days": 90,
                            "assigned_to": "technician_name"
                        }
                    }
                }
            }
        save_to_file: If true, saves configuration to building's asset_metrics.json

    Returns:
        Configuration summary with next steps
    """
    import json
    from pathlib import Path
    from datetime import datetime

    buildings_path = Path(__file__).parent.parent / "data" / "buildings"
    building_path = buildings_path / building_id

    if not building_path.exists():
        return {
            "success": False,
            "error": f"Building '{building_id}' not found. Create it first with create_building.",
        }

    # Merge with templates and validate
    configured_metrics = {}
    total_enabled = 0

    for eq_type, config in metric_config.items():
        template_key = eq_type.lower()
        if template_key not in ASSET_METRIC_TEMPLATES:
            continue

        template = ASSET_METRIC_TEMPLATES[template_key]
        configured_metrics[eq_type] = {
            "category": template.get("category", ""),
            "metrics": [],
            "manual_inspections": [],
        }

        # Process metrics
        if "metrics" in config:
            for metric in template.get("metrics", []):
                metric_id = metric["metric_id"]
                user_config = config["metrics"].get(metric_id, {})

                # Merge template with user config
                configured_metric = {**metric}
                if user_config.get("enabled", True):
                    configured_metric.update({
                        "normal_range": user_config.get("normal_range", metric["normal_range"]),
                        "warning_range": user_config.get("warning_range", metric["warning_range"]),
                        "critical_range": user_config.get("critical_range", metric["critical_range"]),
                        "weight": user_config.get("weight", metric.get("weight", 0.1)),
                        "measurement_interval_days": user_config.get("measurement_interval_days", 7),
                        "custom_threshold": user_config.get("custom_threshold"),
                        "configured_at": datetime.now().isoformat(),
                    })
                    configured_metrics[eq_type]["metrics"].append(configured_metric)
                    total_enabled += 1

        # Process manual inspections
        if "manual_inspections" in config:
            for inspection in template.get("manual_inspections", []):
                inspection_id = inspection["inspection_id"]
                user_config = config["manual_inspections"].get(inspection_id, {})

                configured_inspection = {**inspection}
                if user_config.get("enabled", True):
                    configured_inspection.update({
                        "frequency_days": user_config.get("frequency_days", inspection["frequency_days"]),
                        "assigned_to": user_config.get("assigned_to", "TBD"),
                        "configured_at": datetime.now().isoformat(),
                    })
                    configured_metrics[eq_type]["manual_inspections"].append(configured_inspection)

    # Save to file if requested
    if save_to_file:
        metrics_file = building_path / "asset_metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(configured_metrics, f, indent=2)

        logger.info(f"Configured {total_enabled} metrics for building {building_id}")

    return {
        "success": True,
        "building_id": building_id,
        "metrics_configured": total_enabled,
        "equipment_types": list(configured_metrics.keys()),
        "configuration": configured_metrics,
        "message": f"Configured {total_enabled} metrics across {len(configured_metrics)} equipment types",
        "next_steps": [
            "Asset metrics are now ready for data collection",
            "Use the mobile app to capture manual measurements",
            "ML models will train after 3-6 months of data collection",
        ],
    }


# ============================================================================
# Solar MCP Tool Functions (34-09)
# ============================================================================


async def get_solar_overview_tool(site_id: str = "site-002") -> Dict[str, Any]:
    """Get solar site overview — generation, BESS SOC, grid status, PR.

    MCP Tool: get_solar_overview
    """
    # LOCKED: Clawd only works with site-002 for now
    site_id = "site-002"

    try:
        from app.services.solar_ingestion_service import get_solar_ingestion_service
        svc = get_solar_ingestion_service()
        overview = await svc.get_site_overview(site_id)
        if not overview:
            return {"error": f"Solar site '{site_id}' not found"}
        return overview
    except Exception as e:
        logger.error(f"get_solar_overview error: {e}")
        return {"error": str(e)}


async def get_bess_status_tool(site_id: str = "site-002") -> Dict[str, Any]:
    """Get BESS status — SOC, mode, health, dispatch schedule.

    MCP Tool: get_bess_status
    """
    # LOCKED: Clawd only works with site-002 for now
    site_id = "site-002"

    try:
        from app.services.solar_ingestion_service import get_solar_ingestion_service
        svc = get_solar_ingestion_service()
        bess = await svc.get_bess_status(site_id)
        if not bess:
            return {"error": f"No BESS found at site '{site_id}'"}
        result = bess.to_dict()
        # Add dispatch info
        try:
            from app.services.solar_dispatch_service import get_solar_dispatch_service
            dispatch = get_solar_dispatch_service()
            status = dispatch.get_dispatch_status(site_id)
            if status:
                result["dispatch"] = status.to_dict()
        except Exception:
            pass
        return result
    except Exception as e:
        logger.error(f"get_bess_status error: {e}")
        return {"error": str(e)}


async def get_solar_savings_tool(
    site_id: str = "site-002",
    period: str = "ytd",
) -> Dict[str, Any]:
    """Get financial summary — daily/monthly/YTD savings breakdown.

    MCP Tool: get_solar_savings
    """
    try:
        from app.services.solar_financial_service import get_solar_financial_service
        svc = get_solar_financial_service()
        summary = svc.get_financial_summary(site_id, period=period)
        return summary.to_dict()
    except Exception as e:
        logger.error(f"get_solar_savings error: {e}")
        return {"error": str(e)}


async def get_solar_forecast_tool(
    site_id: str = "site-002",
    hours: int = 24,
) -> Dict[str, Any]:
    """Get next 24h generation forecast with confidence.

    MCP Tool: get_solar_forecast
    """
    try:
        from app.services.solar_forecast_service import get_solar_forecast_service
        svc = get_solar_forecast_service()
        forecast = svc.get_forecast(site_id, hours_ahead=hours)
        return forecast.to_dict()
    except Exception as e:
        logger.error(f"get_solar_forecast error: {e}")
        return {"error": str(e)}


async def get_solar_diagnostics_tool(site_id: str = "site-002") -> Dict[str, Any]:
    """Get solar diagnostics — top issues, underperformers, maintenance.

    MCP Tool: get_solar_diagnostics
    """
    # LOCKED: Clawd only works with site-002 for now
    site_id = "site-002"

    try:
        from app.services.solar_performance_service import get_solar_performance_service
        perf = get_solar_performance_service()
        report = await perf.get_diagnostic_summary(site_id)
        result = report.to_dict() if report else {"issues": []}

        # Add maintenance recommendations
        try:
            from app.services.solar_maintenance_service import get_solar_maintenance_service
            maint = get_solar_maintenance_service()
            recs = await maint.evaluate_maintenance_needs(site_id)
            result["maintenance_recommendations"] = [r.to_dict() for r in recs[:5]]
            result["maintenance_count"] = len(recs)
        except Exception:
            pass

        return result
    except Exception as e:
        logger.error(f"get_solar_diagnostics error: {e}")
        return {"error": str(e)}


# ============================================================================
# MCP Tool Definitions (JSON Schema)
# ============================================================================

MCP_TOOLS = [
    {
        "name": "get_buildings",
        "description": "List buildings with status summary. Returns building information including health scores, asset counts, and alarm status. Supports filtering by status (all/critical/warning/healthy) and region.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "critical", "warning", "healthy"],
                    "description": "Filter buildings by status - all (default), critical (has critical alarms), warning (has warnings), healthy (no issues)"
                },
                "region": {
                    "type": "string",
                    "description": "Filter by region (e.g., Gauteng, Western Cape, KwaZulu-Natal)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_assets",
        "description": "List assets for a building. Returns all BMS-connected assets (HVAC equipment, lighting, security) for a specific building with health scores and alarm status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building/site ID (e.g., site-001)"
                },
                "asset_type": {
                    "type": "string",
                    "description": "Filter by asset type (AHU, Chiller, FCU, VAV, zone_controller, chw_system)"
                },
                "criticality": {
                    "type": "string",
                    "enum": ["critical", "all"],
                    "description": "Filter by criticality level - critical (only critical assets) or all (default)"
                }
            },
            "required": ["building_id"]
        }
    },
    {
        "name": "get_asset_detail",
        "description": "Get comprehensive asset details including current readings, health breakdown, and recent alarms. Use this for detailed equipment analysis and troubleshooting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "Asset/device ID (e.g., S001-CHILLER-B1-001)"
                },
                "include": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["health_breakdown", "recent_alarms", "current_readings"]
                    },
                    "description": "Sections to include in response (default: current_readings)"
                }
            },
            "required": ["asset_id"]
        }
    },
    {
        "name": "get_devices",
        "description": "List BMS devices with protocol and connection status. Use this for device discovery and inventory queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Filter by site ID"
                },
                "device_type": {
                    "type": "string",
                    "enum": ["hvac", "lighting", "security", "fire_safety"],
                    "description": "Filter by device type"
                }
            },
            "required": []
        }
    },
    {
        "name": "read_device_point",
        "description": "Read a device point value from the BMS. Returns current value, unit, quality, and timestamp. Use this for real-time equipment monitoring.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "Device ID (e.g., S001-CHILLER-B1-001)"
                },
                "point_name": {
                    "type": "string",
                    "description": "Point name to read (e.g., chw_supply_temp, fan_status)"
                }
            },
            "required": ["device_id", "point_name"]
        }
    },
    {
        "name": "write_device_point",
        "description": "Write a value to a device point (SAFETY CRITICAL). Includes safety validation and audit logging. Use for control actions like adjusting setpoints or switching equipment on/off.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "Device ID (e.g., S001-CHILLER-B1-001)"
                },
                "point_name": {
                    "type": "string",
                    "description": "Point name to write (e.g., chw_supply_temp_setpoint)"
                },
                "value": {
                    "description": "Value to write (type depends on point - number, boolean, or string)"
                },
                "priority": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 16,
                    "description": "BACnet priority level (1-16, default 8)"
                }
            },
            "required": ["device_id", "point_name", "value"]
        }
    },
    {
        "name": "get_alarms",
        "description": "Get alarms with filtering. Returns alarm history with support for filtering by building, asset, severity, state, and time range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Filter by building/site ID"
                },
                "asset_id": {
                    "type": "string",
                    "description": "Filter by asset/equipment ID"
                },
                "severity": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["critical", "warning", "info"]
                    },
                    "description": "Filter by severity levels"
                },
                "state": {
                    "type": "string",
                    "enum": ["active", "acknowledged", "cleared", "all"],
                    "description": "Filter by alarm state (default: all)"
                },
                "from_time": {
                    "type": "string",
                    "description": "Start time in ISO format (e.g., 2026-01-01T00:00:00)"
                },
                "to_time": {
                    "type": "string",
                    "description": "End time in ISO format"
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "description": "Maximum alarms to return (default: 50)"
                }
            },
            "required": []
        }
    },
    {
        "name": "search_alarms",
        "description": "Natural language alarm search with pattern analysis. Parses queries to find relevant alarms and identify recurring patterns. Use this for investigating equipment issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query (e.g., 'chiller alarms', 'temperature issues last week')"
                },
                "building_id": {
                    "type": "string",
                    "description": "Optional building/site ID filter"
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Maximum results (default: 20)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_trends",
        "description": "Get historical trend data for an asset parameter. Returns time-series data points with statistics. Use for analyzing equipment performance over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "Asset/device ID (e.g., S001-CHILLER-B1-001)"
                },
                "parameter": {
                    "type": "string",
                    "description": "Parameter name to get trends for (e.g., chw_supply_temp, fan_speed)"
                },
                "from_time": {
                    "type": "string",
                    "description": "Start time in ISO format (default: 24 hours ago)"
                },
                "to_time": {
                    "type": "string",
                    "description": "End time in ISO format (default: now)"
                },
                "interval": {
                    "type": "string",
                    "enum": ["1min", "5min", "15min", "1hour", "1day"],
                    "description": "Data interval (default: 1hour)"
                }
            },
            "required": ["asset_id", "parameter"]
        }
    },
    {
        "name": "get_health_score",
        "description": "Get health score breakdown for an asset or building. Returns overall score, status, breakdown by category, and contributing factors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "Asset/device ID (provide either asset_id or building_id)"
                },
                "building_id": {
                    "type": "string",
                    "description": "Building/site ID (provide either asset_id or building_id)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_work_orders",
        "description": "Get work orders. Returns work order history with filtering by building, asset, and status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Filter by building/site ID"
                },
                "asset_id": {
                    "type": "string",
                    "description": "Filter by asset ID"
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "completed", "all"],
                    "description": "Filter by status (default: all)"
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "description": "Maximum work orders to return (default: 50)"
                }
            },
            "required": []
        }
    },
    {
        "name": "create_work_order",
        "description": "Create a work order (SAFETY CRITICAL). Includes audit logging. Use for creating work orders from AI diagnosis or chat requests.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building/site ID"
                },
                "asset_id": {
                    "type": "string",
                    "description": "Asset/device ID"
                },
                "description": {
                    "type": "string",
                    "description": "Fault description"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Priority level (default: medium)"
                },
                "suggested_parts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of suggested parts for the repair"
                }
            },
            "required": ["building_id", "asset_id", "description"]
        }
    },
    # Building Management Tools (for onboarding new buildings)
    {
        "name": "list_managed_buildings",
        "description": "List all managed buildings (active and inactive). Use this to see what buildings are configured in the system.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "create_building",
        "description": "Create a new building configuration. Creates the building folder structure and config files. Building is NOT activated by default.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Unique building ID (lowercase, no spaces, e.g., 'sandton', 'gateway-centre')"
                },
                "name": {
                    "type": "string",
                    "description": "Building display name (e.g., 'Sandton Office Park')"
                },
                "address": {
                    "type": "string",
                    "description": "Building address"
                },
                "floors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of floor identifiers (e.g., ['L1', 'L2', 'L3'])"
                },
                "features": {
                    "type": "object",
                    "description": "Features to enable: {hvac: true, dali: false, desk_diagnosis: true}"
                },
                "client_name": {
                    "type": "string",
                    "description": "Optional client/organization name for auto-creating a basic contract"
                },
                "monthly_fee_zar": {
                    "type": "number",
                    "description": "Optional monthly fee in ZAR (requires client_name, contract_start, contract_end)"
                },
                "contract_start": {
                    "type": "string",
                    "description": "Optional contract start date YYYY-MM-DD (requires client_name, monthly_fee_zar, contract_end)"
                },
                "contract_end": {
                    "type": "string",
                    "description": "Optional contract end date YYYY-MM-DD (requires client_name, monthly_fee_zar, contract_start)"
                }
            },
            "required": ["building_id", "name"]
        }
    },
    {
        "name": "activate_building",
        "description": "Activate a building so it appears in the system. Call this after setting up desks and zones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building ID to activate"
                },
                "set_default": {
                    "type": "boolean",
                    "description": "Set as the default building (default: false)"
                }
            },
            "required": ["building_id"]
        }
    },
    {
        "name": "get_building_config",
        "description": "Get a building's configuration including desks, zones, and features.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building ID to get config for"
                }
            },
            "required": ["building_id"]
        }
    },
    # AI-Assisted Onboarding Tools (for ingesting BMS export data)
    {
        "name": "add_building_zones",
        "description": "Add HVAC zones to a building with equipment mappings (FCU, VAV, AHU). Use after importing point list or when manually configuring zones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building ID to add zones to"
                },
                "zones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "zone_id": {"type": "string", "description": "Unique zone ID (e.g., 'Zone-L12-N')"},
                            "floor": {"type": "string", "description": "Floor identifier (e.g., 'L12')"},
                            "fcu_id": {"type": "string", "description": "Fan Coil Unit device ID"},
                            "vav_id": {"type": "string", "description": "VAV box device ID (optional)"},
                            "ahu_id": {"type": "string", "description": "Air Handling Unit device ID"},
                            "setpoint": {"type": "number", "description": "Temperature setpoint (default 22.0)"},
                            "desk_range": {"type": "string", "description": "Desk range served (e.g., '201-206')"}
                        },
                        "required": ["zone_id"]
                    },
                    "description": "Array of zone definitions with equipment mappings"
                }
            },
            "required": ["building_id", "zones"]
        }
    },
    {
        "name": "add_building_desks",
        "description": "Add desks to a building with zone mappings, DALI lighting, and environmental context. Enables desk-to-zone comfort diagnosis with solar/HVAC/lighting integration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building ID to add desks to"
                },
                "desks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "desk_id": {"type": "string", "description": "Unique desk ID (e.g., '201', 'L12-D001')"},
                            "zone_id": {"type": "string", "description": "HVAC zone the desk belongs to"},
                            "floor": {"type": "string", "description": "Floor identifier (e.g., 'Level 12')"},
                            "near_window": {"type": "boolean", "description": "Near exterior window (solar heat gain)"},
                            "orientation": {"type": "string", "enum": ["N", "S", "E", "W", "NE", "NW", "SE", "SW"], "description": "Window orientation for solar analysis (Southern Hemisphere: N=most sun)"},
                            "near_diffuser": {"type": "string", "description": "Supply air diffuser ID if under one (draft issues)"},
                            "near_printer": {"type": "boolean", "description": "Near heat source (printer/copier)"},
                            "department": {"type": "string", "description": "Department/team"},
                            "occupant": {"type": "string", "description": "Occupant name"},
                            "x_coord": {"type": "number", "description": "Floor plan X coordinate"},
                            "y_coord": {"type": "number", "description": "Floor plan Y coordinate"},
                            "dali_zone": {"type": "string", "description": "DALI lighting zone (often matches HVAC zone)"},
                            "sensor_id": {"type": "string", "description": "DALI PIR occupancy sensor ID (e.g., 'PIR-L12-N-001')"},
                            "luminaire_ids": {"type": "array", "items": {"type": "string"}, "description": "Luminaire IDs serving this desk"},
                            "dali_controller": {"type": "string", "description": "Tridonic Scenecom controller ID (e.g., 'DALI-L12-01')"}
                        },
                        "required": ["desk_id"]
                    },
                    "description": "Array of desk definitions with HVAC and DALI context"
                }
            },
            "required": ["building_id", "desks"]
        }
    },
    {
        "name": "add_building_devices",
        "description": "Add BMS devices (chillers, AHUs, FCUs, VAVs, etc.) to the system. Devices are added to mock_devices.json.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building ID to add devices to"
                },
                "site_code": {
                    "type": "string",
                    "description": "Site code for device ID generation (default: first 3 chars of building_id)"
                },
                "devices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "string", "description": "Device ID (auto-generated if not provided)"},
                            "device_type": {"type": "string", "description": "Type: chiller, ahu, fcu, vav, pump, meter, controller"},
                            "name": {"type": "string", "description": "Display name"},
                            "location": {"type": "string", "description": "Location description"},
                            "protocol": {"type": "string", "description": "Protocol: bacnet, modbus, mock"},
                            "points": {"type": "object", "description": "Point name to value mappings"},
                            "metadata": {"type": "object", "description": "Additional metadata"}
                        },
                        "required": ["device_type"]
                    },
                    "description": "Array of device definitions"
                }
            },
            "required": ["building_id", "devices"]
        }
    },
    {
        "name": "import_point_list",
        "description": "AI-assisted onboarding: Import BACnet point list and auto-generate device/zone structure. Supports multiple BMS vendors with different naming conventions. Auto-detects vendor if not specified.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building ID to import points for"
                },
                "site_code": {
                    "type": "string",
                    "description": "Site code for device ID generation (default: first 3 chars of building_id)"
                },
                "bms_vendor": {
                    "type": "string",
                    "enum": ["auto", "desigo", "siemens", "metasys", "jci", "ebi", "honeywell", "ecostruxure", "schneider", "niagara", "tridium", "trend"],
                    "description": "BMS vendor for naming pattern hints: desigo/siemens, metasys/jci, ebi/honeywell, ecostruxure/schneider, niagara/tridium, trend. Default: auto-detect"
                },
                "point_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "point_name": {"type": "string", "description": "BACnet object name (e.g., 'AHU-L12-01.SupplyAirTemp')"},
                            "object_type": {"type": "string", "description": "BACnet object type (e.g., 'Analog Input', 'Binary Output')"},
                            "instance": {"type": "integer", "description": "BACnet object instance number"},
                            "description": {"type": "string", "description": "Point description"},
                            "units": {"type": "string", "description": "Engineering units"},
                            "value": {"description": "Current value (number, boolean, or string)"}
                        },
                        "required": ["point_name"]
                    },
                    "description": "Array of BACnet points from BMS export"
                }
            },
            "required": ["building_id", "point_list"]
        }
    },
    {
        "name": "import_controller_list",
        "description": "Import BMS controller information (PXC, DDC controllers) and create device structure. Use alongside import_point_list for complete onboarding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building ID to import controllers for"
                },
                "site_code": {
                    "type": "string",
                    "description": "Site code for device ID generation (default: first 3 chars of building_id)"
                },
                "controllers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Controller name (e.g., 'PXC-L12-01')"},
                            "ip_address": {"type": "string", "description": "IP address"},
                            "bacnet_device_id": {"type": "integer", "description": "BACnet device instance"},
                            "area_served": {"type": "string", "description": "Area served (e.g., 'Level 12 North')"},
                            "controller_type": {"type": "string", "description": "Type: PXC, PXA, DDC"},
                            "equipment": {"type": "array", "items": {"type": "string"}, "description": "Equipment names controlled"}
                        },
                        "required": ["name"]
                    },
                    "description": "Array of controller definitions"
                }
            },
            "required": ["building_id", "controllers"]
        }
    },
    {
        "name": "discover_tridonic_gateway",
        "description": "Discover Tridonic DALI gateway and enumerate all lighting devices. Queries gateway for system info and discovers all luminaires, sensors, and controllers across DALI lines. Generates equipment codes following v2.0 naming convention. This is a READ-ONLY discovery tool for commissioning engineers to review before bulk import. Use during building onboarding when Tridonic DALI-2 lighting is present.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building/site ID (e.g., 'site-002')"
                },
                "gateway_ip": {
                    "type": "string",
                    "description": "IP address of DALI gateway (e.g., '192.168.10.50')"
                },
                "gateway_type": {
                    "type": "string",
                    "enum": ["tridonic", "philips", "helvar", "generic"],
                    "description": "DALI gateway manufacturer/type",
                    "default": "tridonic"
                },
                "username": {
                    "type": "string",
                    "description": "Optional HTTP Basic Auth username for gateway API"
                },
                "password": {
                    "type": "string",
                    "description": "Optional HTTP Basic Auth password for gateway API"
                },
                "use_simulated": {
                    "type": "boolean",
                    "description": "Use simulated data if gateway unreachable (for testing)",
                    "default": False
                }
            },
            "required": ["building_id", "gateway_ip"]
        }
    },
    {
        "name": "get_asset_metrics_template",
        "description": "Get asset metric templates for AI/ML predictive maintenance during building onboarding. Returns metric templates based on equipment types present in the building. Engineers can review and configure thresholds, weights, and data sources (BMS sensor, mobile phone, manual) before activation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building/site ID to get metric templates for"
                },
                "equipment_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["generator", "chiller", "ahu", "fcu", "ups", "transformer", "vav", "cooling_tower"]
                    },
                    "description": "Optional list of equipment types to filter. If not provided, will auto-detect from building's devices and zones"
                }
            },
            "required": ["building_id"]
        }
    },
    {
        "name": "configure_asset_metrics",
        "description": "Configure asset metrics for AI/ML predictive maintenance after building onboarding. Engineers can customize thresholds (normal/warning/critical), health score weights, measurement intervals, and specify which metrics use mobile phone vs BMS sensors. Saves configuration to building's asset_metrics.json file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building/site ID to configure metrics for"
                },
                "metric_config": {
                    "type": "object",
                    "description": "Configuration dictionary with equipment_types as keys, containing 'metrics' and 'manual_inspections' with custom thresholds, weights, and intervals",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "metrics": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "properties": {
                                        "enabled": {"type": "boolean", "description": "Enable this metric"},
                                        "normal_range": {"type": "array", "items": {"type": "number"}, "description": "[min, max] normal range"},
                                        "warning_range": {"type": "array", "items": {"type": "number"}, "description": "[min, max] warning range"},
                                        "critical_range": {"type": "array", "items": {"type": "number"}, "description": "[min, max] critical range"},
                                        "weight": {"type": "number", "description": "Health score weight (0-1)"},
                                        "measurement_interval_days": {"type": "integer", "description": "Days between measurements"},
                                        "custom_threshold": {"type": "string", "description": "Custom threshold override"}
                                    }
                                }
                            },
                            "manual_inspections": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "properties": {
                                        "enabled": {"type": "boolean"},
                                        "frequency_days": {"type": "integer"},
                                        "assigned_to": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                },
                "save_to_file": {
                    "type": "boolean",
                    "description": "Save configuration to building's asset_metrics.json file (default: true)"
                }
            },
            "required": ["building_id", "metric_config"]
        }
    },
    # Solar MCP Tools (34-09)
    {
        "name": "get_solar_overview",
        "description": "Get solar site overview including current generation (kW), daily yield (kWh), BESS State of Charge, grid import/export, performance ratio, and estimated savings today. Use this when someone asks about solar generation, how much power the panels are producing, or the solar dashboard.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Solar site ID (default: site-002)",
                    "default": "site-002"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_bess_status",
        "description": "Get BESS (Battery Energy Storage System) status including State of Charge (SOC), current mode (charging/discharging/idle), health, power flow, cycle count, and dispatch schedule. Use this when someone asks about the battery level, battery status, BESS, or energy storage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Solar site ID (default: site-002)",
                    "default": "site-002"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_solar_savings",
        "description": "Get financial savings summary from solar and BESS optimisation. Returns monthly breakdown of arbitrage savings, demand charge savings, self-consumption value, diesel avoidance, total savings, ROI, and carbon offset. Use this when someone asks how much money solar has saved, financial performance, or ROI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Solar site ID (default: site-002)",
                    "default": "site-002"
                },
                "period": {
                    "type": "string",
                    "description": "Period: ytd (year-to-date, default) or month",
                    "default": "ytd",
                    "enum": ["ytd", "month"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_solar_forecast",
        "description": "Get solar generation forecast for the next 24 hours with confidence bands. Returns hourly predicted generation in kW using an ensemble model (persistence + clear-sky + historical + ML). Use this when someone asks about tomorrow's generation forecast, expected solar output, or generation predictions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Solar site ID (default: site-002)",
                    "default": "site-002"
                },
                "hours": {
                    "type": "integer",
                    "description": "Forecast horizon in hours (default: 24, max: 72)",
                    "default": 24
                }
            },
            "required": []
        }
    },
    {
        "name": "get_solar_diagnostics",
        "description": "Get solar diagnostics with top issues, underperforming equipment, and maintenance recommendations. Returns prioritised issues with severity, cost impact, probable cause, recommended action, and upcoming maintenance needs. Use this when someone asks which inverters are underperforming, solar problems, or maintenance needs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Solar site ID (default: site-002)",
                    "default": "site-002"
                }
            },
            "required": []
        }
    },
    # Contract Management tools (Phase 48-02)
    {
        "name": "get_contracts",
        "description": "Get contracts for managed buildings. Returns contract details including organization, type, fees, and dates. Optionally includes SLA terms. Use this when someone asks about contracts, SLAs, client agreements, or 'what is our SLA for building X'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Filter by building/site ID (e.g., site-002)"
                },
                "organization_code": {
                    "type": "string",
                    "description": "Filter by organization code (e.g., ORG-SITE-002)"
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "expired", "draft"],
                    "description": "Filter by contract status"
                },
                "include_sla": {
                    "type": "boolean",
                    "description": "Include SLA terms in response (default: false)",
                    "default": False
                }
            },
            "required": []
        }
    },
    {
        "name": "add_building_contract",
        "description": "Create a detailed contract for a building. Writes contract data and updates building configuration with contract fields. Use this during building onboarding to set up commercial agreements.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_code": {
                    "type": "string",
                    "description": "Building/site ID (e.g., site-002)"
                },
                "organization_name": {
                    "type": "string",
                    "description": "Client organization name (e.g., SITE-002 Commercial Property)"
                },
                "organization_code": {
                    "type": "string",
                    "description": "Organization code (e.g., ORG-SITE-002)"
                },
                "contract_type": {
                    "type": "string",
                    "enum": ["full_maintenance", "preventive_only", "ad_hoc", "consulting"],
                    "description": "Type of maintenance contract"
                },
                "monthly_fee_zar": {
                    "type": "number",
                    "description": "Monthly contract fee in ZAR"
                },
                "start_date": {
                    "type": "string",
                    "description": "Contract start date (YYYY-MM-DD)"
                },
                "end_date": {
                    "type": "string",
                    "description": "Contract end date (YYYY-MM-DD)"
                },
                "sla_terms": {
                    "type": "array",
                    "description": "Optional SLA terms array with metric_type, target_value, penalty details",
                    "items": {"type": "object"}
                },
                "budget": {
                    "type": "object",
                    "description": "Optional budget breakdown (monthly_total_zar, breakdown, equipment_type_budgets)"
                },
                "condition_assessment": {
                    "type": "object",
                    "description": "Optional condition assessment (overall_score, mechanical/electrical/structural scores)"
                }
            },
            "required": ["building_code", "organization_name", "organization_code", "contract_type", "monthly_fee_zar", "start_date", "end_date"]
        }
    },
    {
        "name": "get_contract_profitability",
        "description": "Get contract profitability snapshot for one or all buildings. Returns revenue, costs, margins, and at-risk flags. Use this when someone asks about contract profitability, margins, financial performance, or 'how profitable is building X'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_code": {
                    "type": "string",
                    "description": "Filter by building/site ID (all buildings if not specified)"
                },
                "year": {
                    "type": "integer",
                    "description": "Filter by year (default: current year)"
                },
                "month": {
                    "type": "integer",
                    "description": "Filter by month (optional)"
                }
            },
            "required": []
        }
    },
    # Municipal Billing tools (Phase 49)
    {
        "name": "process_municipal_bill",
        "description": "Process South African municipal utility bill PDF (Johannesburg, Cape Town, Ekurhuleni, eThekwini) for building cost tracking. Extracts invoice data, consumption, and amounts from PDF using PyMuPDF/pdfplumber with OCR fallback. Use this during building onboarding to establish cost baselines or monthly to track utility costs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building/site ID (e.g., site-002)"
                },
                "pdf_file_path": {
                    "type": "string",
                    "description": "Absolute path to PDF file"
                },
                "municipality": {
                    "type": "string",
                    "description": "Municipality name (e.g., city_of_johannesburg, city_of_cape_town, ekurhuleni, ethekwini)"
                },
                "utility_type": {
                    "type": "string",
                    "enum": ["electricity", "water"],
                    "description": "Utility type"
                },
                "account_number": {
                    "type": "string",
                    "description": "Municipal account number"
                },
                "tariff_type": {
                    "type": "string",
                    "description": "Optional tariff type (residential/commercial/industrial)",
                    "enum": ["residential", "commercial", "industrial"]
                }
            },
            "required": ["building_id", "pdf_file_path", "municipality", "utility_type", "account_number"]
        }
    },
    {
        "name": "get_utility_costs",
        "description": "Get utility cost analysis for a building from processed municipal bills. Returns electricity and water costs with totals and averages for specified period. Use this when someone asks about utility costs, municipal bills, electricity/water expenses, or 'what are our utility costs for building X'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "Building/site ID (e.g., site-002)"
                },
                "period_start": {
                    "type": "string",
                    "description": "Period start ISO date (default: current month start)"
                },
                "period_end": {
                    "type": "string",
                    "description": "Period end ISO date (default: current month end)"
                }
            },
            "required": ["building_id"]
        }
    }
]


# ============================================================================
# MCP Server Class
# ============================================================================

class SIMBIOTMCPServer:
    """
    SIMBIOT MCP Server for building data and device control.

    Provides a unified interface for AI chat to query building information,
    assets, and control BMS devices through standardized MCP tools.

    Usage:
        server = SIMBIOTMCPServer()
        tools = server.list_tools()  # Get available tools
        result = await server.call_tool("get_buildings")
        result = await server.call_tool("read_device_point", device_id="S001-CHILLER-B1-001", point_name="chw_supply_temp")
    """

    def __init__(self):
        """Initialize SIMBIOT MCP server."""
        # Import registry tools (code search, code fetch, code_structure)
        from app.mcp.tools.registry import get_all_tools, get_all_handlers
        
        # Merge MCP_TOOLS with registry tools
        self.tools = MCP_TOOLS + get_all_tools()
        self.tool_handlers = {
            # Building/Asset tools (Plan 01)
            "get_buildings": get_buildings_tool,
            "get_assets": get_assets_tool,
            "get_asset_detail": get_asset_detail_tool,
            "get_devices": get_devices_tool,
            "read_device_point": read_device_point_tool,
            "write_device_point": write_device_point_tool,
            # Alarm tools (Plan 02)
            "get_alarms": get_alarms_tool,
            "search_alarms": search_alarms_tool,
            # Trend/Analytics tools (Plan 02)
            "get_trends": get_trends_tool,
            "get_health_score": get_health_score_tool,
            # Work order tools (Plan 02)
            "get_work_orders": get_work_orders_tool,
            "create_work_order": create_work_order_tool,
            # Building management tools (onboarding)
            "list_managed_buildings": list_managed_buildings_tool,
            "create_building": create_building_tool,
            "activate_building": activate_building_tool,
            "get_building_config": get_building_config_tool,
            # AI-Assisted Onboarding tools
            "add_building_zones": add_building_zones_tool,
            "add_building_desks": add_building_desks_tool,
            "add_building_devices": add_building_devices_tool,
            "import_point_list": import_point_list_tool,
            "import_controller_list": import_controller_list_tool,
            "discover_tridonic_gateway": discover_tridonic_gateway_tool,
            # AI/ML Predictive Maintenance tools (asset metric configuration)
            "get_asset_metrics_template": get_asset_metrics_template_tool,
            "configure_asset_metrics": configure_asset_metrics_tool,
            # Solar tools (34-09)
            "get_solar_overview": get_solar_overview_tool,
            "get_bess_status": get_bess_status_tool,
            "get_solar_savings": get_solar_savings_tool,
            "get_solar_forecast": get_solar_forecast_tool,
            "get_solar_diagnostics": get_solar_diagnostics_tool,
            # Contract Management tools (Phase 48-02)
            "get_contracts": get_contracts_tool,
            "add_building_contract": add_building_contract_tool,
            "get_contract_profitability": get_contract_profitability_tool,
            # Municipal Billing tools (Phase 49)
            "process_municipal_bill": process_municipal_bill_tool,
            "get_utility_costs": get_utility_costs_tool,
        }
        
        # Merge registry tools (code search, fetch, structure)
        from app.mcp.tools.registry import get_all_handlers
        self.tool_handlers.update(get_all_handlers())
        logger.info("SIMBIOTMCPServer initialized with %d tools", len(self.tools))

    def list_tools(self) -> List[Dict[str, Any]]:
        """List available MCP tools with their schemas."""
        return self.tools

    async def call_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Call an MCP tool by name.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found
        """
        handler = self.tool_handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}. Available: {list(self.tool_handlers.keys())}")

        return await handler(**kwargs)

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get JSON schema for a specific tool."""
        for tool in self.tools:
            if tool["name"] == tool_name:
                return tool
        return None
