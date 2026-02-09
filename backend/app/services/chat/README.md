# Chat Tool Modules

Modularized chat tool handlers for Claude AI integration with the BMS Intelligence platform.

## Overview

The original `chat_tools.py` (2474 lines) contained 22 tool handlers in a single file. This refactoring splits tools into 6 domain-specific modules for better code organization, testability, and maintenance.

## Directory Structure

```
chat/
├── README.md                    # This file
├── registry.py                  # Central tool registry (planned)
├── __init__.py                  # Package initialization
│
├── device/                      # Device control and queries (3 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Device tool handlers
│
├── system/                      # System status and diagnostics (2 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] System tool handlers
│
├── analysis/                    # Equipment analysis and optimization (6 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Analysis tool handlers
│
├── niagara/                     # Point management and discovery (4 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Niagara tool handlers
│
├── solar/                       # Solar PV and BESS (5 tools)
│   ├── __init__.py
│   └── tools.py                 # [TODO] Solar tool handlers
│
└── security/                    # Security and fire systems (2 tools)
    ├── __init__.py
    └── tools.py                 # [TODO] Security tool handlers
```

## Tool Inventory

### Device Tools (3 tools)
Device control and data queries:
- `list_devices` - List devices with optional filtering
- `get_device_details` - Device metadata, status, points
- `control_device` - Send control command with safety validation

**Domain:** Device access and control
**Original lines:** ~127 (40-167)

### System Tools (2 tools)
Overall system status:
- `get_system_status` - System health, alerts, recommendations
- `get_system_methodology` - How the system works

**Domain:** System diagnostics
**Original lines:** ~50 (estimated)

### Analysis Tools (6 tools)
Equipment analysis, health, and optimization:
- `get_equipment_health` - Health scores by device/system
- `get_optimization_recommendations` - AI recommendations
- `get_alerts_and_anomalies` - Active alerts and anomalies
- `get_energy_analysis` - Energy metrics and analysis
- `lookup_desk` - Find desks by ID or location
- `diagnose_comfort_complaint` - Thermal comfort troubleshooting

**Domain:** Equipment intelligence
**Original lines:** ~1100 (estimated)

### Niagara Tools (4 tools)
BMS point discovery and mapping:
- `discover_niagara_points` - Discover available points
- `review_point_mapping` - Review point classifications
- `approve_point_mapping` - Approve classifications
- `correct_point_classification` - Fix misclassifications

**Domain:** BMS integration and point management
**Original lines:** ~400 (estimated)

### Solar Tools (5 tools)
Solar PV and BESS operations:
- `get_solar_overview` - PV and battery status
- `get_bess_status` - Battery state of charge
- `get_solar_savings` - Financial savings
- `get_solar_forecast` - 24-hour forecast
- `get_solar_diagnostics` - System health

**Domain:** Renewable energy
**Original lines:** ~200 (estimated)

### Security Tools (2 tools)
Access control and fire safety:
- `get_security_status` - Access control status
- `get_fire_system_status` - Fire system status

**Domain:** Safety and security
**Original lines:** ~50 (estimated)

**Total: 22 tools in 2474 lines = average 112 lines per tool**

## Usage

### Current (Original chat_tools.py)
```python
from app.services.chat_tools import execute_tool

result = await execute_tool("list_devices", {"device_type": "hvac"})
```

### During Migration (Using Registry)
```python
from app.services.chat.registry import execute_tool

result = await execute_tool("list_devices", {"device_type": "hvac"})
```

### Direct Module Access (Future)
```python
from app.services.chat.device import TOOL_HANDLERS
from app.services.chat.device.tools import list_devices

result = await list_devices(device_type="hvac")
```

## Migration Plan

### Phase 1: Structure Setup (COMPLETE ✓)
- [x] Create `chat/` directory structure
- [x] Create domain packages: device, system, analysis, niagara, solar, security
- [x] Create `registry.py` with execution interface (stub)
- [x] Document tool inventory and mapping

