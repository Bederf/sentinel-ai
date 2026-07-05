-- ============================================================================
-- Equipment — per-asset service_interval_days
-- Migration: 20260705_equipment_service_interval_days.sql
-- Created: 2026-07-05
-- Purpose: Phase B.4a — per-equipment PPM cadence for big assets
--
-- Today service_interval_days is per-equipment-type (in
-- equipment_health_config / health_calculation_config.json). For big
-- assets like the standby generator, the operator wants the cadence
-- settable per individual unit — generator #1 weekly, generator #2
-- monthly, chiller A every 90 days, chiller B every 120 days. Type-level
-- defaults are too coarse.
--
-- The maintenance page (operator-facing UI) writes this value per asset.
-- NULL means "fall back to the type-level default" — the PPM scheduler
-- resolves the effective interval in code so that the existing config
-- continues to work for any equipment the operator hasn't touched.
--
-- Backward compatibility: nullable, no default. Existing rows stay NULL
-- and keep their type-level cadence. No reader code change required.
-- ============================================================================

ALTER TABLE public.equipment
  ADD COLUMN IF NOT EXISTS service_interval_days integer
    CHECK (service_interval_days IS NULL OR (service_interval_days >= 1 AND service_interval_days <= 365));

-- Partial index supports the PPM scheduler's hot query:
--   "equipment with explicit per-asset cadence and a rollup gap"
-- Keeps the index small (only rows where the column is set).
CREATE INDEX IF NOT EXISTS idx_equipment_service_interval
    ON public.equipment (service_interval_days, last_rollup_at)
    WHERE service_interval_days IS NOT NULL
      AND baseline_state IN ('seed_only', 'rolling_active');

-- ── Rollback (for reference — keep as comment) ────────────────────────────────
-- DROP INDEX IF EXISTS public.idx_equipment_service_interval;
-- ALTER TABLE public.equipment DROP COLUMN IF EXISTS service_interval_days;
