-- Phase: 207-02
-- Purpose: Add 4-milestone SLA tracking columns to recommendations table
-- Milestones: assigned → in_progress → resolved → verified
-- Uses materialised sla_deadline_at column (updated on milestone advance)
-- instead of fragile computed expression index

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = 'recommendations') THEN

    -- Milestone status: which milestone the recommendation is currently in
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS
      milestone_status TEXT NOT NULL DEFAULT 'assigned'
      CHECK (milestone_status IN ('assigned', 'in_progress', 'resolved', 'verified'));

    -- Per-milestone timestamp fields
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ NOT NULL DEFAULT now();
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS in_progress_at TIMESTAMPTZ;
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

    -- Per-milestone SLA hour configs (JSONB: {"assigned": 24, "in_progress": 48, ...})
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS sla_hours JSONB NOT NULL DEFAULT '{}';

    -- Materialised SLA deadline — updated on each milestone advance
    -- This replaces the fragile compound expression index from the original plan
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS sla_deadline_at TIMESTAMPTZ;

    -- Legacy/external correlation (e.g. FSI ticket ID)
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS external_ticket_id TEXT;

  END IF;
END $$;

-- Indexes for milestone queries
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = 'recommendations') THEN

    CREATE INDEX IF NOT EXISTS idx_recommendations_milestone_status
      ON recommendations(milestone_status)
      WHERE milestone_status != 'verified';

    CREATE INDEX IF NOT EXISTS idx_recommendations_sla_deadline
      ON recommendations(sla_deadline_at DESC)
      WHERE sla_deadline_at IS NOT NULL;

    CREATE INDEX IF NOT EXISTS idx_recommendations_assigned_at
      ON recommendations(assigned_at DESC);

    CREATE INDEX IF NOT EXISTS idx_recommendations_external_ticket
      ON recommendations(external_ticket_id)
      WHERE external_ticket_id IS NOT NULL;

  END IF;
END $$;

-- Grant for service_role (Supabase RLS)
GRANT UPDATE ON recommendations TO service_role;
