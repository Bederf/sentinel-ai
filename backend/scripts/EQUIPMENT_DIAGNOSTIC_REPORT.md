# Equipment Data Diagnostic Report

## Problem Summary
Digital Twin and equipment discovery showing only **1 device per building** instead of 50+ expected equipment items.

## Root Cause Analysis

### Data Sources Architecture
The system uses a **3-tier fallback pattern**:

1. **Primary Source**: Supabase `equipment` table
2. **Secondary Source**: JSON fallback files in `backend/app/data/buildings/{site-code}/equipment/`
3. **Tertiary Source**: Other JSON files (zones.json, generators.json, energy_centre.json)

### Current Issue

**Status**: ✅ **JSON fallback data EXISTS** but **Supabase table appears EMPTY or SPARSE**

```
Equipment Available (JSON fallback):
├── site-002: 61 equipment files ✓
├── site-005: ? files
├── site-006: ? files
├── ... (7 more sites)
└── Total: ~500+ equipment items in JSON

Equipment in Supabase:
├── site-002: ? (likely 0-1)
├── site-005: ? (likely 0-1)
└── ... (Unknown - needs verification)
```

## API Endpoint Behavior

### `/api/buildings/{building_id}/equipment` Flow

```python
# File: backend/app/api/buildings.py (line 630-850)

try:
    # Step 1: Query Supabase equipment table
    repo = EquipmentRepository()
    equipment_data = repo.get_by_building_code(site_code)

    if equipment_data:  # ← KEY: Empty list [] is falsy in Python
        # Step 2: Process Supabase results
        # ... build equipment_list ...
        return {"equipment": equipment_list, "source": "supabase"}  # ← EARLY RETURN

except Exception as e:
    # Step 3: Fall back to JSON files
    pass

# Step 4: JSON Fallback (zones.json, generators.json, energy_centre.json, etc.)
equipment_list = []  # Reset
# Load from JSON files...
return {"equipment": equipment_list, "source": "json"}
```

### Execution Path for site-002

**Current behavior (showing 1 device)**:
```
1. Query: repo.get_by_building_code("site-002")
2. Result: [...]  (empty or 1 item from Supabase)
3. Return early with 1 equipment ✗
4. JSON fallback NOT used (except for controllable status merge on lines 755-775)
```

**Expected behavior (showing 61 devices)**:
```
1. Query: repo.get_by_building_code("site-002")
2. Result: []  (empty, OR exception)
3. Fall through to JSON fallback
4. Load zones.json, generators.json, energy_centre.json, equipment/*.json
5. Return 61+ equipment items ✓
```

## Equipment Repository Query

**File**: `backend/app/database/repositories/equipment_repository.py` (line 56-75)

```python
def get_by_building_code(self, building_code: str) -> List[Dict[str, Any]]:
    """Get equipment by building code (e.g., 'site-002')"""
    # 1. Look up building by code
    building_response = self.client.table('buildings').select('id').eq(
        'code', building_code
    ).execute()

    if not building_response.data:
        return []  # ← No building found → returns []

    building_uuid = building_response.data[0]['id']

    # 2. Query equipment table for this building
    equipment_response = self.client.table('equipment').select("*").eq(
        'building_id', building_uuid
    ).execute()

    return equipment_response.data  # ← Returns whatever Supabase returns (could be [])
```

### Query Flow:
```
1. buildings table: LOOKUP "site-002" → get UUID
   - If found: Returns UUID
   - If not found: Returns []

2. equipment table: QUERY WHERE building_id = UUID
   - If building_uuid exists: Returns equipment list (may be empty)
   - If no building_uuid: Returns []
```

## Data Population Status

