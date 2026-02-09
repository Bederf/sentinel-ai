-- Migration: 055_api_keys
-- Description: Persistent API keys with hashed storage

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    owner TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'auditor',
    scopes TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash
    ON api_keys(key_hash);

CREATE INDEX IF NOT EXISTS idx_api_keys_owner
    ON api_keys(owner);

CREATE INDEX IF NOT EXISTS idx_api_keys_revoked
    ON api_keys(revoked);
