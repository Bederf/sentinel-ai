-- Migration: 054_mfa_backup_codes
-- Description: One-time MFA backup codes (hashed) for account recovery

CREATE TABLE IF NOT EXISTS mfa_backup_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mfa_backup_codes_user_id
    ON mfa_backup_codes(user_id);

CREATE INDEX IF NOT EXISTS idx_mfa_backup_codes_user_unused
    ON mfa_backup_codes(user_id, used)
    WHERE used = FALSE;
