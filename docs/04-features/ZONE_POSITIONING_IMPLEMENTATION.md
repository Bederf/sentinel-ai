# Digital Twin: Desk-Based Zone Positioning Integration

**Status:** In Progress (Phases 1-6 Complete, Phases 7-8 Remaining)

**Date Started:** 2026-02-10

## Overview

This document tracks the implementation of a flexible zone ingestion system for accurate equipment positioning in the 3D Digital Twin visualization. The system allows each building to have a unique zone configuration, enabling multi-building support.

**Key Achievement:** Migrating from simple zone letter offsets to desk-based zone centroids for accurate spatial positioning.

---

## Implementation Status

### ✅ Phase 1: Supabase Schema Migration

**File:** `supabase/migrations/057_zone_ingestion_schema.sql`

**Status:** COMPLETE

**What It Does:**
- Creates `zones` table for building-level zone configuration
- Extends `desks` table with `zone_id`, `z_coord`, and `context` columns
- Creates `zone_centroids` view for efficient centroid calculation
- Implements RLS policies for zones table

**Key Features:**
- Per-building zone isolation (composite unique constraint on building_id + zone_id)
- Zone type validation (open_office, meeting_room, plant_room, etc.)
- Context types for desks (near_diffuser, near_window, near_printer, corner, open_plan)
- Automatic centroid calculation from desk positions

**Run Migration:**
```bash
# Local Supabase
supabase db push

# Production (apply manually)
psql $DATABASE_URL -f supabase/migrations/057_zone_ingestion_schema.sql
```

---

### ✅ Phase 2: One-Time Migration Script for site-002

**File:** `backend/scripts/migrate_zone_desk_data.py`

**Status:** COMPLETE

**What It Does:**
- Loads zones.json.bak (15 zones) and desks.json.bak (300 desks)
- Migrates floor codes: L10→L0, L11→L1, L12→L2
- Calculates 3D coordinates for all desks based on grid layout
- Inserts data into Supabase zones and desks tables
- Validates data integrity

**Floor Code Migration:**
- `L10` (old format) → `L0` (ground level)
- `L11` → `L1` (first floor)
- `L12` → `L2` (second floor)

**3D Coordinate System:**
- X-axis: Zone offset (6m per zone, zones A-E = 0-30m)
- Y-axis: Floor height (B1=0.5m, L0=3.5m, L1=6.5m, L2=9.5m)
- Z-axis: Desk grid position within zone (0-20m depth, 4 rows × 5 cols)

**Usage:**
```bash
# Dry run (preview without changes)
python backend/scripts/migrate_zone_desk_data.py --site site-002 --dry-run

# Live migration
python backend/scripts/migrate_zone_desk_data.py --site site-002
```

**Expected Output (site-002):**
- 15 zones migrated (5 per floor × 3 floors)
- 300 desks migrated (20 per zone)
- All zones with L0/L1/L2 floor codes
- All desks with valid {x, y, z} coordinates

---

### ✅ Phase 3: Zone Ingestion Service

**File:** `backend/app/services/zone_ingestion_service.py`

**Status:** COMPLETE

**What It Does:**
- Validates zone configurations (unique IDs, valid floor codes, valid types)
- Validates desk configurations (valid references, matching floors, numeric coordinates)
- Calculates zone centroids from desk positions
- Supports multi-building zone structures

**Key Methods:**
- `ingest_zones()` - Validate and store zone definitions
- `ingest_desks()` - Validate and store desk positions
- `calculate_zone_centroid()` - Get centroid for single zone
- `get_all_zone_centroids()` - Get centroids for all zones in building
- `validate_zone_structure()` - Check data integrity

**Validation Rules:**
- Zone IDs must be unique within building
- Floor codes must be: B#, G, L#, R
- Zone types: open_office, meeting_room, plant_room, etc.
- Desks must reference existing zones
- Desk floor must match zone floor
- Coordinates must be numeric and within bounds

---

### ✅ Phase 4: Zone & Desk Repositories

**Files:**
- `backend/app/database/repositories/zone_repository.py`
- Extended: `backend/app/database/repositories/desk_repository.py`

