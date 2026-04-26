-- Migration: 20260426_001_update_onboarding_phase_constraint
-- Update the onboarding_phase CHECK constraint to include canonical stage names.
-- Before: shadow/advisory/supervised/auto (Phase 111, Feb 2026)
-- After:  commissioning/shadow_live/advisory/supervised/automatic
-- Also maps: shadow->shadow_live, auto->automatic (LEGACY_MAP compatibility)

-- Step 1: Normalise existing legacy values that are already in the DB
UPDATE public.sites
SET onboarding_phase = 'shadow_live'
WHERE onboarding_phase = 'shadow';

UPDATE public.sites
SET onboarding_phase = 'automatic'
WHERE onboarding_phase = 'auto';

-- Step 2: Drop the old constraint
ALTER TABLE public.sites
  DROP CONSTRAINT IF EXISTS sites_onboarding_phase_check;

-- Step 3: Add updated constraint with canonical names
ALTER TABLE public.sites
  ADD CONSTRAINT sites_onboarding_phase_check
    CHECK (onboarding_phase IN (
      'commissioning', 'shadow_live', 'advisory', 'supervised', 'automatic'
    ));

COMMENT ON COLUMN public.sites.onboarding_phase IS
  'SENTINEL trust-building phase. commissioning=setup, shadow_live=ML training (hidden),
   advisory=notify+recommend, supervised=human-approved control, automatic=auto-apply.';
