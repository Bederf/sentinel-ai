---
title: "DALI-HVAC Cross-System Integration"
type: "architecture"
status: "approved"
version: "1.0.0"
created: "2026-01-31"
updated: "2026-01-31"
author: "SENTINEL Development Team"
tags: ["dali", "hvac", "lighting", "occupancy", "comfort", "integration"]
domain: "lighting"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# DALI-HVAC Cross-System Integration

Intelligent comfort diagnosis combining HVAC zone control, DALI-2 lighting, and occupancy sensing for Sandton building.

## Overview

The DALI-HVAC integration enables SENTINEL to diagnose comfort complaints using data from multiple building systems:

- **HVAC**: Temperature, setpoints, FCU/VAV/AHU status
- **DALI Lighting**: Lux levels, luminaire status, dimming
- **Occupancy**: PIR sensors, zone occupancy percentages

### Hero Use Case

```
User: "I'm too hot at desk 201"

SENTINEL analyzes:
├── Desk 201 → Zone-L12-N → FCU-L12-03
├── HVAC: 22.5°C (setpoint 22.0°C) - running normally
├── DALI Lux: 850 lux at desk - HIGH (direct sunlight)
├── Desk context: near_window=true, afternoon
└── Zone occupancy: 42%

Diagnosis:
  Root cause: "Solar heat gain - desk near west-facing window"
  Confidence: HIGH

Suggestions:
  1. Lower FCU-L12-03 setpoint to 20°C for 2 hours
  2. Dim zone lighting to 40% to reduce heat load
  3. Increase VAV-L12-03A airflow to desk area
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Comfort Complaint Flow                             │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   User Input: "Too hot at desk 201"                                  │
│         │                                                             │
│         ▼                                                             │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │              ComfortComplaintHandler                         │    │
│   │              (complaint_handler.py)                          │    │
│   │                                                              │    │
│   │  • Desk lookup (flexible: "201", "L12-201", "Desk 201")     │    │
│   │  • Zone mapping (Desk → Zone → FCU/VAV/AHU)                 │    │
│   │  • Desk context (near_window, near_diffuser, near_printer)  │    │
│   └─────────────────────┬───────────────────────────────────────┘    │
│                         │                                             │
│         ┌───────────────┴───────────────┐                            │
│         ▼                               ▼                             │
│   ┌─────────────────┐           ┌─────────────────┐                  │
│   │ BuildingLoader  │           │  DALI Service   │                  │
│   │                 │           │                 │                  │
│   │ • zones.json    │           │ • Lux sensors   │                  │
│   │ • desks.json    │           │ • PIR occupancy │                  │
│   │ • FCU/VAV/AHU   │           │ • Luminaires    │                  │
│   │ • Temp/Setpoint │           │ • Zone summary  │                  │
│   └────────┬────────┘           └────────┬────────┘                  │
│            │                             │                            │
│            └──────────┬──────────────────┘                            │
│                       ▼                                               │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │              CrossSystemAnalyzer                             │    │
│   │              (cross_system_analyzer.py)                      │    │
│   │                                                              │    │
│   │  • Combine HVAC + DALI + Occupancy data                     │    │
│   │  • Solar heat gain detection (lux > 800)                    │    │
│   │  • HVAC fault detection                                      │    │
│   │  • Occupancy correlation                                     │    │
│   │  • Generate actionable suggestions                           │    │
│   └─────────────────────┬───────────────────────────────────────┘    │
│                         │                                             │
│                         ▼                                             │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │              ComplaintDiagnosis                              │    │
│   │                                                              │    │
│   │  • root_cause: "Solar heat gain from windows..."            │    │
│   │  • confidence: "high" | "medium" | "low"                    │    │
│   │  • suggestions: ["Lower FCU setpoint...", "Dim lights..."] │    │
│   │  • needs_dispatch: true | false                             │    │
│   └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## Data Sources

### HVAC Data (zones.json)

Location: `backend/app/data/buildings/sandton/zones.json`

```json
{
  "zone_id": "Zone-L12-N",
  "zone_name": "Level 12 North",
  "floor": "L12",
  "fcu_id": "FCU-L12-03",
  "vav_id": "VAV-L12-03A",
  "ahu_id": "AHU-L12-01",
  "temp_sensor": "TS-L12-03",
  "co2_sensor": "CO2-L12-03",
  "setpoint": 22.0,
  "current_temp": 22.5,
  "status": "running"
}
```

### DALI Data (dali_mock_data.json)

Location: `backend/app/data/dali_mock_data.json`

**Controllers** (57 total):
```json
{
  "controller_id": "DALI-L12-01",
  "name": "Level 12 North A",
  "location": "DB Room L12",
  "status": "online",
  "channels": 3
}
```

**Sensors** (46 sample, 1315 in production):
```json
{
  "sensor_id": "PIR-L12-N-001",
  "controller_id": "DALI-L12-01",
  "zone_id": "Zone-L12-N",
  "desk_id": "L12-D001",
  "occupancy": true,
  "lux_level": 450.0
}
```

**Luminaires** (32 sample, 619 in production):
```json
{
  "luminaire_id": "LUM-L12-N-001",
  "controller_id": "DALI-L12-01",
  "zone_id": "Zone-L12-N",
  "current_level": 75,
  "power_consumption": 26.25,
  "fault_status": false
}
```

### Desk Data (desks.json)

Location: `backend/app/data/buildings/sandton/desks.json`

```json
{
  "desk_id": "201",
  "floor": "Level 12",
  "zone_id": "Zone-L12-N",
  "near_window": true,
  "near_diffuser": null,
  "near_printer": false,
  "department": "Finance"
}
```

## Key Components

### 1. CrossSystemAnalyzer

**File:** `backend/app/services/cross_system_analyzer.py`

Combines data from HVAC and DALI systems for intelligent diagnosis.

```python
from app.services.cross_system_analyzer import get_cross_system_analyzer

