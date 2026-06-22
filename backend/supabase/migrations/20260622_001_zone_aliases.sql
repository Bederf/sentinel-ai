-- Zone aliases map raw/source zone labels to canonical SENTINEL zones.
-- Example: site-005 source label Zone-L3-ICU -> canonical Zone-300.

CREATE TABLE IF NOT EXISTS public.zone_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
    alias_key TEXT NOT NULL,
    canonical_zone_id TEXT NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'source'
        CHECK (alias_type IN ('source', 'display', 'legacy', 'functional')),
    source TEXT NOT NULL DEFAULT 'onboarding',
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.0
        CHECK (confidence >= 0 AND confidence <= 1),
    review_status TEXT NOT NULL DEFAULT 'approved'
        CHECK (review_status IN ('suggested', 'approved', 'rejected')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (site_id, alias_key)
);

CREATE INDEX IF NOT EXISTS idx_zone_aliases_site_canonical
    ON public.zone_aliases (site_id, canonical_zone_id);

CREATE INDEX IF NOT EXISTS idx_zone_aliases_review_status
    ON public.zone_aliases (review_status);
