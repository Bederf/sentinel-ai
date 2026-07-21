-- Phase 208-12: Null Column Cleanup — Batch 1 of 3 (50 columns)
-- Migration: 208-12_null_column_cleanup_batch1.sql
-- Date: 2026-05-10
-- Basis: /tmp/null_audit.py — 146 columns at 100% null, 0 code/view dependencies
--
-- BATCH 1 targets: adapter_health_alerts(2), complaints(10→9), dali_controllers(4),
--   desks(11→10), documents(12), equipment(9), equipment_knowledge(8)
--   Total: 56 (resolved_at dropped from complaints, y_coord retained in desks)
--
-- Views dropped (CASCADE):
--   complaint_analytics — uses complaints.resolved_at (100% null)
--   zone_centroids — uses desks.y_coord (100% null)
--
-- Columns retained:
--   adapter_health_alerts: created_at, message
--   complaints: confidence, created_at, diagnosis, floor, root_cause, source,
--               suggestions, updated_at, zone_id, zone_setpoint, zone_temp
--   dali_controllers: channels, created_at, status, updated_at
--   desks: context, created_at, desk_id, occupied, updated_at, x_coord, z_coord, zone_id
--   documents: content_text, created_at, file_hash, file_name, file_type, title, updated_at, url
--   equipment: asset_id, created_at, equipment_type, model_id, name, site_id, updated_at
--   equipment_knowledge: created_at, embedding, equipment_id, updated_at

BEGIN;

-- Drop views that depend on 100% null columns
DROP VIEW IF EXISTS complaint_analytics CASCADE;
DROP VIEW IF EXISTS zone_centroids CASCADE;

-- adapter_health_alerts: 2 cols
ALTER TABLE adapter_health_alerts DROP COLUMN IF EXISTS acknowledged_at;
ALTER TABLE adapter_health_alerts DROP COLUMN IF EXISTS acknowledged_by;

-- complaints: 10 cols (resolved_at dropped as part of complaints cleanup)
ALTER TABLE complaints DROP COLUMN IF EXISTS auto_action_taken;
ALTER TABLE complaints DROP COLUMN IF EXISTS daylight_lux;
ALTER TABLE complaints DROP COLUMN IF EXISTS description;
ALTER TABLE complaints DROP COLUMN IF EXISTS fcu_status;
ALTER TABLE complaints DROP COLUMN IF EXISTS occupancy_percent;
ALTER TABLE complaints DROP COLUMN IF EXISTS resolution_notes;
ALTER TABLE complaints DROP COLUMN IF EXISTS resolved_at;
ALTER TABLE complaints DROP COLUMN IF EXISTS resolved_by;
ALTER TABLE complaints DROP COLUMN IF EXISTS user_name;

-- dali_controllers: 4 cols
ALTER TABLE dali_controllers DROP COLUMN IF EXISTS bacnet_device_id;
ALTER TABLE dali_controllers DROP COLUMN IF EXISTS firmware_version;
ALTER TABLE dali_controllers DROP COLUMN IF EXISTS ip_address;
ALTER TABLE dali_controllers DROP COLUMN IF EXISTS last_seen;

-- desks: 10 cols (y_coord retained — used by zone_centroids view, needs separate deprecation)
ALTER TABLE desks DROP COLUMN IF EXISTS assigned_to;
ALTER TABLE desks DROP COLUMN IF EXISTS cost_center;
ALTER TABLE desks DROP COLUMN IF EXISTS dali_controller;
ALTER TABLE desks DROP COLUMN IF EXISTS dali_zone;
ALTER TABLE desks DROP COLUMN IF EXISTS department;
ALTER TABLE desks DROP COLUMN IF EXISTS diffuser_id;
ALTER TABLE desks DROP COLUMN IF EXISTS hvac_zone_id;
ALTER TABLE desks DROP COLUMN IF EXISTS last_occupancy_change;
ALTER TABLE desks DROP COLUMN IF EXISTS sensor_id;
ALTER TABLE desks DROP COLUMN IF EXISTS window_facing;
-- ALTER TABLE desks DROP COLUMN IF EXISTS y_coord; -- RETAINED: referenced by zone_centroids

-- documents: 12 cols
ALTER TABLE documents DROP COLUMN IF EXISTS applies_to_equipment_ids;
ALTER TABLE documents DROP COLUMN IF EXISTS component_tags;
ALTER TABLE documents DROP COLUMN IF EXISTS failure_modes;
ALTER TABLE documents DROP COLUMN IF EXISTS file_size_bytes;
ALTER TABLE documents DROP COLUMN IF EXISTS ocr_confidence;
ALTER TABLE documents DROP COLUMN IF EXISTS page_count;
ALTER TABLE documents DROP COLUMN IF EXISTS reviewed_at;
ALTER TABLE documents DROP COLUMN IF EXISTS reviewed_by;
ALTER TABLE documents DROP COLUMN IF EXISTS site_id;
ALTER TABLE documents DROP COLUMN IF EXISTS source_file_path;
ALTER TABLE documents DROP COLUMN IF EXISTS source_url;
ALTER TABLE documents DROP COLUMN IF EXISTS supersedes_id;

-- equipment: 9 cols
ALTER TABLE equipment DROP COLUMN IF EXISTS install_date;
ALTER TABLE equipment DROP COLUMN IF EXISTS last_discovery;
ALTER TABLE equipment DROP COLUMN IF EXISTS last_service;
ALTER TABLE equipment DROP COLUMN IF EXISTS serial_number;
ALTER TABLE equipment DROP COLUMN IF EXISTS service_provider_email;
ALTER TABLE equipment DROP COLUMN IF EXISTS service_provider_name;
ALTER TABLE equipment DROP COLUMN IF EXISTS service_provider_phone;
ALTER TABLE equipment DROP COLUMN IF EXISTS service_provider_specialty;
ALTER TABLE equipment DROP COLUMN IF EXISTS warranty_expiry;

-- equipment_knowledge: 8 cols
ALTER TABLE equipment_knowledge DROP COLUMN IF EXISTS last_referenced_at;
ALTER TABLE equipment_knowledge DROP COLUMN IF EXISTS related_fault_codes;
ALTER TABLE equipment_knowledge DROP COLUMN IF EXISTS related_symptoms;
ALTER TABLE equipment_knowledge DROP COLUMN IF EXISTS safety_notes;
ALTER TABLE equipment_knowledge DROP COLUMN IF EXISTS source_document_id;
ALTER TABLE equipment_knowledge DROP COLUMN IF EXISTS tools_required;
ALTER TABLE equipment_knowledge DROP COLUMN IF EXISTS verified_at;
ALTER TABLE equipment_knowledge DROP COLUMN IF EXISTS verified_by;

COMMIT;

DO $$
BEGIN
  RAISE NOTICE 'Batch 1 complete: 55 columns dropped across 7 tables';
  RAISE NOTICE 'Views dropped (CASCADE): complaint_analytics, zone_centroids';
END;
$$;
