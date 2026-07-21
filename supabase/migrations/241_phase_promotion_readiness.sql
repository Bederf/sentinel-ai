-- Phase 238 (M2.1 Readiness Orchestrator): complete the readiness persistence
-- schema the phase_promotion_evaluator already targets.
--
-- Readiness ≠ operating mode: these columns record what Sentinel computed
-- (eligibility + evidence); onboarding_phase changes remain operator-only via
-- PATCH /sites/{site_id}/phase.

-- Readiness surface on sites (phase_promotion_ready already exists)
ALTER TABLE sites ADD COLUMN IF NOT EXISTS phase_promotion_ready_since timestamptz;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS phase_promotion_target text;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS phase_promotion_readiness jsonb;

-- Explicit human authorization flag for the automatic tier
-- (read by the human_approved_autonomous promotion gate; never set by Sentinel)
ALTER TABLE sites ADD COLUMN IF NOT EXISTS human_approved_autonomous boolean NOT NULL DEFAULT false;

-- Eligibility-edge log: one row per readiness flip (distinct from phase transitions)
CREATE TABLE IF NOT EXISTS phase_promotion_readiness_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id text NOT NULL,
    from_phase text NOT NULL,
    to_phase text NOT NULL,
    met boolean NOT NULL,
    met_at timestamptz NOT NULL,
    current_progress jsonb,
    gate_results jsonb,
    recorded_by text NOT NULL DEFAULT 'phase_promotion_evaluator',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_phase_promotion_readiness_log_site
    ON phase_promotion_readiness_log (site_id, created_at DESC);

-- Gate-evidence snapshot on the immutable transition log (AC-5/AC-10):
-- the readiness evaluation that authorized a forward transition, replayable.
ALTER TABLE phase_transition_log ADD COLUMN IF NOT EXISTS gate_snapshot jsonb;
