# Digital Twin Zones & Desks Sync - Completion Report

**Date:** 2026-02-10  
**Building:** Sandton City Office Tower (site-002)  
**Status:** ✅ Complete

---

## Summary

Successfully synced corrected zones and desks data to Supabase, enabling zone-based equipment positioning in the digital twin 3D visualization.

### Key Achievements

✅ **Floor Name Correction**
- L10 → L0 (Level 0)
- L11 → L1 (Level 1)
- L12 → L2 (Level 2)

✅ **Data Generation**
- 16 zones (1 basement + 5 per floor × 3 floors)
- 300 desks (20 per zone)
- x_coord & z_coord for all desks (for centroid calculations)

✅ **Supabase Sync**
- 16 zones inserted into `zones` table
- 300 desks inserted into `desks` table
- All records include corrected floors and positioning coordinates

---

## Data Structure

### Zones (16 total)

```
B1 (Basement):     1 zone  - Plant room
├── Zone-B1-001

L0 (Level 0):      5 zones - Open office
├── Zone-L0-A
├── Zone-L0-B
├── Zone-L0-C
├── Zone-L0-D
└── Zone-L0-E

L1 (Level 1):      5 zones - Open office
├── Zone-L1-A
├── Zone-L1-B
├── Zone-L1-C
├── Zone-L1-D
└── Zone-L1-E

L2 (Level 2):      5 zones - Open office
├── Zone-L2-A
├── Zone-L2-B
├── Zone-L2-C
├── Zone-L2-D
└── Zone-L2-E
```

### Desks (300 total)

- **20 desks per zone**
- **Positioned by context:**
  - `near_diffuser`: +2.5x, +0.5z
  - `near_window`: -2.5x, +1.5z
  - `near_printer`: +2.0x, -2.0z
  - `corner`: -2.0x, -2.5z
  - `open_plan`: 0.0x, 0.0z

- **Sample desk:**
  ```json
  {
    "desk_id": "1001",
    "floor": "L0",
    "zone_id": "Zone-L0-A",
    "context": "near_diffuser",
    "x_coord": 7.5,
    "z_coord": 5.5
  }
  ```

---

## Database Schema

### Zones Table

```sql
CREATE TABLE zones (
    id UUID PRIMARY KEY,
    building_id UUID NOT NULL REFERENCES buildings(id),
    zone_id TEXT NOT NULL,           -- e.g., "Zone-L0-A"
    zone_name TEXT NOT NULL,         -- e.g., "Zone A - Level 0"
    floor TEXT NOT NULL,             -- "L0", "L1", "L2", "B1"
    zone_type TEXT,                  -- "open_office", "plant_room"
    typical_occupancy INTEGER,       -- 20 desks
    area_sqm DECIMAL,                -- ~400 sqm
    zone_letter TEXT,                -- "A", "B", "C", "D", "E", "001"
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    UNIQUE(building_id, zone_id)
);
```

### Desks Table (Extended)

```sql
ALTER TABLE desks ADD COLUMN IF NOT EXISTS zone_id TEXT;
ALTER TABLE desks ADD COLUMN IF NOT EXISTS z_coord DECIMAL(6,2);
ALTER TABLE desks ADD COLUMN IF NOT EXISTS context TEXT;

-- Key columns used:
desk_id TEXT UNIQUE NOT NULL,        -- "1001"
building_id UUID NOT NULL,
floor TEXT NOT NULL,                 -- "L0"
zone_id TEXT,                        -- "Zone-L0-A"
x_coord DECIMAL(6,2),                -- 7.5
z_coord DECIMAL(6,2),                -- 5.5
y_coord DECIMAL(6,2),                -- 0.0
context TEXT,                        -- "near_diffuser"
```

### Zone Centroids View

