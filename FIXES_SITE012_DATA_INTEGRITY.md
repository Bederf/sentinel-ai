# Site-012 Data Integrity Fixes

## Problem
Dashboard showed incorrect equipment count for site-012:
- **Frontend display:** 25 equipment, 17/25 Safe, 0 Risks ❌
- **Supabase reality:** 19 equipment, 17 normal + 2 maintenance ✓
- **Root cause:** Backend falling back to JSON/asset_summary instead of using Supabase-only data

User requirement: **"we need to get all the info from the supabse not json files the json is only a backup"**

## Fixes Applied

### 1. Frontend Risk Counter (SiteCard.tsx)
**File:** `frontend/src/components/SiteCard.tsx` (line 477)

Changed risk calculation to include blocked equipment:
```typescript
// Before: Only warnings + alarms
{safetySummary.warning + safetySummary.alarm}

// After: Warnings + alarms + blocked (offline/maintenance)
{safetySummary.warning + safetySummary.alarm + safetySummary.blocked}
```

**Impact:** Risk count now correctly shows equipment that are offline or in maintenance, not just those with active warnings/alarms.

---

### 2. Sites List Endpoint (sites.py - list_sites)
**File:** `backend/app/api/sites.py` (lines 371-390)

**Before:**
- Used asset_summary view (which doesn't exist)
- Fell back to buildings.equipment_count column
- Could include JSON fallback data

**After:**
- Always queries actual equipment count from Supabase equipment table
- Never uses asset_summary or JSON fallback
```python
# Query actual equipment count from Supabase
eq_result = client.table('equipment').select('id', count='exact').eq(
    'building_id', building_uuid
).execute()
eq_count = eq_result.count or 0
```

**Impact:** `/api/sites` endpoint now returns correct equipment counts (19 for site-012, not 25)

---

### 3. Single Site Endpoint (sites.py - get_site_from_supabase)
**File:** `backend/app/api/sites.py` (get_site_from_supabase function)

Applied same fix as #2 to single site endpoint.

**Impact:** `/api/sites/{site_id}` now returns correct equipment count.

---

### 4. Response Builder (sites.py - db_to_site_dict)
**File:** `backend/app/api/sites.py` (lines 219-251)

**Removed:**
- asset_summary fallback logic
- Conditional equipment_count selection

**Result:**
```python
# Always use actual Supabase equipment count
total_assets = equipment_count or 0
```

**Impact:** Prevents JSON asset breakdown from inflating equipment count.

---

### 5. Site Summary Endpoint (sites_aggregation.py)
**File:** `backend/app/api/sites_aggregation.py` (lines 125-149)

**Changed:**
- Disabled device_manager fallback
- Added error log if equipment missing from Supabase
- Clear enforcement: Supabase-only data source

```python
# ⚠️  IMPORTANT: Do NOT fall back to device_manager or JSON data
# If equipment is missing, it should be added to Supabase via seeding
if not equipment_list:
    logger.error(f"Site {site_id}: No equipment found in Supabase!")
    equipment_list = []
```

**Impact:** `/api/sites/{site_id}/summary` uses only Supabase data, no fallbacks.

---

### 6. Added Diagnostics
**Files Created:**
- `backend/scripts/diagnose_site012_equipment.py` - Verify Supabase data integrity
- `backend/scripts/check_buildings_table.py` - Compare buildings.equipment_count vs actual

**Usage:**
```bash
python3 backend/scripts/diagnose_site012_equipment.py
python3 backend/scripts/check_buildings_table.py
```

---

## Expected Results After Deployment

### Site-012 Dashboard Display
| Metric | Before | After |
|--------|--------|-------|
| **Total Equipment** | 25 ❌ | 19 ✓ |
| **Safe** | 17/25 | 17/19 |
| **Risks** | 0 ❌ | 2 ✓ |

### Equipment Breakdown
- **Status: NORMAL** (17 items) - All with health ≥ 85%
  - Safe count: 17 ✓
- **Status: MAINTENANCE** (2 items) - Blocked/offline
  - Risk count: 2 (included with fix #1)

### Data Source Guarantee
✅ All equipment data comes ONLY from Supabase  
✅ JSON files serve as backup only (never used unless Supabase down)  
✅ Asset counts match Supabase exactly  

---

## Deployment Checklist

- [ ] Deploy backend API fixes (sites.py, sites_aggregation.py)
- [ ] Deploy frontend fix (SiteCard.tsx)
- [ ] Verify `/api/sites` returns equipment_count=19 for site-012
- [ ] Verify dashboard shows 19 equipment + 2 risks for site-012
- [ ] Run diagnostic scripts to confirm data integrity
- [ ] Monitor logs for any "No equipment found in Supabase" errors

---

## Code Locations Summary

| Change | File | Function/Component |
|--------|------|-------------------|
| Risk counter | `frontend/src/components/SiteCard.tsx` | Risk display (line 477) |
| Sites list | `backend/app/api/sites.py` | `get_sites_from_supabase()` |
| Single site | `backend/app/api/sites.py` | `get_site_from_supabase()` |
| Response builder | `backend/app/api/sites.py` | `db_to_site_dict()` |
| Site summary | `backend/app/api/sites_aggregation.py` | `get_site_summary()` |

All changes enforce: **SUPABASE ONLY** ✓
