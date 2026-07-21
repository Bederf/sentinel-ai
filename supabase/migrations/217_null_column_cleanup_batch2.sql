-- Phase 208-12: Null Column Cleanup — Batch 2 of 3
-- Migration: 208-12_null_column_cleanup_batch2.sql
-- Date: 2026-05-10
-- Basis: /tmp/null_audit.py — 92 columns at 100% null remaining after batch 1
--
-- BATCH 2: desks(1), hvac_zones(10), log_sources(10), ml_models(3),
--   point_asset_mappings(2), space_focus_room_sessions(1),
--   space_occupancy_events(2), visits(6), zones(7) = 42 columns
--
-- Views referencing sites 100%-null cols: sites (view — dropped via CASCADE, not batched)
-- No other view dependencies for batch 2 tables.
--
-- Columns retained:
--   hvac_zones: air_volume, backup_mode, climate_zone, cooling_enabled, created_at, heating_enabled,
--               name, occupied_hours, outdoor_air_damper, updated_at, zone_type
--   log_sources: created_at, name, site_id, status, sync_frequency_minutes, type, updated_at
--   ml_models: created_at, model_type, name, site_id, status, updated_at, version
--   point_asset_mappings: asset_id, created_at, updated_at, zone_id
--   space_focus_room_sessions: capacity, created_at, duration_minutes, focus_type, session_id, site_id, start_time, updated_at, zone_id
--   space_occupancy_events: created_at, site_id, updated_at, zone_id
--   visits: created_at, host_email, host_name, host_phone, in_at, out_at, site_id, updated_at, visitor_company, visitor_count
--   zones: created_at, floor, name, site_id, updated_at, zone_type
--   desks: [none dropped in batch 1 — all remaining desk cols are populated or view-referenced]

BEGIN;

-- desks: 1 col (y_coord — zone_centroids view dropped in batch 1, now safe)
ALTER TABLE desks DROP COLUMN IF EXISTS y_coord;

-- hvac_zones: 10 cols
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS ahu_id;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS co2_sensor;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS cooling_setpoint;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS current_co2;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS current_humidity;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS fcu_id;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS heating_setpoint;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS humidity_sensor;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS temp_sensor;
ALTER TABLE hvac_zones DROP COLUMN IF EXISTS vav_id;

-- log_sources: 10 cols
ALTER TABLE log_sources DROP COLUMN IF EXISTS api_endpoint;
ALTER TABLE log_sources DROP COLUMN IF EXISTS api_key_encrypted;
ALTER TABLE log_sources DROP COLUMN IF EXISTS connection_string;
ALTER TABLE log_sources DROP COLUMN IF EXISTS db_query;
ALTER TABLE log_sources DROP COLUMN IF EXISTS db_table;
ALTER TABLE log_sources DROP COLUMN IF EXISTS file_format;
ALTER TABLE log_sources DROP COLUMN IF EXISTS file_pattern;
ALTER TABLE log_sources DROP COLUMN IF EXISTS folder_path;
ALTER TABLE log_sources DROP COLUMN IF EXISTS last_sync_error;
ALTER TABLE log_sources DROP COLUMN IF EXISTS vendor_pattern;

-- ml_models: 3 cols
ALTER TABLE ml_models DROP COLUMN IF EXISTS notes;
ALTER TABLE ml_models DROP COLUMN IF EXISTS scaler_path;
ALTER TABLE ml_models DROP COLUMN IF EXISTS validation_samples;

-- point_asset_mappings: 2 cols
ALTER TABLE point_asset_mappings DROP COLUMN IF EXISTS cafm_asset_id;
ALTER TABLE point_asset_mappings DROP COLUMN IF EXISTS cafm_asset_uuid;

-- space_focus_room_sessions: 1 col
ALTER TABLE space_focus_room_sessions DROP COLUMN IF EXISTS door_closed;

-- space_occupancy_events: 2 cols
ALTER TABLE space_occupancy_events DROP COLUMN IF EXISTS moving_gate;
ALTER TABLE space_occupancy_events DROP COLUMN IF EXISTS static_gate;

-- visits: 6 cols
ALTER TABLE visits DROP COLUMN IF EXISTS access_card_id;
ALTER TABLE visits DROP COLUMN IF EXISTS host_mobile;
ALTER TABLE visits DROP COLUMN IF EXISTS visitor_id_number;
ALTER TABLE visits DROP COLUMN IF EXISTS visitor_name;
ALTER TABLE visits DROP COLUMN IF EXISTS visitor_photo;
ALTER TABLE visits DROP COLUMN IF EXISTS visitor_vehicle;

-- zones: 7 cols
ALTER TABLE zones DROP COLUMN IF EXISTS ahu_id;
ALTER TABLE zones DROP COLUMN IF EXISTS area_sqm;
ALTER TABLE zones DROP COLUMN IF EXISTS co2_sensor;
ALTER TABLE zones DROP COLUMN IF EXISTS fcu_id;
ALTER TABLE zones DROP COLUMN IF EXISTS humidity_sensor;
ALTER TABLE zones DROP COLUMN IF EXISTS temp_sensor;
ALTER TABLE zones DROP COLUMN IF EXISTS vav_id;

COMMIT;

DO $$
BEGIN
  RAISE NOTICE 'Batch 2 complete: 42 columns dropped across 9 tables';
END;
$$;
