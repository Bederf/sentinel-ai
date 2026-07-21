CREATE TABLE IF NOT EXISTS sentry_bot_state (
    key        text        PRIMARY KEY,
    value      jsonb       NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE sentry_bot_state IS 'Persistent key-value state for Sentry bot tool scripts (optimization-check, health-alert dedup).';
