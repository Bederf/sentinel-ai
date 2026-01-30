# SENTINEL Naming Conventions

This document defines the standard naming conventions used throughout the SENTINEL BMS Intelligence Platform. **Follow these conventions exactly - do not rename fields or change patterns without updating this document first.**

## API Data Model Field Names

### Equipment/Device Identification

| Context | Field Name | Example | Notes |
|---------|------------|---------|-------|
| Equipment records | `equipment_id` | `"001-gwc-chiller-001"` | Primary identifier for assets |
| Equipment records | `equipment_name` | `"Chiller 1"` | Human-readable name |
| Device control | `device_id` | `"001-gwc-chiller-001"` | Same value as equipment_id |
| Optimization recommendations | `equipment_id` | `"001-gwc-chiller-001"` | Use equipment_id in recommendations |
| Optimization recommendations | `equipment_name` | `"Chiller 1"` | Use equipment_name in recommendations |

**Rule:** In domain models (equipment, assets, recommendations), use `equipment_id` and `equipment_name`. The `device_id` is used only at the device control layer when writing to actual hardware.

### Common Field Names

| Field | Type | Description |
|-------|------|-------------|
| `site_id` | string | Building/site identifier (e.g., `"site-001"`) |
| `building_code` | string | Short building code (e.g., `"gwc"`, `"rbt"`) |
| `point_name` | string | Control point identifier (e.g., `"zone_cooling_setpoint"`) |
| `current_value` | number | Current sensor/setpoint value |
| `recommended_value` | number | AI-recommended value |
| `value` | number | Generic value field for control actions |
| `unit` | string | Unit of measurement (e.g., `"°C"`, `"%"`, `"kW"`) |
| `status` | string | State indicator (see Status Values below) |
| `health_score` | number | 0-100 percentage score |

### Status Values

| Category | Values | Usage |
|----------|--------|-------|
| Equipment Status | `"online"`, `"offline"`, `"warning"`, `"critical"` | Equipment operational state |
| Safety Status | `"safe"`, `"warning"`, `"critical"` | Safety validation result |
| Optimization Status | `"optimized"`, `"recommendation_pending"`, `"warning"`, `"error"`, `"unknown"` | Optimization state |
| Alert Severity | `"low"`, `"medium"`, `"high"`, `"critical"` | Alert priority |

---

## Device ID Format

**Pattern:** `{site_code}-{building_code}-{device_type}-{sequence}`

### Components

| Component | Format | Example |
|-----------|--------|---------|
| Site Code | 3 digits | `001`, `002` |
| Building Code | 2-4 lowercase letters | `gwc`, `rbt`, `cm` |
| Device Type | lowercase with hyphens | `chiller`, `ahu`, `zone-ctrl` |
| Sequence | 3 digits | `001`, `002` |

### Examples

```
001-gwc-chiller-001     # Gateway Centre, Chiller 1
001-gwc-ahu-002         # Gateway Centre, AHU 2
002-rbt-fcu-015         # Rosebank Towers, FCU 15
003-cm-zone-ctrl-001    # Centurion Mall, Zone Controller 1
```

### Device Types

| Type | Code | Description |
|------|------|-------------|
| Chiller | `chiller` | Chilled water plant |
| Air Handling Unit | `ahu` | Central air handler |
| Fan Coil Unit | `fcu` | Terminal unit |
| Variable Air Volume | `vav` | VAV box |
| Zone Controller | `zone-ctrl` | Temperature zone control |
| Split System | `split` | Split AC unit |
| Lighting | `lighting` | Lighting control |
| Access Control | `access` | Door/access control |
| Fire Pump | `firepump` | Fire suppression |
| UPS | `ups` | Uninterruptible power |
| Generator | `generator` | Backup power |

---

## Point Naming

**Pattern:** `{system}_{parameter}_{qualifier}`

### System Prefixes

