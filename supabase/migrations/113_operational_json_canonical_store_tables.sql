-- Operational JSON canonical store migration
-- Creates canonical Postgres tables for JSON-backed SENTINEL operational domains
-- that should not remain JSON-primary.

CREATE TABLE IF NOT EXISTS public.user_entitlements (
    user_id TEXT PRIMARY KEY,
    user_email TEXT NOT NULL UNIQUE,
    modules JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_entitlements_user_email
    ON public.user_entitlements(user_email);

CREATE TABLE IF NOT EXISTS public.decision_records (
    record_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_description TEXT,
    equipment_id TEXT,
    equipment_type TEXT,
    site_id TEXT,
    diagnosis TEXT,
    diagnosis_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    diagnosis_source TEXT NOT NULL DEFAULT 'ai_reasoning',
    action_type TEXT,
    action_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    action_executed_at TIMESTAMPTZ,
    action_executed_by TEXT,
    outcome TEXT NOT NULL DEFAULT 'pending',
    outcome_details TEXT,
    outcome_evaluated_at TIMESTAMPTZ,
    resolution_time_minutes DOUBLE PRECISION,
    signals_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    season TEXT,
    time_of_day TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_id TEXT,
    recommendation_id TEXT,
    work_order_id TEXT,
    event_id TEXT,
    CONSTRAINT valid_decision_outcome
        CHECK (outcome IN ('resolved', 'partially_resolved', 'ineffective', 'worsened', 'pending', 'unknown'))
);

CREATE INDEX IF NOT EXISTS idx_decision_records_event_equipment
    ON public.decision_records(event_type, equipment_type);

CREATE INDEX IF NOT EXISTS idx_decision_records_site_id
    ON public.decision_records(site_id);

CREATE INDEX IF NOT EXISTS idx_decision_records_equipment_id
    ON public.decision_records(equipment_id);

CREATE TABLE IF NOT EXISTS public.decision_patterns (
    pattern_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    equipment_type TEXT NOT NULL,
    likely_diagnosis TEXT NOT NULL,
    diagnosis_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    recommended_action TEXT,
    action_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_occurrences INTEGER NOT NULL DEFAULT 0,
    resolved_count INTEGER NOT NULL DEFAULT 0,
    success_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    avg_resolution_time_minutes DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    applicable_sites JSONB NOT NULL DEFAULT '[]'::jsonb,
    seasonal_pattern TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_matched_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_decision_patterns_key
    ON public.decision_patterns(event_type, equipment_type, likely_diagnosis);

CREATE INDEX IF NOT EXISTS idx_decision_patterns_event_equipment
    ON public.decision_patterns(event_type, equipment_type);

CREATE OR REPLACE FUNCTION public.update_user_entitlements_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_entitlements_updated_at ON public.user_entitlements;
CREATE TRIGGER trg_user_entitlements_updated_at
    BEFORE UPDATE ON public.user_entitlements
    FOR EACH ROW
    EXECUTE FUNCTION public.update_user_entitlements_updated_at();

CREATE OR REPLACE FUNCTION public.update_decision_records_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decision_records_updated_at ON public.decision_records;
CREATE TRIGGER trg_decision_records_updated_at
    BEFORE UPDATE ON public.decision_records
    FOR EACH ROW
    EXECUTE FUNCTION public.update_decision_records_updated_at();

CREATE OR REPLACE FUNCTION public.update_decision_patterns_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decision_patterns_updated_at ON public.decision_patterns;
CREATE TRIGGER trg_decision_patterns_updated_at
    BEFORE UPDATE ON public.decision_patterns
    FOR EACH ROW
    EXECUTE FUNCTION public.update_decision_patterns_updated_at();
