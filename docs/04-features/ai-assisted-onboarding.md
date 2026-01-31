---
title: "AI-Assisted Onboarding"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-01-31"
updated: "2026-01-31"
author: "SENTINEL Development Team"
tags: ["onboarding", "bms", "import", "mcp", "ai"]
domain: "general"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 15
---

# AI-Assisted Onboarding

Guide for onboarding new buildings using AI-assisted tools that parse BMS exports.

## Overview

SENTINEL provides MCP tools that allow AI assistants to help onboard new buildings by parsing standard BMS export formats:

- **Point List Export** - BACnet object names, types, instances
- **Controller List** - PXC/DDC controllers with IPs and areas served
- **Alarm History** - Historical alarms for pattern analysis
- **Trend Data** - Historical trends for baseline analysis

## BMS Data Request Template

When requesting data from the BMS operator, use this template:

```
Subject: SENTINEL Onboarding - BMS Data Request for [Building Name]

We need the following exports from Desigo CC (or equivalent BMS):

1. ALARM HISTORY EXPORT (CSV)
   - Last 7-14 days of alarm history
   - All severity levels (Critical, Warning, Info)
   - Include: Timestamp, Point Name, Description, State

2. TREND DATA EXPORT (CSV)
   - Sample of key points (mix of temps, flows, statuses)
   - 24-48 hours minimum, 1-minute intervals if available
   - Include column headers

3. POINT LIST EXPORT
   - All BACnet objects
   - Include: Object Name, Object Type, Instance, Description, Units, Current Value

4. CONTROLLER INFORMATION
   - List of PXC controllers
   - For each: Name, IP Address, BACnet Device ID, Area Served

5. SYSTEM DETAILS
   - BMS Software version
   - Naming convention documentation (if available)
```

## MCP Tools for Onboarding

### 1. import_point_list

The primary AI-assisted onboarding tool. Parses BACnet point lists and auto-generates device/zone structures.

**Input:**
```json
{
  "building_id": "sandton",
  "point_list": [
    {
      "point_name": "AHU-L12-01.SupplyAirTemp",
      "object_type": "Analog Input",
      "instance": 1001,
      "description": "AHU L12 Supply Air Temperature",
      "units": "°C",
      "value": 14.2
    },
    {
      "point_name": "FCU-L12-03.RoomTemp",
      "object_type": "Analog Input",
      "instance": 2001,
      "description": "FCU L12 North Room Temperature",
      "units": "°C",
      "value": 22.5
    }
  ]
}
```

**What it does:**
1. Parses device names from point names (e.g., "AHU-L12-01" from "AHU-L12-01.SupplyAirTemp")
2. Determines device types (AHU, FCU, VAV, Chiller, etc.)
3. Groups points by device
4. Creates device entries with point mappings
5. Infers zone structure from FCU/VAV patterns

**Output:**
```json
{
  "success": true,
  "analysis": {
    "total_points": 150,
    "unique_devices": 12,
    "device_types": {"ahu": 3, "fcu": 6, "vav": 3}
  },
  "generated": {
    "devices": 12,
    "zones": 6
  },
  "devices": [...],
  "zones": [...],
  "next_steps": [
    "Review the generated devices and zones",
    "Call add_building_devices to save devices",
    "Call add_building_zones to save zones",
    "Call activate_building to make the building active"
  ]
}
```

### 2. import_controller_list

Imports BMS controller information for network topology.

**Input:**
```json
{
  "building_id": "sandton",
  "controllers": [
    {
      "name": "PXC-L12-01",
      "ip_address": "192.168.1.101",
      "bacnet_device_id": 12001,
      "area_served": "Level 12 North",
      "controller_type": "PXC",
      "equipment": ["AHU-L12-01", "VAV-L12-03A", "FCU-L12-03"]
    }
  ]
}
```

### 3. add_building_zones

Adds HVAC zones with equipment mappings.

**Input:**
```json
{
  "building_id": "sandton",
  "zones": [
    {
      "zone_id": "Zone-L12-N",
      "floor": "L12",
      "fcu_id": "san-san-fcu-001",
      "vav_id": "san-san-vav-001",
      "ahu_id": "san-san-ahu-001",
      "setpoint": 22.0,
      "desk_range": "201-206"
    }
  ]
}
```

### 4. add_building_desks

Adds desk definitions for comfort diagnosis.

**Input:**
```json
{
  "building_id": "sandton",
  "desks": [
    {
      "desk_id": "201",
      "zone_id": "Zone-L12-N",
      "floor": "L12",
      "context": "near_window",
      "occupant": "John Smith"
    }
  ]
}
```

