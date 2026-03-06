"""
Onboarding & Configuration MCP Tools

8 tools for AI-assisted building setup and discovery:
1. list_managed_buildings - List buildings in system
2. create_building - Create new building
3. activate_building - Mark building as active
4. get_site_config - Get building configuration
5. add_site_zones - Add thermal/security zones
6. add_building_desks - Register desk locations
7. add_site_devices - Register BMS devices
8. import_point_list - Import device points from file
9. import_controller_list - Import BACnet/Modbus controllers

Module structure (after extraction):
- tools.py: Tool definitions and handler functions
- __init__.py: Package initialization, exports

Eventually:
- get_onboarding_tools() -> List[Dict] of tool metadata
- get_onboarding_handlers() -> Dict of tool_name -> handler
"""
