"""
Operations & Maintenance MCP Tools

3 tools for work order and health monitoring:
1. get_health_score - Get equipment health analytics
2. get_work_orders - List open work orders
3. create_work_order - Create new maintenance work order

Module structure (after extraction):
- tools.py: Tool definitions and handler functions
- __init__.py: Package initialization, exports

Eventually:
- get_operations_tools() -> List[Dict] of tool metadata
- get_operations_handlers() -> Dict of tool_name -> handler
"""
