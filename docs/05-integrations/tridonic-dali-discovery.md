# MCP Tool: discover_tridonic_gateway

## Overview

The `discover_tridonic_gateway` MCP tool automates DALI lighting system discovery during building onboarding. It queries Tridonic DALI-2 gateways, enumerates all devices (luminaires, sensors, controllers), and generates equipment codes following the v2.0 naming convention.

This is a **READ-ONLY discovery tool** - it returns structured data for commissioning engineers to review before bulk import into the system.

## When to Use

Use `discover_tridonic_gateway` when:
- ✅ Onboarding buildings with Tridonic Scenecom or other DALI-2 gateways
- ✅ Automating inventory of DALI lighting equipment (>20 devices per line)
- ✅ Generating equipment codes that match building ID patterns
- ✅ Capturing Tridonic-specific metadata (GTIN, serial numbers, lamp hours)
- ✅ Preparing for cross-system coordination (DALI occupancy → HVAC/Lighting)

Do not use for:
- ❌ Manual lighting configuration (use `add_building_devices` instead)
- ❌ Non-DALI lighting systems (traditional 0-10V, on/off)
- ❌ Offline gateways without simulated mode enabled

## Usage

### Basic Discovery (Real Gateway)

```bash
curl -X POST http://localhost:9095/api/mcp/call-tool \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "discover_tridonic_gateway",
    "arguments": {
      "building_id": "site-002",
      "gateway_ip": "192.168.10.50",
      "gateway_type": "tridonic"
    }
  }'
```

### Testing with Simulated Data

```bash
curl -X POST http://localhost:9095/api/mcp/call-tool \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "discover_tridonic_gateway",
    "arguments": {
      "building_id": "site-003",
      "gateway_ip": "192.168.10.99",
      "gateway_type": "tridonic",
      "use_simulated": true
    }
  }'
```

### With Authentication

```bash
curl -X POST http://localhost:9095/api/mcp/call-tool \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "discover_tridonic_gateway",
    "arguments": {
      "building_id": "site-002",
      "gateway_ip": "192.168.10.50",
      "gateway_type": "tridonic",
      "username": "admin",
      "password": "scenecom_password"
    }
  }'
```

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `building_id` | string | ✓ | - | Building/site ID (e.g., `site-002`) |
| `gateway_ip` | string | ✓ | - | IP address of DALI gateway (e.g., `192.168.10.50`) |
| `gateway_type` | string | - | `tridonic` | Gateway manufacturer: `tridonic`, `philips`, `helvar`, `generic` |
| `username` | string | - | - | HTTP Basic Auth username (if required by gateway) |
| `password` | string | - | - | HTTP Basic Auth password (if required by gateway) |
| `use_simulated` | boolean | - | `false` | Use simulated data if gateway offline (for testing) |

## Response Format

### Success Response

```json
{
  "success": true,
  "building_id": "site-002",
  "gateway_ip": "192.168.10.50",
  "gateway_type": "tridonic",
  "gateway": {
    "ip_address": "192.168.10.50",
    "mac_address": "00:11:22:33:44:55",
    "firmware_version": "2.1.0",
    "model": "Scenecom",
    "manufacturer": "Tridonic",
    "dali_lines": 2,
    "devices_per_line": { "1": 12, "2": 10 },
    "total_devices": 22,
    "online": true,
    "last_poll": "2026-02-09T10:30:15.123456"
  },
  "total_devices": 22,
  "devices_by_line": {
    "1": 12,
    "2": 10
  },
  "equipment_list": [
    {
      "equipment_code": "S002-DALI-L1-01",
      "equipment_type": "DALI",
      "device_type": 0,
      "device_type_name": "Fluorescent",
      "dali_line": 1,
      "dali_address": 1,
      "category": "controllers",
      "manufacturer": "Tridonic",
      "gtin": "04038382003821",
      "serial_number": "TR-12345678"
    },
    {
      "equipment_code": "S002-LUM-L1-001",
      "equipment_type": "LUM",
      "device_type": 6,
      "device_type_name": "LED Module",
      "dali_line": 1,
      "dali_address": 2,
      "category": "luminaires",
      "manufacturer": "Philips",
      "gtin": "07603186029401",
      "serial_number": "PH-87654321"
    }
  ],
  "summary": {
    "controllers": 2,
    "luminaires": 18,
    "sensors": 2,
    "other": 0
  },
  "next_steps": [
    "Review 22 discovered devices and equipment codes",
    "Update building features: set dali=true in building.json",
    "Save gateway IP (192.168.10.50) to building config",
    "Call bulk_discover with equipment_list to fetch full metadata",
    "Call add_building_zones with dali_zone mappings for cross-system coordination",
    "Register site with DALI service: register_niagara_site('site-002', '192.168.10.50')"
  ]
}
```

