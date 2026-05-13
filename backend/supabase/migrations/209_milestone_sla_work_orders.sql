-- Phase: 209-01
-- Purpose: Add 4-milestone SLA tracking to work_orders table
-- Milestones: assigned → in_progress → resolved → verified
-- Uses materialised sla_deadline_at column (updated on milestone advance)
-- instead of fragile computed expression index
-- Note: recommendations table retains AI workflow; work_orders handles facility SLA

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = 'work_orders') THEN

    -- Milestone status: which milestone the work order is currently in
    ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS
      milestone_status TEXT NOT NULL DEFAULT 'assigned'
      CHECK (milestone_status IN ('assigned', 'in_progress', 'resolved', 'verified'));

    -- Per-milestone timestamp fields
    ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ NOT NULL DEFAULT now();
    ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS in_progress_at TIMESTAMPTZ;
    ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
    ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

    -- Per-milestone SLA hour configs (JSONB: {"assigned": 24, "in_progress": 48, ...})
    ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS sla_hours JSONB NOT NULL DEFAULT '{}';

    -- Materialised SLA deadline — updated on each milestone advance
    -- This replaces any fragile compound deadline computation
    ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS sla_deadline_at TIMESTAMPTZ;

  END IF;
END $$;

-- Indexes for milestone queries
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = 'work_orders') THEN

    CREATE INDEX IF NOT EXISTS idx_work_orders_milestone_status
      ON work_orders(milestone_status)
      WHERE milestone_status != 'verified';

    CREATE INDEX IF NOT EXISTS idx_work_orders_sla_deadline
      ON work_orders(sla_deadline_at DESC)
      WHERE sla_deadline_at IS NOT NULL;

    CREATE INDEX IF NOT EXISTS idx_work_orders_assigned_at
      ON work_orders(assigned_at DESC);

  END IF;
END $$;

-- Grant for service_role (Supabase RLS)
GRANT UPDATE ON work_orders TO service_role;
