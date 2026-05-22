-- Migration: retention_enforcement_log
-- Purpose: POPIA Section 14 audit trail for data retention enforcement
-- Proof of compliance: records what was deleted, when, and by which tier
-- Created: 2026-05-22

CREATE TABLE IF NOT EXISTS public.retention_enforcement_log (
    id              BIGSERIAL PRIMARY KEY,
    executed_at     TIMESTAMPTZ NOT NULL,
    dry_run         BOOLEAN NOT NULL DEFAULT FALSE,
    tier            TEXT NOT NULL,                      -- 'ML_TRAINING' | 'SNAPSHOT' | 'AUDIT_TRAIL'
    table_name      TEXT NOT NULL,
    date_column     TEXT NOT NULL DEFAULT 'created_at',
    reviewed        INTEGER NOT NULL DEFAULT 0,
    deleted         INTEGER NOT NULL DEFAULT 0,
    errors          JSONB DEFAULT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.retention_enforcement_log IS
    'POPIA S14 audit trail — records each retention enforcement run and its outcomes';

-- Retention: 5 years (same as AUDIT_TRAIL tier)
-- This table itself is never deleted by the retention job
ALTER TABLE public.retention_enforcement_log SET (
    timescaledb.time_column    = 'executed_at',
    timescaledb.time_interval  = INTERVAL '1 day'
);

-- Index for querying recent runs per table/tier
CREATE INDEX IF NOT EXISTS idx_retention_log_lookup
    ON public.retention_enforcement_log (table_name, tier, executed_at DESC);
