# SIMBIOT MCP Server Integration Guide

This guide explains how to integrate SIMBIOT MCP tools with Claude Desktop and cloud Claude.

## Overview

SIMBIOT MCP Server provides 23 tools for building management:

**Core BMS Tools:**
- `get_buildings`, `get_assets`, `get_asset_detail`
- `get_devices`, `read_device_point`, `write_device_point`
- `get_alarms`, `search_alarms`
- `get_trends`, `get_health_score`
- `get_work_orders`, `create_work_order`

**Building Onboarding Tools (dual-write: Supabase + JSON):**
- `list_managed_buildings`, `create_building`, `activate_building`, `get_building_config`
- `add_building_zones`, `add_building_desks`, `add_building_devices`
- `import_point_list`, `import_controller_list` (AI-assisted from BMS exports)

**AI/ML Predictive Maintenance:**
- `get_asset_metrics_template`, `configure_asset_metrics`

## Integration Methods

### Method 1: Local stdio (Claude Desktop)

**Best for:** Local development, Claude Desktop app

**Setup:**

1. Edit Claude Desktop config:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%/Claude/claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. Add SIMBIOT server:
   ```json
   {
     "mcpServers": {
       "simbiot": {
         "command": "python",
         "args": [
           "-m",
           "app.mcp.simbiot_stdio"
         ],
         "cwd": "/path/to/bms-intelligence/backend",
         "env": {
           "PYTHONPATH": "/path/to/bms-intelligence/backend"
         }
       }
     }
   }
   ```

3. Restart Claude Desktop

4. Verify tools are available in Claude

**Usage:**
In Claude Desktop, ask:
- "Show me all buildings in Gauteng"
- "What's the current status of chiller 001-gwc-chiller-001?"
- "List all active alarms"

### Method 2: Remote SSE (Cloud Claude)

**Best for:** Web applications, cloud-based AI

**Setup:**

1. Start backend server:
   ```bash
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 9095
   ```

2. Connect via SSE:
   ```
   GET http://localhost:9095/api/mcp/sse
   ```

3. Or use POST endpoint:
   ```bash
   curl -X POST http://localhost:9095/api/mcp/sse/request \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "id": 1,
       "method": "tools/call",
       "params": {
         "name": "get_buildings",
         "arguments": {}
       }
     }'
   ```

**Usage in Python:**
```python
import asyncio
from anthropic import Anthropic

client = Anthropic()

async def ask_claude_with_simbiot():
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        tools=[],  # Claude auto-discovers SIMBIOT tools via MCP
        messages=[
            {
                "role": "user",
                "content": "Show me all buildings with critical alarms"
            }
        ]
    )
    return response
```

### Method 3: REST API (Existing)

**Best for:** Traditional web applications, mobile apps

**Documentation:** See http://localhost:9095/docs

**Endpoints:**
- `GET /api/mcp/simbiot/info` - Server info
- `GET /api/mcp/simbiot/tools` - List tools
- `POST /api/mcp/simbiot/call` - Execute tool

## MCP Protocol Reference

### Initialize
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "clientInfo": {
      "name": "claude-desktop",
      "version": "1.0.0"
    }
  }
}
```

### List Tools
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list"
}
```

### Call Tool
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_buildings",
    "arguments": {
      "region": "Gauteng",
      "status_filter": "critical"
    }
  }
}
```

## Testing

### Test stdio server:
```bash
cd backend
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m app.mcp.simbiot_stdio
```

### Test SSE server:
```bash
curl -N http://localhost:9095/api/mcp/sse
```

### Test REST API:
```bash
python test_mcp_api.py
```

## Troubleshooting

**Claude Desktop can't connect:**
- Verify PYTHONPATH includes backend directory
- Check Python executable path
- Enable debug logging in Claude Desktop

**SSE connection drops:**
- Check firewall settings
- Verify backend is running
- Check browser console for errors

**Tools not available:**
- Restart Claude/backend
- Check SIMBIOTMCPServer has 23 tools (run `tools/list` to verify)
- Verify MCP server logs for errors

---

## Building Onboarding with Dual-Write Storage

### Storage Architecture

SIMBIOT MCP tools use a **dual-write pattern** for building data:

| Tool | Supabase Table | JSON Backup |
|------|---------------|-------------|
| `create_building` | `buildings` | `buildings/{id}/building.json` |
| `add_building_zones` | `hvac_zones` | `buildings/{id}/zones.json` |
| `add_building_desks` | `desks` | `buildings/{id}/desks.json` |

**Write Flow:**
1. **Try Supabase first** - If `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are configured
2. **Always write JSON** - Backup for offline mode and disaster recovery
3. **Response indicates storage** - `"storage": "supabase+json"` or `"json"`

