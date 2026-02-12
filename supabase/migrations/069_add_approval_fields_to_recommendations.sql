-- Migration: Add approval workflow fields to recommendations table
-- Purpose: Support Tier 2 (supervised) approval workflow for Niagara equipment control
-- Phase: 68-02

-- Add approval status column
ALTER TABLE recommendations
  ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20)
    DEFAULT 'pending'
    CHECK (approval_status IN ('pending', 'approved', 'rejected', 'executed', 'failed'));

-- Add approver tracking columns
ALTER TABLE recommendations
  ADD COLUMN IF NOT EXISTS approved_by VARCHAR(255);

ALTER TABLE recommendations
  ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE;

-- Add execution result storage (JSON)
ALTER TABLE recommendations
  ADD COLUMN IF NOT EXISTS execution_result JSONB;

-- Add index for approval status lookups
CREATE INDEX IF NOT EXISTS idx_recommendations_approval_status
  ON recommendations(approval_status)
  WHERE approval_status IN ('pending', 'approved');

-- Add index for temporal queries (when was this approved?)
CREATE INDEX IF NOT EXISTS idx_recommendations_approved_at
  ON recommendations(approved_at DESC)
  WHERE approved_at IS NOT NULL;

-- Add index for user-specific lookups (who approved this?)
CREATE INDEX IF NOT EXISTS idx_recommendations_approved_by
  ON recommendations(approved_by)
  WHERE approved_by IS NOT NULL;

-- Add columns documentation
COMMENT ON COLUMN recommendations.approval_status IS 'Status in approval workflow: pending, approved, rejected, executed, or failed';
COMMENT ON COLUMN recommendations.approved_by IS 'User ID or name who approved or rejected this recommendation';
COMMENT ON COLUMN recommendations.approved_at IS 'Timestamp when approval action was taken';
COMMENT ON COLUMN recommendations.execution_result IS 'JSON result of device write execution: {success, device_write, cov_verified, timestamp}';
