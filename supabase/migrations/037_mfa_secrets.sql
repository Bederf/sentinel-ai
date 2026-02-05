-- Migration: 037_mfa_secrets
-- Description: MFA/TOTP secrets table for privileged access
-- FSR Domain: 4.6 - Logical Access Control (MFA for ADMIN role)
-- Created: 2026-02-05

-- ============================================================================
-- MFA SECRETS TABLE
-- ============================================================================
-- Stores TOTP secrets for users enrolled in multi-factor authentication.
-- Required for ADMIN role users (FSR 4.6.3 - MFA for privileged access).

CREATE TABLE IF NOT EXISTS mfa_secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email TEXT NOT NULL UNIQUE,
    totp_secret TEXT NOT NULL,  -- Base32-encoded TOTP secret (encrypted at rest by Supabase)
    enabled BOOLEAN DEFAULT FALSE,  -- MFA is enabled after first successful verification
    backup_codes TEXT[],  -- Optional backup codes for account recovery
    failed_attempts INTEGER DEFAULT 0,  -- Track failed MFA attempts for rate limiting
    last_failed_at TIMESTAMPTZ,  -- Last failed attempt timestamp
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    last_enrolled_at TIMESTAMPTZ  -- When MFA enrollment was completed
);

-- Index for fast email lookups during login
CREATE INDEX IF NOT EXISTS idx_mfa_secrets_email ON mfa_secrets(user_email);

-- Index for finding users who need to enroll
CREATE INDEX IF NOT EXISTS idx_mfa_secrets_enabled ON mfa_secrets(enabled) WHERE enabled = FALSE;

-- ============================================================================
-- MFA EVENTS TABLE
-- ============================================================================
-- Audit log for MFA-related security events.
-- Required for FSR compliance and security monitoring.

CREATE TABLE IF NOT EXISTS mfa_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- mfa_enrolled, mfa_verified, mfa_failed, mfa_disabled, mfa_rate_limited
    source_ip TEXT,
    user_agent TEXT,
    event_data JSONB,  -- Additional event metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for querying user's MFA events
CREATE INDEX IF NOT EXISTS idx_mfa_events_email ON mfa_events(user_email);

-- Index for querying by event type
CREATE INDEX IF NOT EXISTS idx_mfa_events_type ON mfa_events(event_type);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_mfa_events_created ON mfa_events(created_at);

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON TABLE mfa_secrets IS 'TOTP secrets for multi-factor authentication (FSR 4.6.3)';
COMMENT ON COLUMN mfa_secrets.totp_secret IS 'Base32-encoded TOTP secret - encrypted at rest';
COMMENT ON COLUMN mfa_secrets.enabled IS 'FALSE until user completes first verification';
COMMENT ON COLUMN mfa_secrets.failed_attempts IS 'Counter for rate limiting (max 5 per 5 minutes)';
COMMENT ON COLUMN mfa_secrets.backup_codes IS 'One-time backup codes for account recovery';

COMMENT ON TABLE mfa_events IS 'Audit log for MFA security events';
COMMENT ON COLUMN mfa_events.event_type IS 'Event type: enrolled, verified, failed, disabled, rate_limited';
