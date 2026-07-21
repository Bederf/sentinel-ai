-- Phase 208-10: Archive HALF_BUILT tables to _deprecated schema
-- Migration: 208-10_archive_half_built.sql
-- Date: 2026-05-10
-- Executed: 40 public tables → 43 _deprecated tables (was 80/0 before this migration)
-- Views dropped: dali_zone_alignment_status, escalated_work_orders (depended on archived tables)
--
-- Production bugs found during audit (NOT dropped — archived for investigation):
--   - work_orders: 0 rows, 41 code refs, create() silent fail (non-existent method)
--   - audit_log: 0 rows, 33 code refs, INSERT silently fails
--   - retention service: wrong date column (fixed in be1f1037)
--
-- Tables deferred (stakeholder sign-off needed):
--   - site_handbooks: 1 row, orphaned from Phase 206 wizard

BEGIN;

-- ── Drop dependent views FIRST (must be outside transaction) ─────────────────
DROP VIEW IF EXISTS dali_zone_alignment_status CASCADE;
DROP VIEW IF EXISTS escalated_work_orders CASCADE;

-- ── Archive tables with incoming FK constraints (handle FK chain first) ────────
-- notification_delivery_logs → work_orders (FK)
CREATE TABLE _deprecated.notification_delivery_logs AS SELECT * FROM notification_delivery_logs;
DROP TABLE notification_delivery_logs;

-- work_orders → audit_log (FK) + self-reference; use CASCADE to drop FK
CREATE TABLE _deprecated.work_orders AS SELECT * FROM work_orders;
DROP TABLE work_orders CASCADE;

-- audit_log (now orphaned after CASCADE drop of work_orders)
CREATE TABLE _deprecated.audit_log AS SELECT * FROM audit_log;
DROP TABLE audit_log;

-- ── Archive DALI lighting tables ────────────────────────────────────────────────
-- Note: lighting_luminaires was already dropped by prior test run
CREATE TABLE _deprecated.lighting_sensors AS SELECT * FROM lighting_sensors;
DROP TABLE lighting_sensors;

CREATE TABLE _deprecated.lighting_zones AS SELECT * FROM lighting_zones;
DROP TABLE lighting_zones;

CREATE TABLE _deprecated.dali_zone_mapping AS SELECT * FROM dali_zone_mapping;
DROP TABLE dali_zone_mapping;

-- ── Archive Tier 2 HALF_BUILT tables ──────────────────────────────────────────
CREATE TABLE _deprecated.document_chunks AS SELECT * FROM document_chunks;
DROP TABLE document_chunks;

CREATE TABLE _deprecated.emission_factors AS SELECT * FROM emission_factors;
DROP TABLE emission_factors;

CREATE TABLE _deprecated.emissions_baseline AS SELECT * FROM emissions_baseline;
DROP TABLE emissions_baseline;

CREATE TABLE _deprecated.emissions_sources AS SELECT * FROM emissions_sources;
DROP TABLE emissions_sources;

CREATE TABLE _deprecated.municipal_demand_history AS SELECT * FROM municipal_demand_history;
DROP TABLE municipal_demand_history;

CREATE TABLE _deprecated.node_room_mappings AS SELECT * FROM node_room_mappings;
DROP TABLE node_room_mappings;

CREATE TABLE _deprecated.severity_mappings AS SELECT * FROM severity_mappings;
DROP TABLE severity_mappings;

CREATE TABLE _deprecated.solar_inverters AS SELECT * FROM solar_inverters;
DROP TABLE solar_inverters;

CREATE TABLE _deprecated.solar_plants AS SELECT * FROM solar_plants;
DROP TABLE solar_plants;

CREATE TABLE _deprecated.solar_sites AS SELECT * FROM solar_sites;
DROP TABLE solar_sites;

CREATE TABLE _deprecated.bess_containers AS SELECT * FROM bess_containers;
DROP TABLE bess_containers;

CREATE TABLE _deprecated.certification_progress AS SELECT * FROM certification_progress;
DROP TABLE certification_progress;

