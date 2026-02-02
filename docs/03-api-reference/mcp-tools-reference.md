---
title: "MCP Tools Reference (SIMBIOT)"
type: "reference"
status: "approved"
version: "2.0.0"
created: "2026-01-30"
updated: "2026-02-02"
author: "Sentinel Development Team"
tags: ["mcp", "simbiot", "model-context-protocol", "tools"]
related: ["../02-architecture/system-overview.md", "../08-ai-ml/claude-integration.md"]
domain: "bms"
audience: "developers"
complexity: "advanced"
estimated_read_time: 30
---

# SIMBIOT MCP Server Tools Reference

Complete reference for all 23 SIMBIOT MCP tools for building management.

## Overview

SIMBIOT MCP Server provides **23 tools** across 4 categories for building management:

### Tool Categories

| Category | Tools | Purpose |
|----------|-------|---------|
| **Core BMS** | 12 | Building data, device control, alarms, trends, work orders |
| **Building Onboarding** | 9 | Create buildings, add zones/desks/devices, AI-assisted imports |
| **AI/ML Predictive Maintenance** | 2 | Asset metrics templates and configuration |

---

## Core BMS Tools (12)

### Building & Asset Management

#### `get_buildings`
List buildings with health scores and alarm summaries.

**Parameters:**
- `status_filter` (string, optional): "all", "critical", "warning", "healthy"
- `region` (string, optional): "Gauteng", "Western Cape", "KwaZulu-Natal"

**Returns:**
```json
{
  "buildings": [
    {
      "id": "001",
      "name": "Gateway Theatre of Shopping",
      "address": "1 Magwa Crescent, Umhlanga",
      "region": "KwaZulu-Natal",
      "health_score": 85.5,
      "critical_alarms": 2,
      "warnings": 5,
      "asset_count": 45
    }
  ],
  "total": 15,
  "filtered": 15
}
```

#### `get_assets`
List assets/equipment for a building.

**Parameters:**
- `building_id` (string, required): Building identifier
- `asset_type` (string, optional): "chiller", "ahu", "generator", etc.
- `criticality` (string, optional): "critical", "high", "medium", "low"

**Returns:**
```json
{
  "building_id": "001",
  "assets": [
    {
      "equipment_id": "001-gwc-chiller-001",
      "equipment_name": "Chiller 1",
      "type": "chiller",
      "criticality": "critical",
      "health_score": 72.0,
      "status": "warning"
    }
  ],
  "total": 45
}
```

#### `get_asset_detail`
Comprehensive asset details including metrics, readings, and maintenance history.

**Parameters:**
- `asset_id` (string, required): Equipment identifier
- `include` (string array, optional): ["metrics", "readings", "maintenance", "deficiencies"]

**Returns:**
```json
{
  "asset": {
    "equipment_id": "001-gwc-chiller-001",
    "equipment_name": "Chiller 1",
    "type": "chiller",
    "manufacturer": "York",
    "model": "YCIV",
    "serial_number": "YCIV-12345",
    "installation_date": "2003-05-15",
    "criticality": "critical",
    "location": "Roof Level",
    "health_score": 72.0,
    "status": "warning",
    "baseline": {
      "captured_at": "2026-01-15",
      "health_score": 85.0,
      "elements": [...]
    },
    "current_readings": {
      "chw_supply_temp": 7.8,
      "chw_return_temp": 12.5,
      "condenser_entering_temp": 29.5,
      "condenser_leaving_temp": 34.2
    },
    "active_deficiencies": [...],
    "maintenance_history": [...]
  }
}
```

---

### Device Control

#### `get_devices`
BMS device discovery and listing.

**Parameters:**
- `site_id` (string, optional): Filter by site
- `device_type` (string, optional): "chiller", "ahu", "fcu", etc.

**Returns:**
```json
{
  "devices": [
    {
      "device_id": "001-gwc-chiller-001",
      "device_name": "Chiller 1",
      "type": "chiller",
      "protocol": "bacnet",
      "address": "12345",
      "site_id": "001",
      "status": "online",
      "safety_status": "warning",
      "points": ["chw_supply_temp", "chw_return_temp", ...]
    }
  ]
}
```