**Read Flow (BuildingDataLoader):**
1. **Check Supabase first** - Uses repository pattern (`HVACZoneRepository`, `DeskRepository`)
2. **Fall back to JSON** - If Supabase unavailable or returns empty

### Database Schema

```
buildings (id, code, name, address, ...)
    ↓
hvac_zones (id, zone_id, building_id FK, floor, fcu_id, setpoint, ...)
    ↓
desks (id, desk_id, building_id FK, hvac_zone_id FK, floor, comfort context...)
```

**Additional Tables:**
- `diesel_tanks`, `generator_groups`, `generators` - Generator plant
- `energy_centres` + 8 component tables - Electrical distribution
- `v_building_asset_summary` - Aggregated asset counts per building

### Example: Onboarding with Dual-Write

```python
# Step 1: Create building (writes to Supabase + JSON)
result = await create_building(
    building_id="sandton",
    name="Sandton Data Centre",
    address="123 Sandton Drive"
)
# Returns: {"success": True, "storage": "supabase+json", ...}

# Step 2: Add zones (writes to hvac_zones table + zones.json)
result = await add_building_zones(
    building_id="sandton",
    zones=[
        {"zone_id": "Zone-L12-N", "floor": "L12", "fcu_id": "FCU-L12-01"},
        {"zone_id": "Zone-L12-S", "floor": "L12", "fcu_id": "FCU-L12-02"},
    ]
)
# Returns: {"success": True, "storage": "supabase+json", "zones_added": 2}

# Step 3: Add desks (writes to desks table + desks.json)
result = await add_building_desks(
    building_id="sandton",
    desks=[
        {"desk_id": "201", "zone_id": "Zone-L12-N", "floor": "L12", "near_window": True},
        {"desk_id": "202", "zone_id": "Zone-L12-N", "floor": "L12", "near_printer": True},
    ]
)
# Returns: {"success": True, "storage": "supabase+json", "desks_added": 2}
```

### Configuration

```bash
# backend/.env
SUPABASE_URL=https://xxx.supabase.co     # Enable Supabase storage
SUPABASE_SERVICE_ROLE_KEY=eyJ...         # Service role for server-side access

# Without these, tools write JSON only (demo/offline mode)
```

---

## Building Onboarding with Asset Metrics

### Enhanced Onboarding Flow for AI/ML Predictive Maintenance

When onboarding a new building, the system now supports automatic generation of asset metric templates for predictive maintenance:

```
1. create_building - Create building configuration
   ↓
2. add_building_devices - Add BMS devices/equipment
   ↓
3. add_building_zones - Add HVAC zones
   ↓
4. get_asset_metrics_template - Auto-generate metric templates
   (Detects equipment types → generates metric definitions)
   ↓
5. configure_asset_metrics - Engineer configures thresholds/weights
   (Adjust normal/warning/critical ranges, mobile phone sensors)
   ↓
6. activate_building - Activate building
   ↓
7. Start data collection → ML training (after 3-6 months)
```

### Example: Onboarding with Asset Metrics

