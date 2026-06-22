CREATE TABLE IF NOT EXISTS sentry_feedback_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_type text NOT NULL CHECK (batch_type IN ('A', 'B', 'C')),
    bot_workspace text NOT NULL CHECK (bot_workspace IN ('staff', 'tech')),
    site_id text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    telegram_user_hash text,
    intent text,
    skill_name text,
    flow_name text,
    outcome text,
    failure_category text CHECK (failure_category IN (
        'no_skill_matched', 'unhandled_exception', 'policy_or_abuse',
        'out_of_scope', 'escalated_to_human', 'repeat_unresolved',
        'backend_unavailable'
    )),
    feedback_category text CHECK (feedback_category IN (
        'complaint', 'improvement_suggestion'
    )),
    sanitised_message text,
    source_table text,
    source_id text,
    work_order_code text,
    detector text CHECK (detector IN (
        'keyword', 'facilities_thesaurus', 'context_after_failure',
        'llm', 'manual'
    )),
    classifier_confidence numeric,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sfe_occurred ON sentry_feedback_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_sfe_batch_bot ON sentry_feedback_events (batch_type, bot_workspace, occurred_at);
CREATE INDEX IF NOT EXISTS idx_sfe_site ON sentry_feedback_events (site_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_sfe_intent ON sentry_feedback_events (intent, batch_type);