```sql
CREATE VIEW zone_centroids AS
SELECT
    z.building_id,
    z.zone_id,
    z.floor,
    ROUND(AVG(d.x_coord), 2) AS centroid_x,
    ROUND(AVG(d.z_coord), 2) AS centroid_z,
    COUNT(d.id) AS desk_count
FROM zones z
LEFT JOIN desks d ON d.zone_id = z.zone_id AND d.building_id = z.building_id
GROUP BY z.building_id, z.zone_id, z.floor;
```

**Centroids are auto-calculated** from desk positions and used by the digital twin for accurate equipment placement.

---

## Files Modified/Created

### JSON Data Files

| File | Status | Changes |
|------|--------|---------|
| `backend/app/data/buildings/site-002/zones.json` | ✅ Updated | Added all 16 zones with structure |
| `backend/app/data/buildings/site-002/desks.json` | ✅ Created | Corrected floors + coordinates |
| `backend/app/data/buildings/site-002/desks.json.bak` | 📦 Original | Preserved (legacy L10, L11, L12) |

### Scripts Created

| Script | Purpose |
|--------|---------|
| `backend/scripts/generate_corrected_desks.py` | Transform legacy desks: correct floors, generate coordinates |
| `backend/scripts/generate_corrected_zones.py` | Generate complete zones.json with all 16 zones |
| `backend/scripts/sync_to_supabase_final.py` | Main sync script: push zones/desks to Supabase |
| `backend/scripts/verify_zones_desks_sync.py` | Verify sync succeeded (requires .env) |
| `backend/scripts/verify_api_endpoints.sh` | Test API endpoints via curl |

---

## API Endpoints

### Retrieve Zone Centroids
```bash
GET /api/buildings/{building_id}/desks/centroids
```

**Response:**
```json
{
  "building_id": "7e7c1500-d9b2-4b43-b7cf-650648816b21",
  "zone_count": 16,
  "centroid_count": 16,
  "centroids": {
    "Zone-B1-001": {"x": 0.0, "z": 0.0},
    "Zone-L0-A": {"x": 5.0, "z": 5.0},
    ...
  }
}
```

### Retrieve Desks for Building
```bash
GET /api/buildings/{building_id}/desks
```

**Returns:** Array of desk objects with coordinates

### Retrieve Desks by Zone
```bash
GET /api/buildings/{building_id}/desks/zones/{zone_id}
```

**Example:**
```bash
GET /api/buildings/site-002/desks/zones/Zone-L0-A
```

---

## Digital Twin Integration

### Equipment Positioning Flow

1. **Equipment Code Parsed**
   - Example: `S002-CHILLER-B1-001`
   - Floor: B1, Zone: 001

2. **Zone Lookup**
   - Map to correct zone: `Zone-B1-001`
   - Fetch centroid from `zone_centroids` view

3. **Position Calculation**
   - Base: centroid (0.0, 0.0)
   - Offset: type-specific (e.g., CHILLER: [-12, -8])
   - Final: centroid + offset

4. **3D Rendering**
   - EquipmentMarkers component renders at calculated position
   - Color-coded by health score

### Frontend Components

- **DigitalTwin.tsx:** Main orchestrator
  - Loads equipment via `useEquipmentData()`
  - Fetches zone centroids via `sitesApi.getZoneCentroids()`
  
- **EquipmentMarkers.tsx:** Position calculation
  - Uses `getEquipmentPosition()` to calculate 3D coords
  - Falls back to zone letter offset if centroids unavailable

---

## Verification Checklist

- [x] Zones loaded from zones.json
- [x] Desks loaded and transformed from desks.json.bak
- [x] Floor names corrected (L10→L0, L11→L1, L12→L2)
- [x] Coordinates generated for all desks
- [x] Zones synced to Supabase (16 records)
- [x] Desks synced to Supabase (300 records)
- [x] Zone centroids calculated from desk positions
- [x] API endpoints accessible

---

## Known Issues & Next Steps

### ⚠️ Outstanding Issue: Health Score Field

**Problem:** Backend returns `"health"` but frontend expects `"health_score"`

