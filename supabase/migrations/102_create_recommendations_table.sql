-- Migration 102: Create recommendations table
-- Purpose: Base table for AI optimization recommendations (approval workflow, execution tracking)
-- Note: Migration 069 adds extra approval columns to this table and must run AFTER this one

CREATE TABLE IF NOT EXISTS recommendations (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id               TEXT NOT NULL,
    timestamp             TIMESTAMPTZ NOT NULL DEFAULT now(),
    action_type           TEXT NOT NULL DEFAULT '',
    risk_level            TEXT NOT NULL DEFAULT 'medium'
                          CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    target_equipment      TEXT NOT NULL DEFAULT '',
    action                JSONB NOT NULL DEFAULT '{}',
    reason                TEXT NOT NULL DEFAULT '',
    expected_impact       JSONB NOT NULL DEFAULT '{}',
    confidence            TEXT NOT NULL DEFAULT 'medium',
    confidence_score      FLOAT NOT NULL DEFAULT 0.0,
    profile               TEXT NOT NULL DEFAULT '',
    multi_objective_score FLOAT NOT NULL DEFAULT 0.0,
    status                TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN (
                              'pending', 'approved', 'rejected',
                              'auto_executed', 'expired', 'executed',
                              'rolled_back', 'failed'
                          )),
    requires_approval     BOOLEAN NOT NULL DEFAULT false,
    approved_by           TEXT,
    approval_reason       TEXT,
    executed_at           TIMESTAMPTZ,
    execution_result      JSONB,
    rejection_reason      TEXT
);

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_recommendations_site_status
    ON recommendations(site_id, status);

CREATE INDEX IF NOT EXISTS idx_recommendations_timestamp
    ON recommendations(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_site_timestamp
    ON recommendations(site_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_target_equipment
    ON recommendations(target_equipment);

CREATE INDEX IF NOT EXISTS idx_recommendations_approval_pending
    ON recommendations(status)
    WHERE status IN ('pending', 'approved');

CREATE INDEX IF NOT EXISTS idx_recommendations_approved_by
    ON recommendations(approved_by)
    WHERE approved_by IS NOT NULL;