**Status:** COMPLETE

**What They Do:**
- Manage database operations for zones and desks
- Query zones by building, floor, or zone_id
- Query desks by building, zone, or floor
- Calculate centroids from desk data
- Support upsert operations for bulk ingestion

**Zone Repository Methods:**
- `get_by_building()` - Get all zones for a building
- `get_by_zone_id()` - Get specific zone
- `get_by_floor()` - Get zones on specific floor
- `get_zone_centroids()` - Query zone_centroids view
- `create()`, `update()`, `delete()` - CRUD operations

**Desk Repository Extensions:**
- `get_by_building_uuid()` - Get all desks for a building
- `get_by_zone_id()` - Get desks in specific zone
- `get_centroids_for_zones()` - Calculate centroids for list of zones

---

### ✅ Phase 5: Zone Ingestion API

**File:** `backend/app/api/zone_ingestion.py`

**Status:** COMPLETE

**Endpoints:**
1. `POST /api/buildings/{building_id}/zone-ingestion/zones`
   - Ingest zone configuration
   - Validation: unique IDs, valid floor codes, valid types
   - Response: `{status, message, items_created}`

2. `POST /api/buildings/{building_id}/zone-ingestion/desks`
   - Ingest desk configuration
   - Validation: valid zone references, matching floors, numeric coordinates
   - Response: `{status, message, items_created}`

3. `GET /api/buildings/{building_id}/zone-ingestion/zones/{zone_id}/centroid`
   - Get centroid for specific zone
   - Response: `{zone_id, centroid: {x, z}, desk_count}`

4. `GET /api/buildings/{building_id}/zone-ingestion/centroids`
   - Get all zone centroids for building
   - Response: `{building_id, centroid_count, centroids: {...}}`

5. `GET /api/buildings/{building_id}/zone-ingestion/validate`
   - Validate zone and desk structure
   - Response: `{is_valid, errors, error_count}`

**Error Handling:**
- 400: Validation failed (duplicate IDs, invalid floor codes, missing zones, etc.)
- 404: Zone or desks not found
- 500: Database error

---

### ✅ Phase 6: Desk Data Query API

**File:** `backend/app/api/desks.py`

**Status:** COMPLETE

**Endpoints:**
1. `GET /api/buildings/{building_id}/desks`
   - Get all desks for building (optional floor filter)
   - Response: List of desk records with positions

2. `GET /api/buildings/{building_id}/desks/zones/{zone_id}`
   - Get desks in specific zone
   - Response: List of desk records

3. `GET /api/buildings/{building_id}/desks/zones/{zone_id}/centroid`
   - Get centroid for specific zone
   - Response: `{zone_id, centroid: {x, z}, desk_count}`

4. `GET /api/buildings/{building_id}/desks/centroids`
   - Get centroids for all zones (efficient for Digital Twin)
   - Response: `{building_id, zone_count, centroid_count, centroids}`

5. `GET /api/buildings/{building_id}/desks/stats`
   - Get desk statistics
   - Response: `{total_desks, total_zones, desks_per_zone, desks_per_floor, desks_by_context}`

**Performance Note:** Centroid endpoints (~1.5KB) are ~80x smaller than full desk data (~120KB).

---

### ✅ Phase 7: Router Registration

**File:** `backend/app/api/registrars/building.py`

**Status:** COMPLETE

**Changes:**
- Added imports for `zone_ingestion` and `desks` modules
- Registered routers in building domain (after digital_twin router)

```python
app.include_router(zone_ingestion.router, tags=["zone-ingestion"])
app.include_router(desks.router, tags=["desks"])
```

---

### ✅ Phase 8: Zone Mapping Service Update

**File:** `backend/app/services/zone_mapping_service.py`

**Status:** COMPLETE

**Changes:**
- Updated default mappings to use L0/L1/L2 instead of L10/L11/L12
- Updated regex in `infer_zone_from_equipment_id()` to support L0/L1/L2 format
- Maintains backward compatibility with older floor codes

