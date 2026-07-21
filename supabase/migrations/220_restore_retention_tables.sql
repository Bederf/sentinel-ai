-- Phase 209-02: Restore archived retention tables + verify write paths
-- Migration: 209-02_restore_retention_tables.sql
-- Date: 2026-05-10
-- Problem: Phase 208-10 archived 2 ML_TRAINING tables, breaking retention service:
--   - equipment_fault_events (4.2M rows) — archived intact
--   - adapter_health_current (65 rows) — archived intact
-- retention service needs these tables for 7-day rolling delete (POPIA S14(1))

BEGIN;

-- equipment_fault_events: 4.2M rows (matches archived schema exactly)
-- updated_at added for RLS/triggers compatibility
CREATE TABLE public.equipment_fault_events (
  id bigint,
  equipment_code text,
  site_id text,
  alarm_code text,
  severity text,
  description text,
  event_type text,
  source_object text,
  active_text text,
  message_text text,
  event_state text,
  alarm_class text,
  point_name text,
  point_value double precision,
  threshold_value double precision,
  acknowledged boolean DEFAULT false,
  acknowledged_by text,
  acknowledged_at timestamptz,
  cleared boolean DEFAULT false,
  cleared_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT NOW(),
  raw_payload jsonb DEFAULT '{}',
  updated_at timestamptz DEFAULT NOW()
);

-- adapter_health_current: 65 rows (matches archived schema exactly)
-- Note: created_at added for RLS/triggers, updated_at expected by retention service
CREATE TABLE public.adapter_health_current (
  site_id text,
  adapter_name text,
  adapter_type text,
  is_healthy boolean,
  last_check timestamptz,
  consecutive_failures integer DEFAULT 0,
  uptime_1h_percent double precision,
  uptime_24h_percent double precision,
  updated_at timestamptz DEFAULT NOW(),
  created_at timestamptz DEFAULT NOW()
);

-- Restore from _deprecated
INSERT INTO public.equipment_fault_events SELECT * FROM _deprecated.equipment_fault_events;
INSERT INTO public.adapter_health_current SELECT * FROM _deprecated.adapter_health_current;

-- Grants (no triggers since no updated_at on archived schema)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.equipment_fault_events TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.adapter_health_current TO service_role;

COMMIT;

DO $$
BEGIN
  RAISE NOTICE '209-02 restore: equipment_fault_events=%, adapter_health_current=%',
    (SELECT count(*) FROM public.equipment_fault_events),
    (SELECT count(*) FROM public.adapter_health_current);
END;
$$;
