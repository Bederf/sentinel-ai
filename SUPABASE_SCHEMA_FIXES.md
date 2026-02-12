# Supabase Schema Fixes Summary

## ✅ Fixed: Alert Creation Endpoint (alerts.py)

### Issue
The alert creation endpoint was not properly using Supabase as the source of truth for entity relationships.

### Root Cause
- Endpoint was trying to derive building names instead of querying the actual buildings table
- Equipment table has `building_id` foreign key to buildings table - this relationship must be respected
- API responses may not include all fields available in the actual Supabase schema

### Solution Applied

#### Before (Incorrect):
```python
# Tried to use non-existent site_id field
equipment = client.table("equipment").select("id, name, site_id").eq("name", request.equipment_code).execute()

# Derived building name instead of querying table
site_id = eq.get("site_id", "site-001")
building_name = f"Site {site_id.split('-')[-1]}" if site_id else "Unknown"

# Used wrong field in alert creation
alert_data = {
    "site_id": eq.get("site_id"),  # WRONG - alerts table expects building_id
    ...
}
```

#### After (Correct - Supabase Source of Truth):
```python
# Query equipment WITH building_id (the foreign key that exists in schema)
equipment = client.table("equipment").select("id, name, code, building_id").eq(
    "name", request.equipment_code
).execute()

eq = equipment.data[0]
building_id = eq.get("building_id")  # Get from Supabase

# Query buildings table for actual building data
if building_id:
    building = client.table("buildings").select("name").eq("id", building_id).execute()
    if building.data:
        building_name = building.data[0].get("name", "Unknown")

# Use building_id in alert creation (matches alerts table schema)
alert_data = {
    "id": alert_id,
    "building_id": building_id,  # CORRECT - from equipment FK
    "equipment_id": equipment_id,
    ...
}
```

---

## Key Principles Applied

### ✅ Supabase as Source of Truth
- Always query tables from Supabase rather than deriving values
- Don't invent data based on patterns
- Example: Equipment building_name comes from `buildings` table, not string manipulation

### ✅ Respect Foreign Key Relationships
- Equipment table: `building_id UUID NOT NULL REFERENCES buildings(id)`
- Use the relationship: Equipment → (via building_id) → Building
- Query related tables to get authoritative data

### ✅ Query Complete Field Sets
- Include all necessary fields in SELECT statements
- Example: Include `building_id` when querying equipment
- Don't rely on API responses that may transform/omit fields

### ✅ Validate at Boundaries
- When user provides equipment identifier (name/code), validate it exists
- When getting related data, validate it exists before using it
- Handle NULL/missing relationships gracefully

---

## Implementation Checklist

- ✅ Equipment query includes `building_id` foreign key
- ✅ Building lookup queries `buildings` table with the FK
- ✅ Alert creation uses proper `building_id` from Supabase
- ✅ Error handling for missing buildings
- ✅ Syntax validation passed

---

## Schema Reference

### Equipment Table (source: 001_initial_schema.sql)
```sql
CREATE TABLE equipment (
  id UUID PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  building_id UUID NOT NULL REFERENCES buildings(id),  -- Foreign key!
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  -- ... other fields ...
);
```

### Alerts Table
```sql
-- Expects building_id FK relationship
alert_data = {
    "building_id": uuid,      -- From equipment.building_id
    "equipment_id": uuid,     -- From equipment.id
    "severity": string,       -- "critical", "warning", etc.
    "status": string,         -- "active", "acknowledged", "resolved"
    ...
}
```

---

## Testing the Fix

Once backend restarts with the corrected code:

```bash
# Create alert with equipment name
curl -X POST http://localhost:9095/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "equipment_code": "CH-1",
    "severity": "warning",
    "type": "temperature",
    "title": "High Temperature Alert",
    "message": "Exceeded safe threshold",
    "reading": 32.5,
    "setpoint": 25,
    "notify_clawd": false
  }'

# Expected: Alert created with correct building_id from equipment FK
```

---

## Related Fixes

1. **Removed duplicate endpoints** in work_orders.py (lines 1157-1282)
2. **Fixed alerts.py** to use Supabase FK relationships (this fix)
3. **Documented equipment identification** - use `name` field, not non-existent `code` field
4. **Created FIXED_E2E_TEST.md** with corrected endpoint + request formats

---

## Next Steps

1. Restart backend: `./start-backend.sh`
2. Run corrected test from FIXED_E2E_TEST.md
3. Verify alert creation works with proper building_id assignment
4. Monitor logs for any remaining schema mismatches
