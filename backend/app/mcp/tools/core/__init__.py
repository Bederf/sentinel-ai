"""
Core MCP Tools - Buildings, Assets, Devices, Alarms, Trends

9 tools for fundamental building data access and device queries:
1. get_buildings - List all buildings/sites
2. get_assets - List equipment in a building
3. get_asset_detail - Get detailed equipment info
4. get_devices - List BMS devices
5. read_device_point - Query device data point value
6. write_device_point - Write control command to device
7. get_alarms - List current alarms
8. search_alarms - Search alarm history
9. get_trends - Get historical trend data

Module structure (after extraction):
- tools.py: Tool definitions and handler functions
- __init__.py: Package initialization, exports

Eventually:
- get_core_tools() -> List[Dict] of tool metadata
- get_core_handlers() -> Dict of tool_name -> handler
"""
