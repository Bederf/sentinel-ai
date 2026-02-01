-- =====================================================
-- ROLLBACK: Migration 20250201 - Devices and DALI
--
-- Purpose: Safely rollback all changes from 20250201_devices_and_dali.sql
--
-- Warning: This will drop the devices and dali_groups tables
--          and remove building_id FKs from DALI tables
-- =====================================================

-- =====================================================
-- PART 1: Drop RLS Policies
-- =====================================================

-- Drop dali_groups policies
DROP POLICY IF EXISTS dali_groups_delete_policy ON dali_groups;
DROP POLICY IF EXISTS dali_groups_update_policy ON dali_groups;
DROP POLICY IF EXISTS dali_groups_insert_policy ON dali_groups;
DROP POLICY IF EXISTS dali_groups_select_policy ON dali_groups;

-- Drop dali_zones policies
DROP POLICY IF EXISTS dali_zones_delete_policy ON dali_zones;
DROP POLICY IF EXISTS dali_zones_update_policy ON dali_zones;
DROP POLICY IF EXISTS dali_zones_insert_policy ON dali_zones;
DROP POLICY IF EXISTS dali_zones_select_policy ON dali_zones;

-- Drop dali_sensors policies
DROP POLICY IF EXISTS dali_sensors_delete_policy ON dali_sensors;
DROP POLICY IF EXISTS dali_sensors_update_policy ON dali_sensors;
DROP POLICY IF EXISTS dali_sensors_insert_policy ON dali_sensors;
DROP POLICY IF EXISTS dali_sensors_select_policy ON dali_sensors;

-- Drop dali_luminaires policies
DROP POLICY IF EXISTS dali_luminaires_delete_policy ON dali_luminaires;
DROP POLICY IF EXISTS dali_luminaires_update_policy ON dali_luminaires;
DROP POLICY IF EXISTS dali_luminaires_insert_policy ON dali_luminaires;
DROP POLICY IF EXISTS dali_luminaires_select_policy ON dali_luminaires;

-- Drop dali_controllers policies
DROP POLICY IF EXISTS dali_controllers_delete_policy ON dali_controllers;
DROP POLICY IF EXISTS dali_controllers_update_policy ON dali_controllers;
DROP POLICY IF EXISTS dali_controllers_insert_policy ON dali_controllers;
DROP POLICY IF EXISTS dali_controllers_select_policy ON dali_controllers;

-- Drop devices policies
DROP POLICY IF EXISTS devices_delete_policy ON devices;
DROP POLICY IF EXISTS devices_update_policy ON devices;
DROP POLICY IF EXISTS devices_insert_policy ON devices;
DROP POLICY IF EXISTS devices_select_policy ON devices;

-- =====================================================
-- PART 2: Disable RLS
-- =====================================================

ALTER TABLE IF EXISTS dali_groups DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS dali_zones DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS dali_sensors DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS dali_luminaires DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS dali_controllers DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS devices DISABLE ROW LEVEL SECURITY;

-- =====================================================
-- PART 3: Drop Views
-- =====================================================

DROP VIEW IF EXISTS v_building_device_summary;
DROP VIEW IF EXISTS v_luminaires_with_zones;
DROP VIEW IF EXISTS v_devices_with_equipment;

-- =====================================================
-- PART 4: Drop Helper Functions
-- =====================================================

DROP FUNCTION IF EXISTS get_device_by_id(UUID, TEXT);
DROP FUNCTION IF EXISTS update_device_last_seen(TEXT, UUID);

-- =====================================================
-- PART 5: Drop Partial Indexes
-- =====================================================

DROP INDEX IF EXISTS idx_luminaires_active;
DROP INDEX IF EXISTS idx_luminaires_fault;
DROP INDEX IF EXISTS idx_devices_fault;
DROP INDEX IF EXISTS idx_devices_online;

-- =====================================================
-- PART 6: Drop dali_groups Table
-- =====================================================

DROP TRIGGER IF EXISTS update_dali_groups_updated_at ON dali_groups;
DROP INDEX IF EXISTS idx_dali_groups_luminaires_gin;
DROP INDEX IF EXISTS idx_dali_groups_group_id;
DROP INDEX IF EXISTS idx_dali_groups_controller;
DROP INDEX IF EXISTS idx_dali_groups_building;
DROP TABLE IF EXISTS dali_groups;

-- =====================================================
-- PART 7: Revert DALI Table Changes
-- =====================================================

-- Revert dali_zones
DROP INDEX IF EXISTS idx_dali_zones_building;
ALTER TABLE dali_zones
  DROP CONSTRAINT IF EXISTS unique_dali_zone_per_building,
  DROP COLUMN IF EXISTS building_id;

-- Revert dali_sensors
DROP INDEX IF EXISTS idx_dali_sensors_hvac_zone;
DROP INDEX IF EXISTS idx_dali_sensors_building;
ALTER TABLE dali_sensors
  DROP CONSTRAINT IF EXISTS unique_sensor_per_building,
  DROP COLUMN IF EXISTS hvac_zone_id,
  DROP COLUMN IF EXISTS building_id;

-- Revert dali_luminaires
DROP INDEX IF EXISTS idx_dali_luminaires_hvac_zone;
DROP INDEX IF EXISTS idx_dali_luminaires_building;
ALTER TABLE dali_luminaires
  DROP CONSTRAINT IF EXISTS unique_luminaire_per_building,
  DROP COLUMN IF EXISTS hvac_zone_id,
  DROP COLUMN IF EXISTS building_id;

-- Revert dali_controllers
DROP INDEX IF EXISTS idx_dali_controllers_building;
ALTER TABLE dali_controllers
  DROP CONSTRAINT IF EXISTS unique_controller_per_building,
  DROP COLUMN IF EXISTS building_id;

-- =====================================================
-- PART 8: Drop Devices Table
-- =====================================================

DROP TRIGGER IF EXISTS update_devices_updated_at ON devices;
DROP INDEX IF EXISTS idx_devices_metadata_gin;
DROP INDEX IF EXISTS idx_devices_points_gin;
DROP INDEX IF EXISTS idx_devices_location_gin;
DROP INDEX IF EXISTS idx_devices_device_id;
DROP INDEX IF EXISTS idx_devices_status;
DROP INDEX IF EXISTS idx_devices_protocol;
DROP INDEX IF EXISTS idx_devices_type;
DROP INDEX IF EXISTS idx_devices_zone;
DROP INDEX IF EXISTS idx_devices_equipment;
DROP INDEX IF EXISTS idx_devices_building;
DROP TABLE IF EXISTS devices;

-- =====================================================
-- ROLLBACK COMPLETE
-- =====================================================

-- Note: site_id columns in DALI tables remain intact
-- Original migration 011_dali_lighting_schema.sql structure restored
