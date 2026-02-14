# CLAUDE_DATABASE.md

Database schema, migrations, repositories, and Supabase patterns.

## Schema Overview

### Core Tables

```sql
-- Buildings (site-002, site-005, site-012)
buildings (
  id UUID PRIMARY KEY,
  code TEXT UNIQUE,           -- "site-002", "site-005"
  name VARCHAR,
  address TEXT,
  type VARCHAR,
  ...
)

-- Equipment (300+ across 3 sites)
equipment (
  id UUID PRIMARY KEY,
  code TEXT UNIQUE,           -- "S002-CHILLER-B1-001", "S002-VAV-101"
  building_id UUID FK,
  equipment_type VARCHAR,     -- "CHILLER", "VAV", "DALI"
  health_score INT,           -- 0-100
  status VARCHAR,             -- "healthy", "warning", "critical"
  ...
)

-- Alerts
alerts (
  id UUID PRIMARY KEY,
  equipment_id UUID FK,
  severity INT,               -- 0-100
  status VARCHAR,             -- "active", "resolved"
  created_at TIMESTAMP,
  ...
)

-- Work Orders
work_orders (
  id UUID PRIMARY KEY,
  code TEXT UNIQUE,           -- "WO-SIM-001"
  equipment_id UUID FK,
  status VARCHAR,             -- "pending", "assigned", "in_progress", "completed"
  assigned_technician_id UUID,
  ...
)

-- Service Records (feedback from technicians)
service_records (
  id UUID PRIMARY KEY,
  work_order_id UUID FK,
  status VARCHAR,             -- "notified", "data_collection", "submitted"
  health_impact INT,          -- +2, 0, -3, -5
  created_at TIMESTAMP,
  ...
)

-- ML Models
ml_models (
  id UUID PRIMARY KEY,
  equipment_type VARCHAR,     -- "AHU", "CHILLER", "VAV"
  r_squared_avg FLOAT,        -- 0.0-1.0
  status VARCHAR,             -- "active", "deprecated"
  model_path TEXT,            -- S3 path or file
)

-- Model Thresholds
model_thresholds (
  id UUID PRIMARY KEY,
  equipment_type VARCHAR,
  tier2_confidence FLOAT,     -- Min confidence for Tier 2 recommendations
  tier3_confidence FLOAT,
)

-- Recommendations (AI-generated)
recommendations (
  id UUID PRIMARY KEY,
  equipment_id UUID FK,
  status VARCHAR,             -- "pending", "approved", "executed", "rejected", "rolled_back"
  target_value FLOAT,
  reason TEXT,
  ...
)

-- Approvals (Tier 2 device control)
approvals (
  id UUID PRIMARY KEY,
  recommendation_id UUID FK,
  status VARCHAR,             -- "approved", "rejected", "executed", "rolled_back"
  original_value FLOAT,       -- For rollback
  actual_value FLOAT,         -- COV feedback
  ...
)
```

## Naming Conventions

**Primary Keys:** All tables use UUID `id` (except junction tables)
**Unique Identifiers:** Separate `code` TEXT UNIQUE column
  - Equipment: `code` (e.g., "S002-CHILLER-B1-001")
  - Buildings: `code` (e.g., "site-002")
  - Work Orders: `code` (e.g., "WO-SIM-001")

**Foreign Keys:** Reference `.id`, not `.code`
```sql
-- ❌ WRONG
ALTER TABLE work_orders ADD CONSTRAINT fk_equipment
FOREIGN KEY (equipment_code) REFERENCES equipment(code);

-- ✅ CORRECT
ALTER TABLE work_orders ADD CONSTRAINT fk_equipment
FOREIGN KEY (equipment_id) REFERENCES equipment(id);
```

## Repository Pattern

All data access through repositories (Supabase + JSON fallback):

```python
# backend/app/database/repositories/equipment_repository.py

class EquipmentRepository:
    def __init__(self, supabase=None, json_storage=None):
        self.supabase = supabase
        self.json_storage = json_storage
        self.use_json = supabase is None

    async def get_by_code(self, code: str) -> Equipment:
        try:
            # Try Supabase first
            response = await self.supabase.table("equipment") \
                .select("*") \
                .eq("code", code) \
                .single() \
                .execute()
            return Equipment(**response.data)
        except Exception:
            # Fall back to JSON
            if self.use_json:
                data = self.json_storage.load("equipment")
                item = next((e for e in data if e["code"] == code), None)
                return Equipment(**item) if item else None
            raise

    async def list(self) -> List[Equipment]:
        try:
            response = await self.supabase.table("equipment") \
                .select("*") \
                .execute()
            return [Equipment(**item) for item in response.data]
        except Exception:
            if self.use_json:
                data = self.json_storage.load("equipment")
                return [Equipment(**item) for item in data]
            raise
```

**Usage:**
```python
from app.database.repositories.equipment_repository import EquipmentRepository

repo = EquipmentRepository()

# Works whether Supabase is available or not
equipment = await repo.get_by_code("S002-CHILLER-B1-001")
all_equipment = await repo.list()
```

## Database Migrations

### Create Migration File

```bash
# Naming: {timestamp}_{description}.sql
touch supabase/migrations/1708095400_create_equipment_table.sql
```

### Migration Template

