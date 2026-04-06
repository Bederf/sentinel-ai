---
title: "CLAUDE_EQUIPMENT_TYPES.md - Equipment Naming & Type System"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# CLAUDE_EQUIPMENT_TYPES.md - Equipment Naming & Type System

Complete guide to equipment naming conventions and type system.

---

## 🎯 Why Equipment Types Matter

**The Problem It Solves:** Equipment codes are descriptive (S002-VAV-101) but the `type` field is what the system uses for:
- Technician specialty assignment (e.g., type='AHU' → specialty='hvac')
- ML model lookup (e.g., type='CHILLER' → R²=0.6065)
- Dashboard filtering and health scoring
- Predictive maintenance categorization

**If type='unknown', the whole system breaks:** Technicians don't get assigned, ML models fail to predict, dashboard can't filter.

---

## 📐 Two-Tier Equipment Naming System

### Tier 1: Zone Equipment (Offices)

**Pattern:** `{site}-{type}-{zone_id}`

**Examples:**
- `S002-VAV-101` - Level 1, Zone B (VAV serving office cluster)
- `S002-DALI-220` - Level 2, Zone C (DALI lighting controller)
- `S002-FCU-104` - Level 1, Zone D (Fan coil unit)

**Zone ID Encoding:**
- 001-099 = L0 (Ground floor)
- 100-199 = L1 (Level 1)
- 200-299 = L2 (Level 2)
- Format is numeric to support 100 zones per floor

**Best For:** Office buildings with zone-based HVAC/lighting control

### Tier 2: Plant Equipment (Infrastructure)

**Pattern:** `{site}-{type}-{location}-{sequence}`

**Examples:**
- `S002-CHILLER-B1-001` - Basement 1, first chiller
- `S002-GEN-R-001` - Roof, first generator (standby)
- `S002-MTR-B1-002` - Basement 1, second transformer

**Location Codes:**
- B1 = Basement 1
- G = Ground floor
- R = Roof
- L1, L2, etc. = Level 1, 2, etc.

**Best For:** Central plant equipment, infrastructure, emergency systems

---

## 🏥 Hospital Equipment (Site-005)

**Pattern:** `site-005-UMH-{type}-{floor}-{id}.{point}`

**Examples:**
- `site-005-UMH-AHU-L3-ICU.fan` - ICU HVAC (Level 3), fan point
- `site-005-UMH-GEN-B1-001.load` - Emergency generator, load point
- `site-005-UMH-LIFT-L2-001` - Elevator on Level 2
- `site-005-UMH-MEDGAS-L3-001.o2` - Medical gas (O₂) monitoring

**Features:**
- Building code (UMH) identifies hospital structure
- Floor labels show medical areas (L3 = ICU, theatres)
- Point-level monitoring (.fan, .load, .o2, .hepa, etc.)
- Type extraction: SUBSTRING(code FROM 'site-005-UMH-([A-Z]+)-') → AHU, GEN, LIFT, etc.

**Floors at Site-005:**
- B1 = Basement (emergency power, MEP)
- L1 = Level 1 (Administration)
- L2 = Level 2 (Surgical)
- L3 = Level 3 (ICU, Theatres, Critical care)
- L4-L9 = Levels 4-9 (Wards)
- R = Roof (Mechanical)

---

## ⚙️ Equipment Type Mapping

### HVAC Types (Specialty: hvac)
| Type | Count | Sites | Examples |
|------|-------|-------|----------|
| CHILLER | 4 | S002, site-012 | Central cooling |
| AHU | 25 | S002, site-005, site-012 | Air handling unit |
| FCU | 8 | S002, site-012 | Fan coil unit |
| VAV | 4 | S002 | Variable air volume |
| SPLIT | 1 | site-005 | Split system |
| CT | 8 | S002, site-005 | Cooling tower |
| CRAC | 1 | site-012 | Computer room AC |
| PUMP | 3 | site-005 | Water circulation |

### Electrical Types (Specialty: electrical)
| Type | Count | Sites | Examples |
|------|-------|-------|----------|
| GEN | 14 | S002, site-005, site-012 | Generator (standby) |
| TX | 2 | S002 | Transformer |
| UPS | 4 | S002, site-005, site-012 | Uninterruptible power |
| ATS | 2 | S002 | Automatic transfer switch |
| MSB | 3 | S002, site-005 | Main switch board |
| MTR | 2 | S002, site-005 | Motor/control |
| PFC | 1 | S002 | Power factor correction |
| FDR | 1 | S002 | Feeder |
| MV | 1 | S002 | Medium voltage |
| DB | 2 | S002, site-005 | Distribution board |

### Lighting Types (Specialty: dali)
| Type | Count | Sites | Examples |
|------|-------|-------|----------|
| DALI | 4 | S002 | DALI controller |
| LUM | 2 | S002 | Luminaire (fixture) |

### Specialized Types
| Type | Specialty | Count | Sites | Notes |
|------|-----------|-------|-------|-------|
| LIFT | general | 12 | site-005 | Hospital elevators |
| FIRE | fire | 4 | site-005 | Fire safety systems |
| ACC | security | 2 | site-005 | Access control |
| CCTV | security | 2 | site-005 | Surveillance |
| JACE | general | 10 | site-005 | Building automation controller |
| COLD | general | 3 | site-005 | Cold storage (pharma) |
| MEDGAS | general | 1 | site-005 | Medical gas monitoring |
| BOILER | hvac | 2 | site-005 | Hot water boiler |
| KEF | general | 2 | site-005 | Kitchen exhaust |

