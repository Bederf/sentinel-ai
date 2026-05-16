-- Stage 03 Distillation: User Preferences Table
-- Captures FM preferences extracted from chat interactions.
-- One active preference per type per user (site-scoped).

CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    preference_type TEXT NOT NULL CHECK (preference_type IN ('setpoint', 'priority', 'timing', 'equipment')),
    preference_value JSONB NOT NULL,
    source TEXT NOT NULL DEFAULT 'chat_explicit',
    confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enforce one active preference per type per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_preferences_type
    ON user_preferences (site_id, user_id, preference_type);

-- Fast lookup for context injection (fetch all active for user)
CREATE INDEX IF NOT EXISTS idx_user_preferences_active
    ON user_preferences (site_id, user_id);

COMMENT ON TABLE user_preferences IS 'FM preferences extracted from chat interactions (Stage 03 Distillation)';
COMMENT ON COLUMN user_preferences.preference_type IS 'setpoint | priority | timing | equipment';
COMMENT ON COLUMN user_preferences.preference_value IS 'Flexible JSONB per type (see backend/app/models/preference.py for schemas)';
COMMENT ON COLUMN user_preferences.confidence IS 'Extraction confidence 0.0-1.0. Only >0.75 stored.';
COMMENT ON COLUMN user_preferences.source IS 'chat_explicit | api | inferred';
