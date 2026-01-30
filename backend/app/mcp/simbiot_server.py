"""
SIMBIOT MCP Server for Building Data and Device Control

Provides tools for AI chat integration with building data, asset management,
and BMS device control through a standardized MCP interface.

Usage:
    from app.mcp import SIMBIOTMCPServer

    server = SIMBIOTMCPServer()
    result = await server.call_tool("get_buildings")
    result = await server.call_tool("read_device_point", device_id="001-gwc-chiller-001", point_name="chw_supply_temp")
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
                    "description": "Asset/device ID (e.g., 001-gwc-chiller-001)"
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
                    "description": "Device ID (e.g., 001-gwc-chiller-001)"
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
                    "description": "Device ID (e.g., 001-gwc-chiller-001)"
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
                    "description": "Asset/device ID (e.g., 001-gwc-chiller-001)"
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
        result = await server.call_tool("read_device_point", device_id="001-gwc-chiller-001", point_name="chw_supply_temp")
    """

    def __init__(self):
        """Initialize SIMBIOT MCP server."""
        self.tools = MCP_TOOLS
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
        }
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