#### `read_device_point`
Read current value from device point.

**Parameters:**
- `device_id` (string, required): Device identifier
- `point_name` (string, required): Point name (e.g., "chw_supply_temp")

**Returns:**
```json
{
  "device_id": "001-gwc-chiller-001",
  "point_name": "chw_supply_temp",
  "value": 7.8,
  "unit": "°C",
  "timestamp": "2026-02-02T10:30:00Z",
  "quality": "good"
}
```

#### `write_device_point`
Write value to device point **with safety validation**.

**Parameters:**
- `device_id` (string, required): Device identifier
- `point_name` (string, required): Point name
- `value` (number, required): Value to write
- `priority` (string, optional): "supervised" (default), "override", "manual"

**Safety Validation:**
- Checks against safety rules (temperature ranges, pressure limits, interlocks)
- Blocks unsafe operations
- Logs all write attempts to audit trail

**Returns:**
```json
{
  "success": true,
  "device_id": "001-gwc-chiller-001",
  "point_name": "zone_cooling_setpoint",
  "previous_value": 22.0,
  "new_value": 21.0,
  "safety_validation": {
    "safe": true,
    "rules_checked": ["TemperatureRange", "Interlock"]
  },
  "audit_id": "audit-20260202-103000",
  "timestamp": "2026-02-02T10:30:00Z"
}
```

**Error Response (Unsafe):**
```json
{
  "success": false,
  "error": "Safety validation failed",
  "safety_validation": {
    "safe": false,
    "blocking_rule": {
      "type": "TemperatureRange",
      "reason": "Value 16°C below minimum safe temperature 18°C",
      "rule_id": "temp-range-001"
    }
  }
}
```

---

### Alarms & Analytics

#### `get_alarms`
List active alarms with filtering.

**Parameters:**
- `building_id` (string, optional): Filter by building
- `severity` (string, optional): "critical", "high", "medium", "low"
- `limit` (integer, optional): Max results (default: 50)

**Returns:**
```json
{
  "alarms": [
    {
      "id": "alarm-001",
      "equipment_id": "001-gwc-chiller-001",
      "equipment_name": "Chiller 1",
      "title": "High Discharge Pressure",
      "message": "Discharge pressure exceeded threshold: 250 psi (limit: 240 psi)",
      "severity": "critical",
      "timestamp": "2026-02-02T09:15:00Z",
      "acknowledged": false
    }
  ],
  "total": 12,
  "critical": 3,
  "high": 5
}
```

#### `search_alarms`
**Natural language alarm search with pattern detection.**

**Parameters:**
- `query` (string, required): Natural language query
- `time_range` (string, optional): "today", "week", "month" (default: 14 days)
- `building_id` (string, optional): Filter by building

**Natural Language Processing:**

The tool uses sophisticated NLP to extract intent from queries:

| Query Pattern | Interpretation |
|---------------|----------------|
| "chiller high pressure" | Equipment type + parameter |
| "critical alarms today" | Severity + time range |
| "AHU vibration week" | Equipment + parameter + time |
| "temperature problems Gateway" | Parameter + building |

**Keyword Mappings:**
```python
KEYWORD_MAPPINGS = {
    # Equipment types
    "chiller": ["chiller", "chillers", "cooling tower"],
    "ahu": ["ahu", "air handling unit", "air handler"],
    "generator": ["generator", "gen", "genset"],

    # Parameters
    "temperature": ["temp", "temperature", "overtemp", "high temp", "low temp"],
    "pressure": ["press", "pressure", "high press", "low press"],
    "vibration": ["vib", "vibration", "shaking", "rattle"],

    # Severity
    "critical": ["critical", "alarm", "emergency", "urgent"],
    "warning": ["warning", "caution", "advisory"],

    # 20+ keyword categories total
}
```

**Time Range Detection:**
- "today" → 1 day
- "week" → 7 days
- "month" → 30 days
- Default → 14 days

**Pattern Detection:**

Automatically detects recurring alarm patterns:

```json
{
  "asset_tag": "001-gwc-chiller-001",
  "asset_name": "Chiller 1",
  "alarm_count": 5,
  "dates": ["2026-01-15", "2026-01-22", "2026-01-29", "2026-02-01", "2026-02-02"],
  "severities": ["critical", "high", "warning"],
  "pattern": "Recurring every 7 days",
  "latest_alarm": {
    "title": "High Discharge Pressure",
    "severity": "critical",
    "timestamp": "2026-02-02T09:15:00Z"
  }
}
```

**Pattern Types:**
- "Single occurrence" - 1 alarm
- "Multiple occurrences" - 2 alarms
- "Recurring every X days" - 3+ alarms with calculated interval

**Returns:**
```json
{
  "interpretation": "critical chiller alarms in last 14 days",
  "results": [...],
  "keywords_matched": ["chiller", "critical"],
  "total_matches": 8,
  "assets_affected": 2
}
```

#### `get_trends`
Historical trend data for parameters.

**Parameters:**
- `asset_id` (string, required): Equipment identifier
- `parameter` (string, required): Parameter name
- `from_time` (string, optional): ISO timestamp
- `to_time` (string, optional): ISO timestamp
- `aggregation` (string, optional): "raw", "1h", "1d" (default: "raw")

**Returns:**
```json
{
  "asset_id": "001-gwc-chiller-001",
  "parameter": "chw_supply_temp",
  "from_time": "2026-02-01T00:00:00Z",
  "to_time": "2026-02-02T00:00:00Z",
  "data_points": [
    {"timestamp": "2026-02-01T01:00:00Z", "value": 7.2},
    {"timestamp": "2026-02-01T02:00:00Z", "value": 7.5},
    ...
  ],
  "statistics": {
    "min": 7.0,
    "max": 8.5,
    "avg": 7.6,
    "stddev": 0.4
  }
}
```

**Note:** Currently returns synthetic data in demo mode. Integrates with InfluxDB in production.

#### `get_health_score`
Calculate health score for asset or building.

**Parameters:**
- `target_id` (string, required): Asset or building ID
- `target_type` (string, required): "asset" or "building"

**Asset Health Score:**
Derived from device `safety_status`:
- "safe" → 100 points
- "warning" → 70 points
- "critical" or "alarm" → 30 points

**Building Health Score:**
Average of all asset health scores in building.

**Returns:**
```json
{
  "target_id": "001-gwc-chiller-001",
  "target_type": "asset",
  "health_score": 72.0,
  "status": "warning",
  "components": [
    {"name": "compressor", "score": 65.0},
    {"name": "condenser", "score": 80.0},
    {"name": "evaporator", "score": 75.0}
  ],
  "trend": "declining",
  "last_updated": "2026-02-02T10:30:00Z"
}
```

---

### Work Orders

#### `get_work_orders`
List work orders with filtering.

**Parameters:**
- `building_id` (string, optional): Filter by building
- `status` (string, optional): "open", "in_progress", "completed", "closed"
- `assignee` (string, optional): Filter by assigned technician

**Returns:**
```json
{
  "work_orders": [
    {
      "id": "WO-2026-00123",
      "building_id": "001",
      "asset_id": "001-gwc-chiller-001",
      "title": "Replace Chiller Compressor Bearing",
      "description": "Vibration analysis indicates bearing failure...",
      "priority": "critical",
      "status": "open",
      "created_at": "2026-02-01T14:30:00Z",
      "assigned_to": "tech-001",
      "estimated_cost": 15000.00
    }
  ],
  "total": 45,
  "open": 12,
  "overdue": 3
}
```

#### `create_work_order`
Create new work order.

**Parameters:**
- `building_id` (string, required): Building identifier
- `asset_id` (string, required): Asset identifier
- `title` (string, required): Work order title
- `description` (string, required): Detailed description
- `priority` (string, required): "critical", "high", "medium", "low"
- `assigned_to` (string, optional): Technician ID

**Returns:**
```json
{
  "success": true,
  "work_order": {
    "id": "WO-2026-00124",
    "building_id": "001",
    "asset_id": "001-gwc-chiller-001",
    "title": "Inspect Chiller Refrigerant Leak",
    "priority": "high",
    "status": "open",
    "created_at": "2026-02-02T10:30:00Z",
    "created_by": "simbiot-mcp"
  },
  "audit_id": "audit-20260202-103000"
}
```

