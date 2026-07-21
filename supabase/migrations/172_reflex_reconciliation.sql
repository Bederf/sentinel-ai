-- Reflex reconciliation findings and recurrence tracking.
-- These tables support deterministic cross-signal reconciliation without
-- coupling the reflex layer to the LLM optimizer.

CREATE TABLE IF NOT EXISTS public.reflex_reconciliation_occurrences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    canonical_zone_id TEXT NOT NULL,
    source_zone_id TEXT,
    system_type TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    local_day_of_week SMALLINT NOT NULL,
    local_time_bucket TEXT NOT NULL,
    recommendation_id UUID NULL,
    finding_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reflex_occurrence_recurrence
    ON public.reflex_reconciliation_occurrences (
        site_id,
        canonical_zone_id,
        system_type,
        rule_key,
        local_day_of_week,
        local_time_bucket,
        occurred_at DESC
    );

CREATE INDEX IF NOT EXISTS idx_reflex_occurrence_site_time
    ON public.reflex_reconciliation_occurrences (site_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS public.reflex_zone_resolution_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    source_zone_id TEXT NOT NULL,
    source_context TEXT NOT NULL,
    reason TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reflex_zone_resolution_gaps_site_time
    ON public.reflex_zone_resolution_gaps (site_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_reflex_zone_resolution_gaps_zone
    ON public.reflex_zone_resolution_gaps (site_id, source_zone_id, observed_at DESC);

COMMENT ON TABLE public.reflex_reconciliation_occurrences IS
    'Deterministic zone/system mismatch occurrences used to detect recurring schedule defects.';

COMMENT ON TABLE public.reflex_zone_resolution_gaps IS
    'Visible data-quality gaps when zone identifiers cannot be safely mapped to canonical zones.';
