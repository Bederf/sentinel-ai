-- Phase 168-01: API Keys Table for Production-Ready Key Storage
-- Replaces in-memory API key store with persistent, auditable Supabase storage

CREATE TABLE IF NOT EXISTS api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key_hash TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  owner_role INTEGER NOT NULL,
  last_rotated_at TIMESTAMP DEFAULT now(),
  expires_at TIMESTAMP,
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT now(),
  created_by UUID REFERENCES auth.users(id),
  CONSTRAINT valid_role CHECK (owner_role >= 1 AND owner_role <= 5)
);

-- Index for fast key_hash lookups
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);

-- Index for active keys queries
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(active) WHERE active = true;

-- Enable Row-Level Security
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- Policy: Authenticated AUDITOR+ can select their own keys and those created by them
CREATE POLICY IF NOT EXISTS api_keys_select_self ON api_keys
  FOR SELECT
  USING (
    auth.uid() IS NOT NULL
    AND (
      created_by = auth.uid()
      OR EXISTS (
        SELECT 1 FROM sentinel_users su
        WHERE su.auth_user_id = auth.uid()
        AND su.role >= 3  -- AUDITOR (3) or ADMIN (5)
      )
    )
  );

-- Policy: ADMIN can insert, update, delete
CREATE POLICY IF NOT EXISTS api_keys_insert_admin ON api_keys
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM sentinel_users su
      WHERE su.auth_user_id = auth.uid()
      AND su.role = 5  -- ADMIN only
    )
  );

CREATE POLICY IF NOT EXISTS api_keys_update_admin ON api_keys
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM sentinel_users su
      WHERE su.auth_user_id = auth.uid()
      AND su.role = 5
    )
  );

CREATE POLICY IF NOT EXISTS api_keys_delete_admin ON api_keys
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM sentinel_users su
      WHERE su.auth_user_id = auth.uid()
      AND su.role = 5
    )
  );
