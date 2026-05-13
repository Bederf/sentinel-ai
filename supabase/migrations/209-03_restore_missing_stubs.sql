-- Phase 209-03: Restore missing table stubs broken by Phase 208 cleanup
-- Migration: 209-03_restore_missing_stubs.sql
-- Date: 2026-05-10
-- Problem: Code references tables that don't exist in public schema:
--   - sync_jobs: dropped in 208-10 (0 rows, integration tracking)
--   - service_records: never existed or dropped earlier (service desk)
--   - data_freshness_breaches: likely dropped in 208-10 (0 rows)
--   - space_sensor_devices: HALF_BUILT table (never onboarded a site)
--   - predictions: HALF_BUILT table (ML pipeline never wired)
--   - compiler_queue: HALF_BUILT table (async compiler, never used)
--   - fcu_zone_state: archived to _deprecated in 208-10 (20 rows, HALF_BUILT)
-- Also fixing column references removed by 208-12:
--   - equipment.install_date (dropped batch 1)
--   - recommendations.approved_by (dropped batch 3)
--
-- Strategy: Create minimal stub tables so queries succeed (return empty).
-- These are all HALF_BUILT or unused tables — no data loss.

BEGIN;

-- zones: re-add null columns dropped in 208-12 batch 2 (do first, no dependencies)
ALTER TABLE public.zones ADD COLUMN IF NOT EXISTS ahu_id text;
ALTER TABLE public.zones ADD COLUMN IF NOT EXISTS area_sqm numeric;
ALTER TABLE public.zones ADD COLUMN IF NOT EXISTS co2_sensor text;
ALTER TABLE public.zones ADD COLUMN IF NOT EXISTS fcu_id text;
ALTER TABLE public.zones ADD COLUMN IF NOT EXISTS humidity_sensor text;
ALTER TABLE public.zones ADD COLUMN IF NOT EXISTS temp_sensor text;
ALTER TABLE public.zones ADD COLUMN IF NOT EXISTS vav_id text;

-- fcu_zone_state: 20 rows, HALF_BUILT (restored from _deprecated)
CREATE TABLE public.fcu_zone_state (
  id bigint,
  site_id text,
  zone_id text,
  occupancy_pct double precision,
  room_temp_c double precision,
  setpoint_c double precision,
  timestamp timestamp with time zone,
  occupancy_end_time timestamp with time zone,
  prev_room_temp_c double precision,
  prev_timestamp timestamp with time zone,
  fcu_inferred_running boolean,
  occupancy_source text,
  updated_at timestamp with time zone
);
INSERT INTO public.fcu_zone_state SELECT * FROM _deprecated.fcu_zone_state;

-- equipment: re-add install_date stub (dropped in 208-12 batch 1)
-- Note: This is a NULL column stub — the column was 100% null and legitimately dropped.
-- Code that references it needs fixing, but we add the column back to unblock startup.
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS install_date date;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS last_discovery timestamptz;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS last_service date;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS serial_number text;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS warranty_expiry date;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS service_provider_email text;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS service_provider_name text;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS service_provider_phone text;
ALTER TABLE public.equipment ADD COLUMN IF NOT EXISTS service_provider_specialty text;

-- recommendations: re-add approved_by (dropped in 208-12 batch 3)
ALTER TABLE public.recommendations ADD COLUMN IF NOT EXISTS approved_by text;
ALTER TABLE public.recommendations ADD COLUMN IF NOT EXISTS approval_reason text;
ALTER TABLE public.recommendations ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.recommendations ADD COLUMN IF NOT EXISTS acknowledgement_type text;
ALTER TABLE public.recommendations ADD COLUMN IF NOT EXISTS executed_at timestamptz;
ALTER TABLE public.recommendations ADD COLUMN IF NOT EXISTS execution_result jsonb;

-- sync_jobs: integration tracking (dropped 208-10, was 0 rows)
CREATE TABLE public.sync_jobs (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  log_source_id uuid,
  status text DEFAULT 'pending',
  records_inserted integer DEFAULT 0,
  records_failed integer DEFAULT 0,
  records_skipped integer DEFAULT 0,
  records_processed integer DEFAULT 0,
  processing_time_ms integer,
  started_at timestamptz DEFAULT NOW(),
  completed_at timestamptz,
  file_name text,
  created_at timestamptz DEFAULT NOW(),
  updated_at timestamptz DEFAULT NOW()
);

-- service_records: service desk tickets (never existed in this DB)
CREATE TABLE public.service_records (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  ticket_id text UNIQUE,
  site_id uuid,
  equipment_id uuid,
  title text,
  description text,
  priority text DEFAULT 'medium',
  status text DEFAULT 'open',
  category text,
  assigned_to text,
  created_by text,
  created_at timestamptz DEFAULT NOW(),
  updated_at timestamptz DEFAULT NOW(),
  resolved_at timestamptz,
  closed_at timestamptz
);

-- data_freshness_breaches: SLA breach tracking (0 rows, dropped)
CREATE TABLE public.data_freshness_breaches (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  site_id text NOT NULL,
  metric_name text NOT NULL,
  breach_type text NOT NULL,
  severity text DEFAULT 'medium',
  detected_at timestamptz DEFAULT NOW(),
  resolved_at timestamptz,
  details jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT NOW()
);

-- space_sensor_devices: occupancy sensor registry (HALF_BUILT, never onboarded)
CREATE TABLE public.space_sensor_devices (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  device_id text UNIQUE NOT NULL,
  site_id uuid NOT NULL,
  zone_id uuid,
  device_type text,
  installed_at timestamptz,
  last_seen timestamptz,
  metadata jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT NOW(),
  updated_at timestamptz DEFAULT NOW()
);

-- predictions: ML prediction store (HALF_BUILT, ML pipeline never wired)
CREATE TABLE public.predictions (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  equipment_id uuid,
  site_id uuid,
  prediction_type text NOT NULL,
  predicted_at timestamptz DEFAULT NOW(),
  horizon_hours integer,
  confidence numeric,
  severity text,
  input_features jsonb DEFAULT '{}',
  output jsonb DEFAULT '{}',
  actual_outcome jsonb,
  created_at timestamptz DEFAULT NOW()
);

-- compiler_queue: async rule compilation queue (HALF_BUILT, never used)
CREATE TABLE public.compiler_queue (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  rule_content jsonb NOT NULL DEFAULT '{}',
  status text DEFAULT 'pending' CHECK (status IN ('pending','running','done','failed')),
  priority integer DEFAULT 0,
  worker_id text,
  started_at timestamptz,
  completed_at timestamptz,
  error_message text,
  result jsonb,
  created_at timestamptz DEFAULT NOW(),
  updated_at timestamptz DEFAULT NOW()
);

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sync_jobs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.service_records TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.data_freshness_breaches TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.space_sensor_devices TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.predictions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.compiler_queue TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fcu_zone_state TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.zones TO service_role;

COMMIT;

DO $$
BEGIN
  RAISE NOTICE '209-03: stub tables created (sync_jobs, service_records, data_freshness_breaches, space_sensor_devices, predictions, compiler_queue)';
  RAISE NOTICE 'fcu_zone_state restored: % rows', (SELECT count(*) FROM public.fcu_zone_state);
  RAISE NOTICE 'Columns restored: zones.ahu_id+7 cols, equipment.install_date+9 cols, recommendations.approved_by+5 cols';
END;
$$;