### JSON Fallback Files (✓ Confirmed to Exist)
- **site-002/equipment/**: 61 files with equipment definitions
- **site-002/zones.json**: ~15 HVAC zones
- **site-002/generators.json**: Generator plant configuration
- **site-002/energy_centre.json**: Power distribution components

### Supabase Tables (❓ Status Unknown)

Need to verify:
1. **buildings** table:
   - Does it have rows for site-002, site-005, etc.?
   - Are the `code` values populated correctly?

2. **equipment** table:
   - Is it empty?
   - How many rows per building_id?
   - Are building_id foreign keys correct?

## Next Diagnostic Steps

### Step 1: Verify Buildings Table
```sql
SELECT id, code, name FROM buildings WHERE code LIKE 'site-%';
-- Should return: site-002, site-005, site-006, ... site-013
```

### Step 2: Count Equipment per Building
```sql
SELECT building_id, COUNT(*) as count
FROM equipment
GROUP BY building_id
ORDER BY count DESC;
-- Shows distribution of equipment across buildings
```

### Step 3: Check for Specific Equipment
```sql
SELECT id, code, name, building_id
FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
LIMIT 5;
-- Should show equipment like S002-CHILLER-B1-001, S002-FCU-L1-A, etc.
```

## Solution Options

### Option A: Rely on JSON Fallback (Quick Fix)
- ✅ No database changes needed
- ✅ 61 equipment items already exist in JSON
- ✅ Will work immediately
- ❌ Not scalable long-term
- ❌ Frontend doesn't benefit from Supabase features

**Action**: Let Supabase return empty, fallback to JSON works automatically

### Option B: Populate Supabase Equipment Table (Proper Fix)
- ✅ Scalable, searchable, performant
- ✅ Enables advanced features (health scoring, alerts, etc.)
- ✅ Backend can use Supabase directly
- ❌ Requires data migration from JSON
- ❌ Requires seeding script

**Action**: Create migration to populate equipment table from JSON files

### Option C: Hybrid Approach (Recommended)
- ✅ Keep JSON as fallback
- ✅ Also populate Supabase incrementally
- ✅ Both sources work in parallel
- ✅ Can migrate gradually

**Action**:
1. Fix JSON fallback to work (Option A)
2. Create seed script for Supabase (Option B)
3. Run both in parallel during transition

## API Testing

### Test Current Behavior
```bash
# Should show 1 equipment (broken)
curl http://localhost:9095/api/buildings/site-002/equipment | jq '.equipment | length'

# Should show 61 equipment if JSON fallback worked
curl http://localhost:9095/api/buildings/site-002/equipment | jq '.equipment | length'
```

### Test Different Sites
```bash
# site-005, site-006, etc.
for site in site-005 site-006 site-007 site-008 site-009 site-010 site-011 site-012 site-013; do
  count=$(curl -s http://localhost:9095/api/buildings/$site/equipment | jq '.equipment | length')
  echo "$site: $count equipment"
done
```

## Supabase Schema Status

### Buildings Table (Migration 001)
```sql
CREATE TABLE buildings (
  id UUID PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,  -- e.g., "site-002"
  name TEXT NOT NULL,
  ...
);
```

### Equipment Table (Migration 001)
```sql
CREATE TABLE equipment (
  id UUID PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,  -- e.g., "S002-CHILLER-B1-001"
  building_id UUID NOT NULL REFERENCES buildings(id),
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  ...
);
```

**Critical Issue**: If `buildings` table is empty or `equipment.building_id` references don't exist, queries return [].

## Recommended Investigation

1. **Check Supabase Connection**
   - Is `USE_JSON_STORAGE=true` in .env? (If yes, Supabase is disabled)
   - Can backend connect to Supabase successfully?

2. **Verify Database Population**
   - Run diagnostic PostgreSQL queries above
   - Check if any equipment rows exist

3. **Test JSON Fallback**
   - Temporarily disable Supabase in endpoint (force exception)
   - Verify JSON fallback returns 61 items

4. **Fix Issue**
   - If Supabase is disabled: Already working via JSON
   - If Supabase is empty: Populate with seed script
   - If both exist: Ensure Supabase takes priority correctly

## Files Involved

- **Frontend**:
  - `frontend/src/components/digital-twin/DigitalTwin.tsx` (uses equipment API)
  - `frontend/src/hooks/useSitesList.ts` (fetches sites)
  - `frontend/src/hooks/useZoneCentroids.ts` (fetches zone positions)

- **Backend**:
  - `backend/app/api/buildings.py` (line 630-850: equipment endpoint)
  - `backend/app/database/repositories/equipment_repository.py` (Supabase queries)
  - `backend/app/data/buildings/site-002/equipment/` (JSON fallback)

- **Database**:
  - `supabase/migrations/001_initial_schema.sql` (tables: buildings, equipment)
  - Local Supabase: postgresql://postgres:postgres@localhost:55322/postgres

---

**Status**: AWAITING SUPABASE VERIFICATION
Next action: Query Supabase tables to determine root cause
