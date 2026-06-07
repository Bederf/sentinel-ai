-- Phase 223: Alarm Lifecycle Integrity
-- Adds lifecycle tracking to the alerts table so BACnet persistent alarms
-- are correctly upserted (not blindly re-inserted) on every bridge poll.
--
-- Key invariants after this migration:
--   * event_at, first_seen_at  — immutable, set on first INSERT only
--   * last_seen_at              — refreshed on every poll cycle
--   * resolved_at               — set exactly once when alarm clears
--   * source + source_dedupe_key — stable BACnet identity for UPSERT target
--   * lifecycle_state           — 'active' | 'resolved' | 'reopened'
--   * occurrence_count          — increments on each reopen

-- ── 1. Add lifecycle columns ─────────────────────────────────────────────────

ALTER TABLE public.alerts
  ADD COLUMN IF NOT EXISTS source text,
  ADD COLUMN IF NOT EXISTS source_dedupe_key text,
  ADD COLUMN IF NOT EXISTS event_at timestamptz,
  ADD COLUMN IF NOT EXISTS first_seen_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_seen_at timestamptz,
  ADD COLUMN IF NOT EXISTS resolved_at timestamptz,
  ADD COLUMN IF NOT EXISTS lifecycle_state text DEFAULT 'active'
    CHECK (lifecycle_state IN ('active', 'resolved', 'reopened')),
  ADD COLUMN IF NOT EXISTS occurrence_count integer NOT NULL DEFAULT 1;

-- ── 2. Unique constraint for UPSERT deduplication ────────────────────────────
-- NULL values in PostgreSQL UNIQUE constraints are treated as distinct, so
-- legacy rows with NULL source/source_dedupe_key will not conflict with each
-- other or with new rows that carry real dedupe keys.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'alerts_source_dedupe_key_unique'
  ) THEN
    ALTER TABLE public.alerts
      ADD CONSTRAINT alerts_source_dedupe_key_unique
      UNIQUE (site_id, source, source_dedupe_key);
  END IF;
END $$;

-- ── 3. Immutability trigger for event_at and first_seen_at ───────────────────

CREATE OR REPLACE FUNCTION alerts_protect_immutable_fields()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.event_at IS NOT NULL AND NEW.event_at IS DISTINCT FROM OLD.event_at THEN
    NEW.event_at := OLD.event_at;
  END IF;
  IF OLD.first_seen_at IS NOT NULL AND NEW.first_seen_at IS DISTINCT FROM OLD.first_seen_at THEN
    NEW.first_seen_at := OLD.first_seen_at;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_alerts_protect_immutable ON public.alerts;
CREATE TRIGGER trg_alerts_protect_immutable
  BEFORE UPDATE ON public.alerts
  FOR EACH ROW EXECUTE FUNCTION alerts_protect_immutable_fields();

-- ── 4. Backfill existing rows ────────────────────────────────────────────────
-- Give legacy rows meaningful lifecycle fields so queries don't have to
-- handle NULLs for active/acknowledged rows.
-- resolved rows get resolved_at = updated_at; all others get lifecycle_state = status.

UPDATE public.alerts
SET
  event_at        = COALESCE(event_at, created_at),
  first_seen_at   = COALESCE(first_seen_at, created_at),
  last_seen_at    = COALESCE(last_seen_at, updated_at),
  lifecycle_state = COALESCE(lifecycle_state,
                     CASE status
                       WHEN 'resolved' THEN 'resolved'
                       ELSE 'active'
                     END),
  resolved_at     = CASE WHEN status = 'resolved' THEN COALESCE(resolved_at, updated_at)
                         ELSE resolved_at
                    END
WHERE event_at IS NULL
   OR first_seen_at IS NULL
   OR last_seen_at IS NULL
   OR lifecycle_state IS NULL;
