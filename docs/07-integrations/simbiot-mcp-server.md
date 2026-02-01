---
status: implemented
version: 24
date: 2026-01-30
---

# SIMBIOT MCP Server - Building Management Protocol

## Overview

SIMBIOT MCP Server provides 23 tools for building management, exposing BMS data and device operations as standardized MCP (Model Context Protocol) tools for Claude Desktop, cloud Claude, and SENTINEL AI integration.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Claude Desktop / Cloud                      │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  stdio Transport         │    │  SSE Transport           │
│  (Claude Desktop)        │    │  (Cloud/Web)             │
│  simbiot_stdio.py        │    │  /api/mcp/sse            │
└──────────────────────────┘    └──────────────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  SIMBIOT MCP Server (simbiot_server.py)                        │
│  - 23 tools across 5 categories                                │
│  - Dual data source (device_manager + JSON fallback)           │
│  - Safety validation on writes                                 │
│  - Audit logging integration                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Device Manager  │ │  Supabase    │ │  JSON Files      │
│  (BACnet/Modbus) │ │  Database    │ │  (Fallback)      │
└──────────────────┘ └──────────────┘ └──────────────────┘
```

## MCP Tools

### Core BMS Tools (12)

| Tool | Description | Input |
|------|-------------|-------|
| `get_buildings` | List buildings with health scores | status_filter, region |
| `get_assets` | List assets for a building | building_id, asset_type, criticality |
| `get_asset_detail` | Comprehensive asset details | asset_id, include |
| `get_devices` | BMS device discovery | site_id, device_type |
| `read_device_point` | Read device point value | device_id, point_name |
| `write_device_point` | Write with safety validation | device_id, point_name, value, priority |
| `get_alarms` | Active alarms list | building_id, severity, limit |
| `search_alarms` | Natural language alarm search | query, time_range |
| `get_trends` | Historical trend data | asset_id, point_names, time_range |
| `get_health_score` | Asset/building health | target_id, target_type |
| `get_work_orders` | Work order list | building_id, status, assignee |
| `create_work_order` | Create work order | building_id, asset_id, description, priority |

### Building Onboarding Tools (9)

| Tool | Description | Dual-Write |
|------|-------------|------------|
| `list_managed_buildings` | Show all managed buildings | - |
| `create_building` | Create building config | ✓ Supabase + JSON |
| `activate_building` | Add to active registry | - |
| `get_building_config` | Get building details | - |
| `add_building_zones` | Add HVAC zones | ✓ Supabase + JSON |
| `add_building_desks` | Add desks with zone mapping | ✓ Supabase + JSON |
| `add_building_devices` | Add BMS devices | ✓ Supabase + JSON |
| `import_point_list` | Parse BACnet point CSV | AI-assisted |
| `import_controller_list` | Parse controller info | AI-assisted |

### AI/ML Tools (2)

| Tool | Description |
|------|-------------|
| `get_asset_metrics_template` | Get ML metrics template for equipment type |
| `configure_asset_metrics` | Configure metrics for specific asset |

## Integration Methods

### Method 1: Claude Desktop (stdio)

**Best for:** Local development, Claude Desktop app

**Setup:**

1. Edit Claude Desktop config:
   ```
   macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
   Windows: %APPDATA%/Claude/claude_desktop_config.json
   Linux: ~/.config/Claude/claude_desktop_config.json
   ```

2. Add SIMBIOT server:
   ```json
   {
     "mcpServers": {
       "simbiot": {
         "command": "python",
         "args": ["-m", "app.mcp.simbiot_stdio"],
         "cwd": "/opt/bms-intelligence/backend",
         "env": {
           "PYTHONPATH": "/opt/bms-intelligence/backend"
         }
       }
     }
   }
   ```

3. Restart Claude Desktop

**Usage:**
```
User: "Show me all buildings in Gauteng"
Claude: [Calls get_buildings with region="gauteng"]

User: "What's the current status of chiller 001-gwc-chiller-001?"
Claude: [Calls read_device_point with device_id and points]

User: "Create a work order for the faulty FCU on Level 10"
Claude: [Calls create_work_order with building_id, asset_id, description]
```

### Method 2: SSE Transport (Cloud/Web)

**Best for:** Web applications, cloud-based AI

**Endpoints:**

```bash
# SSE stream endpoint
GET http://localhost:9095/api/mcp/sse

# POST request endpoint
POST http://localhost:9095/api/mcp/sse/request
Content-Type: application/json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_buildings",
    "arguments": {}
  }
}
```

### Method 3: REST API Wrapper

**Best for:** Traditional web applications, testing

```bash
# Get server info
GET /api/mcp/simbiot/info

# List all tools
GET /api/mcp/simbiot/tools

# Get specific tool schema
GET /api/mcp/simbiot/tools/{tool_name}

# Call a tool
POST /api/mcp/simbiot/call
{
  "tool": "get_buildings",
  "arguments": {"region": "gauteng"}
}
```

## Tool Examples

### get_buildings

```python
# Request
await server.call_tool("get_buildings", {"region": "gauteng"})

