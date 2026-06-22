---
title: "Equipment Naming Conventions (Two-Tier System)"
type: "architecture"
status: "approved"
version: "1.1.0"
created: "2026-03-31"
updated: "2026-06-22"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Equipment Naming Conventions (Two-Tier System)

**Complete Alignment:** Zones, desks, and equipment all reference the same canonical zone identifiers. Occupied-zone equipment uses the numeric zone code. Plant equipment in basement/roof areas uses location plus sequence.

**See CLAUDE.md for quick reference. This document covers full naming system details.**

## Zone Numbering System (Self-Documenting)

```
L0 (Ground):  Zone-001 to Zone-099
L1 (Level 1): Zone-100 to Zone-199
L2 (Level 2): Zone-200 to Zone-299
L5 (Level 5): Zone-500 to Zone-599
B1 (Basement): Zone-B1-001 (plant room)
R (Roof):     Zone-R-001 (plant room)

Zone number encodes floor: 0XX = L0/Ground, 1XX = L1, 2XX = L2, 5XX = L5
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

### Tier 1: Occupied-Zone Equipment

```
Pattern: {site}-{type}-{zone_id}
Examples:
  S005-AHU-003    ← Site 005, AHU, Ground/L0 Zone 003 (Zone-003)
  S002-VAV-100    ← Site 002, VAV, Level 1 Zone 001 (Zone-100)
  S002-FCU-204    ← Site 002, FCU, Level 2 Zone 005 (Zone-204)
  S005-DALI-510   ← Site 005, DALI, Level 5 Zone 011 (Zone-510)

Applies to: AHU, FCU, VAV, DALI, LUM, sensors, and other equipment assigned to a canonical occupied zone.
```

### Tier 2: Plant Equipment (Infrastructure)

```
Pattern: {site}-{type}-{location}-{sequence}
Examples:
  S002-CHILLER-B1-001  ← Basement 1, Chiller #1
  S002-AHU-R-001       ← Roof, AHU #1
  S002-PUMP-B1-CHW1    ← Basement 1, Chilled Water Pump
  S002-MTR-B1-MAIN     ← Basement 1, Main Meter

Locations: B1/B2 (Basement), R (Roof)
Applies to: CHILLER, AHU, GEN, UPS, PUMP, MTR, CT (building-wide infrastructure)
```

Ground-floor equipment that serves a normal occupied zone uses the occupied-zone pattern, e.g. `S005-AHU-003`. Use the plant pattern only where the asset is physically in a plant area or has no single occupied-zone assignment.

## Zone Mapping Reference

```
Zone-001 = L0, Zone 001 |  Zone-100 = L1, Zone 001 |  Zone-200 = L2, Zone 001
Zone-002 = L0, Zone 002 |  Zone-101 = L1, Zone 002 |  Zone-201 = L2, Zone 002
Zone-003 = L0, Zone 003 |  Zone-102 = L1, Zone 003 |  Zone-202 = L2, Zone 003
Zone-004 = L0, Zone 004 |  Zone-103 = L1, Zone 004 |  Zone-203 = L2, Zone 004
Zone-005 = L0, Zone 005 |  Zone-104 = L1, Zone 005 |  Zone-204 = L2, Zone 005
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

## Raw Source Naming and Site-005 Hospital Labels

External BMS/vendor naming is not the SENTINEL canonical code. During onboarding, preserve the raw source identifier and map it to the canonical equipment code and canonical zone.

### Required Fields

- `raw_code` / source object ID: original BMS/vendor identifier.
- `code`: SENTINEL canonical equipment code.
- `type`: normalized equipment type.
- `zone_key`: normalized raw/source zone key when available.
- `canonical_zone_id`: canonical `Zone-###` or plant zone.
- `location`: human-readable location label.

### Site-005 Examples

Raw hospital labels such as ICU, theatres, wards, and plant rooms are retained as aliases or display labels, not as the canonical equipment code.

```
raw_code:           site-005-UMH-AHU-L3-ICU.fan
code:               S005-AHU-300
zone_key:           Zone-L3-ICU
canonical_zone_id:  Zone-300
location:           Level 3 ICU

raw_code:           site-005-UMH-AHU-L3-TH1.air
code:               S005-AHU-301
zone_key:           Zone-L3-TH1
canonical_zone_id:  Zone-301
location:           Level 3 Theatre 1

raw_code:           site-005-UMH-CT-R-001
code:               S005-CT-R-001
canonical_zone_id:  Zone-R-001
location:           Roof plant
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

- **Site-002 (Office):** Raw source IDs and canonical IDs are often already close to `S002-TYPE-ZONE`.
- **Site-005 (Hospital):** Raw source IDs may be verbose and clinical (`site-005-UMH-AHU-L3-ICU`), but the canonical code still uses `S005-TYPE-ZONE`.
- **Both sites:** Downstream services use canonical `equipment.code` and canonical zones. Raw source names remain available for integration, audit, and operator context.

## Naming System Benefits

- ✅ Zone number self-documents floor (001-099=L0, 100-199=L1, 200-299=L2)
- ✅ Desk number self-documents floor (001-100=L0, 102-201=L1, 202-301=L2)
- ✅ Equipment code directly references zone — no translation needed
- ✅ Perfect alignment: Zone-100 = Level 1 Zone 001 = S002-XXX-100
- ✅ Eliminates L0 vs L10 ambiguity (now it's 001 vs 101, crystal clear)
- ✅ Queries simple: WHERE code LIKE '%-100' = all Zone-100 equipment
- ✅ Hospital-specific raw naming preserved as source metadata, aliases, and display labels
- ✅ Multi-campus support enabled (different sites can have different building codes: UMH, BTU, etc.)