### Phase 2: Tool Extraction (Planned)
1. Extract tool handlers to domain modules:
   ```python
   # chat/device/tools.py
   async def list_devices(device_type: str | None = None, ...) -> dict[str, Any]:
       """List available devices with optional filtering."""
       # Extract from original chat_tools.py lines 40-70

   async def get_device_details(...) -> dict[str, Any]:
       """Get device metadata and status."""
       # Extract from original chat_tools.py

   async def control_device(...) -> dict[str, Any]:
       """Send control command to device."""
       # Extract from original chat_tools.py

   TOOL_HANDLERS = {
       "list_devices": list_devices,
       "get_device_details": get_device_details,
       "control_device": control_device,
   }
   ```

2. Update domain `__init__.py` to export handlers:
   ```python
   # chat/device/__init__.py
   from .tools import TOOL_HANDLERS
   __all__ = ['TOOL_HANDLERS']
   ```

3. Populate `registry.py` to aggregate handlers:
   ```python
   from app.services.chat.device import TOOL_HANDLERS as DEVICE_HANDLERS
   from app.services.chat.system import TOOL_HANDLERS as SYSTEM_HANDLERS
   # ... etc

   def get_all_handlers() -> Dict[str, Callable]:
       return {
           **DEVICE_HANDLERS,
           **SYSTEM_HANDLERS,
           # ...
       }
   ```

### Phase 3: Verification (Planned)
- Integration tests for all tools
- Verify Claude can still call all tools
- Performance benchmarks
- Error handling validation

### Phase 4: Cleanup (Planned)
- Remove tool handlers from original chat_tools.py
- Keep only utility functions and imports
- Update imports in chat service
- Archive original for reference

## Tool Handler Pattern

Each domain module follows this pattern:

```python
# chat/{domain}/tools.py
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)

async def tool_handler_name(param1: str, param2: int | None = None) -> Dict[str, Any]:
    """
    Tool docstring for Claude.

    Args:
        param1: Description
        param2: Optional parameter

    Returns:
        Result dict with 'error' or data keys
    """
    try:
        # Implementation (extracted from original chat_tools.py)
        return {"data": result}
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"error": str(e)}

# Tool handlers dict
TOOL_HANDLERS = {
    "tool_name": tool_handler_name,
    # ...
}
```

## Testing

### Unit Tests by Domain
```bash
# Test device tools
pytest backend/tests/services/chat/test_device_tools.py

# Test analysis tools
pytest backend/tests/services/chat/test_analysis_tools.py
```

### Integration Tests
```bash
# Test full chat tool execution
pytest backend/tests/services/chat/test_chat_registry.py

# Test with Claude integration
pytest backend/tests/integration/test_chat_with_tools.py
```

## Dependencies

Each domain module depends on:
- `device_abstraction.py` - Device access
- `health_threshold_service.py` - Health calculations
- `supabase_client.py` - Data access
- Building loader and data files

These dependencies are imported as needed by each module.

## Performance

### Current
- Single 2474-line file
- 22 tool handlers + utility functions
- Monolithic structure
- Slow IDE response for large file

### After Refactoring
- 6 modules (estimated 200-400 lines each)
- Tools per module: 2-6
- Better IDE performance
- Easier to locate and modify tools
- Potential for lazy loading

## Future Enhancements

1. **Type Stubs:** Generate type hints for tool parameters
2. **Tool Discovery:** Auto-generate Claude tool schema from handlers
3. **Caching:** Cache frequent queries (equipment health, system status)
4. **Validation:** Validate parameters before handler execution
5. **Monitoring:** Track tool usage and performance per domain
6. **Versioning:** Support tool API versioning

## References

- [Original chat_tools.py](../chat_tools.py)
- [Chat Service](../hybrid_ai_service.py)
- [Device Abstraction](../device_abstraction.py)

## Questions?

See original chat_tools.py for implementation details during Phase 2 extraction.
