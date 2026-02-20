# Equipment Naming Conventions (Two-Tier System)

**Complete Alignment:** Zones, Desks, and Equipment all reference the same numeric zone identifiers for office areas. Plant equipment uses location codes.

**See CLAUDE.md for quick reference. This document covers full naming system details.**

## Zone Numbering System (Self-Documenting)

```
L0 (Ground):  Zone-001 to Zone-005  (5 zones)
L1 (Level 1): Zone-100 to Zone-104  (5 zones)
L2 (Level 2): Zone-200 to Zone-204  (5 zones)
B1 (Basement): Zone-B1-001 (plant room)
R (Roof):     Zone-R-001 (plant room)

Zone number encodes floor: 0XX = L0, 1XX = L1, 2XX = L2
```

## Desk Numbering System (Encodes Floor)

```
L0 (Ground):  Desk-001 to Desk-100  (100 desks, 20 per zone)
L1 (Level 1): Desk-102 to Desk-201  (100 desks, 20 per zone)
L2 (Level 2): Desk-202 to Desk-301  (100 desks, 20 per zone)

Desk number range tells you the floor: 001-100=L0, 102-201=L1, 202-301=L2
Desk distribution: 20 desks per zone (e.g., Desk-001-020 in Zone-001)
```

## Equipment Code System — TWO-TIER

### Tier 1: Zone Equipment (Offices)

```
Pattern: {site}-{type}-{zone_id}
Examples:
  S002-VAV-101    ← Level 1, Zone B (Zone-101)
  S002-FCU-200    ← Level 2, Zone A (Zone-200)
  S002-DALI-104   ← Level 1, Zone E (Zone-104)

Applies to: VAV, FCU, DALI units serving specific office zones
```

### Tier 2: Plant Equipment (Infrastructure)

```
Pattern: {site}-{type}-{location}-{sequence}
Examples:
  S002-CHILLER-B1-001  ← Basement 1, Chiller #1
  S002-AHU-R-001       ← Roof, AHU #1
  S002-GEN-G-001       ← Ground, Generator #1
  S002-PUMP-B1-CHW1    ← Basement 1, Chilled Water Pump
  S002-MTR-B1-MAIN     ← Basement 1, Main Meter

Locations: B1 (Basement), R (Roof), G (Ground Plant)
Applies to: CHILLER, AHU, GEN, UPS, PUMP, MTR, CT (building-wide infrastructure)
```

## Zone Mapping Reference

```
Zone-001 = L0, Zone A   |  Zone-100 = L1, Zone A   |  Zone-200 = L2, Zone A
Zone-002 = L0, Zone B   |  Zone-101 = L1, Zone B   |  Zone-201 = L2, Zone B
Zone-003 = L0, Zone C   |  Zone-102 = L1, Zone C   |  Zone-202 = L2, Zone C
Zone-004 = L0, Zone D   |  Zone-103 = L1, Zone D   |  Zone-203 = L2, Zone D
Zone-005 = L0, Zone E   |  Zone-104 = L1, Zone E   |  Zone-204 = L2, Zone E
```

## Type → Technician Specialty Mapping

- **HVAC:** CHILLER, AHU, FCU, VAV, SPLIT, CT, CRAC, PUMP
- **DALI (Lighting):** DALI, LUM
- **Electrical:** GEN, TX, UPS, ATS, MSB, MTR, PFC, FDR, MV, DB
- **Fire Safety:** FIRE
- **Security:** ACC, CCTV

## Other Naming Conventions

- **Point naming:** `{system}_{parameter}_{qualifier}` (e.g., `chw_supply_temp`)
- Use `equipment_id`/`equipment_name` in domain models, `device_id` only at device control layer

## Site-005 Hospital Naming System (Floor-Based with Point Monitoring)

**Context:** Busamed Gateway Private Hospital (Umhlanga) - 25,000 sqm, 9 levels, 90 equipment items