---

## Building Onboarding Tools (9)

### Building Management

#### `list_managed_buildings`
List all buildings managed by SIMBIOT.

**Returns:**
```json
{
  "buildings": [
    {
      "building_id": "sandton",
      "name": "Sandton City",
      "status": "active",
      "device_count": 156,
      "zone_count": 24,
      "desk_count": 450
    }
  ]
}
```

#### `create_building`
**Create new building configuration with dual-write storage.**

**Dual-Write Pattern:**
1. **Supabase:** Primary database (if configured)
2. **JSON:** Backup file (always written)

**Parameters:**
- `building_id` (string, required): Unique building identifier
- `name` (string, required): Building name
- `address` (string, required): Physical address
- `region` (string, optional): Geographic region
- `building_type` (string, optional): "commercial", "retail", "datacentre", etc.
- `sqm` (number, optional): Gross floor area
- `floors` (integer, optional): Number of floors

**Storage:**
- Supabase Table: `buildings`
- JSON File: `data/buildings/{building_id}/building.json`

**Returns:**
```json
{
  "success": true,
  "building_id": "new-building",
  "storage": "supabase+json",
  "created_at": "2026-02-02T10:30:00Z",
  "message": "Building created in Supabase and JSON backup written"
}
```

**Without Supabase configured:**
```json
{
  "success": true,
  "building_id": "new-building",
  "storage": "json",
  "message": "Building created in JSON (demo/offline mode)"
}
```

#### `activate_building`
Add building to active registry.

**Parameters:**
- `building_id` (string, required): Building to activate

**Returns:**
```json
{
  "success": true,
  "building_id": "sandton",
  "status": "active",
  "activated_at": "2026-02-02T10:30:00Z"
}
```

#### `get_building_config`
Retrieve complete building configuration.

**Parameters:**
- `building_id` (string, required): Building identifier

**Returns:**
```json
{
  "building": {
    "building_id": "sandton",
    "name": "Sandton City",
    "address": "123 Sandton Drive",
    "zones": [...],
    "desks": [...],
    "devices": [...],
    "active_modules": ["hvac", "lighting", "energy"]
  },
  "storage": "supabase+json"
}
```

---

### Zone, Desk, Device Management

#### `add_building_zones`
**Add HVAC zones with equipment mappings (dual-write).**

**Parameters:**
- `building_id` (string, required): Building identifier
- `zones` (array, required): Array of zone objects

**Zone Object:**
```json
{
  "zone_id": "Zone-L12-N",
  "floor": "L12",
  "floor_area": 450,
  "zone_type": "open_office",
  "fcu_id": "FCU-L12-01",
  "setpoint": 22.0,
  "occupancy": 45,
  "equipment": {
    "fcu": "001-sandton-fcu-001",
    "vav": "001-sandton-vav-001"
  }
}
```

**Storage:**
- Supabase Table: `hvac_zones`
- JSON File: `data/buildings/{building_id}/zones.json`

**Returns:**
```json
{
  "success": true,
  "building_id": "sandton",
  "zones_added": 5,
  "storage": "supabase+json",
  "zones": [...]
}
```

#### `add_building_desks`
**Add workspace positions with comfort context (dual-write).**

**Parameters:**
- `building_id` (string, required): Building identifier
- `desks` (array, required): Array of desk objects

**Desk Object:**
```json
{
  "desk_id": "201",
  "zone_id": "Zone-L12-N",
  "floor": "L12",
  "near_window": true,
  "near_diffuser": false,
  "near_printer": false,
  "occupant": "john.doe@company.com"
}
```

**Comfort Context Flags:**
- `near_window`: Solar heat gain analysis
- `near_diffuser`: Draft detection
- `near_printer`: Heat/noise consideration

**Storage:**
- Supabase Table: `desks`
- JSON File: `data/buildings/{building_id}/desks.json`

**Returns:**
```json
{
  "success": true,
  "building_id": "sandton",
  "desks_added": 24,
  "storage": "supabase+json",
  "desks": [...]
}
```

#### `add_building_devices`
**Add BMS devices to building (dual-write).**

