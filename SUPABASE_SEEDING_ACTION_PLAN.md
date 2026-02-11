# Supabase Seeding Action Plan

## Objective
Populate Supabase with ALL equipment, zones, and building data from JSON files so that Supabase becomes the PRIMARY data source (JSON files remain as fallback only).

## Current Status

### JSON Fallback Data (✓ Exists)
- **site-002**: 88 equipment items (65 files + 6 generators + 17 energy centre components)
- **site-005**: 90 equipment items
- **site-012**: 29 equipment items
- **Total**: 207+ equipment items across all sites

### Supabase Status (❌ Empty or Sparse)
- Supabase `equipment` table appears to have 0-1 items per building
- Digital Twin shows only 1 device instead of 88

## Root Cause
API endpoint (`/api/buildings/{building_id}/equipment`) queries Supabase first and returns whatever it finds (0-1 items), without falling back to JSON unless there's an exception.

## Solution: Seed Supabase

### Step 1: Ensure Local Supabase is Running

```bash
# Check if Supabase is already running
supabase status

# If not running, start it
supabase start
```

**Expected output:**
```
API URL: http://localhost:55321
DB URL: postgresql://postgres:postgres@localhost:55322/postgres
Studio URL: http://localhost:54323
```

### Step 2: Run Migrations

```bash
# Apply all pending migrations to local Supabase
supabase db push
```

This ensures all table schemas exist (buildings, equipment, hvac_zones, zones, etc.)

### Step 3: Run Seeding Script

```bash
# Seed all equipment from JSON files to Supabase
python backend/scripts/seed_equipment_to_supabase.py
```

**Script does:**
1. ✓ Connects to Supabase
2. ✓ Creates/updates buildings (from `building.json`)
3. ✓ Creates/updates equipment (from `equipment/*.json` files)
4. ✓ Creates/updates HVAC zones (from `zones.json`)
5. ✓ Verifies data was inserted

**Expected output:**
```
================================================================================
SEEDING SUPABASE WITH EQUIPMENT & ZONES DATA FROM JSON FILES
================================================================================
✓ Connected to Supabase

Found 10 sites to seed: site-002, site-005, ...

Processing site-002...
  ✓ Building site-002 already exists (UUID: xxxxxxxx...)
  ✓ Seeded 65 equipment items for site-002
  ✓ Seeded 0 HVAC zones for site-002

Processing site-005...
  ✓ Created building site-005 (UUID: xxxxxxxx...)
  ✓ Seeded 90 equipment items for site-005
  ✓ Seeded 0 HVAC zones for site-005

...

================================================================================
SEEDING COMPLETE
================================================================================
Buildings created/updated: 10
Equipment created/updated: 207
HVAC Zones created/updated: N
Total items seeded: 207+N

VERIFICATION:
Buildings in Supabase: 10
Equipment in Supabase: 207
HVAC Zones in Supabase: N

Equipment per building:
  site-002: 88 equipment
  site-005: 90 equipment
  site-012: 29 equipment
  ...

✓ SUCCESS: Supabase is now the primary data source
```

### Step 4: Verify in Frontend

Restart backend service if needed:

```bash
# Terminal 1
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 9095
```

Test API endpoint:

```bash
# Should show 88 equipment for site-002
curl http://localhost:9095/api/buildings/site-002/equipment | jq '.total_equipment'

# Should show "supabase" as source (not "json")
curl http://localhost:9095/api/buildings/site-002/equipment | jq '.source'
```

Go to Digital Twin in frontend - should now show **88 equipment items** for site-002 instead of 1 ✓

### Step 5: Restart Frontend

```bash
# Terminal 2
cd frontend && npm run dev
```

## Troubleshooting

### Issue: "Cannot connect to Supabase"
```
Error: Could not connect to Supabase: Failed to fetch user data
```

**Solution:**
1. Make sure Supabase is running: `supabase status`
2. Check `.env` has DATABASE_URL set
3. Verify migrations are applied: `supabase db push`

### Issue: "Table does not exist"
```
Error: relation "equipment" does not exist
```

**Solution:**
Run migrations first: `supabase db push`

### Issue: "UUID foreign key constraint failed"
```
Error: insert into equipment violates foreign key constraint
```

