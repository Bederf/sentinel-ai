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
from pathlib import Path
from datetime import datetime

from app.services.device_abstraction import device_manager
from app.models.device import DeviceStatus

logger = logging.getLogger(__name__)

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
SITES_FILE = DATA_DIR / "sites.json"
DEVICES_FILE = DATA_DIR / "mock_devices.json"


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
            "get_buildings": get_buildings_tool,
            "get_assets": get_assets_tool,
            "get_asset_detail": get_asset_detail_tool,
            "get_devices": get_devices_tool,
            "read_device_point": read_device_point_tool,
            "write_device_point": write_device_point_tool
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