**Parameters:**
- `building_id` (string, required): Building identifier
- `devices` (array, required): Array of device objects

**Device Object:**
```json
{
  "device_id": "001-sandton-chiller-001",
  "device_name": "Chiller 1",
  "device_type": "chiller",
  "protocol": "bacnet",
  "address": "12345",
  "floor": "Roof",
  "critical": true
}
```

**Storage:**
- Supabase: Via device repository
- JSON File: `data/buildings/{building_id}/devices.json`

**Returns:**
```json
{
  "success": true,
  "building_id": "sandton",
  "devices_added": 12,
  "storage": "supabase+json"
}
```

---

### AI-Assisted Onboarding

#### `import_point_list`
**Parse BACnet point list CSV and auto-generate device/zone structure.**

**AI-Assisted Features:**

1. **Auto-Detect BMS Vendor:**
   - Analyzes point ID patterns
   - Detects Honeywell, Siemens, JCI, Schneider formats

2. **Auto-Generate Device Structure:**
   - Groups points by device
   - Identifies device types from point names
   - Creates zone assignments

**Vendor Detection Patterns:**
```python
VENDOR_PATTERNS = {
    "Honeywell": r"PXC-\d+|X-\d+",           # PXC-770, X-123
    "Siemens": r"TEC-\d+|PAA-\d+",          # TEC-1234, PAA-10
    "JCI": r"NAE-\d+|N30|\d{5}",            # NAE-123, N30, 12345
    "Schneider": r"ASB-\d+|PNT-\d+"         # ASB-123, PNT-456
}
```

**Parameters:**
- `building_id` (string, required): Target building
- `point_list` (string, required): CSV content or file path
- `site_code` (string, optional): Site code for device ID generation

**CSV Format:**
```csv
Point Name,Address,Description,Device
PXC-770.CHWST.AI-1,12345,Chilled Water Supply Temp,PXC-770
PXC-770.CHWRT.AI-1,12346,Chilled Water Return Temp,PXC-770
TEC-1234.ZN-T.AI-1,23456,Zone Temperature,TEC-1234
```

**Auto-Generation Logic:**
```python
# 1. Extract device ID from point name
device_id = extract_device(point_name)  # "PXC-770"

# 2. Group points by device
devices = group_by(points, device_id)

# 3. Detect device type from point names
if "CHWST" in points or "CHWRT" in points:
    device_type = "chiller"
elif "ZN-T" in points or "SA-T" in points:
    device_type = "ahu"

# 4. Generate zone assignments
zone_id = extract_zone(point_name)  # "L12-N"
```

**Returns:**
```json
{
  "success": true,
  "building_id": "new-building",
  "vendor_detected": "Honeywell",
  "devices_generated": 8,
  "zones_created": 5,
  "points_imported": 156,
  "devices": [
    {
      "device_id": "001-new-chiller-001",
      "device_name": "Chiller 1",
      "device_type": "chiller",
      "protocol": "bacnet",
      "points": ["chw_supply_temp", "chw_return_temp", ...],
      "suggested_zone": "Zone-L12-N"
    }
  ],
  "warnings": [
    "2 points could not be mapped to devices",
    "Device type uncertain for PXC-775 (detected as 'ahu')"
  ]
}
```

#### `import_controller_list`
**Parse BMS controller information and create device structure.**

**Parameters:**
- `building_id` (string, required): Target building
- `controllers` (array, required): Array of controller objects

**Controller Object:**
```json
{
  "name": "PXC-L12-01",
  "ip_address": "192.168.1.100",
  "bacnet_device_id": 12345,
  "area_served": "Level 12 North",
  "controller_type": "PXC",
  "equipment": ["AHU-L12-01", "FCU-L12-01", "VAV-L12-01"]
}
```

**Returns:**
```json
{
  "success": true,
  "building_id": "sandton",
  "controllers_imported": 8,
  "devices_created": 24,
  "controllers": [...]
}
```

---

## AI/ML Predictive Maintenance Tools (2)

### Asset Metrics Templates

#### `get_asset_metrics_template`
**Get auto-generated ML metric templates for equipment types.**