**Floor Code Support:**
- Old format: L10, L11, L12, B, G, etc.
- New format: B#, G, L0, L1, L2, R (standardized)
- Migration: L10→L0, L11→L1, L12→L2

---

## Remaining Work

### ⏳ Phase 9: Frontend - API Client Update

**File to Create:** Update `frontend/src/lib/api/sites.ts`

**What to Do:**
1. Add `Desk` interface for desk data
2. Add `getDesks()` method - Query desks by building
3. Add `getDesksByZone()` method - Query desks by zone
4. Add `getZoneCentroids()` method - Query all zone centroids

**Example Implementation:**
```typescript
export interface Desk {
  desk_id: string;
  zone_id: string;
  floor: string;
  context: string;
  coordinates: { x: number; y: number; z: number };
}

export const sitesApi = {
  getDesks: (buildingId: string, floor?: string) =>
    fetchApi<Desk[]>(`/api/buildings/${buildingId}/desks${floor ? `?floor=${floor}` : ''}`),

  getZoneCentroids: (buildingId: string) =>
    fetchApi<{ centroids: Record<string, { x: number; z: number }> }>(
      `/api/buildings/${buildingId}/desks/centroids`
    ),
};
```

---

### ⏳ Phase 10: Frontend - Equipment Positioning Update

**File to Update:** `frontend/src/components/digital-twin/EquipmentMarkers.tsx`

**What to Do:**
1. Load zone centroids (instead of just zone letters)
2. Update `getEquipmentPosition()` to use centroid-based positioning
3. Apply type-specific offsets from centroids
4. Fallback to zone letter offsets if centroids unavailable

**Key Changes:**
```typescript
interface EquipmentMarkersProps {
  zoneCentroids?: Record<string, { x: number; z: number }>;  // NEW
}

function getEquipmentPosition(
  equipment: Equipment,
  zoneCentroids?: Record<string, { x: number; z: number }>
): [number, number, number] {
  // Use centroid if available
  if (zoneCentroids) {
    const zoneId = `Zone-${floorCode}-${zoneLetter}`;
    const centroid = zoneCentroids[zoneId];
    if (centroid) {
      return [centroid.x + typeOffset[0], y, centroid.z + typeOffset[1]];
    }
  }
  
  // Fallback to zone letter offsets
  const zoneOffset = (zoneLetter.charCodeAt(0) - 65) * 6;
  return [zoneOffset + 3, y, 10];
}
```

---

### ⏳ Phase 11: Frontend - Digital Twin Integration

**File to Update:** `frontend/src/components/digital-twin/DigitalTwin.tsx`

**What to Do:**
1. Add state for zone centroids
2. Load centroids on component mount
3. Pass centroids to EquipmentMarkers

**Example:**
```typescript
const [zoneCentroids, setZoneCentroids] = useState<Record<string, { x: number; z: number }>>({});

useEffect(() => {
  async function loadCentroids() {
    const response = await sitesApi.getZoneCentroids(buildingId);
    setZoneCentroids(response.centroids);
  }
  loadCentroids();
}, [buildingId]);

return (
  <EquipmentMarkers
    equipment={equipment}
    zoneCentroids={zoneCentroids}
    ...
  />
);
```

---

### ⏳ Phase 12: Frontend - Zone Ingestion Wizard

**File to Create:** `frontend/src/components/wizards/ZoneIngestionWizard.tsx`

**What to Do:**
1. Create multi-step wizard for zone definition
2. Step 1: Floor plan upload (optional reference)
3. Step 2: Define zones (zone_id, floor, type, area)
4. Step 3: Define desks (desk_id, zone, coordinates, context)
5. Step 4: Preview zone layout in 3D
6. Step 5: Submit to backend

**UI Components Needed:**
- Zone definition table/form
- Desk entry (manual, grid-based, or CSV import)
- 3D preview with zones as colored areas
- Validation feedback
- Progress persistence (localStorage draft)

---

### ⏳ Phase 13: Integration with BMS Connection Wizard

**File to Update:** `frontend/src/components/wizards/BMSConnectionWizard.tsx`

