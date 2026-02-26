-- Migration: Add approval workflow fields to recommendations table
-- Purpose: Support Tier 2 (supervised) approval workflow for Niagara equipment control
-- Phase: 68-02
-- Note: recommendations table may not exist yet (created in 102). Conditional execution.

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'recommendations') THEN
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) DEFAULT 'pending';
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS approved_by VARCHAR(255);
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE;
    ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS execution_result JSONB;
  END IF;
END $$;

-- Indexes are created conditionally too
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'recommendations') THEN
    CREATE INDEX IF NOT EXISTS idx_recommendations_approval_status
      ON recommendations(approval_status)
      WHERE approval_status IN ('pending', 'approved');

    CREATE INDEX IF NOT EXISTS idx_recommendations_approved_at
      ON recommendations(approved_at DESC)
      WHERE approved_at IS NOT NULL;

    CREATE INDEX IF NOT EXISTS idx_recommendations_approved_by
      ON recommendations(approved_by)
      WHERE approved_by IS NOT NULL;
  END IF;
END $$;