**Solution:**
Building must exist first. Script creates buildings before equipment, but if you run script twice rapidly, you might hit this. Just run again:
```bash
python backend/scripts/seed_equipment_to_supabase.py
```

### Issue: Frontend still shows 1 equipment

**Solution:**
1. Check that Supabase seeding completed successfully
2. Clear browser cache: Hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
3. Check `/api/buildings/site-002/equipment?source=debug` response
4. Verify Supabase table: Query in Studio UI or with psql

## Post-Seeding Verification

### Direct SQL Check

```bash
# Connect to Supabase
psql "postgresql://postgres:postgres@localhost:55322/postgres"
```

```sql
-- Count buildings
SELECT COUNT(*) FROM buildings;
-- Expected: 10

-- Count equipment
SELECT COUNT(*) FROM equipment;
-- Expected: ~207

-- Count equipment per building
SELECT b.code, COUNT(e.id) as equipment_count
FROM buildings b
LEFT JOIN equipment e ON b.id = e.building_id
GROUP BY b.code
ORDER BY equipment_count DESC;

-- Expected: site-002: 88, site-005: 90, site-012: 29, ...
```

### API Endpoint Check

```bash
# Get equipment for site-002
curl -s http://localhost:9095/api/buildings/site-002/equipment | jq '
{
  total: .total_equipment,
  source: .source,
  sample_equipment: .equipment[0:3] | map({name, code, type})
}'
```

**Expected:**
```json
{
  "total": 88,
  "source": "supabase",
  "sample_equipment": [
    {"name": "Chiller 1", "code": "S002-CHILLER-B1-001", "type": "chiller"},
    {"name": "FCU Zone L1-A", "code": "S002-FCU-L1-A", "type": "fcu"},
    ...
  ]
}
```

### Frontend Verification

1. Open http://localhost:9096 in browser
2. Navigate to Digital Twin
3. Select site-002 from dropdown
4. **Should see ~88 equipment items** (zones, chillers, FCUs, AHUs, VAVs, DALI, energy centre, etc.)
5. Not just 1! ✓

## Data Flow After Seeding

```
Frontend (React)
    ↓
API Endpoint: /api/buildings/{building_id}/equipment
    ↓
Backend Controller: buildings.py
    ↓
repository.get_by_building_code(site_code)
    ↓
Supabase Equipment Table ← [NOW HAS 88 ITEMS FOR SITE-002] ✓
    ↓
Return 88 equipment items
    ↓
Frontend renders Digital Twin with 88 equipment markers ✓
```

## Rollback (If Needed)

To revert to JSON-only (if seeding causes issues):

```bash
# Delete all seeded data (CAREFUL!)
psql "postgresql://postgres:postgres@localhost:55322/postgres" -c "
DELETE FROM equipment WHERE building_id IN (SELECT id FROM buildings WHERE code LIKE 'site-%');
DELETE FROM hvac_zones WHERE building_id IN (SELECT id FROM buildings WHERE code LIKE 'site-%');
DELETE FROM buildings WHERE code LIKE 'site-%';
"
```

Then API will fall back to JSON files automatically.

## Files Involved

**Seeding Script:**
- `backend/scripts/seed_equipment_to_supabase.py` (executable)

**Source Data:**
- `backend/app/data/buildings/{site-code}/equipment/*.json` (65 files per site)
- `backend/app/data/buildings/{site-code}/zones.json`
- `backend/app/data/buildings/{site-code}/building.json`

**API Endpoint:**
- `backend/app/api/buildings.py` line 630-850 (equipment endpoint)

**Frontend:**
- `frontend/src/components/digital-twin/DigitalTwin.tsx` (uses equipment API)
- `frontend/src/hooks/useSitesList.ts` (fetches sites)

## Timeline

- **Supabase start**: < 1 minute
- **Migrations**: 1-2 minutes
- **Seeding script**: 3-5 minutes (207 items)
- **Verification**: 2-3 minutes
- **Frontend test**: 1 minute

**Total: ~10-15 minutes**

## Success Criteria

✓ Supabase `equipment` table has 207+ items
✓ API returns 88 equipment for site-002 (from Supabase, not JSON)
✓ Digital Twin shows 88 equipment markers for site-002
✓ All zones, equipment types properly populated
✓ No errors in backend logs

---

**Status**: READY TO EXECUTE

Run seeding script when ready!
