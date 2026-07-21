-- Phase 186: Critical Path Latency (Tier 3)
-- Tracks wall-clock latency: PARASITE decision generated → human approval → actuator response
-- SLO target: p99 < 7000ms (7 seconds) for supervised-phase operations

BEGIN;

-- Raw latency traces (one row per approved+executed action)
CREATE TABLE IF NOT EXISTS supervised_action_traces (
    id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    approval_latency_ms FLOAT,   -- approved_at - timestamp (human think time)
    execution_latency_ms FLOAT,  -- executed_at - approved_at (device write + verify)
    total_latency_ms FLOAT,      -- executed_at - timestamp (end-to-end)
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_trace_per_rec UNIQUE (site_id, recommendation_id)
);

CREATE INDEX IF NOT EXISTS idx_traces_site_time ON supervised_action_traces (site_id, timestamp DESC);

-- Hourly percentile aggregation (computed by APScheduler hourly job)
CREATE TABLE IF NOT EXISTS critical_path_hourly (
    id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL,
    hour_start TIMESTAMPTZ NOT NULL,
    total_actions INT,
    p50_total_ms FLOAT,
    p99_total_ms FLOAT,
    p99_9_total_ms FLOAT,
    max_total_ms FLOAT,
    avg_total_ms FLOAT,
    slo_target_ms INT DEFAULT 7000,  -- 7 second wall-clock target
    slo_pass BOOLEAN,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_hour_per_site UNIQUE (site_id, hour_start)
);

CREATE INDEX IF NOT EXISTS idx_path_hourly_site ON critical_path_hourly (site_id, hour_start DESC);

COMMIT;
