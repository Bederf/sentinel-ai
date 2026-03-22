-- Migration: Create audit_archive table for immutable archival
-- Phase: 168-03 (Quality & Audit Trail)
-- Purpose: Archive old audit log entries (> 30 days) to immutable Supabase table
-- Control: AUDIT-001 (Immutable Audit Trail)

CREATE TABLE IF NOT EXISTS audit_archive (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  archived_from TEXT NOT NULL DEFAULT 'audit_log.json',
  archived_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  event_data JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,

  -- Constraint: prevent duplicate archival of same entry
  UNIQUE(created_at, archived_from)
);

-- Enable Row Level Security for audit_archive table
ALTER TABLE audit_archive ENABLE ROW LEVEL SECURITY;

-- Create index for efficient archival queries (by created_at)
CREATE INDEX IF NOT EXISTS idx_audit_archive_created_at
  ON audit_archive(created_at DESC);

-- Create index for efficient archival queries (by archived_at)
CREATE INDEX IF NOT EXISTS idx_audit_archive_archived_at
  ON audit_archive(archived_at DESC);

-- RLS policy: Allow system to INSERT archived records (audit archival job)
CREATE POLICY IF NOT EXISTS audit_archive_allow_insert_system
  ON audit_archive
  FOR INSERT
  WITH CHECK (true);

-- RLS policy: Allow system to SELECT archived records (audit queries)
CREATE POLICY IF NOT EXISTS audit_archive_allow_select_system
  ON audit_archive
  FOR SELECT
  USING (true);

-- RLS policy: DENY UPDATE (immutable — no modifications allowed)
CREATE POLICY IF NOT EXISTS audit_archive_deny_update
  ON audit_archive
  FOR UPDATE
  USING (false);

-- RLS policy: DENY DELETE (immutable — no deletions allowed)
CREATE POLICY IF NOT EXISTS audit_archive_deny_delete
  ON audit_archive
  FOR DELETE
  USING (false);