**Auto-Detection:**
If `equipment_types` not provided, auto-detects from building's devices and zones.

**Parameters:**
- `building_id` (string, required): Building identifier
- `equipment_types` (array, optional): Filter to specific types

**Supported Equipment Types:**
| Equipment | Metrics | Manual Inspections | Mobile Sensors |
|-----------|---------|-------------------|----------------|
| **Generator** | 10 | 4 (oil, belts, hoses, exhaust) | Sound, Vibration |
| **Chiller** | 10 | 4 (refrigerant, belts, electrical, coils) | Sound, Vibration |
| **AHU** | 9 | 4 (belts, bearings, coils, dampers) | Sound, Vibration |
| **FCU** | 7 | 3 (filter, condensate, fan motor) | Sound, Vibration |
| **UPS** | 6 | 3 (battery visual, fan, capacitors) | Manual (battery tester) |
| **Transformer** | 5 | 3 (oil quality, bushings, OLTC) | Manual (oil sample) |
| **VAV** | 4 | 2 (actuator, flow sensor) | None |
| **Cooling Tower** | 6 | 3 (fill, nozzles, drift eliminator) | Sound, Vibration |

**Metric Template Structure:**
```json
{
  "equipment_type": "chiller",
  "metrics": {
    "chill_suction_press": {
      "description": "Refrigerant suction pressure",
      "unit": "bar",
      "data_source": "bms_sensor",
      "normal_range": [3.5, 5.5],
      "warning_range": [2.5, 3.5],
      "critical_range": [1.5, 2.5],
      "weight": 0.15,
      "measurement_interval_days": 1
    },
    "chill_sound_compressor": {
      "description": "Compressor sound level",
      "unit": "dBA",
      "data_source": "mobile_phone",
      "normal_range": [65, 85],
      "warning_range": [85, 95],
      "critical_range": [95, 105],
      "weight": 0.05,
      "measurement_interval_days": 7,
      "sampling_notes": "Record 10s at 1-5m from equipment"
    }
  },
  "manual_inspections": {
    "refrigerant_leak_check": {
      "description": "Check for refrigerant leaks using sniffer",
      "frequency_days": 30,
      "assigned_to": "technician",
      "data_source": "manual"
    }
  }
}
```

**Data Sources:**
- `bms_sensor`: Automatic polling from BMS (BACnet/Modbus)
- `mobile_phone`: Technician collects via mobile app (audio/vibration)
- `manual`: Manual measurement (gauges, test equipment, lab analysis)

**Returns:**
```json
{
  "building_id": "sandton",
  "equipment_detected": ["chiller", "ahu", "fcu", "generator"],
  "templates": {
    "chiller": {...},
    "ahu": {...},
    "fcu": {...},
    "generator": {...}
  },
  "total_metrics": 36,
  "total_inspections": 15
}
```

#### `configure_asset_metrics`
**Configure custom thresholds, weights, and intervals for asset metrics.**

**Parameters:**
- `building_id` (string, required): Building identifier
- `metric_config` (object, required): Configuration by equipment type

**Configuration Structure:**
```json
{
  "chiller": {
    "metrics": {
      "chill_suction_press": {
        "enabled": true,
        "normal_range": [3.5, 5.5],
        "warning_range": [2.5, 3.5],
        "critical_range": [1.5, 2.5],
        "weight": 0.20,
        "measurement_interval_days": 1,
        "custom_threshold": "Critical if below 2.0 bar for >5min"
      },
      "chill_sound_compressor": {
        "enabled": true,
        "normal_range": [70, 85],
        "warning_range": [85, 95],
        "critical_range": [95, 105],
        "weight": 0.10,
        "measurement_interval_days": 7
      }
    },
    "manual_inspections": {
      "refrigerant_leak_check": {
        "enabled": true,
        "frequency_days": 30,
        "assigned_to": "tech-lead"
      }
    }
  }
}
```

**Returns:**
```json
{
  "success": true,
  "building_id": "sandton",
  "config_saved": "asset_metrics.json",
  "metrics_configured": 36,
  "inspections_configured": 15,
  "updated_at": "2026-02-02T10:30:00Z"
}
```

---