### Error Response

```json
{
  "success": false,
  "building_id": "site-002",
  "gateway_ip": "192.168.10.99",
  "error": "DALI gateway at 192.168.10.99 is offline or unreachable",
  "gateway": null,
  "total_devices": 0,
  "equipment_list": [],
  "summary": {
    "controllers": 0,
    "luminaires": 0,
    "sensors": 0,
    "other": 0
  },
  "next_steps": [
    "Verify gateway IP address and network connectivity",
    "Check gateway power and Ethernet connection",
    "Try with use_simulated=true for testing"
  ]
}
```

## Equipment Code Format (v2.0)

Generated equipment codes follow the BMS Intelligence v2.0 naming convention:

### Controllers
- **Format:** `{site}-DALI-L{line}-{address:02d}`
- **Example:** `S002-DALI-L1-01`
- **Components:**
  - `S002`: Site code (extracted from building_id)
  - `DALI`: Equipment type
  - `L1`: DALI line number
  - `01`: DALI short address (00-63)

### Luminaires
- **Format:** `{site}-LUM-L{line}-{sequence:03d}`
- **Example:** `S002-LUM-L1-042`
- **Components:**
  - `S002`: Site code
  - `LUM`: Equipment type (luminaire)
  - `L1`: DALI line number
  - `042`: Sequential number across all lines

### PIR Sensors
- **Format:** `{site}-PIR-L{line}-{sequence:03d}`
- **Example:** `S002-PIR-L1-001`
- **Components:**
  - `S002`: Site code
  - `PIR`: Equipment type (sensor)
  - `L1`: DALI line number
  - `001`: Sequential number

### Site Code Extraction
| Building ID | Site Code |
|-------------|-----------|
| `site-001` | `S001` |
| `site-099` | `S099` |
| `site-123` | `S123` |

## Device Classification

The tool classifies DALI devices into three categories based on device type and name:

| Classification | Device Types | Equipment Type |
|----------------|--------------|----------------|
| **Controllers** | Type 0, name contains "controller" | `DALI` |
| **Luminaires** | Type 1 (Emergency), Type 6 (LED Module), Type 2-5, 7-8 | `LUM` |
| **Sensors** | Name contains "sensor" or "pir" | `PIR` |

## Integration Workflow

### 1. Create Building
```bash
# First, create the building
discover_tridonic_gateway requires an existing building
```

### 2. Discover DALI Gateway
```bash
# Run discovery
POST /api/mcp/call-tool discover_tridonic_gateway
- Returns: equipment_list with all discovered devices and codes
```

### 3. Review Equipment Codes
```bash
# Commissioning engineer reviews the returned equipment_list
# Verifies codes match building layout and DALI line assignments
# Makes notes for any manual corrections needed
```

### 4. Bulk Import Metadata
```bash
# Call bulk_discover_equipment with the equipment_list
POST /api/equipment/bulk-discover
- Input: equipment_list from step 2
- Output: Full metadata (GTIN, serial, lamp hours, etc.)
```

