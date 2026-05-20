---
title: "AI-Assisted Onboarding"
type: "guide"
status: "approved"
version: "2.0.0"
created: "2026-01-31"
updated: "2026-02-23"
author: "SENTINEL Development Team"
tags: ["onboarding", "bms", "import", "mcp", "ai", "desigo", "metasys", "ebi"]
domain: "general"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 20
---

# AI-Assisted Building Onboarding

Complete guide for onboarding new buildings into SENTINEL using the SIMBIOT MCP tools. This covers the full workflow from creating a building to configuring predictive maintenance metrics.

For deterministic stage progression on Site-002 (`commissioning -> shadow_live -> supervised -> automatic`), see [Phase 109C: Site-002 deterministic mode policy dry-run](109C-site-002-mode-policy-dry-run.md).

## Overview

SENTINEL uses 8 SIMBIOT MCP tools to onboard a building in a structured workflow. The AI assistant (Claude) drives the process, parsing BMS exports and auto-generating device/zone structures.

**Complete Onboarding Workflow:**

```
Step 1: create_building         → Create building config and folder structure
Step 2: import_point_list       → AI parses BMS point export, generates devices/zones
    OR: POST /api/niagara/discover/csv → Upload Desigo CSV with auto lighting classification
Step 3: add_building_devices    → Save parsed devices to system
Step 4: add_building_zones      → Save HVAC zones with equipment mappings
Step 5: add_building_desks      → Map desks to zones for comfort diagnosis (optional)
Step 6: activate_building       → Make building live in the system
Step 7: get_asset_metrics_template → Get ML metric templates for equipment types
Step 8: configure_asset_metrics → Customize thresholds for predictive maintenance
```

**Time to onboard:** Typically 30-60 minutes for a standard office building with the AI assistant.

### Alternative Step 2: CSV Upload with Lighting Discovery (Phase 130)

For buildings with Desigo CC + Tridonic net4more (or any BMS exposing lighting as BACnet), you can upload the raw CSV export directly:

```bash
curl -X POST "http://localhost:9095/api/niagara/discover/csv?site_id=site-002" \
  -F "file=@point_list_siemens-desigo.csv"
```

This auto-classifies both HVAC and lighting points in a single pass, recognizing 8 lighting-specific categories (brightness, lighting_power, lighting_energy, driver_temperature, lamp_hours, light_output, emergency_battery, emergency_test) alongside standard HVAC equipment types.