CREATE TABLE _deprecated.health_score_weights AS SELECT * FROM health_score_weights;
DROP TABLE health_score_weights;

CREATE TABLE _deprecated.model_thresholds AS SELECT * FROM model_thresholds;
DROP TABLE model_thresholds;

CREATE TABLE _deprecated.room_registry AS SELECT * FROM room_registry;
DROP TABLE room_registry;

CREATE TABLE _deprecated.user_module_access AS SELECT * FROM user_module_access;
DROP TABLE user_module_access;

CREATE TABLE _deprecated.water_alerts AS SELECT * FROM water_alerts;
DROP TABLE water_alerts;

CREATE TABLE _deprecated.zone_display_mappings AS SELECT * FROM zone_display_mappings;
DROP TABLE zone_display_mappings;

CREATE TABLE _deprecated.block_booking_records AS SELECT * FROM block_booking_records;
DROP TABLE block_booking_records;

CREATE TABLE _deprecated.alarm_taxonomy AS SELECT * FROM alarm_taxonomy;
DROP TABLE alarm_taxonomy;

CREATE TABLE _deprecated.api_uptime_checks AS SELECT * FROM api_uptime_checks;
DROP TABLE api_uptime_checks;

CREATE TABLE _deprecated.api_uptime_daily AS SELECT * FROM api_uptime_daily;
DROP TABLE api_uptime_daily;

CREATE TABLE _deprecated.asset_health_daily_rollups AS SELECT * FROM asset_health_daily_rollups;
DROP TABLE asset_health_daily_rollups;

CREATE TABLE _deprecated.cross_module_links AS SELECT * FROM cross_module_links;
DROP TABLE cross_module_links;

CREATE TABLE _deprecated.fcu_zone_state AS SELECT * FROM fcu_zone_state;
DROP TABLE fcu_zone_state;

CREATE TABLE _deprecated.login_audit AS SELECT * FROM login_audit;
DROP TABLE login_audit;

CREATE TABLE _deprecated.site_technicians AS SELECT * FROM site_technicians;
DROP TABLE site_technicians;

CREATE TABLE _deprecated.equipment_baselines AS SELECT * FROM equipment_baselines;
DROP TABLE equipment_baselines;

-- ── Large historical data (retention was broken — archive intact) ──────────────
CREATE TABLE _deprecated.adapter_health_current AS SELECT * FROM adapter_health_current;
DROP TABLE adapter_health_current;

CREATE TABLE _deprecated.equipment_fault_events AS SELECT * FROM equipment_fault_events;
DROP TABLE equipment_fault_events;

CREATE TABLE _deprecated.ml_feedback_state AS SELECT * FROM ml_feedback_state;
DROP TABLE ml_feedback_state;

-- ── Zero-row tables (drop — nothing to preserve) ──────────────────────────────
DROP TABLE IF EXISTS decision_records;
DROP TABLE IF EXISTS retention_execution_log;
DROP TABLE IF EXISTS sync_jobs;

-- ── Deferred tables (need stakeholder sign-off) ────────────────────────────────
-- site_handbooks: 1 row, orphaned from Phase 206 wizard

COMMIT;

-- ── Post-migration: Recreate view for dali_zone_alignment_status ──────────────
-- The DALI tables are archived but the view was for site-002 DALI alignment.
-- If the DALI lighting module is re-enabled, recreate the view from archived tables.
-- For now, dali_zone_alignment_status is dropped (site-002 doesn't use DALI lighting).

DO $$
BEGIN
  RAISE NOTICE 'Phase 208-10 archive complete.';
  RAISE NOTICE 'Public tables: %', (SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public');
  RAISE NOTICE 'Deprecated tables: %', (SELECT COUNT(*) FROM pg_tables WHERE schemaname = '_deprecated');
  RAISE NOTICE 'Remaining views: %', (SELECT COUNT(*) FROM pg_views WHERE schemaname = 'public');
END;
$$;
