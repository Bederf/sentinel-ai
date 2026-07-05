-- ============================================================================
-- Equipment Baselines — source_record_id link
-- Migration: 20260705_equipment_baselines_source_record.sql
-- Created: 2026-07-05
-- Purpose: Phase A.3 — auditable prediction lineage (Phase E)
--
-- Today each equipment_baselines row tracks baseline_type / source_type /
-- captured_by / notes but not which concrete measurement event produced it.
-- The rollup service (Phase B) writes a new baseline row every W=8 visits;
-- without a back-pointer, an operator clicking a prediction card cannot
-- follow it back to the WO + readings + attachments that produced it.
--
-- This column is the join key for the lineage route GET /api/predictions/
-- {code}/lineage — it links a forecast back to its source service_records
-- row, which in turn links to service_readings and service_attachments.
--
-- Backward compatibility: nullable. Existing rows (today's count: 0 in DB,
-- schema-level rows from earlier phases) get NULL. New rows written by the
-- rollup service will always populate.
--
-- We deliberately do NOT FK to service_records(id) — that table may have
-- historical rows we haven't migrated, and a hard FK would block the
-- capture-before-rollup flow. Application code validates the link.
-- ============================================================================

ALTER TABLE public.equipment_baselines
  ADD COLUMN IF NOT EXISTS source_record_id uuid;

-- Lookup index for the lineage route: "find baselines produced by this
-- service_record" (rare) and "find baselines NOT yet linked to a rollup
-- (i.e., manual onboarding snapshots)" (rare). The hot path is "find
-- the active baseline per equipment" — already covered by existing
-- get_active_equipment_baseline via status + baseline_date DESC.

CREATE INDEX IF NOT EXISTS idx_equipment_baselines_source_record
    ON public.equipment_baselines (source_record_id)
    WHERE source_record_id IS NOT NULL;

-- Partial index for the onboarding catch-up flow: "find equipment whose
-- baseline has no source_record_id" — these are the manual snapshots
-- that need a rollup or a maintenance-tab CTA before any prediction can
-- be shown for them.
CREATE INDEX IF NOT EXISTS idx_equipment_baselines_unlinked
    ON public.equipment_baselines (equipment_id)
    WHERE source_record_id IS NULL;

-- ── Rollback (for reference — keep as comment) ────────────────────────────────
-- DROP INDEX IF EXISTS public.idx_equipment_baselines_unlinked;
-- DROP INDEX IF EXISTS public.idx_equipment_baselines_source_record;
-- ALTER TABLE public.equipment_baselines DROP COLUMN IF EXISTS source_record_id;