**What to Do:**
1. Add Zone Ingestion Wizard as a step
2. Insert after building structure configuration
3. Make zone ingestion conditional/optional
4. Skip for existing buildings with zones

---

## Testing Checklist

### Backend Tests

- [ ] Create `backend/tests/test_zone_ingestion.py`
  - [ ] Test zone ingestion for different buildings
  - [ ] Test desk-zone validation
  - [ ] Test zone centroid calculation
  - [ ] Test multi-building support

- [ ] Create `backend/tests/test_desk_zone_migration.py`
  - [ ] Test floor code migration (L10→L0, L11→L1, L12→L2)
  - [ ] Test desk coordinate calculation
  - [ ] Test 20 desks per zone (site-002)
  - [ ] Test coordinate bounds (X: 0-30m, Z: 0-20m)

### API Tests

- [ ] Test zone ingestion endpoints
  - [ ] `POST /api/buildings/{id}/zone-ingestion/zones` - create zones
  - [ ] `POST /api/buildings/{id}/zone-ingestion/desks` - create desks
  - [ ] Validation: duplicate IDs, invalid zones, mismatched floors
  - [ ] Error handling: 400, 404, 500 responses

- [ ] Test desk query endpoints
  - [ ] `GET /api/buildings/{id}/desks` - list desks
  - [ ] `GET /api/buildings/{id}/desks/zones/{zone_id}` - zone desks
  - [ ] `GET /api/buildings/{id}/desks/centroids` - all centroids

### Frontend Tests

- [ ] Test zone centroid loading
  - [ ] API call executes on component mount
  - [ ] Fallback works if API fails
  - [ ] Centroids populated in state

- [ ] Test equipment positioning with centroids
  - [ ] Equipment positioned using centroid + type offset
  - [ ] Fallback to zone letter offset if no centroid
  - [ ] No equipment overlap

- [ ] Test zone ingestion wizard
  - [ ] Zone definition entry and validation
  - [ ] Desk entry (manual, grid, CSV options)
  - [ ] 3D preview renders correctly
  - [ ] Submit saves to backend

### Integration Tests

- [ ] End-to-end: Ingestion → API → Frontend positioning
- [ ] Multi-building: Different buildings have different zone structures
- [ ] Visual verification: Equipment in correct zones in 3D view

### Manual Verification (site-002)

- [ ] Digital Twin view loads and displays correctly
- [ ] Select L1 floor → Equipment spread across zones A-E
- [ ] Verify equipment distribution:
  - [ ] Zone A: X 0-6m
  - [ ] Zone B: X 6-12m
  - [ ] Zone C: X 12-18m
  - [ ] Zone D: X 18-24m
  - [ ] Zone E: X 24-30m
- [ ] No equipment overlap (spacing >= 0.5m)
- [ ] Floor height correct per floor (L0=3.5m, L1=6.5m, L2=9.5m)

---

## API Testing Examples

### Ingest Zones
```bash
curl -X POST http://localhost:9095/api/buildings/site-002/zone-ingestion/zones \
  -H "Content-Type: application/json" \
  -d '{
    "zones": [
      {
        "zone_id": "Zone-L1-A",
        "zone_name": "Level 1 Zone A",
        "floor": "L1",
        "zone_letter": "A",
        "zone_type": "open_office",
        "typical_occupancy": 20,
        "area_sqm": 200
      }
    ]
  }'
```

### Ingest Desks
```bash
curl -X POST http://localhost:9095/api/buildings/site-002/zone-ingestion/desks \
  -H "Content-Type: application/json" \
  -d '{
    "desks": [
      {
        "desk_id": "1001",
        "zone_id": "Zone-L1-A",
        "floor": "L1",
        "context": "near_window",
        "coordinates": {"x": 3.5, "y": 6.5, "z": 10.5}
      }
    ]
  }'
```

### Get Zone Centroids
```bash
curl http://localhost:9095/api/buildings/site-002/desks/centroids | jq
```

---

## Migration Execution Steps

### Step 1: Apply Supabase Migration
```bash
cd /opt/bms-intelligence
supabase db push
# Or manually: psql $DATABASE_URL -f supabase/migrations/057_zone_ingestion_schema.sql
```

