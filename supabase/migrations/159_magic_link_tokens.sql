-- Magic link invitation tokens for user onboarding
-- Enables admin-sent invite links with time-limited tokens

CREATE TABLE IF NOT EXISTS magic_link_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator'
        CHECK (role IN ('admin', 'operator', 'developer', 'auditor')),
    site_id TEXT NOT NULL,
    invited_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    accepted_ip TEXT,
    accepted_user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_mlt_token ON magic_link_tokens(token);
CREATE INDEX IF NOT EXISTS idx_mlt_email ON magic_link_tokens(email);
CREATE INDEX IF NOT EXISTS idx_mlt_expires ON magic_link_tokens(expires_at);

-- Self-revocation: cleaner invites table after acceptance (optional, can run separately)
-- DELETE FROM magic_link_tokens WHERE accepted_at IS NOT NULL AND accepted_at < now() - INTERVAL '7 days';

-- Add password_hash to sentinel_users so invite-accept can set credentials
ALTER TABLE sentinel_users
    ADD COLUMN IF NOT EXISTS password_hash TEXT,
    ADD COLUMN IF NOT EXISTS must_set_password BOOLEAN NOT NULL DEFAULT true;
