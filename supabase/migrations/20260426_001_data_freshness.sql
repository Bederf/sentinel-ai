-- Phase 186: Data Freshness SLI — Tier 2: Data Freshness Pipeline
-- Tracks age of normalized data at each stage: BMS telemetry → Supabase → ML → Recommendations
-- Runs every 5 minutes via DataFreshnessMonitor; calculates age, updates SLI pass/fail, logs breaches

BEGIN;

-- Materialized freshness state per (site, data_source)
CREATE TABLE IF NOT EXISTS data_freshness (
    id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL,
    data_source TEXT NOT NULL,         -- 'bms_telemetry' | 'documents' | 'anomalies' | 'recommendations'
    last_updated TIMESTAMPTZ,
    age_seconds INT,
    sli_target_seconds INT NOT NULL,  -- e.g. 30=BMS realtime, 7200=batched docs, 300=ML anomalies
    sli_pass BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_source_per_site UNIQUE (site_id, data_source)
);

CREATE INDEX IF NOT EXISTS idx_freshness_by_site ON data_freshness (site_id);

-- Breach audit trail (SLO accountability)
CREATE TABLE IF NOT EXISTS data_freshness_breaches (
    id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL,
    data_source TEXT NOT NULL,
    breach_time TIMESTAMPTZ DEFAULT NOW(),
    age_seconds INT,
    sli_target INT,
    duration_seconds INT,
    resolved_at TIMESTAMPTZ,
    CONSTRAINT unique_breach_interval UNIQUE (site_id, data_source, breach_time)
);

CREATE INDEX IF NOT EXISTS idx_breaches_unresolved ON data_freshness_breaches (site_id) WHERE resolved_at IS NULL;

-- Initialize markers for known sites and data sources
INSERT INTO data_freshness (site_id, data_source, sli_target_seconds) VALUES
    ('S002', 'bms_telemetry', 30),
    ('S002', 'documents', 7200),
    ('S002', 'anomalies', 300),
    ('S002', 'recommendations', 900),
    ('S001', 'bms_telemetry', 30),
    ('S001', 'documents', 7200),
    ('S001', 'anomalies', 300),
    ('S001', 'recommendations', 900)
ON CONFLICT (site_id, data_source) DO NOTHING;

COMMIT;