# Response
{
  "buildings": [
    {
      "id": "sandton",
      "name": "Sandton Office Park",
      "region": "gauteng",
      "status": "active",
      "health_score": 87,
      "alarm_count": 2,
      "asset_count": 145
    }
  ],
  "total": 1
}
```

### read_device_point

```python
# Request
await server.call_tool("read_device_point", {
  "device_id": "001-gwc-chiller-001",
  "point_name": "chw_supply_temp"
})

# Response
{
  "device_id": "001-gwc-chiller-001",
  "point_name": "chw_supply_temp",
  "value": 7.2,
  "unit": "°C",
  "quality": "good",
  "timestamp": "2026-01-30T10:30:00Z"
}
```

### write_device_point

```python
# Request
await server.call_tool("write_device_point", {
  "device_id": "001-gwc-fcu-001",
  "point_name": "cooling_setpoint",
  "value": 22.0,
  "priority": 8
})

# Response
{
  "success": true,
  "device_id": "001-gwc-fcu-001",
  "point_name": "cooling_setpoint",
  "value": 22.0,
  "previous_value": 24.0,
  "audit_id": "audit-abc123",
  "safety_validation": {
    "passed": true,
    "rules_checked": ["temperature_range", "rate_of_change"]
  }
}
```

### create_building (Onboarding)

```python
# Request
await server.call_tool("create_building", {
  "building_id": "centurion-01",
  "name": "Centurion Office Tower",
  "address": "123 Main Road, Centurion",
  "region": "gauteng",
  "floors": 12,
  "area_sqm": 25000
})

# Response
{
  "success": true,
  "building_id": "centurion-01",
  "storage": "supabase+json",  # Dual-write indicator
  "files_created": [
    "backend/app/data/buildings/centurion-01/building.json"
  ],
  "next_steps": [
    "add_building_zones",
    "add_building_desks",
    "add_building_devices"
  ]
}
```

## Safety & Audit

### Write Safety Validation

All write operations pass through safety validation:

1. **Safety Rules Checked:**
   - Temperature range (16-28°C)
   - Pressure limits
   - Runtime limits
   - Interlock conditions

2. **Blocked if unsafe:**
   ```json
   {
     "success": false,
     "error": "Safety validation failed",
     "rule": "temperature_range",
     "message": "Value 35°C exceeds maximum 28°C",
     "severity": "BLOCK"
   }
   ```

3. **Safety-first design:**
   - `write_device_point` refuses to write when device_manager unavailable
   - All writes logged to audit trail
   - Audit ID returned in response

### Audit Integration

Every write operation creates an audit record:

```json
{
  "audit_id": "audit-abc123",
  "action": "write_device_point",
  "device_id": "001-gwc-fcu-001",
  "point_name": "cooling_setpoint",
  "old_value": 24.0,
  "new_value": 22.0,
  "user": "claude-mcp",
  "timestamp": "2026-01-30T10:30:00Z",
  "safety_validation": "passed"
}
```

## Dual Data Source

Tools automatically handle data source fallback:

```python
# 1. Try device_manager first (real devices)
if device_manager and device_manager.initialized:
    return await device_manager.read_point(device_id, point_name)

# 2. Fall back to JSON files (demo/offline)
else:
    return load_from_json(f"data/buildings/{building_id}/devices.json")
```

**Response indicates source:**
```json
{
  "data": [...],
  "source": "device_manager"  // or "json_fallback"
}
```

## Files Reference

### Core Server

| File | Lines | Description |
|------|-------|-------------|
| `simbiot_server.py` | 1800+ | Main MCP server, all tools |
| `simbiot_stdio.py` | 50 | stdio transport wrapper |
| `simbiot_sse.py` | 200 | SSE transport |

### API Wrapper

| File | Description |
|------|-------------|
| `api/mcp.py` | REST API wrapper for MCP tools |
| `api/mcp_sse.py` | SSE endpoint for web clients |

### Documentation

| File | Description |
|------|-------------|
| `backend/README_MCP_INTEGRATION.md` | Setup guide |
| `docs/03-api-reference/mcp-tools-reference.md` | Tool schemas |

## Python Usage

```python
from app.mcp.simbiot_server import SIMBIOTMCPServer

# Initialize
server = SIMBIOTMCPServer()

# List available tools
tools = server.list_tools()
for tool in tools:
    print(f"{tool['name']}: {tool['description']}")

# Call a tool
result = await server.call_tool("get_buildings", {"region": "gauteng"})
print(result)

# With safety validation
result = await server.call_tool("write_device_point", {
    "device_id": "fcu-001",
    "point_name": "setpoint",
    "value": 22.0
})
if result.get("safety_validation", {}).get("passed"):
    print("Write successful")
```

## Status

✅ **IMPLEMENTED** - Phase 24 complete

- 24-01: Core MCP server (6 tools) ✓
- 24-02: Alarm, trend, work order tools (+6) ✓
- 24-03: REST API wrapper ✓
- 24-04: Building onboarding tools (+9) ✓

Total: 23 MCP tools available
