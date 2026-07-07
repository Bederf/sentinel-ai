-- ============================================================
-- Migration: Add discovery session and onboarding state tables
--
-- Tables:
--   site_discovery_sessions — durable record of each discovery run
--   site_onboarding_state   — canonical onboarding state machine
--
-- Used by:
--   - api/simbiot_capabilities.py (GET /sites/{id}/capabilities)
--   - api/onboarding.py (POST /bridge-review/{id}/commit)
--   - commit_bridge_review RPC (Slice 2)
-- ============================================================

BEGIN;

-- ── site_discovery_sessions ──────────────────────────────────
CREATE TABLE IF NOT EXISTS public.site_discovery_sessions (
    discovery_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id             TEXT NOT NULL,
    adapter_type        TEXT NOT NULL,
    host                TEXT,
    port                INT,
    discovered_at       TIMESTAMPTZ DEFAULT now(),
    device_count        INT,
    point_count         INT,
    writable_point_count INT,
    raw_response_hash   TEXT,  -- SHA-256 of canonical JSON, not full payload
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'stale', 'committed', 'superseded')),
    committed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_discovery_sessions_site
    ON public.site_discovery_sessions (site_id);

CREATE INDEX IF NOT EXISTS idx_discovery_sessions_status
    ON public.site_discovery_sessions (status);

CREATE INDEX IF NOT EXISTS idx_discovery_sessions_active_site
    ON public.site_discovery_sessions (site_id, status)
    WHERE status = 'active';

-- ── site_onboarding_state ────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.site_onboarding_state (
    site_id             TEXT PRIMARY KEY,
    state               TEXT NOT NULL DEFAULT 'created'
                        CHECK (state IN ('created', 'discovered', 'synced', 'canonical', 'live')),
    last_transition_at  TIMESTAMPTZ DEFAULT now(),
    error_message       TEXT,
    checkpoint          JSONB DEFAULT '{}',
    discovery_id        UUID REFERENCES public.site_discovery_sessions(discovery_id)
                        ON DELETE SET NULL,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Upsert trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION public.set_site_onboarding_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_site_onboarding_state_updated_at
    ON public.site_onboarding_state;

CREATE TRIGGER trg_site_onboarding_state_updated_at
    BEFORE UPDATE ON public.site_onboarding_state
    FOR EACH ROW
    EXECUTE FUNCTION public.set_site_onboarding_state_updated_at();

-- Seed existing sites into onboarding_state (backward compat)
INSERT INTO public.site_onboarding_state (site_id, state, last_transition_at)
SELECT code,
       CASE
           WHEN onboarding_phase = 'shadow_live' THEN 'created'
           WHEN onboarding_phase = 'advisory' THEN 'live'
           WHEN onboarding_phase = 'supervised' THEN 'live'
           WHEN onboarding_phase = 'automatic' THEN 'live'
           ELSE 'created'
       END,
       COALESCE(updated_at, now())
FROM public.sites
ON CONFLICT (site_id) DO NOTHING;

COMMIT;