---

## 🔍 Extracting Type from Equipment Code

### Automated Extraction Process

```sql
-- For office equipment (S002-TYPE-ZONE)
UPDATE equipment
SET type = SUBSTRING(code FROM 'S002-([A-Z]+)-')
WHERE site_id = 'S002' AND type = 'unknown';

-- For hospital equipment (site-005-UMH-TYPE-FLOOR)
UPDATE equipment
SET type = SUBSTRING(code FROM 'site-005-UMH-([A-Z]+)-')
WHERE site_id = 'site-005' AND type = 'unknown';

-- For other sites (site-NNN-TYPE-LOCATION)
UPDATE equipment
SET type = SUBSTRING(code FROM 'site-[0-9]+-([A-Z]+)-')
WHERE type = 'unknown';
```

### Python Extraction

```python
import re

def extract_type_from_code(code: str) -> str:
    """Extract equipment type from code pattern."""
    # Match office pattern: S002-TYPE-...
    match = re.search(r'S\d{3}-([A-Z]+)-', code)
    if match:
        return match.group(1)

    # Match hospital pattern: site-NNN-UMH-TYPE-...
    match = re.search(r'site-\d+-UMH-([A-Z]+)-', code)
    if match:
        return match.group(1)

    # Generic pattern: site-NNN-TYPE-...
    match = re.search(r'site-\d+-([A-Z]+)-', code)
    if match:
        return match.group(1)

    return 'unknown'

# Examples
assert extract_type_from_code('S002-VAV-101') == 'VAV'
assert extract_type_from_code('site-005-UMH-AHU-L3-ICU.fan') == 'AHU'
assert extract_type_from_code('S002-CHILLER-B1-001') == 'CHILLER'
```

---

## ✅ Type Validation

### When Adding New Equipment

1. ✅ Code contains `{site}-{type}-{location}` pattern
2. ✅ Extract `type` from code during INSERT/migration
3. ✅ Verify type exists in `EQUIPMENT_TYPE_TO_SPECIALTY` mapping
4. ✅ Run: `SELECT DISTINCT type FROM equipment ORDER BY type;`

### Check for Unknown Types

```sql
-- Find equipment with unknown type
SELECT code, type FROM equipment WHERE type = 'unknown' LIMIT 10;

-- Count by site
SELECT site_id, COUNT(*) as unknown_count FROM equipment
WHERE type = 'unknown' GROUP BY site_id;
```

### If Type is Missing

**Problem:** Work orders can't auto-assign technicians, ML models fail, dashboard filters break.

**Solution:**
1. Verify equipment code has type embedded: `S002-VAV-101` → VAV
2. Run extraction migration
3. Verify: `SELECT COUNT(*) FROM equipment WHERE type = 'unknown';` → should be 0

---

## 🔗 Type to Technician Specialty Mapping

```python
EQUIPMENT_TYPE_TO_SPECIALTY = {
    # HVAC (read-only comfort optimization)
    'CHILLER': 'hvac', 'AHU': 'hvac', 'FCU': 'hvac', 'VAV': 'hvac',
    'SPLIT': 'hvac', 'CT': 'hvac', 'CRAC': 'hvac', 'PUMP': 'hvac', 'BOILER': 'hvac',

    # DALI (lighting control)
    'DALI': 'dali', 'LUM': 'dali',

    # Electrical (power systems)
    'GEN': 'electrical', 'TX': 'electrical', 'UPS': 'electrical',
    'ATS': 'electrical', 'MSB': 'electrical', 'MTR': 'electrical',
    'PFC': 'electrical', 'FDR': 'electrical', 'MV': 'electrical', 'DB': 'electrical',

    # Specialized
    'FIRE': 'fire',           # Fire safety
    'ACC': 'security',        # Access control
    'CCTV': 'security',       # Surveillance

    # Default for medical/other
    'JACE': 'general',        # Building automation
    'LIFT': 'general',        # Elevators
    'COLD': 'general',        # Cold storage
    'MEDGAS': 'general',      # Medical gas
    'KEF': 'general',         # Kitchen exhaust
}
```

---

## 📊 Multi-Site Equipment Registry

**Current State (All 3 sites):**

| Site | Name | Total Equipment | Types | ML-Enabled | Key Equipment |
|------|------|-----------------|-------|-----------|----------------|
| S002 | Office (Sandton) | 34 | 12 | 21% | VAV, FCU, CHILLER, UPS, DALI |
| site-005 | Hospital (Umhlanga) | 90 | 15 | 56% | AHU (25), GEN (12), LIFT (12) |
| site-012 | Office (Generic) | 19 | 7 | 79% | AHU, FCU, CHILLER |
| **TOTAL** | | **142** | **23** | **52%** | |

**ML Coverage:**
- Models available: CHILLER, AHU, FCU, VAV, UPS, GEN, DALI
- 65+ items with ML capability
- 77 items using rules-based predictions

---

## 🚀 Future-Proofing

**New Sites:** Just follow the pattern
- Office: `SITE_CODE-TYPE-ZONE_ID` (e.g., site-013-VAV-101)
- Hospital: `site-NNN-BUILDING_CODE-TYPE-FLOOR-ID.POINT`
- Infrastructure: `SITE_CODE-TYPE-LOCATION-SEQ`

**No code changes needed:** Type extraction is pattern-based, works for any site.

---

See also: `CLAUDE_ARCHITECTURE.md`, `CLAUDE_PATTERNS.md`