analyzer = get_cross_system_analyzer()

# Analyze comfort complaint
diagnosis = analyzer.analyze_comfort_complaint(
    zone_id="Zone-L12-N",
    complaint_type="too_hot",
    desk_id="201"
)

print(diagnosis.root_cause)      # "Solar heat gain from windows..."
print(diagnosis.confidence)       # "high"
print(diagnosis.suggestions)      # ["Lower FCU...", "Dim lights..."]
```

**Key Methods:**

| Method | Description |
|--------|-------------|
| `analyze_comfort_complaint()` | Main diagnosis entry point |
| `get_zone_context_for_chat()` | Get formatted zone context for AI chat |
| `refresh_hvac_data()` | Reload HVAC data from zones.json |

### 2. ComfortComplaintHandler

**File:** `backend/app/services/complaint_handler.py`

Links desk locations to HVAC equipment and handles complaint workflow.

```python
from app.services.complaint_handler import get_complaint_handler

handler = get_complaint_handler()

# Lookup desk BMS context
context = handler.lookup_desk_bms("201")
# Returns: desk, zone, bms_context (fcu_id, vav_id, etc.)

# Handle complaint with full diagnosis
diagnosis = handler.handle_complaint(
    desk_id="201",
    complaint_type="too_hot",
    user_name="John",
    description="Very warm at my desk"
)
```

**Key Methods:**

| Method | Description |
|--------|-------------|
| `lookup_desk_bms()` | Desk ID → Zone → FCU → Sensors |
| `handle_complaint()` | Full complaint handling with diagnosis |
| `get_zone_context()` | Combined HVAC + DALI context for zone |
| `get_complaint_history()` | Pattern analysis of complaints |

### 3. DALIService

**File:** `backend/app/services/dali_service.py`

Provides access to DALI lighting and occupancy data.

```python
from app.services.dali_service import get_dali_service

dali = get_dali_service()

# Get zone occupancy
occupancy = dali.get_zone_occupancy("Zone-L12-N")
print(occupancy.occupancy_percent)  # 42.0
print(occupancy.avg_lux_level)      # 450.0

# Get zone lighting
lighting = dali.get_zone_lighting("Zone-L12-N")
print(lighting.avg_dim_level)       # 75.0
print(lighting.faulty_count)        # 0

# Get sensor by desk
sensor = dali.get_sensor_by_desk("L12-D001")
print(sensor.lux_level)             # 450.0
print(sensor.occupancy)             # True
```

## API Endpoints

### Complaints API

**POST /api/complaints/diagnose**
```json
{
  "desk_id": "201",
  "complaint_type": "too_hot",
  "user_name": "John",
  "description": "Very warm near window"
}
```

Response:
```json
{
  "complaint_id": "abc123",
  "desk": { "desk_id": "201", "zone_id": "Zone-L12-N", ... },
  "zone": { "zone_id": "Zone-L12-N", "fcu_id": "FCU-L12-03", ... },
  "diagnosis": "Zone at 22.5C (setpoint 22.0C) | HIGH DAYLIGHT 850 lux",
  "root_cause": "Solar heat gain - desk near west-facing window",
  "confidence": "high",
  "suggestions": [
    "Lower FCU-L12-03 setpoint to 20°C for 2 hours",
    "Dim zone lighting to 40% to reduce heat load",
    "Increase VAV-L12-03A airflow to desk area"
  ],
  "needs_dispatch": false
}
```

### DALI API

**GET /api/dali/zones/{zone_id}/summary**
```json
{
  "occupancy": {
    "zone_id": "Zone-L12-N",
    "total_sensors": 10,
    "occupied_sensors": 4,
    "occupancy_percent": 40.0,
    "avg_lux_level": 450.0
  },
  "lighting": {
    "zone_id": "Zone-L12-N",
    "total_luminaires": 5,
    "active_luminaires": 5,
    "avg_dim_level": 75.0,
    "faulty_count": 0
  }
}
```

**GET /api/dali/building/occupancy**
```json
{
  "floors": [
    { "floor": "L10", "occupancy_percent": 35.0 },
    { "floor": "L11", "occupancy_percent": 28.0 },
    { "floor": "L12", "occupancy_percent": 42.0 }
  ],
  "total_sensors": 1315,
  "total_occupied": 438,
  "overall_occupancy_percent": 33.3
}
```

## Diagnosis Logic

### Solar Heat Gain Detection

```python
# Triggered when:
# - complaint_type == "too_hot"
# - desk lux > 800 OR zone max lux > 800
# - HVAC is operating normally (temp near setpoint)

