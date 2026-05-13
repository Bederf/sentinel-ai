-- Phase 209-04: Restore more HALF_BUILT tables + ml_models column
-- Migration: 209-04_restore_block_booking_cross_module_ml.sql
-- Date: 2026-05-10
-- Problem: Backend reports missing tables:
--   - block_booking_records: booking store (1 row in _deprecated)
--   - cross_module_links: module registry (20 rows in _deprecated)
--   - ml_models.scaler_path: ML registry sync fails on all models

BEGIN;

-- block_booking_records: 1 row (room booking records)
CREATE TABLE public.block_booking_records (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  site_id text,
  organiser_email text,
  organiser_name text,
  room_id text,
  room_name text,
  booking_date date,
  start_time timestamp with time zone,
  end_time timestamp with time zone,
  raw_email_hash text,
  ingested_at timestamp with time zone,
  flagged boolean DEFAULT false,
  created_at timestamptz DEFAULT NOW()
);
INSERT INTO public.block_booking_records SELECT * FROM _deprecated.block_booking_records;

-- cross_module_links: 20 rows (module integration registry)
CREATE TABLE public.cross_module_links (
  link_id text PRIMARY KEY,
  site_id text,
  source_module text,
  target_module text,
  integration_type text,
  enabled boolean DEFAULT true,
  config jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT NOW(),
  updated_at timestamptz DEFAULT NOW()
);
INSERT INTO public.cross_module_links SELECT * FROM _deprecated.cross_module_links;

-- ml_models: add scaler_path column (dropped in 208-12, needed for ML registry sync)
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS scaler_path text;
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS scaler_type text;
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS feature_columns text[];
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS target_column text;

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON public.block_booking_records TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cross_module_links TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ml_models TO service_role;

COMMIT;

DO $$
BEGIN
  RAISE NOTICE '209-04: block_booking_records=%, cross_module_links=%, ml_models.scaler_path added',
    (SELECT count(*) FROM public.block_booking_records),
    (SELECT count(*) FROM public.cross_module_links),
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='ml_models' AND column_name='scaler_path');
END;
$$;