| Prefix | System |
|--------|--------|
| `zone_` | Zone/space control |
| `chw_` | Chilled water |
| `hw_` | Hot water |
| `sa_` | Supply air |
| `ra_` | Return air |
| `oa_` | Outside air |

### Common Points

| Point Name | Description | Unit |
|------------|-------------|------|
| `zone_cooling_setpoint` | Zone cooling temperature setpoint | °C |
| `cooling_setpoint` | Generic cooling setpoint | °C |
| `heating_setpoint` | Heating temperature setpoint | °C |
| `zone_temp` | Zone temperature reading | °C |
| `humidity_setpoint` | Humidity setpoint | % |
| `chw_supply_temp_setpoint` | Chilled water supply setpoint | °C |
| `fan_speed` | Fan speed | % |
| `damper_position` | Damper position | % |
| `valve_position` | Valve position | % |
| `occupancy` | Occupancy state | boolean |
| `enable` | Equipment enable | boolean |

---

## Location Metadata

### Floor Naming

| Format | Example | Description |
|--------|---------|-------------|
| `FL{n}` | `FL1`, `FL12` | Standard floors |
| `Ground` | `Ground` | Ground floor |
| `Basement` | `Basement` | Below ground |
| `Roof` | `Roof` | Roof level |
| `Mezzanine` | `Mezzanine` | Mezzanine level |

### Zone Naming

| Format | Example | Description |
|--------|---------|-------------|
| `Q{1-4}` | `Q1`, `Q2` | Quadrant-based |
| Directional | `North`, `South`, `East`, `West` | Cardinal directions |
| Named | `Lobby`, `Atrium`, `Core` | Named zones |

### Room Types

| Code | Meaning |
|------|---------|
| `MR` | Mechanical Room |
| `ER` | Electrical Room |
| `SR` | Server Room |
| `CR` | Conference Room |
| `OF` | Office |
| `LB` | Lobby |

---

## Zone Priority System

Used for load shedding optimization.

| Priority | Code | Zone Types | Description |
|----------|------|------------|-------------|
| P1 | Critical | Executive, Server Rooms | Never shed |
| P2 | High | Meeting Rooms, Reception | Minimal shedding |
| P3 | Medium | Open Plan Offices | Standard optimization |
| P4 | Low | Corridors, Lobby | Aggressive optimization |
| P5 | Lowest | Parking, Plant Rooms | First to shed |

---

## API Response Structures

### Optimization Recommendation

```typescript
interface OptimizationAction {
  equipment_id: string;      // NOT device_id
  equipment_name: string;    // NOT device_name
  point_name: string;        // Actual point to modify
  current_value: number;
  recommended_value: number;
  unit: string;              // "°C", "%", etc.
  reason: string;
}
```

### Control Action Request

```typescript
interface ControlAction {
  device_id: string;         // Maps to equipment_id
  point_name: string;
  value: number;
}
```

### Equipment Record

```typescript
interface Equipment {
  id: string;                // Equipment ID
  name: string;              // Human-readable name
  type: string;              // Device type code
  site_id: string;
  status: string;            // "online" | "offline" | "warning" | "critical"
  health_score: number;      // 0-100
}
```

---

## File Naming

| Type | Pattern | Example |
|------|---------|---------|
| React Components | PascalCase | `SiteDetail.tsx`, `DeviceControl.tsx` |
| API modules | snake_case | `ai_optimizer.py`, `safety_interlocks.py` |
| Data files | snake_case | `mock_devices.json`, `safety_rules.json` |
| Planning docs | `{phase}-{number}-{TYPE}.md` | `24-03-SUMMARY.md` |

---

## Change Process

**Before renaming any field or pattern:**

1. Update this document first
2. Search codebase for all usages
3. Update backend AND frontend together
4. Update TypeScript interfaces
5. Test the full flow

**Do not create ad-hoc field name variations.** If a new pattern is needed, document it here first.