See [Tridonic DALI Discovery — CSV Ingestion](../05-integrations/tridonic-dali-discovery.md#desigo-csv-point-export-ingestion-phase-130) for full details.

## Step-by-Step: Onboarding a Siemens Desigo CC Building

This walkthrough uses a real example: onboarding a 3-floor office building running Siemens Desigo CC V5.0.

### Step 1: Create Building

The first step creates the building configuration and folder structure. The building starts inactive.

**Tool:** `create_building`

**Example:**
```json
{
  "building_id": "sandton",
  "name": "Sandton City Office Tower",
  "address": "83 Rivonia Road, Sandton, Johannesburg",
  "floors": ["L0", "L1", "L2"],
  "features": {
    "hvac": true,
    "dali": true,
    "desk_diagnosis": true,
    "energy_monitoring": true
  }
}
```

**What happens:**
- Creates directory: `backend/app/data/buildings/sandton/`
- Writes `building.json` config file
- Creates empty `zones.json` and `desks.json`
- Dual-writes to Supabase (if configured) + JSON backup
- Building status: **created** (not yet active)

**Output:**
```json
{
  "success": true,
  "building_id": "sandton",
  "status": "created",
  "storage": "supabase+json",
  "next_steps": [
    "Add desks to the building",
    "Add HVAC zones to the building",
    "Call activate_building with building_id='sandton'"
  ]
}
```

### Step 2: Import BMS Point List

This is the AI-powered step. You provide the raw BMS point export, and SENTINEL auto-parses it into devices and zones. For Desigo CC, use `bms_vendor: "desigo"`.

**Tool:** `import_point_list`

**Getting the point list from Desigo CC:**
1. Open Desigo CC Management Station
2. Navigate to Project > BACnet Network
3. Export all BACnet objects to CSV
4. Include: Object Name, Object Type, Instance, Description, Units, Current Value

**Example with Desigo CC points:**
```json
{
  "building_id": "sandton",
  "bms_vendor": "desigo",
  "site_code": "san",
  "point_list": [
    {
      "point_name": "AHU-L0-01.SupplyAirTemp",
      "object_type": "Analog Input",
      "instance": 1001,
      "description": "AHU Ground Floor Supply Air Temperature",
      "units": "degC",
      "value": 14.2
    },
    {
      "point_name": "AHU-L0-01.ReturnAirTemp",
      "object_type": "Analog Input",
      "instance": 1002,
      "description": "AHU Ground Floor Return Air Temperature",
      "units": "degC",
      "value": 23.5
    },
    {
      "point_name": "AHU-L0-01.FanStatus",
      "object_type": "Binary Input",
      "instance": 1003,
      "description": "AHU Ground Floor Supply Fan Status",
      "value": true
    },
    {
      "point_name": "AHU-L0-01.ChwValve",
      "object_type": "Analog Output",
      "instance": 1004,
      "description": "AHU Ground Floor CHW Valve Position",
      "units": "%",
      "value": 65
    },
    {
      "point_name": "FCU-L0-01.RoomTemp",
      "object_type": "Analog Input",
      "instance": 2001,
      "description": "FCU L0 Zone A Room Temperature",
      "units": "degC",
      "value": 22.5
    },
    {
      "point_name": "FCU-L0-01.Setpoint",
      "object_type": "Analog Value",
      "instance": 2002,
      "description": "FCU L0 Zone A Temperature Setpoint",
      "units": "degC",
      "value": 22.0
    },
    {
      "point_name": "FCU-L0-01.FanSpeed",
      "object_type": "Analog Output",
      "instance": 2003,
      "description": "FCU L0 Zone A Fan Speed",
      "units": "%",
      "value": 60
    },
    {
      "point_name": "VAV-L0-01.DamperPosition",
      "object_type": "Analog Output",
      "instance": 3001,
      "description": "VAV L0 Zone A Damper Position",
      "units": "%",
      "value": 75
    },
    {
      "point_name": "VAV-L0-01.AirflowRate",
      "object_type": "Analog Input",
      "instance": 3002,
      "description": "VAV L0 Zone A Airflow",
      "units": "L/s",
      "value": 250
    },
    {
      "point_name": "Chiller-01.ChwSupplyTemp",
      "object_type": "Analog Input",
      "instance": 4001,
      "description": "Chiller 1 CHW Supply Temperature",
      "units": "degC",
      "value": 6.5
    },
    {
      "point_name": "Chiller-01.ChwReturnTemp",
      "object_type": "Analog Input",
      "instance": 4002,
      "description": "Chiller 1 CHW Return Temperature",
      "units": "degC",
      "value": 12.0
    },
    {
      "point_name": "Chiller-01.CompressorStatus",
      "object_type": "Binary Input",
      "instance": 4003,
      "description": "Chiller 1 Compressor Running",
      "value": true
    }
  ]
}
```

**What happens:**
1. AI parses device names from point names using Desigo CC dot notation (e.g., `AHU-L0-01` from `AHU-L0-01.SupplyAirTemp`)
2. Determines device types: AHU, FCU, VAV, Chiller, etc.
3. Extracts floor information (L0, L1, L2)
4. Groups points by device
5. Normalizes point names to standard format (supply_air_temp, chw_valve, etc.)
6. Infers zone structure from FCU/VAV devices
7. Returns generated devices and zones for review

**Output:**
```json
{
  "success": true,
  "bms_vendor": "desigo",
  "analysis": {
    "total_points": 150,
    "unique_devices": 12,
    "device_types": {"ahu": 3, "fcu": 6, "vav": 3}
  },
  "generated": {
    "devices": 12,
    "zones": 6
  },
  "devices": [
    {
      "device_id": "san-san-ahu-001",
      "device_type": "ahu",
      "name": "AHU-L0-01",
      "location": "sandton L0",
      "protocol": "bacnet",
      "floor": "L0",
      "points": {
        "supply_air_temp": 14.2,
        "return_air_temp": 23.5,
        "fan_status": true,
        "chw_valve": 65
      }
    }
  ],
  "zones": [
    {
      "zone_id": "Zone-L0-01",
      "floor": "L0",
      "fcu_id": "san-san-fcu-001",
      "vav_id": "san-san-vav-001",
      "ahu_id": "san-san-ahu-001",
      "setpoint": 22.0
    }
  ],
  "next_steps": [
    "Review the generated devices and zones",
    "Call add_building_devices to save devices",
    "Call add_building_zones to save zones",
    "Call activate_building to make the building active"
  ]
}
```

**Important:** `import_point_list` does NOT save to the database. It returns the parsed data for you to review. You save it in the next steps.

### Step 3: Save Devices

After reviewing the parsed output, save the devices to the system.

**Tool:** `add_building_devices`

**Example:**
```json
{
  "building_id": "sandton",
  "site_code": "san",
  "devices": [
    {
      "device_type": "ahu",
      "name": "AHU-L0-01",
      "location": "Sandton L0 Plantroom",
      "protocol": "bacnet",
      "points": {
        "supply_air_temp": 14.2,
        "return_air_temp": 23.5,
        "fan_status": true,
        "chw_valve": 65
      },
      "metadata": {
        "manufacturer": "Siemens",
        "model": "AHU-3000"
      }
    },
    {
      "device_type": "fcu",
      "name": "FCU-L0-01",
      "location": "Sandton L0 Zone A",
      "protocol": "bacnet",
      "points": {
        "room_temp": 22.5,
        "setpoint": 22.0,
        "fan_speed": 60
      }
    },
    {
      "device_type": "chiller",
      "name": "Chiller-01",
      "location": "Sandton Basement Plantroom",
      "protocol": "bacnet",
      "points": {
        "chw_supply_temp": 6.5,
        "chw_return_temp": 12.0,
        "compressor_status": true
      },
      "metadata": {
        "manufacturer": "York",
        "model": "YCIV",
        "capacity_kw": 500
      }
    }
  ]
}
```

**What happens:**
- Auto-generates device IDs: `san-san-ahu-001`, `san-san-fcu-001`, etc.
- Merges with existing devices in mock_devices.json
- Returns all new device IDs

**Output:**
```json
{
  "success": true,
  "building_id": "sandton",
  "devices_added": 12,
  "device_ids": ["san-san-ahu-001", "san-san-fcu-001", "san-san-chiller-001", ...]
}
```

### Step 4: Save HVAC Zones

Save the zone-to-equipment mappings. Each zone links to its FCU, VAV, and AHU.

**Tool:** `add_building_zones`

**Example:**
```json
{
  "building_id": "sandton",
  "zones": [
    {
      "zone_id": "Zone-L0-A",
      "zone_name": "Ground Floor Zone A",
      "floor": "L0",
      "fcu_id": "san-san-fcu-001",
      "vav_id": "san-san-vav-001",
      "ahu_id": "san-san-ahu-001",
      "setpoint": 22.0,
      "typical_occupancy": 25,
      "area_sqm": 300,
      "desk_range": "001-025"
    },
    {
      "zone_id": "Zone-L0-B",
      "zone_name": "Ground Floor Zone B",
      "floor": "L0",
      "fcu_id": "san-san-fcu-002",
      "vav_id": "san-san-vav-002",
      "ahu_id": "san-san-ahu-001",
      "setpoint": 22.0
    }
  ]
}
```

**What happens:**
- Dual-writes to Supabase (hvac_zones table) + zones.json
- Links zones to devices via device IDs
- Enables zone-based comfort diagnosis and optimization

### Step 5: Add Desks (Optional)

If you have a floor plan, add desk mappings for individual comfort diagnosis. This enables SENTINEL to trace a comfort complaint from a specific desk to its HVAC zone, FCU, DALI lighting, and environmental factors.

**Tool:** `add_building_desks`

**Example:**
```json
{
  "building_id": "sandton",
  "desks": [
    {
      "desk_id": "001",
      "zone_id": "Zone-L0-A",
      "floor": "L0",
      "near_window": true,
      "orientation": "N",
      "near_diffuser": "VAV-L0-01A",
      "near_printer": false,
      "department": "Engineering",
      "dali_zone": "Zone-L0-A",
      "sensor_id": "PIR-L0-A-001",
      "luminaire_ids": ["LUM-L0-001", "LUM-L0-002"],
      "dali_controller": "DALI-L0-01"
    },
    {
      "desk_id": "002",
      "zone_id": "Zone-L0-A",
      "floor": "L0",
      "near_window": false,
      "near_printer": true,
      "department": "Engineering"
    }
  ]
}
```

**What this enables:**
- Desk-level comfort complaints ("I'm hot at desk 201") traced to exact zone, FCU, and AHU
- Solar heat gain analysis (near_window + orientation)
- Draft detection (near_diffuser)
- Heat source awareness (near_printer)
- DALI lighting integration for coordinated HVAC + lighting optimization

### Step 6: Activate Building

Once all configuration is done, activate the building to make it visible in the system.

**Tool:** `activate_building`

**Example:**
```json
{
  "building_id": "sandton",
  "set_default": true
}
```

**What happens:**
- Adds building to `_registry.json` active list
- Sets as default building if `set_default: true`
- Reloads building loader to refresh system state
- Building now appears in the SENTINEL dashboard and API

**Output:**
```json
{
  "success": true,
  "building_id": "sandton",
  "status": "active",
  "is_default": true,
  "message": "Building 'sandton' is now active"
}
```

### Step 7: Get Asset Metric Templates

After the building is active, configure predictive maintenance. SENTINEL generates metric templates based on the equipment types in the building.

**Tool:** `get_asset_metrics_template`

**Example:**
```json
{
  "building_id": "sandton"
}
```

The tool auto-detects equipment types from the building's devices and zones. For our Sandton example, it would find: AHU, FCU, VAV, Chiller.

**Output (excerpt):**
```json
{
  "success": true,
  "equipment_types_detected": ["ahu", "fcu", "vav", "chiller"],
  "metric_templates": {
    "chiller": {
      "category": "HVAC/Refrigeration",
      "metrics": [
        {
          "metric_id": "chill_suction_press",
          "name": "Suction Pressure",
          "unit": "bar",
          "data_source": "bms_sensor",
          "normal_range": [3.5, 5.5],
          "warning_range": [2.5, 6.5],
          "critical_range": [1.5, 7.5],
          "weight": 0.15
        },
        {
          "metric_id": "chill_sound_compressor",
          "name": "Compressor Sound Level",
          "unit": "dBA",
          "data_source": "mobile_phone",
          "measurement_type": "audio",
          "normal_range": [65, 85],
          "warning_range": [85, 95],
          "critical_range": [95, 105],
          "weight": 0.05,
          "sampling_notes": "Record 10s at 1m from compressor"
        }
      ],
      "manual_inspections": [
        {
          "inspection_id": "chill_refrigerant_leak",
          "name": "Refrigerant Leak Check",
          "frequency_days": 90,
          "parameters": ["leak_detected", "pressure_drop"]
        }
      ]
    },
    "ahu": {
      "category": "HVAC/Air Handling",
      "metrics": [...]
    }
  },
  "total_metrics": 32,
  "total_inspections": 14
}
```

**Data source types:**
- `bms_sensor` - Automatic from Desigo CC BACnet points
- `mobile_phone` - Technician uses SENTINEL mobile app (audio/vibration sensors)
- `manual` - Manual measurements with test equipment or lab analysis

### Step 8: Configure Asset Metrics

Review and customize the metric thresholds, weights, and inspection schedules for the building's specific equipment.

**Tool:** `configure_asset_metrics`

**Example:**
```json
{
  "building_id": "sandton",
  "metric_config": {
    "chiller": {
      "metrics": {
        "chill_suction_press": {
          "enabled": true,
          "normal_range": [3.5, 5.5],
          "weight": 0.15,
          "measurement_interval_days": 1
        },
        "chill_sound_compressor": {
          "enabled": true,
          "normal_range": [65, 85],
          "weight": 0.05,
          "measurement_interval_days": 7
        }
      },
      "manual_inspections": {
        "chill_refrigerant_leak": {
          "enabled": true,
          "frequency_days": 90,
          "assigned_to": "HVAC Technician 1"
        }
      }
    },
    "ahu": {
      "metrics": {
        "ahu_supply_temp": {
          "enabled": true,
          "normal_range": [12, 16],
          "weight": 0.2
        }
      }
    }
  },
  "save_to_file": true
}
```

**What happens:**
- Merges your customizations with the template defaults
- Saves to `buildings/sandton/asset_metrics.json`
- ML models will train on collected data after 3-6 months
- Health scores calculate based on configured weights and thresholds

**Output:**
```json
{
  "success": true,
  "building_id": "sandton",
  "metrics_configured": 32,
  "equipment_types": ["ahu", "fcu", "vav", "chiller"],
  "message": "Configured 32 metrics across 4 equipment types"
}
```

## Onboarding Complete

After completing all 8 steps, the building is fully configured with:
- Building profile with floors and features
- All BMS devices with BACnet point mappings
- HVAC zones linked to devices
- Desk-to-zone mappings for comfort diagnosis (optional)
- Predictive maintenance metrics with thresholds
- Building active and visible in SENTINEL dashboard

The system will begin collecting data from the BMS, and ML models will train on the data over 3-6 months for predictive maintenance.

## BMS Data Request Template

When requesting data from the BMS operator, use this template:

```
Subject: SENTINEL Onboarding - BMS Data Request for [Building Name]

We need the following exports from Desigo CC (or equivalent BMS):

1. POINT LIST EXPORT (most important)
   - All BACnet objects
   - Include: Object Name, Object Type, Instance, Description, Units, Current Value
   - Export from Management Station > Project > BACnet Network

2. CONTROLLER INFORMATION
   - List of PXC/PXM controllers
   - For each: Name, IP Address, BACnet Device ID, Area Served

3. ALARM HISTORY EXPORT (CSV) - optional
   - Last 7-14 days of alarm history
   - All severity levels (Critical, Warning, Info)

4. TREND DATA EXPORT (CSV) - optional
   - Sample of key points (temps, flows, statuses)
   - 24-48 hours minimum

5. SYSTEM DETAILS
   - BMS Software version (e.g., Desigo CC V5.0)
   - Naming convention documentation (if available)
```

## Supported BMS Systems

The `import_point_list` tool supports these BMS vendors with their naming conventions:

| Vendor | bms_vendor value | Example Point Name | Separator |
|--------|-----------------|-------------------|-----------|
| **Siemens Desigo CC** | `desigo` or `siemens` | `AHU-L12-01.SupplyAirTemp` | Dot (.) |
| **Johnson Controls Metasys** | `metasys` or `jci` | `NAE-1/AHU-1.SAT` | Slash + dot |
| **Honeywell EBI** | `ebi` or `honeywell` | `AHU_01_SAT` | Underscore |
| **Schneider EcoStruxure** | `ecostruxure` or `schneider` | `Building/Floor12/AHU01/SupplyAirTemp` | Path slashes |
| **Tridium Niagara** | `niagara` or `tridium` | `station/Drivers/BACnet/AHU_01/SAT` | Deep path |
| **Trend Controls** | `trend` | `AHU1.SAT` | Short dot |
| **Auto-detect** | `auto` (default) | (any) | Auto-detects from patterns |

### Auto-Detection Logic

If you don't specify `bms_vendor`, the tool auto-detects based on naming patterns:
- Path separators (`/`) with deep paths -> Niagara
- Path separators with building hierarchy -> EcoStruxure
- `NAE` prefix -> Metasys
- Heavy underscore use with floor patterns -> Honeywell EBI
- Dot separators with device-point format -> Desigo or Trend

For best results, always specify the `bms_vendor` when you know the system.

## Point Name Parsing

### 3-Tier Vendor-Agnostic Classification

The classifier uses a metadata-first approach that works with any BMS vendor:

1. **Tier 1 — Metadata (preferred):** When equipment JSON files provide `_equipment_id`, `_equipment_type`, `_point_type`, they are used directly with HIGH confidence. No regex needed.
2. **Tier 2 — ID extraction:** When metadata says `equipment_type: "unknown"`, the type code is extracted from the equipment ID segments (e.g., `COLD` from `site-003-UMH-COLD-B1-001`).
3. **Tier 3 — Regex fallback:** Pattern matching for raw BACnet points without metadata.

### Supported Equipment Types (30+)

| Category | Type Codes | Device Type |
|----------|-----------|-------------|
| **HVAC** | AHU, FCU, VAV, CH/CHILLER, CT, SPLIT, CRAC, PUMP, BOILER, COLD, KEF | Air Handling, Fan Coil, VAV, Chiller, Cooling Tower, Split Unit, CRAC, Pump, Boiler, Cold Room, Kitchen Extract Fan |
| **Electrical** | GEN, UPS, ATS, MSB, DB, MTR/METER, TX, PFC, FDR, MV | Generator, UPS, Transfer Switch, Switchboard, Distribution Board, Meter, Transformer, PFC, Feeder, Medium Voltage |
| **Lighting** | DALI, LUM | DALI Controller, Luminaire |
| **Fire/Safety** | FIRE | Fire Panel |
| **Security** | ACC, CCTV | Access Control, CCTV Camera |
| **Transport** | LIFT | Lift/Elevator |
| **Medical** | MEDGAS | Medical Gas System |
| **Controllers** | JACE, PXC, BMS | JACE Controller, Siemens PXC, BMS Controller |

### Floor Extraction (Vendor-Agnostic)

Floor codes are extracted from any position in hyphen/dot-separated equipment IDs:

| Pattern | Example ID | Extracted Floor |
|---------|-----------|-----------------|
| L## | `site-003-UMH-AHU-L3-ICU` | L3 |
| B## | `site-003-UMH-GEN-B1-001` | B1 |
| G | `S002-AHU-G-01` | G |
| R | `site-003-UMH-CT-R-001` | R (Roof) |

Works for Niagara, Desigo, Schneider, Honeywell, Trend, and generic BACnet naming.

## Device ID Naming Convention

Auto-generated device IDs follow this format:
```
{site_code}-{building_code}-{device_type}-{sequence}
```

Examples:
- `san-san-ahu-001` (Sandton site, Sandton building, AHU #1)
- `san-san-fcu-003` (Sandton site, Sandton building, FCU #3)
- `san-san-chiller-001` (Sandton site, Sandton building, Chiller #1)

## Dual-Write Storage

All onboarding data is written to two locations for resilience:

1. **Supabase** (primary) - `buildings`, `hvac_zones`, `desks` tables
2. **JSON** (backup/offline) - `backend/app/data/buildings/{building_id}/`

```
backend/app/data/buildings/
+-- _registry.json          (active buildings, default building)
+-- sandton/
    +-- building.json        (building config)
    +-- zones.json           (HVAC zones)
    +-- desks.json           (desk mappings)
    +-- devices.json         (device references)
    +-- asset_metrics.json   (metric configuration)
```

If Supabase is unavailable, data is written to JSON only. The response indicates storage: `"storage": "supabase+json"` or `"storage": "json"`.

## Troubleshooting

### Points not being grouped correctly
- Specify the correct `bms_vendor` instead of relying on auto-detection
- Check that point names follow the vendor's standard naming convention
- You can manually assign devices using `add_building_devices` if parsing fails

### Missing zone relationships
- `import_point_list` infers zones from FCU/VAV groupings
- If zones aren't detected, provide them manually with `add_building_zones`
- Ensure each zone has at minimum a `zone_id` and `floor`

### Building doesn't appear after creation
- Call `activate_building` - buildings are inactive by default
- Check `_registry.json` has the building in `active_buildings`

### Import errors
- Empty `point_name` fields - ensure all points have names
- Building doesn't exist - run `create_building` first
- Invalid JSON format - validate your point list data

## Alternative Onboarding: Niagara Connection Wizard

For buildings running Tridium Niagara 4, a faster onboarding path is available via the **Niagara Connection Wizard** on the Integration Monitoring page. This 4-step wizard connects directly to the Niagara supervisor, discovers BACnet points, and creates equipment models — no file exports needed.

See [Niagara BMS Connection Wizard](niagara-connection-wizard.md) for details.

## Related Documentation

- [Niagara BMS Connection Wizard](niagara-connection-wizard.md) - Direct Niagara supervisor connection wizard
- [MCP Tools Reference](../03-api-reference/mcp-tools-reference.md) - Full tool schemas
- [Naming Conventions](../02-architecture/NAMING_CONVENTIONS.md) - Device ID patterns
- [BMS Fundamentals](../05-bms-concepts/bms-fundamentals.md) - BMS concepts
- [Safety Interlocks](../06-safety-compliance/safety-interlocks-engine.md) - Safety system