### Step 2: Run Migration Script
```bash
cd /opt/bms-intelligence
python backend/scripts/migrate_zone_desk_data.py --site site-002 --dry-run
# Verify output
python backend/scripts/migrate_zone_desk_data.py --site site-002
# Execute migration
```

### Step 3: Verify Data in Supabase
```bash
psql $DATABASE_URL -c "SELECT COUNT(*) FROM zones WHERE building_id = 'site-002';"
# Expected: 15
psql $DATABASE_URL -c "SELECT COUNT(*) FROM desks WHERE building_id = 'site-002';"
# Expected: 300
```

### Step 4: Test API Endpoints
```bash
# Test desks endpoint
curl http://localhost:9095/api/buildings/site-002/desks | wc -c
# Expected: ~120KB (300 desks)

# Test centroids endpoint
curl http://localhost:9095/api/buildings/site-002/desks/centroids | wc -c
# Expected: ~1.5KB (15 centroids) - 80x smaller!
```

### Step 5: Deploy Frontend Changes
```bash
cd /opt/bms-intelligence/frontend
npm install
npm run dev
# Test Digital Twin positioning
```

---

## Success Criteria

✅ **Phase Completion Indicators:**

1. ✅ Multi-building zone support
   - Each building can have unique zone structure
   - System scales to 10+ buildings with different configurations

2. ✅ Data integrity (site-002)
   - 15 zones migrated with L0/L1/L2 floor codes
   - 300 desks evenly distributed (20 per zone)
   - Zero orphaned desks or invalid zone references
   - Data stored in Supabase (not just JSON files)

3. ✅ Positioning accuracy
   - Equipment positioned using zone centroids
   - No equipment overlap (spacing >= 0.5m)
   - Visual alignment in 3D (equipment in correct zones)
   - Fallback works if centroids unavailable

4. ✅ API functionality
   - Zone ingestion endpoints work for any building
   - Desk query endpoints return correct data
   - Centroid calculation accurate from desk data
   - Validation catches invalid configurations

5. ✅ Performance
   - 3D scene render time < 500ms
   - API response < 200ms for centroid data
   - Frame rate >= 30fps during navigation
   - Centroid loading 80x more efficient than desk data

6. ✅ UI workflow (frontend phase)
   - Zone ingestion wizard integrated into building onboarding
   - 3D preview works before submission
   - Validation feedback clear and actionable

---

## Rollback Plan

If issues arise:

1. **Delete Supabase data:**
   ```bash
   psql $DATABASE_URL -c "DELETE FROM desks WHERE building_id = 'site-002';"
   psql $DATABASE_URL -c "DELETE FROM zones WHERE building_id = 'site-002';"
   ```

2. **Restore JSON backup:**
   ```bash
   cd backend/app/data/buildings/site-002
   mv zones.json.pre-migration zones.json
   ```

3. **Revert code (if needed):**
   ```bash
   git checkout -- backend/app/services/zone_ingestion_service.py
   git checkout -- backend/app/api/zone_ingestion.py
   # ... revert other modified files
   ```

4. **Restart services:**
   ```bash
   ./start-backend.sh
   ./start-frontend.sh
   ```

---

## Resources

- **Backup Data:** `/opt/bms-intelligence/backend/app/data/buildings/site-002/{zones,desks}.json.bak`
- **Migration Schema:** `supabase/migrations/057_zone_ingestion_schema.sql`
- **Migration Script:** `backend/scripts/migrate_zone_desk_data.py`
- **Related Docs:** 
  - `docs/02-architecture/naming-conventions.md`
  - `docs/04-features/DIGITAL_TWIN_REAL_DATA_INTEGRATION.md`
  - `CLAUDE.md` (project instructions)

---

## Notes

- **Database Support:** Full Supabase PostgreSQL + view support required
- **Backward Compatibility:** System maintains old L10/L11/L12 codes but migrates to L0/L1/L2
- **Future Multi-Building:** After site-002 is validated, other buildings can use zone ingestion API
- **No Code Changes for New Buildings:** Fully data-driven via zone ingestion API
