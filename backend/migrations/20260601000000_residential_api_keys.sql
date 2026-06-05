-- Phase 221: Residential API keys for tier gate (free vs paid)
-- Free tier: AEGIS alerts only (no AI recommendations)
-- Paid tier: Full AI recommendations + morning summary

CREATE TABLE IF NOT EXISTS residential_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key VARCHAR NOT NULL UNIQUE,
    chat_id BIGINT,
    tier VARCHAR DEFAULT 'paid',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_residential_api_keys_active
    ON residential_api_keys(api_key)
    WHERE is_active = TRUE;