**Pattern:** `site-005-UMH-{TYPE}-{FLOOR}-{ID}.{POINT}` (site-005 preserves hospital naming for multi-campus systems)

### Structure

- `site-005-UMH-` - Hospital building identifier (UMH = Umhlanga Hospital)
- `{TYPE}` - Equipment type (AHU, GEN, LIFT, JACE, CT, FIRE, PUMP, COLD, MSB, UPS, BOILER, DB, KEF, SPLIT, MEDGAS)
- `{FLOOR}` - Floor location: B1 (Basement), L1-L9 (Levels), R (Roof)
- `{ID}` - Equipment ID (room identifier for zones: ICU, THeatre, etc.; or sequence for infrastructure)
- `.{POINT}` - Optional point suffix for monitoring (e.g., `.fan`, `.load`, `.fuel`, `.hepa`, `.door`, `.o2`)

### Examples

```
# Critical Medical Equipment (ICU, Operating Theatres)
site-005-UMH-AHU-L3-ICU.fan      ← ICU air handler fan
site-005-UMH-AHU-L3-ICU.hepa     ← ICU HEPA filter
site-005-UMH-AHU-L3-TH1.air      ← Theatre 1 air supply
site-005-UMH-DB-L3-001.total     ← Level 3 electrical panel

# Infrastructure Equipment (Plant, Basement, Roof)
site-005-UMH-GEN-B1-001.fuel     ← Basement generator #1 fuel level
site-005-UMH-PUMP-B1-001         ← Basement pump #1
site-005-UMH-CT-R-001            ← Roof cooling tower #1
site-005-UMH-LIFT-L4-001.door    ← Level 4 elevator door status
site-005-UMH-COLD-L2-001         ← Level 2 cold storage (pharma/blood)
```

### Medical Equipment Specialties

- **HVAC (Medical):** AHU (25 items, ICU/Theatre critical), FCU, SPLIT, CT, PUMP
- **Electrical:** GEN (12 items, emergency backup), MSB, DB, UPS (2 items, L3 critical systems)
- **Vertical Transport:** LIFT (12 items, patient transport)
- **Building Automation:** JACE (10 items, controllers)
- **Life Safety:** FIRE (4 items)
- **Medical Infrastructure:** COLD (3 items, vaccine/blood storage), MEDGAS (1 item, oxygen monitoring)
- **Utilities:** BOILER (2 items), KEF (2 items, kitchen exhaust)

### Point-Level Monitoring

- 46% of equipment (41/90 items) have point suffixes for medical-grade monitoring
- Critical points: `.fan` (AHU status), `.hepa` (filter integrity), `.load` (power), `.fuel` (generator), `.o2` (oxygen), `.door` (elevator/storage access)
- Example: ICU air handler monitored at 4 points: `site-005-UMH-AHU-L3-ICU.{air, fan, hepa, room}`

## Difference from Site-002

- **Site-002 (Office):** Zone-based (Zone-001-004), compact format (S002-TYPE-ZONE_ID)
- **Site-005 (Hospital):** Floor-based (B1, L1-L9, R), verbose format (site-005-UMH-TYPE-FLOOR-ID), point-level monitoring
- **Site-002:** ~30 equipment across 3 floors
- **Site-005:** ~90 equipment across 11 floor levels

## Naming System Benefits

- ✅ Zone number self-documents floor (001-099=L0, 100-199=L1, 200-299=L2)
- ✅ Desk number self-documents floor (001-100=L0, 102-201=L1, 202-301=L2)
- ✅ Equipment code directly references zone — no translation needed
- ✅ Perfect alignment: Zone-101 = Desk-122-141 = S002-XXX-101
- ✅ Eliminates L0 vs L10 ambiguity (now it's 001 vs 101, crystal clear)
- ✅ Queries simple: WHERE code LIKE '%-101' = all Zone-101 equipment
- ✅ Hospital-specific naming preserved (UMH identifier, floor labels, point monitoring)
- ✅ Multi-campus support enabled (different sites can have different building codes: UMH, BTU, etc.)
