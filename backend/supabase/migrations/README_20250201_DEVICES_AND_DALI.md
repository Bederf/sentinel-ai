# Migration 20250201: BMS Devices and DALI Lighting Integration

## Overview

This migration adds comprehensive support for BMS device control and refactors the DALI lighting system to integrate with the building hierarchy.

## Schema Changes

### 1. New Tables

#### devices
Protocol-agnostic BMS control layer linking buildings, equipment, and zones.

**Key Features:**
- Links to `buildings` (required), `equipment` (optional), `hvac_zones` (optional)
- Composite unique: `(building_id, device_id)`
- JSONB fields for flexible device location, equipment specs, and control points
- Supports multiple protocols: BACnet, Modbus, DALI, Mock, HTTP, MQTT
- Device types: HVAC, Lighting, Security, Fire Safety, Access Control, Power

**Columns:**
```sql
id UUID                         -- Primary key
building_id UUID                -- FK to buildings (required)
equipment_id UUID               -- FK to equipment (optional)
zone_id UUID                    -- FK to hvac_zones (optional)
device_id TEXT                  -- Device identifier (unique per building)
name TEXT                       -- Device name
device_type TEXT                -- hvac, lighting, security, etc.
protocol TEXT                   -- bacnet, modbus, dali, mock, etc.
status TEXT                     -- online, offline, fault, maintenance, standby
device_location JSONB           -- Structured location data
equipment_specs JSONB           -- Manufacturer, model, capacity, etc.
points JSONB                    -- Control/monitoring points
description TEXT
metadata JSONB
last_seen TIMESTAMPTZ
created_at, updated_at TIMESTAMPTZ
```

**Indexes:**
- Building, equipment, zone, type, protocol, status, device_id
- GIN indexes on JSONB fields (location, points, metadata)
- Partial indexes for online/fault devices

#### dali_groups
Lighting groups and scenes for coordinated control.

**Key Features:**
- Links to `buildings` (required), `dali_controllers` (optional)
- Composite unique: `(building_id, group_id)`
- JSONB arrays for luminaire membership
- JSONB scenes for predefined lighting configurations

**Columns:**
```sql
id UUID                         -- Primary key
building_id UUID                -- FK to buildings
controller_id UUID              -- FK to dali_controllers
group_id TEXT                   -- Group identifier (unique per building)
group_address INTEGER           -- DALI group address (0-15)
name TEXT
description TEXT
luminaire_ids JSONB             -- Array of luminaire UUIDs
scene_levels JSONB              -- Scene configurations
created_at, updated_at TIMESTAMPTZ
```

**Indexes:**
- Building, controller, group_id
- GIN index on luminaire_ids

### 2. Refactored Tables

All DALI tables now use `building_id UUID` instead of `site_id TEXT`:

#### dali_controllers
- Added `building_id UUID` FK to buildings
- Added composite unique: `(building_id, controller_id)`
- Backfilled from existing `site_id`

#### dali_luminaires
- Added `building_id UUID` FK to buildings
- Added `hvac_zone_id UUID` FK to hvac_zones
- Added composite unique: `(building_id, luminaire_id)`
- Backfilled from controller and zone_id

#### dali_sensors
- Added `building_id UUID` FK to buildings
- Added `hvac_zone_id UUID` FK to hvac_zones
- Added composite unique: `(building_id, sensor_id)`
- Backfilled from controller and zone_id

#### dali_zones
- Added `building_id UUID` FK to buildings
- Added composite unique: `(building_id, zone_id)`
- Backfilled from existing `site_id`

### 3. Views

#### v_devices_with_equipment
Enriched device view with building, equipment, and zone details.

**Returns:**
- All device columns
- Building: code, name, region
- Equipment: code, name, type, status, health_score
- HVAC Zone: zone_id, zone_name, floor

**Usage:**
```sql
SELECT * FROM v_devices_with_equipment WHERE building_code = 'sandton';
```

#### v_luminaires_with_zones
Enriched luminaire view with building, controller, and zone context.

**Returns:**
- All luminaire columns
- Building details
- Controller details and status
- HVAC zone details (if linked)
- DALI zone details (name, floor, area, desk count)

**Usage:**
```sql
SELECT * FROM v_luminaires_with_zones
WHERE building_code = 'sandton' AND fault_status = TRUE;
```

#### v_building_device_summary
Per-building device counts and health metrics.

**Returns:**
- Total devices, by status (online, offline, fault)
- Counts by device type (hvac, lighting, security, power)
- DALI equipment counts (controllers, luminaires, sensors)
- DALI fault count

**Usage:**
```sql
SELECT * FROM v_building_device_summary WHERE building_code = 'sandton';
```

### 4. Helper Functions