```python
# Step 1: Create building
create_building(
    building_id="sandton",
    name="Sandton Data Centre",
    address="123 Sandton Drive, Gauteng"
)

# Step 2: Add devices (from BMS export)
add_building_devices(
    building_id="sandton",
    devices=[
        {"device_type": "chiller", "name": "CH-1", "protocol": "bacnet"},
        {"device_type": "ahu", "name": "AHU-L12-01", "protocol": "bacnet"},
        {"device_type": "generator", "name": "GEN-1", "protocol": "modbus"},
    ]
)

# Step 3: Get auto-generated metric templates
templates = get_asset_metrics_template(building_id="sandton")

# Returns:
# - chiller: 10 metrics (pressure, temp, motor, sound, vibration)
# - ahu: 9 metrics (airflow, pressure, filter, sound, vibration)
# - generator: 10 metrics (voltage, frequency, coolant, sound, vibration)

# Step 4: Engineer configures (customizes thresholds, weights)
configure_asset_metrics(
    building_id="sandton",
    metric_config={
        "chiller": {
            "metrics": {
                "chill_suction_press": {
                    "enabled": True,
                    "normal_range": [3.5, 5.5],
                    "warning_range": [2.5, 3.5],
                    "critical_range": [1.5, 2.5],
                    "weight": 0.15,
                    "measurement_interval_days": 1
                },
                "chill_sound_compressor": {
                    "enabled": True,
                    "normal_range": [65, 85],
                    "warning_range": [85, 95],
                    "critical_range": [95, 105],
                    "weight": 0.05,
                    "measurement_interval_days": 7
                }
            }
        }
    }
)

# Step 5: Activate building
activate_building(building_id="sandton")
```

### Asset Metric Templates Available

| Equipment Type | Metrics | Manual Inspections | Mobile Phone Sensors |
|---------------|---------|-------------------|---------------------|
| **Generator** | 10 metrics (voltage, frequency, coolant, oil pressure, fuel, battery, runtime) | 4 inspections (oil analysis, belts, hoses, exhaust) | Sound (dBA), Vibration (mm/s) |
| **Chiller** | 10 metrics (suction/discharge pressure, superheat, subcooling, CHW temps, motor, oil) | 4 inspections (refrigerant leak, belts, electrical, coils) | Sound (dBA), Vibration (mm/s) |
| **AHU** | 9 metrics (supply/return/mixed air temp, static pressure, filter DP, fan current, damper) | 4 inspections (belts, bearings, coils, dampers) | Sound (dBA), Vibration (mm/s) |
| **FCU** | 7 metrics (coil temp, fan speed, valve position, room temp, motor current) | 3 inspections (filter, condensate tray, fan motor) | Sound (dBA), Vibration (mm/s) |
| **UPS** | 6 metrics (battery voltage, load, temp, runtime, output frequency, battery impedance) | 3 inspections (battery visual, fan, capacitors) | Manual (battery tester) |
| **Transformer** | 5 metrics (winding temp, oil temp, load, tap position, DGA) | 3 inspections (oil quality, bushings, OLTC) | Manual (oil sample) |
| **VAV** | 4 metrics (airflow, damper position, reheat valve, room temp) | 2 inspections (actuator, flow sensor) | None |
| **Cooling Tower** | 6 metrics (basin temp, fan speed, water level, fan current, sound, vibration) | 3 inspections (fill, nozzles, drift eliminator) | Sound (dBA), Vibration (mm/s) |

### Mobile Phone Sensor Integration

The system supports mobile phone sensors for technician-collected data:

| Sensor | Use Case | Equipment Types | Sampling Notes |
|--------|----------|-----------------|----------------|
| **Microphone (Audio)** | Sound level analysis, detecting bearing squeal, compressor anomalies, electrical arcing | Generator, Chiller, AHU, FCU, Cooling Tower | Record 10s at 1-5m from equipment |
| **Accelerometer (Vibration)** | Motor imbalance, misalignment, bearing wear, looseness detection | Generator, Chiller, AHU, FCU, Cooling Tower | Phone mounted on housing, 10s sample |
| **Camera (Visual)** | Photo documentation, visual inspection (oil leaks, belt wear, corrosion) | All equipment | Photo upload with annotation |

### Data Sources

Each metric specifies its data source:

- **`bms_sensor`**: Automatic polling from BMS (BACnet/Modbus)
- **`mobile_phone`**: Technician collects via mobile app (audio/vibration/photo)
- **`manual`**: Manual measurement (gauges, test equipment, lab analysis)

## Security Notes

**Local (stdio):** Runs on your machine, no network exposure

**Remote (SSE):** Exposes building data over network:
- Use HTTPS in production
- Add authentication middleware
- Implement rate limiting
- Audit all tool calls

## Next Steps

- Add authentication for SSE endpoint
- Implement request signing
- Add usage metrics and monitoring
- Create admin dashboard for MCP connections
