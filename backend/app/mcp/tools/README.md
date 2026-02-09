# MCP Tools Modular Architecture

This directory contains the modularized MCP (Model Context Protocol) tools for the SIMBIOT building management platform.

## Overview

The original `simbiot_server.py` (4450 lines) contained 33 tool definitions in a single file. This refactoring splits tools into 6 domain-specific packages for better maintainability, testability, and organization.

## Directory Structure

```
tools/
├── README.md                    # This file
├── registry.py                  # Central tool registry (planned)
├── __init__.py                  # Package initialization
│
├── core/                        # Buildings, assets, devices, alarms (9 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Extract tool definitions
│
├── operations/                  # Work orders, health monitoring (3 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Extract tool definitions
│
├── commercial/                  # Contracts, profitability, billing (5 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Extract tool definitions
│
├── onboarding/                  # Building/zone/device creation (8 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Extract tool definitions
│
├── ai/                          # Health scores, asset metrics (2 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Extract tool definitions
│
└── solar/                       # Solar PV and BESS (5 tools)
    ├── __init__.py
    └── tools.py                 # [TODO] Extract tool definitions
```

## Tool Inventory

### Core Tools (9 tools)
Essential building data access:
- `get_buildings` - List all buildings/sites
- `get_assets` - List equipment in building
- `get_asset_detail` - Equipment details and metadata
- `get_devices` - List BMS devices
- `read_device_point` - Query device data point
- `write_device_point` - Send control command
- `get_alarms` - List current alarms
- `search_alarms` - Alarm history search
- `get_trends` - Historical trend data

**Domain:** Buildings, assets, devices, alarms
**Lines:** ~700 (estimated from simbiot_server.py)

### Operations Tools (3 tools)
Work orders and maintenance:
- `get_health_score` - Equipment health analytics
- `get_work_orders` - Open maintenance work orders
- `create_work_order` - Create new work order

**Domain:** Maintenance, health monitoring
**Lines:** ~400 (estimated)

### Commercial Tools (5 tools)
Contracts and financial tracking:
- `get_contracts` - FM service contracts
- `add_building_contract` - Register contract
- `get_contract_profitability` - Portfolio analysis
- `process_municipal_bill` - Utility billing
- `get_utility_costs` - Cost analytics

**Domain:** FM commercial intelligence
**Lines:** ~500 (estimated)

### Onboarding Tools (8 tools)
AI-assisted building configuration:
- `list_managed_buildings` - List buildings
- `create_building` - New building setup
- `activate_building` - Mark active
- `get_building_config` - Configuration retrieval
- `add_building_zones` - Zone registration
- `add_building_desks` - Desk location registry
- `add_building_devices` - Device registration
- `import_point_list` - Bulk point import
- `import_controller_list` - Controller discovery

**Domain:** Building onboarding
**Lines:** ~900 (estimated)

### AI Tools (2 tools)
ML and predictive maintenance:
- `get_asset_metrics_template` - Equipment-type templates
- `configure_asset_metrics` - Metric configuration

**Domain:** AI/ML predictive maintenance
**Lines:** ~200 (estimated)

### Solar Tools (5 tools)
Solar PV and BESS operations:
- `get_solar_overview` - PV and battery status
- `get_bess_status` - BESS state of charge
- `get_solar_savings` - Financial metrics
- `get_solar_forecast` - Generation forecast
- `get_solar_diagnostics` - System health

**Domain:** Renewable energy operations
**Lines:** ~200 (estimated)

**Total: 32 tools in 4450 lines = average 139 lines per tool**

## Migration Plan

### Phase 1: Structure Setup (COMPLETE ✓)
- [x] Create `tools/` directory structure
- [x] Create domain packages: core, operations, commercial, onboarding, ai, solar
- [x] Create `registry.py` with aggregation functions (stub)
- [x] Document tool inventory and mapping

### Phase 2: Tool Extraction (Planned)
1. Extract tool functions to domain modules:
   - Each `tools.py` file contains tool definitions and handlers
   - Export `get_tools()` and `get_handlers()` functions
   - Maintain original function signatures

2. Create tool pattern for each module:
   ```python
   # tools/core/tools.py
   from typing import Dict, List, Any

   async def get_buildings_tool(**kwargs) -> Dict[str, Any]:
       """Tool implementation - extracted from simbiot_server.py"""
       # Original code from line 101-173

   async def get_assets_tool(**kwargs) -> Dict[str, Any]:
       """Tool implementation"""
       # Original code from line 174-257

   # Tool metadata
   TOOLS = [
       {
           "name": "get_buildings",
           "description": "List all buildings/sites",
           "inputSchema": {...}
       },
       # ...
   ]

   def get_core_tools() -> List[Dict[str, Any]]:
       """Return core tool definitions."""
       return TOOLS

   def get_core_handlers() -> Dict[str, callable]:
       """Return core tool handlers."""
       return {
           "get_buildings": get_buildings_tool,
           "get_assets": get_assets_tool,
           # ...
       }
   ```

3. Update `registry.py` to import and aggregate from modules

4. Update `simbiot_server.py` to use registry:
   ```python
   from app.mcp.tools.registry import get_all_tools, get_all_handlers

   class SIMBIOTMCPServer:
       def __init__(self):
           self.tools = get_all_tools()  # From registry
           self.tool_handlers = get_all_handlers()  # From registry
   ```

### Phase 3: Verification & Testing
- Test tool discovery (list_tools())
- Test tool invocation (call_tool())
- Verify no functionality loss
- Update tests to use modular imports

### Phase 4: Cleanup
- Remove tool definitions from original `simbiot_server.py`
- Keep only SIMBIOTMCPServer class and initialization logic
- Archive original for reference if needed

## Design Principles

### Single Responsibility
Each package handles one domain (core tools, operations, etc.).
No cross-package tool dependencies.

### Consistency
All packages follow the same pattern:
1. `tools.py` - Tool definitions and handlers
2. `get_*.py` functions for tool metadata/handlers
3. Consistent naming: `{domain}_tools.py`

### Backward Compatibility
- SIMBIOTMCPServer API unchanged
- Tool names and signatures preserved
- No impact on Claude desktop integration

### Testability
- Tools can be tested independently
- Mock fixtures per domain package
- Clear import paths for test setup

## Testing

### Unit Tests by Domain
```bash
# Test core tools
pytest backend/tests/mcp/tools/test_core_tools.py

# Test onboarding workflow
pytest backend/tests/mcp/tools/test_onboarding_tools.py

# Test full registry
pytest backend/tests/mcp/test_tools_registry.py
```

### Integration Tests
```bash
# Test server with all tools
pytest backend/tests/mcp/test_simbiot_server.py
```

## Performance Notes

### Current
- Single 4450-line file
- 37 functions, 33 tools
- Monolithic structure

### After Refactoring
- 6 modules (estimated 400-900 lines each)
- Tools per module: 2-9
- Better IDE performance (smaller files)
- Faster import times (lazy loading possible)

## Future Enhancements

1. **Lazy Loading:** Load domain packages only when needed
2. **Tool Filtering:** Access control based on user role
3. **Versioning:** Support tool API versioning
4. **Monitoring:** Per-domain tool usage metrics
5. **Documentation:** Auto-generate docs from tool schemas

## References

- [SIMBIOT MCP Server](../simbiot_server.py)
- [MCP Specification](https://modelcontextprotocol.io)
- [Tool Registry Pattern](../tools/registry.py)

## Questions?

See [original simbiot_server.py](../simbiot_server.py) for tool implementation details during Phase 2 extraction.
