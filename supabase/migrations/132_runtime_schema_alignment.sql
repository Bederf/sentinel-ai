-- Runtime schema alignment for live backend warnings discovered on 2026-03-26.
-- Fixes:
-- 1. recommendations missing approval workflow columns expected by repository code
-- 2. parasite_decisions missing model-backed execution/audit columns
-- 3. audit_archive table absent, causing archival retry loops and log noise

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'recommendations'
  ) THEN
    ALTER TABLE public.recommendations
      ADD COLUMN IF NOT EXISTS approval_status TEXT DEFAULT 'pending',
      ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

    UPDATE public.recommendations
    SET approval_status = 'pending'
    WHERE approval_status IS NULL;

    CREATE INDEX IF NOT EXISTS idx_recommendations_approval_status
      ON public.recommendations (approval_status);

    CREATE INDEX IF NOT EXISTS idx_recommendations_approved_at
      ON public.recommendations (approved_at DESC)
      WHERE approved_at IS NOT NULL;
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'parasite_decisions'
  ) THEN
    ALTER TABLE public.parasite_decisions
      ADD COLUMN IF NOT EXISTS correlation_id TEXT,
      ADD COLUMN IF NOT EXISTS device_id TEXT,
      ADD COLUMN IF NOT EXISTS mode TEXT,
      ADD COLUMN IF NOT EXISTS gate_status TEXT,
      ADD COLUMN IF NOT EXISTS enforcement TEXT,
      ADD COLUMN IF NOT EXISTS gate_snapshot_id TEXT,
      ADD COLUMN IF NOT EXISTS safety_check_version TEXT,
      ADD COLUMN IF NOT EXISTS safety_rules_evaluated JSONB DEFAULT '[]'::jsonb,
      ADD COLUMN IF NOT EXISTS safety_rules_triggered JSONB DEFAULT '[]'::jsonb,
      ADD COLUMN IF NOT EXISTS safety_result TEXT,
      ADD COLUMN IF NOT EXISTS actor TEXT,
      ADD COLUMN IF NOT EXISTS approval_id TEXT,
      ADD COLUMN IF NOT EXISTS command_id TEXT,
      ADD COLUMN IF NOT EXISTS write_status TEXT,
      ADD COLUMN IF NOT EXISTS write_attempt_count INTEGER DEFAULT 1,
      ADD COLUMN IF NOT EXISTS failure_reason TEXT,
      ADD COLUMN IF NOT EXISTS point_name TEXT,
      ADD COLUMN IF NOT EXISTS cov_tolerance JSONB,
      ADD COLUMN IF NOT EXISTS cov_latency_ms INTEGER,
      ADD COLUMN IF NOT EXISTS device_response_latency_ms INTEGER,
      ADD COLUMN IF NOT EXISTS predicted_impact JSONB,
      ADD COLUMN IF NOT EXISTS measured_impact JSONB,
      ADD COLUMN IF NOT EXISTS rejection_category TEXT;

    UPDATE public.parasite_decisions
    SET point_name = control_point
    WHERE point_name IS NULL
      AND control_point IS NOT NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.audit_archive (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  archived_from TEXT NOT NULL DEFAULT 'audit_log.json',
  archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE (created_at, archived_from)
);

CREATE INDEX IF NOT EXISTS idx_audit_archive_created_at
  ON public.audit_archive (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_archive_archived_at
  ON public.audit_archive (archived_at DESC);

ALTER TABLE public.audit_archive ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'audit_archive'
      AND policyname = 'audit_archive_allow_insert_system'
  ) THEN
    CREATE POLICY audit_archive_allow_insert_system
      ON public.audit_archive
      FOR INSERT
      WITH CHECK (true);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'audit_archive'
      AND policyname = 'audit_archive_allow_select_system'
  ) THEN
    CREATE POLICY audit_archive_allow_select_system
      ON public.audit_archive
      FOR SELECT
      USING (true);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'audit_archive'
      AND policyname = 'audit_archive_deny_update'
  ) THEN
    CREATE POLICY audit_archive_deny_update
      ON public.audit_archive
      FOR UPDATE
      USING (false);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'audit_archive'
      AND policyname = 'audit_archive_deny_delete'
  ) THEN
    CREATE POLICY audit_archive_deny_delete
      ON public.audit_archive
      FOR DELETE
      USING (false);
  END IF;
END $$;
