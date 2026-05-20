-- Migration: 20260519_001_add_whatsapp_onboarding.sql
-- Phase 211: WhatsApp staff onboarding
-- 1. Add whatsapp_phone to sites (per-site WhatsApp Business number for inbound routing)
-- 2. Create reporter_location_memory table (used by OpenClaw workspace SOUL.md onboarding)

BEGIN;

-- Per-site WhatsApp Business number for inbound routing (Meta Cloud API WABA phone ID)
ALTER TABLE sites ADD COLUMN IF NOT EXISTS whatsapp_phone TEXT;
COMMENT ON COLUMN sites.whatsapp_phone IS 'WhatsApp Business phone ID for this site (WABA phone_number_id from Meta API)';

-- reporter_location_memory: OpenClaw workspace writes here via location-memory API
-- Used by staff workspace SOUL.md Step 0 onboarding and location pre-fill
CREATE TABLE IF NOT EXISTS reporter_location_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_phone TEXT,                              -- Normalized to +27XXXXXXXXX
    reporter_telegram_id TEXT,
    reporter_name TEXT,
    site_id TEXT NOT NULL DEFAULT 'site-002',
    zone_id TEXT,
    floor TEXT,
    desk_id TEXT,
    location_text TEXT,                              -- Free-text: "Shop G123", "Bay 4", "Level 2"
    last_work_order_code TEXT,
    last_confirmed_at TIMESTAMPTZ,
    channel TEXT DEFAULT 'unknown',
    source TEXT DEFAULT 'call_log',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT rlm_phone_or_telegram CHECK (reporter_phone IS NOT NULL OR reporter_telegram_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_rlm_phone ON reporter_location_memory(reporter_phone);
CREATE INDEX IF NOT EXISTS idx_rlm_telegram ON reporter_location_memory(reporter_telegram_id);
CREATE INDEX IF NOT EXISTS idx_rlm_site ON reporter_location_memory(site_id);
CREATE INDEX IF NOT EXISTS idx_rlm_updated ON reporter_location_memory(updated_at DESC);

COMMENT ON TABLE reporter_location_memory IS 'OpenClaw workspace: per-reporter last known location + contact. Written by SOUL.md Step 0 onboarding.';

COMMIT;