-- Phase 209-05: Restore additional HALF_BUILT table columns
-- Migration: 209-05_restore_additional_columns.sql
-- Date: 2026-05-10
-- Problem: Backend startup revealed more columns missing after Phase 208-12 cleanup
-- discovered via iterative backend restart cycles

BEGIN;

-- predictions: missing columns (code references them)
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS probability_percent numeric;
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS contributing_factors jsonb DEFAULT '[]';
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS predicted_failure_date timestamptz;
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS evidence jsonb DEFAULT '{}';
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS recommended_action text;
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS status text DEFAULT 'active';
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS created_by text;

-- sites: missing columns
ALTER TABLE public.sites ADD COLUMN IF NOT EXISTS occupancy_pattern text;
ALTER TABLE public.sites ADD COLUMN IF NOT EXISTS contact_email text;
ALTER TABLE public.sites ADD COLUMN IF NOT EXISTS control_note text;

-- data_freshness_breaches: missing columns
ALTER TABLE public.data_freshness_breaches ADD COLUMN IF NOT EXISTS breach_time timestamptz;
ALTER TABLE public.data_freshness_breaches ADD COLUMN IF NOT EXISTS data_source text;

-- ml_models: missing columns
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS scaler_path text;
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS scaler_type text;
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS feature_columns text[];
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS target_column text;
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS validation_samples integer;
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS notes text;

-- fcu_zone_state: add unique constraint for upsert operations
ALTER TABLE public.fcu_zone_state ADD CONSTRAINT fcu_zone_state_site_zone_unique UNIQUE (site_id, zone_id);

-- asset_health_daily_rollups: missing PK (needed for upsert ON CONFLICT)
ALTER TABLE public.asset_health_daily_rollups ADD CONSTRAINT asset_health_daily_rollups_pkey PRIMARY KEY (equipment_id, date);

COMMIT;

DO $$
BEGIN
  RAISE NOTICE '209-05: additional columns restored';
  RAISE NOTICE 'predictions: probability_percent, contributing_factors, predicted_failure_date, evidence, recommended_action, status, created_by';
  RAISE NOTICE 'sites: occupancy_pattern, contact_email, control_note';
  RAISE NOTICE 'data_freshness_breaches: breach_time, data_source';
  RAISE NOTICE 'ml_models: scaler_path, scaler_type, feature_columns, target_column, validation_samples, notes';
END;
$$;
