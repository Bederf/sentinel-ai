"""
MCP (Model Context Protocol) Servers for SENTINEL AI integration.

Available servers:
- EquipmentMCPServer: Fault code lookup, parts search, equipment issues
- SIMBIOTMCPServer: Building data, assets, device control (BACnet/Modbus abstraction)
"""

from app.mcp.equipment_server import (
    MCP_TOOLS as EQUIPMENT_MCP_TOOLS,
)
from app.mcp.equipment_server import (
    EquipmentMCPServer,
    lookup_fault_code_tool,
    lookup_parts_tool,
    search_equipment_issue_tool,
)
from app.mcp.openai_connector_server import OpenAIConnectorMCPServer, get_openai_connector_server
from app.mcp.simbiot_server import (
    MCP_TOOLS as SIMBIOT_MCP_TOOLS,
)
from app.mcp.simbiot_server import (
    SIMBIOTMCPServer,
    create_work_order_tool,
    # Alarm tools
    get_alarms_tool,
    get_asset_detail_tool,
    get_assets_tool,
    get_devices_tool,
    get_health_score_tool,
    # Building/Asset tools
    get_sites_tool,
    # Trend/Analytics tools
    get_trends_tool,
    # Work order tools
    get_work_orders_tool,
    read_device_point_tool,
    search_alarms_tool,
    write_device_point_tool,
)
from app.mcp.simbiot_stdio import MCPServerStdio
from app.mcp.simbiot_stdio import main as simbiot_stdio_main

__all__ = [
    "EQUIPMENT_MCP_TOOLS",
    "SIMBIOT_MCP_TOOLS",
    # Equipment MCP
    "EquipmentMCPServer",
    # SIMBIOT stdio transport
    "MCPServerStdio",
    # OpenAI ChatGPT Connector
    "OpenAIConnectorMCPServer",
    # SIMBIOT MCP
    "SIMBIOTMCPServer",
    "create_work_order_tool",
    # Alarm tools
    "get_alarms_tool",
    "get_asset_detail_tool",
    "get_assets_tool",
    "get_devices_tool",
    "get_health_score_tool",
    "get_openai_connector_server",
    # Building/Asset tools
    "get_sites_tool",
    # Trend/Analytics tools
    "get_trends_tool",
    # Work order tools
    "get_work_orders_tool",
    "lookup_fault_code_tool",
    "lookup_parts_tool",
    "read_device_point_tool",
    "search_alarms_tool",
    "search_equipment_issue_tool",
    "simbiot_stdio_main",
    "write_device_point_tool",
]
