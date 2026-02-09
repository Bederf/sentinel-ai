"""
Solar PV & BESS MCP Tools

5 tools for solar energy operations and optimization:
1. get_solar_overview - Solar PV and BESS status overview
2. get_bess_status - Battery energy storage system status
3. get_solar_savings - Financial savings from solar generation
4. get_solar_forecast - 24-hour generation forecast
5. get_solar_diagnostics - Solar system health diagnostics

Module structure (after extraction):
- tools.py: Tool definitions and handler functions
- __init__.py: Package initialization, exports

Eventually:
- get_solar_tools() -> List[Dict] of tool metadata
- get_solar_handlers() -> Dict of tool_name -> handler
"""
