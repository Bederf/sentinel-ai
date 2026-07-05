-- ============================================================================
-- Equipment — baseline lifecycle columns
-- Migration: 20260705_equipment_baseline_state.sql
-- Created: 2026-07-05
-- Purpose: Phase A.2 — gate prediction cards on baseline maturity
--
-- Today every equipment row has health_score computed against a threshold
-- but no machine-readable answer to "has this equipment ever been baselined,
-- and if so, how recently?" The frontend predictions tab currently serves
-- 10 template-derived forecasts for site-002 with no way to say "skip this
-- one — its baseline is missing or stale."
--
-- baseline_state gates the prediction card render. last_rollup_at drives
-- the PPM scheduler (Phase B.8) which auto-emits preventive WOs when the
-- gap exceeds the equipment's service_interval_days.
--
-- Backward compatibility: existing rows default to 'none'. S002 behaviour
-- stays the same — empty-state UI shows "baseline incomplete" once Phase D
-- lands. No reader code path changes.
-- ============================================================================

ALTER TABLE public.equipment
  ADD COLUMN IF NOT EXISTS baseline_state text NOT NULL DEFAULT 'none'
    CHECK (baseline_state IN ('none', 'seed_only', 'rolling_active', 'locked')),
  ADD COLUMN IF NOT EXISTS last_rollup_at timestamptz;

-- Partial index: PPM scheduler queries equipment whose last_rollup_at is
-- NULL or older than the cadence. Keeping the index partial means we don't
-- pay maintenance cost on equipment in 'none' state (which never qualifies
-- for auto-emission under gating policy A).
CREATE INDEX IF NOT EXISTS idx_equipment_rollup_due
    ON public.equipment (last_rollup_at)
    WHERE baseline_state IN ('seed_only', 'rolling_active');

-- ── Rollback (for reference — keep as comment) ────────────────────────────────
-- ALTER TABLE public.equipment DROP COLUMN IF EXISTS last_rollup_at;
-- ALTER TABLE public.equipment DROP COLUMN IF EXISTS baseline_state;