if complaint_type == "too_hot" and (desk_lux > 800 or max_lux > 800):
    if hvac["temp"] <= hvac["setpoint"] + 0.5:
        # HVAC is fine, solar is the issue
        cause = "Solar heat gain from windows"
        confidence = "high"
        suggestions = [
            f"Dim zone lighting from {lighting_level}% to 30%",
            f"Lower FCU setpoint from {setpoint}°C to {setpoint - 2}°C",
            "Increase VAV airflow to desk area"
        ]
```

### HVAC Fault Detection

```python
# Triggered when zone status == "fault"

if hvac["status"] == "fault":
    cause = "HVAC equipment fault - FCU not operating correctly"
    confidence = "high"
    suggestions = [
        "Create maintenance job for FCU inspection",
        "Check BMS alarms for fault codes"
    ]
    needs_dispatch = True
```

### Desk Context Enhancement

```python
# Near window + too_hot + afternoon = solar
if desk.near_window and complaint_type == "too_hot" and 12 <= hour <= 18:
    suggestions.insert(0, f"Lower FCU {zone.fcu_id} setpoint")

# Under diffuser + too_cold = direct airflow
if desk.near_diffuser and complaint_type == "too_cold":
    root_cause = f"Direct airflow from diffuser {desk.near_diffuser}"
    suggestions = ["Reduce VAV airflow", "Adjust diffuser direction"]

# Near printer + too_hot = heat source
if desk.near_printer and complaint_type == "too_hot":
    suggestions.insert(0, "Increase VAV airflow to dissipate printer heat")
```

## Demo Scenarios

### Sandton Building (site-002)

| Zone | Status | Demo Scenario |
|------|--------|---------------|
| Zone-L12-N | Running | Normal operation, 45% occupied |
| Zone-L12-S | Running | Slightly warm (23°C vs 22°C setpoint) |
| Zone-L11-N | Running | Normal operation |
| Zone-L11-S | **FAULT** | FCU fault + 0% occupancy with 100% lighting |
| Zone-L10-N | Running | Normal operation |

### Energy Waste Demo (Zone-L11-S)

```
DALI sensors show:
- 0% occupancy (no one in zone)
- 100% lighting level (all lights on)
- 105W power consumption (wasted)

HVAC shows:
- Status: FAULT
- Temp: 24°C (2°C above setpoint)

Diagnosis: "HVAC FAULT + Energy waste - empty zone with full lighting"
```

### Faulty Equipment

| ID | Type | Issue |
|----|------|-------|
| LUM-L12-FAULT-001 | Luminaire | Lamp failure, 0% output |
| LUM-L11-FAULT-001 | Luminaire | Lamp failure, 0% output |
| PIR-L12-FAULT-001 | Sensor | Sensor fault, 0 lux reading |
| DALI-L11-04 | Controller | Offline status |

## Integration with Clawd (Telegram)

The DALI-HVAC integration is exposed to Clawd via the BMS desk diagnosis tool:

```python
# Clawd tool: bms_desk_diagnosis.py
# Parses messages like "user at desk 201 is too hot"

result = handler.handle_complaint(
    desk_id="201",
    complaint_type="too_hot"
)

# Returns formatted Telegram message with diagnosis
```

## Configuration

### Environment Variables

```bash
# Enable DALI integration (default: true for Sandton)
DALI_ENABLED=true

# DALI controller polling interval
DALI_POLL_INTERVAL_SECONDS=30

# Occupancy simulation for demo
DALI_SIMULATE_OCCUPANCY=true
```

### Adding New Buildings

1. Create building folder: `backend/app/data/buildings/{building_id}/`
2. Add required files:
   - `building.json` - Building metadata with `"dali": true`
   - `zones.json` - HVAC zones with FCU/VAV/AHU references
   - `desks.json` - Desk definitions with zone mappings
3. Add DALI data to `dali_mock_data.json` (or create per-building DALI files)
4. Register in `_registry.json`

## Troubleshooting

### No zones loaded

```python
analyzer = get_cross_system_analyzer()
print(len(analyzer._hvac_data))  # Should be > 0
```

Check:
- Building is registered in `_registry.json`
- `zones.json` exists in building folder
- Zone data has `zone_id` field

### DALI data not showing

```python
dali = get_dali_service()
print(len(dali._sensors))  # Should be > 0
```

Check:
- `dali_mock_data.json` exists
- Sensors have matching `zone_id` to HVAC zones

### Desk not found

```python
handler = get_complaint_handler()
print(list(handler._desks.keys())[:5])  # See available desks
```

Check:
- `desks.json` exists in building folder
- Desk has `zone_id` matching a zone in `zones.json`

## Related Documentation

- [DALI API Reference](../03-api-reference/dali-api.md)
- [Comfort Complaints API](../03-api-reference/complaints-api.md)
- [Building Data Loader](../02-architecture/building-loader.md)
- [Clawd Integration](CLAWD_INTEGRATION.md)
