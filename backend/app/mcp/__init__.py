"""
MCP (Model Context Protocol) Servers for SENTINEL AI integration.

Available servers:
- EquipmentMCPServer: Fault code lookup, parts search, equipment issues
- SIMBIOTMCPServer: Building data, assets, device control (BACnet/Modbus abstraction)
"""

from app.mcp.equipment_server import (
    EquipmentMCPServer,
    lookup_fault_code_tool,
    lookup_parts_tool,
    search_equipment_issue_tool,
    MCP_TOOLS as EQUIPMENT_MCP_TOOLS
)

from app.mcp.simbiot_server import (
    SIMBIOTMCPServer,
    get_buildings_tool,
    get_assets_tool,
    get_asset_detail_tool,
    get_devices_tool,
    read_device_point_tool,
    write_device_point_tool,
    MCP_TOOLS as SIMBIOT_MCP_TOOLS
)

__all__ = [
    # Equipment MCP
    "EquipmentMCPServer",
    "lookup_fault_code_tool",
    "lookup_parts_tool",
    "search_equipment_issue_tool",
    "EQUIPMENT_MCP_TOOLS",
    # SIMBIOT MCP
    "SIMBIOTMCPServer",
    "get_buildings_tool",
    "get_assets_tool",
    "get_asset_detail_tool",
    "get_devices_tool",
    "read_device_point_tool",
    "write_device_point_tool",
    "SIMBIOT_MCP_TOOLS"
]
