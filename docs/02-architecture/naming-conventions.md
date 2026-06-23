---
title: "Equipment & Device Naming Conventions"
type: "reference"
status: "approved"
version: "3.1.0"
created: "2026-01-30"
updated: "2026-06-22"
author: "Sentinel Development Team"
tags: ["naming-conventions", "bms", "device-identification", "equipment-id"]
related: ["system-overview.md", "../07-integrations/cafm-schema.md"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# SENTINEL Equipment & Device Naming Conventions

**Purpose:** Standardize SENTINEL's internal equipment/device identification so that any ID immediately tells you **which site**, **what device type**, and **which canonical zone or plant unit**.

**Scope:** This standard applies to SENTINEL's **internal** model — the single canonical ID used in Supabase (`equipment.code`), device control (`mock_devices.json`), audit logs, and all frontend/backend references. External BMS/CAFM systems use their own conventions mapped via the integration layer.

**Key Principle:** One ID system. Equipment and devices are the same entity. The ID is used everywhere — no separate "equipment ID" vs "device ID".

---

## 1. Equipment ID Format

SENTINEL uses a two-tier canonical code. External BMS/vendor IDs are preserved separately as source metadata.

### Tier 1: Occupied-Zone Equipment

**Pattern:** `{site}-{type}-{zone_id}`

Examples:

```
S005-AHU-003      Site 005, AHU, Ground/L0 Zone 003
S002-VAV-100      Site 002, VAV, Level 1 Zone 001
S002-FCU-204      Site 002, FCU, Level 2 Zone 005
S005-DALI-510     Site 005, DALI, Level 5 Zone 011
```

### Tier 2: Basement/Roof Plant Equipment

**Pattern:** `{site}-{type}-{location}-{sequence}`

Examples:

```
S002-CHILLER-B1-001     Chiller #1, Basement 1 plant room
S005-CT-R-002           Cooling Tower #2, Roof
S005-GEN-B1-001         Generator #1, Basement 1
```

**Components:**

| Component | Format | Description |
|-----------|--------|-------------|
| `site` | `S###` (3-digit, zero-padded) | Site identifier from site registry |
| `type` | UPPERCASE abbreviation | Device/equipment type from approved list |
| `zone_id` | 3-digit (`001`-`999`) | Canonical occupied-zone code. Hundreds digit encodes floor. |
| `location` | `B#` / `R` | Plant location for basement/roof infrastructure |
| `sequence` | 3-digit (`001`-`999`) | Plant asset sequence where multiple units can exist |

**Floor Codes:**

| Code | Meaning | Examples |
|------|---------|---------|
| `B1`, `B2` | Basement levels (B1 = first basement) | `B1`, `B2` |
| `G` / `L0` | Ground floor | encoded as `0XX` |
| `L1`...`L9` | Above-ground levels supported by three-digit zone codes | `1XX`, `2XX`, `5XX` |
| `R` | Roof level | `R` |

**Zone vs Sequence:**
- **Canonical zone code** (`001`-`999`): Used when equipment belongs to or serves a specific occupied zone.
- **Plant sequence** (`B1-001`, `R-002`): Used for basement/roof plant equipment where multiple units can exist without a single occupied-zone assignment.
- For unusual duplicate equipment in the same occupied zone, add a sequence only after review. The normal case remains `S###-TYPE-ZZZ`.

**Zone-equipment pointers:** SENTINEL keeps the canonical relationship in `equipment_zone_relationships` and mirrors direct pointers onto zone records for runtime compatibility. When onboarding resolves equipment for a zone, the direct zone fields (`fcu_id`, `vav_id`, `ahu_id`, `lighting_id`) should match the canonical relationship state rather than being treated as an alternate source of truth.

---

## 2. Site Code Registry

**Pattern:** `S###` — three-digit zero-padded number.

The site code is the sole location identifier. There is no separate "building code" — each site represents one building.

| Site Code | Building Name | City |
|-----------|---------------|------|
| `S001` | Gateway Centre | Johannesburg |
| `S002` | Sandton City Office Tower | Sandton |
| `S003` | Menlyn Maine | Pretoria |
| `S004` | Rosebank Towers | Rosebank |
| `S005` | Century City | Cape Town |
| `S006` | V&A Waterfront | Cape Town |
| `S007` | Umhlanga Ridge | Durban |
| `S008` | Sandton Views | Sandton |
| `S009` | Bryanston Office Park | Bryanston |
| `S010` | Midrand Business Park | Midrand |

**Supabase mapping:** The `buildings` table `code` column stores `site-002` format. The equipment ID prefix `S002` maps to `site-002` by convention (`S` + zero-padded number = `site-` + number).

---

## 3. Device Type List

| Type Code | Description | Category | Typical Location |
|-----------|-------------|----------|-----------------|
| **HVAC** | | | |
| `CHILLER` | Chiller unit | HVAC | Plant room (B1) |
| `AHU` | Air Handling Unit | HVAC | Plant room or per-floor |
| `FCU` | Fan Coil Unit | HVAC | Per zone |
| `VAV` | Variable Air Volume | HVAC | Per zone |
| `SPLIT` | Split AC unit | HVAC | Per room |
| `CT` | Cooling Tower | HVAC | Roof |
| **Lighting** | | | |
| `DALI` | DALI-2 Controller | Lighting | Per zone |
| `LUM` | Luminaire Group | Lighting | Per zone |
| **Energy Centre** | | | |
| `GEN` | Generator | Energy | Plant room (B1) |
| `TX` | Transformer | Energy | Plant room (B1) |
| `UPS` | UPS system | Energy | Plant room (B1) |
| `ATS` | Auto Transfer Switch | Energy | Plant room (B1) |
| `MSB` | Main Switchboard | Energy | Plant room (B1) |
| `MTR` | Power Meter | Energy | Per floor or plant room |
| `PFC` | Power Factor Correction | Energy | Plant room (B1) |
| `FDR` | Feeder/Distribution Board | Energy | Per floor |
| `MV` | Medium Voltage Incomer | Energy | Plant room (B1) |
| **Sensors** | | | |
| `TS` | Temperature Sensor | Sensors | Per zone |
| `CO2` | CO2 Sensor | Sensors | Per zone |
| `OCC` | Occupancy Sensor | Sensors | Per zone |
| `DLS` | Daylight Sensor | Sensors | Per zone |
| **Other** | | | |
| `ACC` | Access Control | Security | Per entry point |
| `FIRE` | Fire System | Fire | Per zone/floor |
| `LIFT` | Lift/Elevator | Transport | Per shaft |
| `BMS` | BMS Controller | Controls | Plant room |
| `PXC` | Desigo PXC Controller | Controls | Per floor or plant room |

---

## 4. Examples — Sandton City (S002)

### HVAC Equipment
```
S002-CHILLER-B1-001     Chiller #1, Basement 1 plant room
S002-CHILLER-B1-002     Chiller #2, Basement 1 plant room
S002-CHILLER-B1-003     Standby Chiller #3, Basement 1
S002-AHU-001            AHU serving Ground/L0 Zone 001
S002-AHU-100            AHU serving Level 1 Zone 001
S002-AHU-200            AHU serving Level 2 Zone 001
S002-FCU-001            FCU, Ground/L0 Zone 001
S002-FCU-102            FCU, Level 1 Zone 003
S002-VAV-100            VAV, Level 1 Zone 001
S002-VAV-204            VAV, Level 2 Zone 005
S002-CT-R-001           Cooling Tower #1, Roof
```

### Lighting
```
S002-DALI-001           DALI Controller, Ground/L0 Zone 001
S002-DALI-204           DALI Controller, Level 2 Zone 005
S002-LUM-102            Luminaire Group, Level 1 Zone 002
S002-LUM-205            Luminaire Group, Level 2 Zone 005
```

### Energy Centre
```
S002-GEN-B1-001         Generator #1 (Primary A)
S002-GEN-B1-002         Generator #2 (Primary B)
S002-GEN-B1-003         Generator #3 (Standby A)
S002-GEN-B1-004         Generator #4 (Standby B)
S002-TX-B1-001          Transformer #1 (Essential)
S002-TX-B1-002          Transformer #2 (Non-Essential)
S002-UPS-B1-001         IT Critical UPS
S002-UPS-B1-002         Building Services UPS
S002-ATS-B1-001         Main ATS
S002-MSB-B1-001         Main LV Switchboard
S002-MTR-B1-MAIN        Main Incomer Meter (named sequence)
S002-MTR-B1-GEN         Generator Output Meter
S002-MTR-B1-TENANT      Tenant Sub-Metering Bus
S002-MV-B1-001          Eskom 11kV Incomer
S002-PFC-B1-001         Main PFC Bank
S002-FDR-L1-001         Level 1 Distribution Board
S002-FDR-B1-HVAC        HVAC Plant Room Feeder
```

### Sensors
```
S002-TS-100             Temperature Sensor, Level 1 Zone 001
S002-CO2-104            CO2 Sensor, Level 1 Zone 005
S002-OCC-003            Occupancy Sensor, Ground/L0 Zone 003
S002-DLS-201            Daylight Sensor, Level 2 Zone 001
```

### Controllers
```
S002-BMS-B1-001         Siemens Desigo CC (main BMS/SCADA)
S002-PXC-B1-CHP         PXC Chiller Plant Controller
S002-PXC-L1-HVAC        PXC Level 1 HVAC Controller
```

---

## 5. Point Naming Convention

Points represent individual data values on a device. They are **not** globally unique — they are scoped to the device.

**Pattern:** `{system}_{parameter}_{qualifier}`

**System Codes:**

| Code | System |
|------|--------|
| `chw` | Chilled Water |
| `hw` | Hot Water |
| `sa` | Supply Air |
| `ra` | Return Air |
| `da` | Discharge Air |
| `zone` | Zone/Room |
| `chiller` | Chiller-specific |
| `boiler` | Boiler-specific |

**Parameter Codes:**

| Code | Parameter |
|------|-----------|
| `temp` | Temperature |
| `pressure` | Pressure |
| `flow` | Flow rate |
| `status` | On/off status |
| `setpoint` | Setpoint value |
| `position` | Position (0-100%) |
| `level` | Level (0-100%) |
| `amps` | Current draw |
| `volts` | Voltage |
| `hz` | Frequency |
| `runtime` | Runtime hours |
| `load` | Load percentage |
| `brightness` | Light level (0-100%) |
| `scene` | Lighting scene number |

**Qualifier Codes:**

| Code | Qualifier |
|------|-----------|
| `supply` | Supply side |
| `return` | Return side |
| `discharge` | Discharge side |
| `inlet` | Inlet |
| `outlet` | Outlet |

**Examples:**
```
chw_supply_temp          Chilled Water Supply Temperature
chw_return_temp          Chilled Water Return Temperature
chw_setpoint             Chilled Water Setpoint
sa_damper_position       Supply Air Damper Position
ra_temp                  Return Air Temperature
zone_temp_setpoint       Zone Temperature Setpoint
chiller_status           Chiller On/Off Status
compressor_amps          Compressor Current Draw
brightness               Light brightness level
scene                    Active lighting scene
load_percent             Generator/UPS load percentage
runtime_hours            Cumulative runtime
```

**Fully qualified point reference:** `{equipment_id}.{point_name}`
```
S002-CHILLER-B1-001.chw_supply_temp
S002-VAV-100.sa_damper_position
S002-DALI-204.brightness
```

---

## 6. Location Metadata

Every device MUST include a `location` object for technician-friendly navigation. This is **supplementary** to the ID — the ID encodes site/floor/zone, the metadata provides human-readable detail.

**Structure:**
```json
{
  "location": {
    "building": "Sandton City Office Tower",
    "floor": "L1",
    "zone": "A",
    "room": "MR1",
    "description": "Level 1, Zone A, Mechanical Room 1"
  }
}
```

**Room Type Codes:**

| Code | Meaning |
|------|---------|
| `MR` | Mechanical Room |
| `ER` | Electrical Room |
| `OR` | Office |
| `SR` | Server Room |
| `LR` | Lobby/Reception |
| `PR` | Plant Room |
| `ST` | Storage |

---

## 7. Equipment Metadata

Every device MUST include an `equipment` object with make, model, and specifications.

```json
{
  "equipment": {
    "manufacturer": "York",
    "model": "YCIV",
    "serial_number": "YK-SAN-2020-001",
    "installation_year": 2020,
    "capacity_kw": 350,
    "specifications": {
      "refrigerant": "R134a",
      "compressor_type": "Screw",
      "number_of_compressors": 2
    }
  }
}
```

---

## 8. Complete Device Example

```json
{
  "id": "S002-CHILLER-B1-001",
  "site_id": "site-002",
  "name": "York YCIV Chiller 1",
  "device_type": "chiller",
  "protocol": "bacnet",
  "location": {
    "building": "Sandton City Office Tower",
    "floor": "B1",
    "zone": "PR",
    "room": "PR1",
    "description": "Basement 1, Plant Room 1"
  },
  "equipment": {
    "manufacturer": "York",
    "model": "YCIV",
    "serial_number": "YK-SAN-2020-001",
    "installation_year": 2020,
    "capacity_kw": 350,
    "specifications": {
      "refrigerant": "R134a",
      "compressor_type": "Screw",
      "number_of_compressors": 2
    }
  },
  "points": {
    "chw_supply_temp": {
      "name": "chw_supply_temp",
      "point_type": "analog_input",
      "description": "Chilled water supply temperature",
      "unit": "°C",
      "min_value": 4.0,
      "max_value": 15.0,
      "default_value": 7.0
    },
    "chw_return_temp": {
      "name": "chw_return_temp",
      "point_type": "analog_input",
      "description": "Chilled water return temperature",
      "unit": "°C"
    },
    "chw_setpoint": {
      "name": "chw_setpoint",
      "point_type": "analog_output",
      "description": "Chilled water setpoint",
      "unit": "°C",
      "min_value": 5.0,
      "max_value": 12.0,
      "default_value": 7.0,
      "writable": true
    },
    "chiller_status": {
      "name": "chiller_status",
      "point_type": "binary_input",
      "description": "Chiller running status"
    }
  }
}
```

---

## 9. External System Integration

**IMPORTANT:** This standard is for SENTINEL's **internal** representation only.

External BMS/CAFM systems use their own naming conventions. The integration layer handles translation:

```
External BMS Point              →  SENTINEL Internal
-----------------------------     →  ----------------------------
"NAE01/CHW-PLT-01.CTL"          →  S002-CHILLER-B1-001.chw_setpoint
"Site11_Chiller_Main.Temp"      →  S002-CHILLER-B1-001.chw_supply_temp
"AHU-L12-001.SAT"               →  S002-AHU-L1-01.sa_supply_temp
```

The `point_asset_mappings` table stores these mappings with confidence scores.

---

## 10. Validation Rules

1. **Equipment IDs must be globally unique** across all sites
2. **Site code must exist** in the site registry
3. **Device type must be from approved list** (Section 3)
4. **Occupied-zone code must be:** 3 digits (`001`-`999`)
5. **Plant location/sequence must be:** `B#-###`, `R-###`, or approved short named key (`MAIN`, `HVAC`, `CHP`) for plant-only assets
6. **Point names must follow** `{system}_{parameter}_{qualifier}` pattern
7. **Location metadata is required** for all devices

---

## 11. Migration from Legacy IDs

### ID Format Mapping

| Legacy Format | New Format | Rule |
|---------------|------------|------|
| `001-gwc-chiller-001` | `S001-CHILLER-B1-001` | Drop building code, use site prefix |
| `CHILLER-001` | `S002-CHILLER-B1-001` | Add site + floor |
| `VAV-L1-05` | `S002-VAV-104` | Add site, encode floor/zone as canonical zone |
| `SAN-GEN-001` | `S002-GEN-B1-001` | Replace building abbrev with site code |
| `011-stc-ahu-001` | `S002-AHU-001` | Remap site code, map to ground canonical zone |
| `FCU-L12-03` | `S002-FCU-102` | Add site, correct floor, encode zone |
| `002-stc-vav-l12-01` | `S002-VAV-100` | Simplify to standard canonical format |
| `S001-FCU-101` | `S001-FCU-101` | Already correct |

### Legacy Zone Number/Alias Mapping

Site onboarding may use site-specific aliases to resolve raw source labels to canonical zone numbers.

| Source Label | Canonical Zone | Zone Name |
|--------------|----------------|-----------|
| `L1-01`, `L1-A` | `Zone-100` | Level 1 Zone 001 |
| `L2-05`, `L2-E` | `Zone-204` | Level 2 Zone 005 |
| `L3-ICU` | `Zone-300` | Level 3 ICU |

---

## 12. Display Name Normalization

Equipment display names shown in the UI (e.g., dashboard, equipment lists) follow a human-readable format derived from the canonical ID. The normalisation is applied at two layers — no DB migration required.

### Display Name Format

| Equipment ID Pattern | Location Part | Display Name | Rule |
|----------------------|---------------|--------------|------|
| `S002-AHU-B1-001` | `B1-001` | "AHU Basement" | Basement floor, no zone number |
| `S002-AHU-105` | `105` | "AHU Level 1 Zone 5" | `1` = Level 1, `05` = Zone 5 |
| `S002-CHILLER-R-001` | `R-001` | "CHILLER Roof Unit 1" | Roof plant with numeric sequence |
| `S002-VAV-205` | `205` | "VAV Level 2 Zone 5" | Canonical zone code |
| `S002-LTG-021` | `021` | "LTG Ground Zone 21" | Ground/L0 canonical zone |
| `S002-UNKNOWN-R-001` | `R-001` | "Outdoor Air Sensor Roof" | UNKNOWN type + roof → special case |
| `S002-UNKNOWN-201` | `201` | "Sensor Level 2 Zone 1" | UNKNOWN type, canonical zone pattern |

### Normalisation Layers

**Layer 1 — Bridge auto-create** (`shadow_mode_polling.py`):
New equipment synced from the SIMBIOT bridge is named correctly at creation time. The formatter `_parse_eq_code_parts()` splits the full ID (`S002-AHU-B1-001`) into type and location, then `_format_display_name()` produces the display string.

**Layer 2 — API response** (`buildings.py`):
The `get_site_equipment()` endpoint normalises names on read via `_normalize_equipment_name()`. Existing DB records retain their stored `name` but the API returns the normalised version. No DB writes required.

### Formatter Reference

```python
# shadow_mode_polling.py — at module level
def _format_display_name(eq_type: str, eq_code: str) -> str
def _format_unknown_name(eq_code: str) -> str
def _parse_eq_code_parts(code: str) -> tuple[str, str]

# buildings.py — at module level
def _normalize_equipment_name(eq: dict) -> str
```

---

**Document Version:** 3.0
**Last Updated:** 2026-05-08
**Status:** Approved — Display Name Normalisation (Phase 193+)