### 5. add_building_devices

Adds BMS devices to the system.

**Input:**
```json
{
  "building_id": "sandton",
  "devices": [
    {
      "device_type": "ahu",
      "name": "AHU-L12-01",
      "location": "Sandton L12 Plantroom",
      "protocol": "bacnet",
      "points": {
        "supply_air_temp": 14.2,
        "fan_status": true,
        "chw_valve": 65
      }
    }
  ]
}
```

## Onboarding Workflow

### Step 1: Create Building

```
AI: I'll create the building configuration.
> create_building(building_id="sandton", name="Sandton Office Park",
                  floors=["L10", "L11", "L12"])
```

### Step 2: Import Point List

```
AI: Now I'll parse the BMS point list to identify devices and zones.
> import_point_list(building_id="sandton", point_list=[...])

Result: Found 12 devices (3 AHU, 6 FCU, 3 VAV) and inferred 6 zones.
```

### Step 3: Review and Save

```
AI: The analysis looks correct. I'll save the devices and zones.
> add_building_devices(building_id="sandton", devices=[...])
> add_building_zones(building_id="sandton", zones=[...])
```

### Step 4: Add Desks (Optional)

```
AI: Do you have a desk layout? I can add desk-to-zone mappings for comfort diagnosis.
User: Yes, here's the floor plan data...
> add_building_desks(building_id="sandton", desks=[...])
```

### Step 5: Activate Building

```
AI: Everything is configured. I'll activate the building now.
> activate_building(building_id="sandton", set_default=true)

Result: Building 'sandton' is now active and set as default.
```

## Point Name Parsing

The import_point_list tool recognizes common BMS naming patterns:

| Pattern | Example | Device Type |
|---------|---------|-------------|
| AHU-xxx | AHU-L12-01 | Air Handling Unit |
| FCU-xxx | FCU-L12-03 | Fan Coil Unit |
| VAV-xxx | VAV-L12-03A | Variable Air Volume |
| CH-xxx, Chiller | CH-001, Chiller-1 | Chiller |
| CT-xxx | CT-001 | Cooling Tower |
| PUMP-xxx, CHWP | CHWP-001 | Pump |

Floors are extracted from patterns like:
- L12, L11 (Level 12, Level 11)
- B1, B2 (Basement 1, 2)
- GF, G (Ground Floor)

## Supported BMS Systems

The `import_point_list` tool supports these BMS vendors with their naming conventions:

| Vendor | bms_vendor value | Example Point Name |
|--------|-----------------|-------------------|
| **Siemens Desigo CC** | `desigo` or `siemens` | `AHU-L12-01.SupplyAirTemp` |
| **Johnson Controls Metasys** | `metasys` or `jci` | `NAE-1/AHU-1.SAT`, `AHU1.SA-T` |
| **Honeywell EBI** | `ebi` or `honeywell` | `AHU_01_SAT`, `FCU_L12_03_ZNT` |
| **Schneider EcoStruxure** | `ecostruxure` or `schneider` | `Building/Floor12/AHU01/SupplyAirTemp` |
| **Tridium Niagara** | `niagara` or `tridium` | `station/Drivers/BACnet/AHU_01/SAT` |
| **Trend Controls** | `trend` | `AHU1.SAT`, `FCU1.RT` |
| **Auto-detect** | `auto` (default) | Tries common patterns |

### Vendor Selection

If you know the BMS vendor, specify it for better parsing accuracy:

```json
{
  "building_id": "sandton",
  "bms_vendor": "desigo",
  "point_list": [...]
}
```

If not specified, the tool auto-detects based on naming patterns:
- Path separators (`/`) → Niagara or EcoStruxure
- NAE prefix → Metasys
- Heavy underscore use → Honeywell EBI
- Dot separators → Desigo or Trend

## Troubleshooting

### Points not being grouped correctly

If device names aren't being parsed correctly, you can:
1. Provide a naming convention hint in the conversation
2. Manually specify device mappings using add_building_devices

### Missing zone relationships

If zones aren't being inferred correctly:
1. Provide the zone-to-equipment mapping manually
2. Use add_building_zones with explicit FCU/VAV/AHU IDs

### Import errors

Common issues:
- Empty point_name fields - ensure all points have names
- Invalid JSON format - validate your point list data
- Building doesn't exist - create_building first

## Related Documentation

- [MCP Tools Reference](../03-api-reference/mcp-tools-reference.md) - Full tool schemas
- [Naming Conventions](../02-architecture/naming-conventions.md) - Device ID patterns
- [BMS Fundamentals](../05-bms-concepts/bms-fundamentals.md) - BMS concepts