```sql
-- supabase/migrations/1708095400_create_equipment_table.sql

-- Create table
CREATE TABLE equipment (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  equipment_type VARCHAR NOT NULL,
  health_score INT DEFAULT 100 CHECK (health_score >= 0 AND health_score <= 100),
  status VARCHAR DEFAULT 'healthy',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Create indexes
CREATE INDEX idx_equipment_code ON equipment(code);
CREATE INDEX idx_equipment_building ON equipment(building_id);
CREATE INDEX idx_equipment_type ON equipment(equipment_type);
CREATE INDEX idx_equipment_health ON equipment(health_score);

-- Add RLS policy
ALTER TABLE equipment ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Equipment readable by authenticated users"
ON equipment FOR SELECT
TO authenticated
USING (true);

-- Trigger: Update updated_at
CREATE OR REPLACE FUNCTION update_equipment_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER equipment_updated_at_trigger
BEFORE UPDATE ON equipment
FOR EACH ROW
EXECUTE FUNCTION update_equipment_updated_at();
```

### Apply Migration

```bash
# Apply to local Supabase
supabase db push

# Verify schema synced
supabase db pull

# View in Studio
supabase status  # Opens http://localhost:54323
```

## PostgreSQL Patterns

### TEXT Arrays (NOT JSON)

```sql
-- ❌ WRONG - JSON array syntax
INSERT INTO equipment (tags) VALUES ('["hvac", "critical"]'::TEXT[]);

-- ✅ CORRECT - PostgreSQL array syntax
INSERT INTO equipment (tags) VALUES (ARRAY['hvac', 'critical']);

-- Query:
SELECT * FROM equipment WHERE 'hvac' = ANY(tags);
```

### PL/pgSQL Blocks

```sql
-- ❌ WRONG - Escaped dollars
CREATE FUNCTION my_func() RETURNS VOID AS \$\$
BEGIN
  -- Logic here
END;
\$\$ LANGUAGE plpgsql;

-- ✅ CORRECT - Double dollar
CREATE FUNCTION my_func() RETURNS VOID AS $$
BEGIN
  -- Logic here
END;
$$ LANGUAGE plpgsql;
```

### Triggers for Auto-Updates

```sql
-- Create function
CREATE OR REPLACE FUNCTION update_health_on_alert()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE equipment
  SET health_score = CASE
    WHEN NEW.severity > 80 THEN health_score - 30
    WHEN NEW.severity > 50 THEN health_score - 15
    ELSE health_score - 5
  END
  WHERE id = NEW.equipment_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger
CREATE TRIGGER alert_health_trigger
AFTER INSERT ON alerts
FOR EACH ROW
EXECUTE FUNCTION update_health_on_alert();
```

## Before Database Changes

**Always verify schema before modifying unfamiliar tables:**

```sql
-- Check table structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'equipment'
ORDER BY ordinal_position;

-- Check constraints
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'equipment';

-- Check foreign keys
SELECT constraint_name, column_name, referenced_table_name, referenced_column_name
FROM information_schema.referential_constraints
WHERE table_name = 'equipment';
```

## Local Supabase Management

```bash
# Start/stop local Supabase
supabase start
supabase stop

# Reset all data (caution: DELETES everything)
supabase db reset

# View status
supabase status

# Access Studio (database UI)
# Automatically opens at http://localhost:54323
# Or: supabase open studio

# Push migrations to production
supabase db push --linked

# Pull schema from remote
supabase db pull
```

## JSON Fallback Storage

When `USE_JSON_STORAGE=true` or Supabase unavailable:

```
backend/app/data/
├── equipment.json          # Equipment records
├── alerts.json             # Alert history
├── work_orders.json        # Work order records
├── buildings.json          # Building records
└── ...                     # One JSON per table
```

**Fallback is AUTOMATIC via repositories** — developers don't need to change code.

## Performance Optimization

### Indexes (Most Important)

```sql
-- Equipment table indexes
CREATE INDEX idx_equipment_building ON equipment(building_id);
CREATE INDEX idx_equipment_type ON equipment(equipment_type);
CREATE INDEX idx_equipment_health ON equipment(health_score);

-- Alerts table indexes
CREATE INDEX idx_alerts_equipment ON alerts(equipment_id);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_created ON alerts(created_at DESC);

-- Work orders
CREATE INDEX idx_wo_equipment ON work_orders(equipment_id);
CREATE INDEX idx_wo_status ON work_orders(status);
```

### N+1 Query Prevention

```python
# ❌ WRONG - N+1 queries (1 equipment + N comments)
equipment = await repo.get_by_code("S002-VAV-101")
for alert in equipment.alerts:  # Separate query per alert
    print(alert.message)

# ✅ CORRECT - Single query with JOIN
equipment = await repo.get_by_code_with_alerts("S002-VAV-101")
# Returns equipment with alerts already loaded
```

## Health Score Update Flow

```
Trigger: Alert created or health command
    ↓
Check PostgreSQL trigger on alerts table
    ↓
Update equipment.health_score
    ↓
If health_score < 50: Status = 'warning' ⚠️
    ↓
If health_score >= 80: Status = 'healthy' ✅
    ↓
Real-time SSE broadcast to frontend
    ↓
Dashboard updates in real-time
```

---

See `CLAUDE_WORKFLOWS.md` for equipment fault-to-resolution data flow.