## Transport Methods

### Method 1: stdio (Claude Desktop)

**Best for:** Local development, Claude Desktop app

**Configuration:**
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

**Advantages:**
- No network exposure
- Low latency
- Simple setup

**Limitations:**
- Single client only
- No web integration

---

### Method 2: SSE (Server-Sent Events)

**Best for:** Cloud Claude, web applications

**Endpoints:**

**SSE Stream:**
```bash
GET http://localhost:9095/api/mcp/sse
```

**POST Request:**
```bash
POST http://localhost:9095/api/mcp/sse/request
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_buildings",
    "arguments": {"region": "Gauteng"}
  }
}
```

**SSE Message Format:**
```
data: {"type": "event", "name": "tools/list", "data": {...}}

data: {"type": "event", "name": "initialize", "data": {...}}

data: [DONE]
```

**SSE Implementation Details:**

**Keep-Alive:**
- Heartbeat every 15 seconds
- Prevents connection timeout

**Reconnection:**
- Automatic reconnection with exponential backoff
- Last request ID replayed for at-least-once semantics

**Error Handling:**
- Errors sent as SSE events
- Connection stays open for recovery

**Message Types:**
| Type | Description |
|------|-------------|
| `event` | Normal data/event |
| `error` | Error with message |
| `keepalive` | Heartbeat (no data) |
| `[DONE]` | Stream end |

**Advantages:**
- Multiple clients
- Web integration
- Real-time streaming

**Limitations:**
- Requires network
- More complex setup

---

## Dual Data Source Pattern

All SIMBIOT tools implement graceful degradation:

```python
def _load_data():
    # 1. Try device_manager (real BMS)
    if device_manager and device_manager.initialized:
        return device_manager.get_devices()

    # 2. Fall back to JSON (demo mode)
    return json.load(open('data/mock_devices.json'))
```

**Read Priority:**
1. Supabase (via repository)
2. JSON files (fallback)

**Write Behavior:**
- Always write JSON
- Write Supabase if configured
- Response indicates storage method

---

## Safety & Security

### Safety Validation

All `write_device_point` calls validated through `SafetyEngine`:

| Rule Type | Description | Example |
|-----------|-------------|---------|
| `TemperatureRange` | Min/max temperature limits | 16-28°C range |
| `PressureLimit` | Max pressure thresholds | Chiller discharge < 250 psi |
| `Interlock` | Equipment interlocks | AHU off if fire alarm |
| `RuntimeLimit` | Max runtime hours | Pump < 24h continuous |
| `BrightnessLimit` | Lighting max brightness | DALI < 100% |

**Blocking Behavior:**
```json
{
  "success": false,
  "error": "Safety validation failed",
  "blocking_rule": {
    "type": "TemperatureRange",
    "reason": "Value 16°C below minimum safe temperature 18°C",
    "rule_id": "temp-range-001"
  }
}
```

### Audit Logging

All tool calls logged to `audit_log.json`:
- Tool name
- Parameters
- Result
- Timestamp
- User (if available)

---

## Testing

### Test stdio:
```bash
cd backend
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m app.mcp.simbiot_stdio
```

### Test SSE:
```bash
curl -N http://localhost:9095/api/mcp/sse
```

### Test specific tool:
```bash
curl -X POST http://localhost:9095/api/mcp/simbiot/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_buildings",
    "arguments": {"region": "Gauteng"}
  }'
```

---

## Troubleshooting

**Claude Desktop can't connect:**
- Verify PYTHONPATH includes backend directory
- Check Python executable path
- Enable debug logging in Claude Desktop

**SSE connection drops:**
- Check firewall settings
- Verify backend is running
- Check browser console for errors

**Tools return empty results:**
- Check device_manager initialized
- Verify JSON data files exist
- Check Supabase credentials

**Safety validation blocks writes:**
- Review safety rules in `data/safety_rules.json`
- Adjust thresholds if needed
- Use `write_device_point` with appropriate priority

---

## Version History

- **v2.0.0** (2026-02-02): Complete rewrite with all 23 tools documented, NLP details, SSE transport
- **v1.0.0** (2026-01-30): Initial release (12 tools documented - incomplete)