#### update_device_last_seen(p_device_id TEXT, p_building_id UUID)
Fast heartbeat update for device last_seen timestamp.

**Usage:**
```sql
SELECT update_device_last_seen('S001-CHILLER-B1-001', 'building-uuid');
```

#### get_device_by_id(p_building_id UUID, p_device_id TEXT)
Retrieve device by composite key.

**Usage:**
```sql
SELECT * FROM get_device_by_id('building-uuid', 'S001-CHILLER-B1-001');
```

## Row Level Security (RLS)

### Enabled Tables
- devices
- dali_controllers
- dali_luminaires
- dali_sensors
- dali_zones
- dali_groups

### Policy Pattern
All tables use building-level isolation:

```sql
-- SELECT: Users can only see data for buildings they have access to
CREATE POLICY table_select_policy ON table_name
  FOR SELECT
  USING (
    building_id IN (
      SELECT id FROM buildings WHERE auth.uid() IS NOT NULL
    )
  );

-- INSERT/UPDATE/DELETE: Similar building-level checks
```

**Note:** Current policies allow all authenticated users. Refine in production based on:
- User roles (admin, operator, viewer)
- Building assignments per user
- Tenant isolation for multi-tenant deployments

## Performance Optimizations

### Indexes Created
- **15 standard B-tree indexes** on FK columns, device IDs, status fields
- **3 GIN indexes** for JSONB field searches (device_location, points, metadata, luminaire_ids)
- **4 partial indexes** for common filtered queries (online devices, fault devices, fault luminaires, active luminaires)

### Query Performance Targets
- Device lookup by composite key: < 5ms
- Building device summary: < 50ms
- Luminaire with zone info: < 100ms
- Device heartbeat update: < 2ms (using stored function)

## Migration Execution

### Prerequisites
1. Existing migrations 001, 011, 013 must be applied
2. Ensure `buildings`, `equipment`, `hvac_zones` tables exist
3. Backup database before migration

### Apply Migration
```bash
# Using Supabase CLI
supabase db push

# Or via psql
psql -h your-db-host -U postgres -d postgres -f 20250201_devices_and_dali.sql
```

### Rollback
```bash
psql -h your-db-host -U postgres -d postgres -f 20250201_devices_and_dali_rollback.sql
```

**Warning:** Rollback will:
- Drop `devices` and `dali_groups` tables (data loss)
- Remove `building_id` FK from DALI tables (reverts to `site_id` only)

## Repository Usage

### Python Repositories

```python
from app.database.repositories import (
    DeviceRepository,
    DALIControllerRepository,
    DALILuminaireRepository,
    DALISensorRepository,
    DALIGroupRepository,
)

# Device CRUD
device_repo = DeviceRepository()
devices = device_repo.get_by_building_code('sandton')
device = device_repo.get_by_id(building_uuid, 'S001-CHILLER-B1-001')
device_repo.update_status(building_uuid, 'S001-CHILLER-B1-001', 'fault')
device_repo.update_last_seen(building_uuid, 'S001-CHILLER-B1-001')

# DALI Controllers
controller_repo = DALIControllerRepository()
controllers = controller_repo.get_all(building_id=building_uuid)

# DALI Luminaires
luminaire_repo = DALILuminaireRepository()
luminaires = luminaire_repo.get_with_zone_info(building_id=building_uuid)
fault_lights = luminaire_repo.get_fault_luminaires(building_id=building_uuid)
luminaire_repo.update_level(building_uuid, 'LUM-L12-025', 80)

# DALI Groups
group_repo = DALIGroupRepository()
group_repo.add_luminaire(building_uuid, 'GRP-L12-N-001', luminaire_uuid)
group_repo.update_scene(building_uuid, 'GRP-L12-N-001', 'working', {
    'level': 80,
    'color_temp': 4000
})
```

## Data Model Examples

### Device Entry
```json
{
  "building_id": "uuid-for-sandton",
  "device_id": "S001-CHILLER-B1-001",
  "name": "Chiller Plant 001",
  "device_type": "hvac",
  "protocol": "bacnet",
  "status": "online",
  "equipment_id": "uuid-for-chiller-equipment",
  "zone_id": "uuid-for-plant-room-zone",
  "device_location": {
    "building": "Sandton City Branch",
    "floor": "B1",
    "zone": "Plant Room",
    "room": "MR1",
    "description": "Main Mechanical Room",
    "zone_id": "Zone-B1-Plant",
    "zone_type": "plant_room",
    "exposure": "interior",
    "zone_priority": 5
  },
  "equipment_specs": {
    "manufacturer": "Trane",
    "model": "RTAC-225",
    "serial_number": "SN123456",
    "installation_year": 2018,
    "capacity_kw": 790.0
  },
  "points": {
    "chw_supply_temp": {
      "name": "chw_supply_temp",
      "point_type": "analog_input",
      "description": "Chilled water supply temperature",
      "unit": "°C",
      "min_value": 0,
      "max_value": 30,
      "writable": false
    },
    "enable": {
      "name": "enable",
      "point_type": "binary_output",
      "description": "Chiller enable/disable",
      "writable": true,
      "priority": 8
    }
  }
}
```