**Impact:** Equipment shows 0% health and displays as critical

**Files Affected:**
- `backend/app/api/buildings.py` line ~633: GET `/api/buildings/{id}/equipment`

**Fix Required:**
Replace `"health": health` with `"health_score": health` in the equipment response mapping

**User Status:** "i will fix the health issue"

### ✅ Verification Steps

1. **Test API endpoints:**
   ```bash
   bash backend/scripts/verify_api_endpoints.sh
   ```

2. **Check zone centroids:**
   ```bash
   curl http://localhost:9095/api/buildings/site-002/desks/centroids | jq
   ```

3. **Open digital twin:**
   - Navigate to http://localhost:9096/digital-twin
   - Equipment should appear in zones
   - Compare with expected positions from zones.json

4. **Check health scores:**
   ```bash
   curl http://localhost:9095/api/buildings/site-002/equipment | jq '.[0]'
   ```
   - Look for `health` vs `health_score` field
   - Should be non-zero values (not all 0%)

---

## Troubleshooting

### Equipment Still Not Visible

**Possible Causes:**

1. **Centroids not calculated**
   - Check: `SELECT * FROM zone_centroids WHERE building_id = '...';`
   - Fix: Ensure desks have x_coord and z_coord (verified ✅)

2. **API not returning centroids**
   - Check: `GET /api/buildings/site-002/desks/centroids`
   - Fix: Verify migrations ran, check backend logs

3. **Health all zero**
   - Check: `GET /api/buildings/site-002/equipment`
   - Fix: Change `health` → `health_score` in buildings.py

4. **Browser cache**
   - Clear: F12 → Application → Clear site data
   - Or: Hard refresh (Ctrl+Shift+R)

### Sync Errors

**If re-running sync:**
```bash
# Dry-run first:
python backend/scripts/sync_to_supabase_final.py --dry-run

# Then sync:
python backend/scripts/sync_to_supabase_final.py
```

**Upsert strategy:** Records with same `desk_id` will be updated (safe to re-run)

---

## Performance Notes

- **Zone Centroids View:** Calculated on-demand, no pre-computation needed
- **Query Optimization:** Indexed on `building_id`, `zone_id`, `floor`
- **Desktop Coordinates:** Stored as DECIMAL(6,2) for precision (±0.01 units)
- **Centroid Aggregation:** AVG() function used for smooth distribution

---

## Testing Commands

### Verify Zones in Supabase
```sql
SELECT zone_id, floor, COUNT(*) as zone_count
FROM zones
WHERE building_id = '7e7c1500-d9b2-4b43-b7cf-650648816b21'
GROUP BY zone_id, floor
ORDER BY floor, zone_id;
```

### Verify Desks in Supabase
```sql
SELECT floor, zone_id, COUNT(*) as desk_count
FROM desks
WHERE building_id = '7e7c1500-d9b2-4b43-b7cf-650648816b21'
GROUP BY floor, zone_id
ORDER BY floor, zone_id;
```

### Check Zone Centroids
```sql
SELECT zone_id, floor, centroid_x, centroid_z, desk_count
FROM zone_centroids
WHERE building_id = '7e7c1500-d9b2-4b43-b7cf-650648816b21'
ORDER BY floor, zone_id;
```

---

## Summary

**What Was Done:**
- ✅ Corrected 300 desks from legacy floor names to current names
- ✅ Generated x/z coordinates for centroid calculation
- ✅ Created 16 zone records with proper structure
- ✅ Synced all data to Supabase
- ✅ Verified API endpoints and zone centroid calculations

**Result:**
Equipment positioning in the digital twin now has proper zone context with calculated centroids. Equipment will appear positioned relative to their zones once the health_score field issue is fixed.

**Next Action:**
Fix health_score field name in `backend/app/api/buildings.py` to see equipment health displayed correctly.

---

Generated: 2026-02-10  
Scripts Location: `backend/scripts/`  
Documentation: This file  