### 5. Register with DALI Service
```bash
# Register site for real-time DALI data
POST /api/dali/register-site
{
  "building_id": "site-002",
  "gateway_ip": "192.168.10.50",
  "gateway_type": "tridonic"
}
```

### 6. Configure Zones (Optional)
```bash
# Add DALI zone mappings for cross-system coordination
POST /api/buildings/{building_id}/zones
- DALI zones mapped to building floors/areas
- Enables occupancy-based HVAC/Lighting optimization
```

## Real-World Example: Sandton City Office Tower

### Configuration
- **Building ID:** `site-002`
- **Gateway IP:** `192.168.10.50`
- **Gateway Type:** Tridonic Scenecom (connecDIM)
- **DALI Lines:** 2 (L1: Floors 1-2, L2: Floors 3+)
- **Total Devices:** 64 luminaires + 2 controllers + 4 PIR sensors

### Discovery Call
```bash
POST /api/mcp/call-tool
{
  "tool_name": "discover_tridonic_gateway",
  "arguments": {
    "building_id": "site-002",
    "gateway_ip": "192.168.10.50",
    "gateway_type": "tridonic"
  }
}
```

### Response Summary
```json
{
  "success": true,
  "total_devices": 70,
  "devices_by_line": { "1": 35, "2": 35 },
  "summary": {
    "controllers": 2,
    "luminaires": 64,
    "sensors": 4,
    "other": 0
  },
  "equipment_list": [
    { "equipment_code": "S002-DALI-L1-01", "device_type_name": "LED Module", ... },
    { "equipment_code": "S002-LUM-L1-001", "device_type_name": "LED Module", ... },
    ...
  ]
}
```

## Features & Benefits

### Automated Discovery ✅
- **Problem Solved:** Manual DALI enumeration is tedious and error-prone for large installations
- **Solution:** Queries gateway API to auto-discover all devices in seconds

### v2.0 Code Generation ✅
- **Problem Solved:** Equipment codes must match naming convention for system integration
- **Solution:** Automatically generates compliant codes based on device type and DALI address

### Metadata Capture ✅
- **Problem Solved:** Manual entry of GTIN, serial, lamp hours leads to data inconsistency
- **Solution:** Extracts Tridonic-specific metadata during discovery for later bulk import

### Graceful Degradation ✅
- **Problem Solved:** Gateway offline during commissioning blocks progress
- **Solution:** Supports simulated mode for testing and development

### Non-Destructive ✅
- **Problem Solved:** Accidental data loss during discovery
- **Solution:** Read-only tool returns data for engineer review before any database writes

## Troubleshooting

### Gateway Unreachable

**Error:** `DALI gateway at 192.168.10.50 is offline or unreachable`

**Solutions:**
1. Verify gateway IP address with network admin: `ping 192.168.10.50`
2. Check gateway power: LED lights on gateway should be active
3. Verify Ethernet cable connection to gateway
4. Check firewall rules allowing HTTP access to gateway
5. Use `use_simulated=true` for testing without gateway

### Authentication Failures

**Error:** `HTTP 401 Unauthorized`

**Solutions:**
1. Verify username and password with gateway admin
2. Check if gateway requires HTTP Basic Auth: review Tridonic documentation
3. Some gateways may not require credentials: try omitting `username` and `password`

### Duplicate Equipment Codes

**Error:** Equipment codes conflict with manually-created devices

**Solutions:**
1. This is expected in mixed-mode commissioning (some manual, some automated)
2. Review equipment list carefully before bulk import
3. Adjust starting sequences in code generation if needed
4. Coordinate with other technicians before running discovery

### Missing Metadata (GTIN, Serial)

**Issue:** Returned equipment_list has null GTIN/serial values

**Causes & Solutions:**
1. Older DALI devices may not support GTIN queries - expected behavior
2. Device firmware needs update - contact Tridonic support
3. Check gateway API supports full DALI-2 queries
4. Manual entry needed for non-compliant devices

