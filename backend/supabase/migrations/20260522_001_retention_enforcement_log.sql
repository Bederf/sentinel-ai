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

-- Index for querying recent runs per table/tier
CREATE INDEX IF NOT EXISTS idx_retention_log_lookup
    ON public.retention_enforcement_log (table_name, tier, executed_at DESC);

-- POPIA S14 retention: service_role needs DELETE on all tier tables
-- (authenticator already has DELETE; service_role is used by PostgREST REST API)
GRANT DELETE ON equipment_sensor_readings TO service_role;
GRANT DELETE ON alerts TO service_role;
GRANT DELETE ON equipment_fault_events TO service_role;
GRANT DELETE ON adapter_health TO service_role;
GRANT DELETE ON adapter_health_current TO service_role;
GRANT DELETE ON adapter_health_alerts TO service_role;
GRANT DELETE ON space_occupancy_events TO service_role;
GRANT DELETE ON asset_health_snapshots TO service_role;
GRANT DELETE ON system_health_snapshots TO service_role;
GRANT DELETE ON recommendations TO service_role;
GRANT DELETE ON parasite_decisions TO service_role;
