-- Migration 111: Add onboarding_phase to sites
--
-- Gates SENTINEL feature exposure progressively as a site earns trust.
-- shadow    → telemetry/ML/faults only, nothing surfaced
-- advisory  → recommendations + notifications visible, no control writes
-- supervised → approve/reject controls enabled
-- auto      → auto-apply within defined safety limits

ALTER TABLE public.sites
  ADD COLUMN IF NOT EXISTS onboarding_phase TEXT
    NOT NULL DEFAULT 'shadow'
    CHECK (onboarding_phase IN ('shadow', 'advisory', 'supervised', 'auto'));

COMMENT ON COLUMN public.sites.onboarding_phase IS
  'SENTINEL trust-building phase. shadow=monitor only, advisory=notify+recommend, supervised=human-approved control, auto=auto-apply within safety limits.';

-- Seed FNB Fairlands (S001) to advisory — telemetry already flowing
UPDATE public.sites
SET onboarding_phase = 'advisory'
WHERE code = 'site-001';
