-- Phase 188: Outcome-gated recommendation validation foundation.
-- Report-only foundation: explicit historical tagging plus runtime-readable
-- threshold and safety-profile config. This migration does not alter routing.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'recommendations'
          AND column_name = 'phase188_evidence_epoch'
    ) THEN
        ALTER TABLE public.recommendations
            ADD COLUMN phase188_evidence_epoch text NOT NULL DEFAULT 'excluded_unknown',
            ADD COLUMN phase188_evidence_epoch_set_at timestamptz,
            ADD COLUMN phase188_evidence_epoch_reason text;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'recommendations_phase188_evidence_epoch_check'
    ) THEN
        ALTER TABLE public.recommendations
            ADD CONSTRAINT recommendations_phase188_evidence_epoch_check
            CHECK (
                phase188_evidence_epoch IN (
                    'pre_cutover_legacy',
                    'post_phase185_cutover',
                    'excluded_unknown'
                )
            );
    END IF;
END $$;

UPDATE public.recommendations
SET phase188_evidence_epoch = 'pre_cutover_legacy',
    phase188_evidence_epoch_set_at = COALESCE(phase188_evidence_epoch_set_at, now()),
    phase188_evidence_epoch_reason = COALESCE(
        phase188_evidence_epoch_reason,
        'Phase 188 migration: existing recommendation history predates provenance-clean cutover'
    )
WHERE phase188_evidence_epoch = 'excluded_unknown'
  AND phase188_evidence_epoch_set_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_recommendations_phase188_epoch
    ON public.recommendations(site_id, phase188_evidence_epoch, timestamp DESC);

CREATE TABLE IF NOT EXISTS public.phase188_equipment_safety_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id text,
    equipment_type text NOT NULL,
    default_safety_class text NOT NULL CHECK (default_safety_class IN ('LOW', 'MEDIUM', 'HIGH')),
    source text NOT NULL DEFAULT 'equipment_type_profile',
    reason text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (site_id, equipment_type)
);

CREATE INDEX IF NOT EXISTS idx_phase188_safety_profiles_lookup
    ON public.phase188_equipment_safety_profiles(site_id, equipment_type)
    WHERE enabled = true;

CREATE TABLE IF NOT EXISTS public.phase188_outcome_thresholds (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id text,
    equipment_type text NOT NULL,
    recommendation_type text NOT NULL,
    safety_class text NOT NULL CHECK (safety_class IN ('LOW', 'MEDIUM', 'HIGH')),
    min_validated_recommendations integer NOT NULL DEFAULT 1 CHECK (min_validated_recommendations >= 0),
    min_measured_outcomes integer NOT NULL DEFAULT 1 CHECK (min_measured_outcomes >= 0),
    min_fault_prediction_samples integer NOT NULL DEFAULT 0 CHECK (min_fault_prediction_samples >= 0),
    max_false_positive_rate numeric NOT NULL DEFAULT 1.0 CHECK (max_false_positive_rate >= 0 AND max_false_positive_rate <= 1),
    max_false_negative_rate numeric NOT NULL DEFAULT 1.0 CHECK (max_false_negative_rate >= 0 AND max_false_negative_rate <= 1),
    min_positive_outcome_rate numeric NOT NULL DEFAULT 0.0 CHECK (min_positive_outcome_rate >= 0 AND min_positive_outcome_rate <= 1),
    min_energy_savings_confidence numeric NOT NULL DEFAULT 0.0 CHECK (min_energy_savings_confidence >= 0 AND min_energy_savings_confidence <= 1),
    promotion_mode text NOT NULL DEFAULT 'blocked'
        CHECK (promotion_mode IN ('blocked', 'advisory_only', 'supervised_eligible')),
    enabled boolean NOT NULL DEFAULT true,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (site_id, equipment_type, recommendation_type, safety_class)
);

CREATE INDEX IF NOT EXISTS idx_phase188_thresholds_lookup
    ON public.phase188_outcome_thresholds(site_id, equipment_type, recommendation_type, safety_class)
    WHERE enabled = true;

COMMENT ON COLUMN public.recommendations.phase188_evidence_epoch IS
    'Phase 188 evidence epoch. pre_cutover_legacy and excluded_unknown are excluded from promotion math.';

COMMENT ON TABLE public.phase188_equipment_safety_profiles IS
    'Phase 188 fallback mapping from equipment_type to gate safety class when point-level SafetyClass cannot be resolved.';

COMMENT ON TABLE public.phase188_outcome_thresholds IS
    'Phase 188 report-only outcome promotion thresholds by site/equipment/recommendation/safety class.';
