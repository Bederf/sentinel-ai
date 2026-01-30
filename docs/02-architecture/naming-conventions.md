---
title: "Device and Location Naming Conventions"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["naming-conventions", "bms", "device-identification"]
related: ["system-overview.md", "../07-integrations/cafm-schema.md"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# SENTINEL Device Naming Conventions

**Purpose:** Standardize SENTINEL's internal device representation for consistent data management, technician navigation, and system integration.

**Scope:** This standard applies to SENTINEL's **internal** device model. External BMS/CAFM systems use their own conventions, which Phase 14 integration layer maps to this standard.

---

## 1. Device ID Format

**Pattern:** `{site_code}-{building_code}-{device_type}-{sequence}`

**Components:**
- `site_code` (3 digits): Site identifier from site inventory (001, 002, 011, etc.)
- `building_code` (3 chars): Building abbreviation from approved list
- `device_type` (lowercase): Device type from approved list
- `sequence` (3 digits): Sequential number starting at 001

**Examples:**
```
001-gwc-chiller-001  (Gateway Centre, Chiller #1)
011-stc-ahu-001      (Sandton City, AHU #1)
002-wcp-fcu-012      (Western Cape Park, FCU #12)
006-flt-lighting-003 (Flagship, Lighting Panel #3)
```

**Building Code List:**
| Code | Building Name |
|------|---------------|
| gwc  | Gateway Centre |
| stc  | Sandton City |
| wcp  | Western Cape Park |
| flt  | Flagship |
| cmp  | Centurion Mall |
| prp  | Pretoria |

**Device Type List:**
| Type | Description |
|------|-------------|
| chiller | Chiller unit |
| ahu | Air Handling Unit |
| fcu | Fan Coil Unit |
| vav | Variable Air Volume |
| split | Split AC unit |
| lighting | Lighting panel/controller |
| access | Access control panel |
| firepump | Fire pump controller |
| ups | UPS system |
| generator | Generator |

---

## 2. Location Metadata

Every device MUST include a `location` object with technician-friendly information.

**Structure:**
```json
{
  "location": {
    "building": "Gateway Centre",
    "floor": "FL2",
    "zone": "Q3",
    "room": "MR4",
    "description": "Floor 2, Quadrant 3, Mechanical Room 4"
  }
}
```

**Field Descriptions:**
- `building` (required): Full building name
- `floor` (required): Floor identifier
  - Format: `FL{number}` (FL1, FL2, FL3) or `Basement` or `Roof` or `Ground`
- `zone` (required): Zone/quadrant identifier
  - Format: `Q{1-4}` or directional names (North, South, East, West)
- `room` (required): Room identifier
  - Format: `{type}{number}` where type is from approved list
  - Examples: MR4 (Mechanical Room 4), ER1 (Electrical Room 1), OR12 (Office Room 12)
- `description` (required): Human-readable location string

**Room Type Codes:**
| Code | Meaning |
|------|---------|
| MR | Mechanical Room |
| ER | Electrical Room |
| OR | Office Room |
| SR | Server Room |
| WR | Washroom |
| KR | Kitchen |
| LR | Lobby/Reception |
| ST | Storage |

**Display Formats:**
- **Compact:** `FL2/Q3/MR4`
- **Full:** `Gateway Centre, Floor 2, Quadrant 3, Mechanical Room 4`
- **Short:** `FL2 - MR4 (Q3)`

---

## 3. Equipment Metadata

Every device MUST include an `equipment` object with make, model, and specifications.

**Structure:**
```json
{
  "equipment": {
    "manufacturer": "Trane",
    "model": "RTAC 200",
    "serial_number": "TR-2024-001",
    "installation_year": 2015,
    "capacity_kw": 220,
    "specifications": {
      "refrigerant": "R134a",
      "compressor_type": "Scroll",
      "number_of_compressors": 2
    }
  }
}
```

**Required Fields:**
- `manufacturer` (required): Manufacturer name
- `model` (required): Model number/name
- `serial_number` (optional): Asset serial number
- `installation_year` (optional): Year installed
- `capacity_kw` (optional): Capacity in kW (for HVAC equipment)

**Common Manufacturers:**
- HVAC: Trane, Carrier, York, Daikin, Samsung, Mitsubishi
- Lighting: Tridonic, Philips, Osram, Schneider
- Access Control: HID, Suprema, Dormakaba
- Fire: Honeywell, Siemens, Notifier, Johnson Controls

---

## 4. Point Naming Convention

**Pattern:** `{system}_{parameter}_{qualifier}`

**System Codes:**
| Code | System |
|------|--------|
| chw | Chilled Water |
| hw | Hot Water |
| sa | Supply Air |
| ra | Return Air |
| da | Discharge Air |
| zone | Zone/Room |
| chiller | Chiller-specific |
| boiler | Boiler-specific |

**Parameter Codes:**
| Code | Parameter |
|------|-----------|
| temp | Temperature |
| pressure | Pressure |
| flow | Flow rate |
| status | On/off status |
| setpoint | Setpoint value |
| position | Position (0-100%) |
| level | Level (0-100%) |
| amps | Current draw |
| volts | Voltage |
| hz | Frequency |

**Qualifier Codes:**
| Code | Qualifier |
|------|-----------|
| supply | Supply side |
| return | Return side |
| discharge | Discharge side |
| inlet | Inlet |
| outlet | Outlet |
| left | Left side |
| right | Right side |

**Examples:**
```
chw_supply_temp          (Chilled Water Supply Temperature)
chw_return_temp          (Chilled Water Return Temperature)
chw_setpoint             (Chilled Water Setpoint)
sa_damper_position       (Supply Air Damper Position)
ra_temp                  (Return Air Temperature)
zone_temp_setpoint       (Zone Temperature Setpoint)
chiller_status           (Chiller On/Off Status)
compressor_amps          (Compressor Current Draw)
```

---

## 5. Site ID Format

**Pattern:** `{region_code}-{site_number}`

**Examples:**
```
gwc-001  (Gateway Centre, Site #001)
stc-011  (Sandton City, Site #011)
wcp-002  (Western Cape Park, Site #002)
```

**Region Codes:**
| Code | Region |
|------|--------|
| gwc | Gateway Centre |
| stc | Sandton City |
| wcp | Western Cape Park |
| flt | Flagship |
| cmp | Centurion Mall |
| prp | Pretoria |

---

## 6. Data Model Changes

### Device Model (backend/app/models/device.py)

Add to Device dataclass:
```python
@dataclass
class Device:
    # ... existing fields ...

    location: DeviceLocation
    equipment: DeviceEquipment

@dataclass
class DeviceLocation:
    building: str
    floor: str
    zone: str
    room: str
    description: str

@dataclass
class DeviceEquipment:
    manufacturer: str
    model: str
    serial_number: Optional[str] = None
    installation_year: Optional[int] = None
    capacity_kw: Optional[float] = None
    specifications: Dict[str, Any] = field(default_factory=dict)
```

---

## 7. Migration Checklist

- [ ] Update Device model with location and equipment fields
- [ ] Update all devices in mock_devices.json with new IDs
- [ ] Add location metadata to all devices
- [ ] Add equipment metadata to all devices
- [ ] Standardize point names across all devices
- [ ] Update safety_rules.json with new point names
- [ ] Update any API responses or UI code referencing old fields
- [ ] Update test data and fixtures

---

## 8. External System Integration (Phase 14)

**IMPORTANT:** This standard is for SENTINEL's **internal** representation only.

External BMS/CAFM systems use their own naming conventions. Phase 14 integration layer handles the translation:

```
External BMS Point              →  SENTINEL Internal Point
-----------------------------     →  ------------------------
"NAE01/CHW-PLT-01.CTL"          →  "001-gwc-chiller-001.points.chw_setpoint"
"Site11_Chiller_Main.Temp"      →  "011-stc-chiller-001.points.chw_supply_temp"
"AHU-L12-001.SAT"               →  "001-gwc-ahu-001.points.sa_supply_temp"
```

The `point_asset_mappings` table (Migration 010) stores these mappings with confidence scores.

---

## 9. Examples

### Complete Device Example

```json
{
  "id": "001-gwc-chiller-001",
  "site_id": "gwc-001",
  "name": "Gateway Centre Chiller 1",
  "device_type": "hvac",
  "protocol": "mock",
  "location": {
    "building": "Gateway Centre",
    "floor": "Basement",
    "zone": "Q1",
    "room": "MR1",
    "description": "Basement, Quadrant 1, Main Mechanical Room"
  },
  "equipment": {
    "manufacturer": "Trane",
    "model": "RTAC 200",
    "serial_number": "TR-GWC-2015-001",
    "installation_year": 2015,
    "capacity_kw": 220,
    "specifications": {
      "refrigerant": "R134a",
      "compressor_type": "Scroll",
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
    "chw_return_temp": { ... },
    "chw_setpoint": { ... },
    "chiller_status": { ... },
    "compressor_amps": { ... }
  }
}
```

---

## 10. Validation Rules

1. **Device IDs must be unique** across all sites
2. **Location fields are required** for all devices
3. **Equipment manufacturer and model are required**
4. **Point names must follow** {system}_{parameter}_{qualifier} pattern
5. **Device type must be from approved list**
6. **Floor format must be** FL{number}, Ground, Basement, or Roof
7. **Zone format must be** Q{1-4} or directional name

---

**Document Version:** 1.0
**Last Updated:** 2026-01-29
**Status:** Ready for Implementation