## API Integration Examples

### Python (FastAPI Client)
```python
from app.mcp.simbiot_server import SIMBIOTMCPServer

server = SIMBIOTMCPServer()
result = await server.call_tool(
    "discover_tridonic_gateway",
    building_id="site-002",
    gateway_ip="192.168.10.50",
    use_simulated=True
)

if result["success"]:
    for equipment in result["equipment_list"]:
        print(f"{equipment['equipment_code']}: {equipment['device_type_name']}")
else:
    print(f"Discovery failed: {result['error']}")
```

### JavaScript/TypeScript (Frontend)
```typescript
const result = await fetch('/api/mcp/call-tool', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    tool_name: 'discover_tridonic_gateway',
    arguments: {
      building_id: 'site-002',
      gateway_ip: '192.168.10.50',
      use_simulated: false
    }
  })
}).then(r => r.json());

if (result.success) {
  console.log(`Found ${result.total_devices} DALI devices`);
}
```

## Performance Characteristics

| Aspect | Value | Notes |
|--------|-------|-------|
| Gateway Query Timeout | 10 seconds | Configurable in service |
| Typical Discovery Time | 2-5 seconds | Per DALI line |
| Max Devices Supported | 256 per line | 64 DALI short addresses per line, theoretically unlimited |
| Simulated Mode Speed | <100ms | No network I/O |
| Response Size | ~50-100 KB | For typical 50-100 device discovery |

## Security Considerations

✅ **Safe Operations:**
- Read-only discovery (no writes to gateway)
- No database modifications until explicit bulk import
- Supports HTTP Basic Auth for gateway API
- Credentials not stored (pass per-call only)

⚠️ **Recommendations:**
1. Use HTTPS gateway URLs when available (customize service if needed)
2. Store gateway credentials in secure vault, not in config files
3. Limit DALI gateway API access to BMS network only
4. Audit discovery operations via logging

## Related Tools

- **`add_building_devices`** - Manually add devices after discovery review
- **`bulk_discover_equipment`** - Fetch full metadata for discovered devices
- **`add_building_zones`** - Create zone mappings for DALI zones
- **`import_point_list`** - For importing HVAC/other non-DALI equipment
- **`POST /api/niagara/discover/csv`** - Upload Desigo CSV BACnet exports with lighting point classification (see below)

---

## Desigo CSV Point Export Ingestion (Phase 130)

### Overview

When a Desigo CC system has Tridonic lighting points exposed via net4more BACnet gateway, the standard BACnet export CSV will contain both HVAC and lighting points. The CSV ingestion endpoint classifies all points automatically, identifying 8 lighting-specific categories alongside standard HVAC equipment.

### API Endpoint

