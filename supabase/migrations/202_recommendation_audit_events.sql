-- Append-only audit/event log for recommendation accountability and quality review.
-- Current recommendation state may remain materialized on recommendations for queue speed,
-- but dispute/accountability history is derived from this immutable event chain.

CREATE TABLE IF NOT EXISTS recommendation_audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id uuid REFERENCES recommendations(id) ON DELETE CASCADE,
    linked_recommendation_id uuid REFERENCES recommendations(id) ON DELETE SET NULL,
    site_id text NOT NULL,
    event_track text NOT NULL DEFAULT 'lifecycle'
        CHECK (event_track IN ('lifecycle', 'system_quality')),
    event_type text NOT NULL CHECK (event_type IN (
        'created',
        'surfaced',
        'viewed',
        'acknowledged',
        'approved',
        'rejected',
        'deferred',
        'wo_linked',
        'resolved',
        'expired',
        'escalated',
        'executed',
        'failed',
        'updated',
        'system_quality_exception'
    )),
    quality_exception_type text CHECK (
        quality_exception_type IS NULL OR quality_exception_type IN (
            'severity_reclassified',
            'missed_escalation',
            'confidence_gate_failed',
            'false_positive_marked',
            'false_negative_identified',
            'recommendation_withdrawn',
            'model_logic_corrected',
            'other'
        )
    ),
    actor_type text NOT NULL DEFAULT 'system',
    actor_id text,
    detected_by text,
    source text NOT NULL DEFAULT 'sentinel',
    previous_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    new_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (event_track = 'lifecycle' AND recommendation_id IS NOT NULL)
        OR (
            event_type = 'system_quality_exception'
            AND quality_exception_type IS NOT NULL
            AND linked_recommendation_id IS NOT NULL
            AND detected_by IS NOT NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_recommendation_audit_events_rec_time
    ON recommendation_audit_events(recommendation_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_recommendation_audit_events_site_time
    ON recommendation_audit_events(site_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_audit_events_quality
    ON recommendation_audit_events(site_id, quality_exception_type, occurred_at DESC)
    WHERE event_track = 'system_quality';

CREATE INDEX IF NOT EXISTS idx_recommendation_audit_events_linked_rec
    ON recommendation_audit_events(linked_recommendation_id, occurred_at DESC)
    WHERE linked_recommendation_id IS NOT NULL;

CREATE OR REPLACE FUNCTION prevent_recommendation_audit_event_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'recommendation_audit_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_recommendation_audit_events_no_update
    ON recommendation_audit_events;
CREATE TRIGGER trg_recommendation_audit_events_no_update
    BEFORE UPDATE ON recommendation_audit_events
    FOR EACH ROW EXECUTE FUNCTION prevent_recommendation_audit_event_mutation();

DROP TRIGGER IF EXISTS trg_recommendation_audit_events_no_delete
    ON recommendation_audit_events;
CREATE TRIGGER trg_recommendation_audit_events_no_delete
    BEFORE DELETE ON recommendation_audit_events
    FOR EACH ROW EXECUTE FUNCTION prevent_recommendation_audit_event_mutation();