### DALI Group Entry
```json
{
  "building_id": "uuid-for-sandton",
  "group_id": "GRP-L12-N-001",
  "group_address": 1,
  "name": "Level 12 North",
  "controller_id": "uuid-for-dali-controller",
  "luminaire_ids": [
    "uuid-lum-1",
    "uuid-lum-2",
    "uuid-lum-3"
  ],
  "scene_levels": {
    "full_bright": {"level": 100, "color_temp": 4000},
    "working": {"level": 80, "color_temp": 4000},
    "presentation": {"level": 50, "color_temp": 3000},
    "cleaning": {"level": 100, "color_temp": 5000},
    "after_hours": {"level": 30, "color_temp": 3000}
  }
}
```

## Testing Checklist

### Pre-Migration
- [ ] Backup database
- [ ] Verify existing DALI tables have data
- [ ] Note existing `site_id` to `buildings.code` mappings

### Post-Migration
- [ ] Verify `devices` table created
- [ ] Verify `dali_groups` table created
- [ ] Check all DALI tables have `building_id` populated
- [ ] Verify composite unique constraints exist
- [ ] Test RLS policies (SELECT, INSERT, UPDATE, DELETE)
- [ ] Verify views return data
- [ ] Test helper functions
- [ ] Check indexes created (use `\d+ devices` in psql)

### Performance Tests
- [ ] Device lookup by composite key < 5ms
- [ ] Building device summary < 50ms
- [ ] Luminaire with zone info < 100ms
- [ ] Device heartbeat update < 2ms

### Repository Tests
- [ ] DeviceRepository CRUD operations
- [ ] DALI repository CRUD operations
- [ ] View queries via repositories
- [ ] Batch upsert operations

## Migration Metrics

### Database Objects Created
- **2 tables**: devices, dali_groups
- **4 table refactors**: dali_controllers, dali_luminaires, dali_sensors, dali_zones
- **15 indexes**: Standard B-tree indexes
- **3 GIN indexes**: JSONB search indexes
- **4 partial indexes**: Filtered query optimization
- **3 views**: Enriched query views
- **24 RLS policies**: 4 policies × 6 tables
- **2 functions**: Helper functions

### Estimated Migration Time
- Small dataset (< 1000 rows): ~5 seconds
- Medium dataset (< 10,000 rows): ~30 seconds
- Large dataset (> 100,000 rows): ~2-5 minutes

### Storage Impact
- Devices table: ~2KB per device × device count
- DALI groups: ~1KB per group × group count
- DALI table refactor: Minimal (UUID vs TEXT is same size)

## Future Enhancements

### Performance
- [ ] Add TimescaleDB hypertables for device_history time-series
- [ ] Implement materialized views for heavy aggregations
- [ ] Add database-level caching for frequently accessed devices

### Security
- [ ] Refine RLS policies for role-based access (admin/operator/viewer)
- [ ] Add tenant isolation for multi-tenant deployments
- [ ] Implement audit triggers for device control actions

### Features
- [ ] Add device_health table for historical health scoring
- [ ] Add device_alarms table for fault tracking
- [ ] Add dali_schedules table for time-based lighting control
- [ ] Add device_metrics table for performance monitoring

## References

### Related Files
- Migration: `/opt/bms-intelligence/backend/supabase/migrations/20250201_devices_and_dali.sql`
- Rollback: `/opt/bms-intelligence/backend/supabase/migrations/20250201_devices_and_dali_rollback.sql`
- Repositories: `/opt/bms-intelligence/backend/app/database/repositories/device_repository.py`
- Repositories: `/opt/bms-intelligence/backend/app/database/repositories/dali_repository.py`

### Related Migrations
- `001_initial_schema.sql` - Buildings, equipment base schema
- `011_dali_lighting_schema.sql` - Original DALI tables
- `013_hvac_zones.sql` - HVAC zones schema

### Documentation
- Device Model: `/opt/bms-intelligence/backend/app/models/device.py`
- CLAUDE.md: Building architecture section
- NAMING_CONVENTIONS.md: Device ID patterns

## Support

For questions or issues with this migration:
1. Check PostgreSQL logs for errors
2. Verify all prerequisites are met
3. Review RLS policy configuration
4. Test rollback script in staging first
5. Contact: BMS Platform Team