```
POST /api/niagara/discover/csv
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | File upload | Yes | CSV file from Desigo CC BACnet export |
| `site_id` | string (query) | Yes | SENTINEL site ID (e.g., `site-002`) |
| `source_label` | string (query) | No | Label for this export (default: `desigo-export`) |

**Expected CSV format** (Desigo CC export):
```csv
name,object_type,instance,units,present_value,description,min_value,max_value,writable
STC/L1/DALI-01/Lum01_DimLevel,analogOutput,3000,percent,85,Luminaire 01 dimming level,0,100,True
STC/L1/DALI-01/Lum01_ActivePower,analogInput,3001,watt,42.5,Luminaire 01 active power,0,120,False
STC/RF/AHU-01/SupplyAirTemp,analogInput,1000,degC,15.2,Supply air temperature,12.0,25.0,False
```

**Hierarchical name parsing:**
- `STC/L1/DALI-01/Lum01_DimLevel` → equipment_id=`DALI-01`, point=`Lum01_DimLevel`
- `STC/RF/AHU-01/SupplyAirTemp` → equipment_id=`AHU-01`, point=`SupplyAirTemp`

### Lighting Point Categories

The PointClassifier recognizes 8 lighting-specific categories from Tridonic/net4more BACnet naming:

| Category | Keywords | Example Point Names |
|----------|----------|-------------------|
| `brightness` | dimlevel, dim_level, brightness | `Lum01_DimLevel` |
| `lighting_power` | activepower, active_power, luminaire_power | `Lum01_ActivePower` |
| `lighting_energy` | accumenergy, accum_energy, accumulated_energy | `Lum01_AccumEnergy` |
| `driver_temperature` | drivertemp, driver_temp | `Lum01_DriverTemp` |
| `lamp_hours` | lamphours, lamp_hours, operating_hours | `Lum01_LampHours` |
| `light_output` | lightoutput, light_output, luminous_flux | `Lum01_LightOutput` |
| `emergency_battery` | embatt, em_batt, battlevel | `Em01_BattLevel` |
| `emergency_test` | emtest, em_test, testresult | `Em01_TestResult` |

### Equipment Pattern Recognition

| Pattern | Match Examples | Equipment Type |
|---------|---------------|---------------|
| `dali_controller` | DALI-01, DALI-CTRL, net4more, n4m | `dali_controller` |
| `luminaire` | LUM-01, DALI-LUM, dali-l | `luminaire` |
| `light_sensor` | PIR-01, DALI-SENS, dali-pir | `light_sensor` |
| `emergency_luminaire` | EM-LUM, EMERG-LUM | `emergency_luminaire` |

### Response Format

```json
{
  "discovery_id": "csv-site-002-desigo-export-20260226T143000",
  "status": "complete",
  "total_points": 397,
  "classified_points": 385,
  "equipment_groups": 24,
  "lighting_summary": {
    "total": 19,
    "by_category": {
      "brightness": 2,
      "lighting_power": 2,
      "lighting_energy": 1,
      "lux": 3,
      "lamp_hours": 1,
      "emergency_battery": 1,
      "emergency_test": 1,
      "lamp_status": 2
    },
    "by_equipment_type": {
      "dali_controller": 19
    }
  }
}
```

### Usage Example

**Getting the CSV from Desigo CC:**
1. Open Desigo CC Management Station
2. Navigate to Project > BACnet Network
3. Right-click > Export Objects to CSV
4. Include: Object Name, Type, Instance, Description, Units, Value, Writable

**Uploading to SENTINEL:**
```bash
curl -X POST "http://localhost:9095/api/niagara/discover/csv?site_id=site-002" \
  -F "file=@point_list_site-002_siemens-desigo.csv"
```

**Notes:**
- Handles UTF-8 BOM from Excel exports (`utf-8-sig`)
- Falls back to `latin-1` if UTF-8 decoding fails
- Both HVAC and lighting points are classified in a single pass
- Discovery results are cached and can be reviewed/approved via existing mapping endpoints

## File Modifications

**Added/Modified:**
- `backend/app/mcp/simbiot_server.py` - MCP tool registration (3 locations)
  - Line ~2960: `discover_tridonic_gateway_tool()` function
  - Line ~4264: Tool registry entry in `MCP_TOOLS`
  - Line ~4677: Handler registration in `tool_handlers`

**No changes to:**
- Database schema (discovery is read-only)
- Building model (compatible with existing structure)
- Frontend code (backend MCP tool only)

## Future Enhancements

1. **Auto-floor detection** - Parse gateway hostname or SNMP location for floor assignment
2. **Zone classification** - Auto-map DALI zone letters (A-Z) based on device locations
3. **Parallel line discovery** - Query all DALI lines concurrently with `asyncio.gather()`
4. **Progress streaming** - Return partial results via SSE as discovery progresses
5. **Device filtering** - Option to discover only specific device types (e.g., luminaires only)
6. **Legacy gateway support** - Extend to older DALI-1 systems with manual enumeration
