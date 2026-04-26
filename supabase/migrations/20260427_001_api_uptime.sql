-- Phase 186: Availability SLI (Tier 4)
-- Tracks API uptime via synthetic checks: 99.5% SLO target
-- k6 runs every 60s → backend endpoint → api_uptime_checks
-- APScheduler aggregates daily (01:00 SAST) + monthly (1st of month 02:00 SAST)

BEGIN;

-- Raw synthetic check results (one row per 60s poll)
CREATE TABLE IF NOT EXISTS api_uptime_checks (
    id BIGSERIAL PRIMARY KEY,
    check_time TIMESTAMPTZ DEFAULT NOW(),
    status_code INT,
    latency_ms FLOAT,
    error_detail TEXT,
    endpoint TEXT DEFAULT '/api/health'
);

CREATE INDEX IF NOT EXISTS idx_uptime_checks_time ON api_uptime_checks (check_time DESC);

-- Daily uptime aggregation (1 row per day, computed by APScheduler job)
CREATE TABLE IF NOT EXISTS api_uptime_daily (
    id BIGSERIAL PRIMARY KEY,
    check_date DATE NOT NULL,
    total_checks INT,
    successful_checks INT,
    uptime_percent FLOAT,
    avg_latency_ms FLOAT,
    max_latency_ms FLOAT,
    CONSTRAINT unique_date UNIQUE (check_date)
);

CREATE INDEX IF NOT EXISTS idx_uptime_daily_date ON api_uptime_daily (check_date DESC);

-- Monthly SLO audit (one row per month)
CREATE TABLE IF NOT EXISTS api_uptime_monthly (
    id BIGSERIAL PRIMARY KEY,
    month TEXT NOT NULL,  -- 'YYYY-MM'
    total_checks INT,
    successful_checks INT,
    uptime_percent FLOAT,
    error_budget_remaining FLOAT,  -- 100 - uptime_percent
    downtime_minutes FLOAT,
    slo_target FLOAT DEFAULT 99.5,
    slo_pass BOOLEAN,
    incidents TEXT,  -- JSON array of high-severity events
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_month UNIQUE (month)
);

CREATE INDEX IF NOT EXISTS idx_uptime_monthly_month ON api_uptime_monthly (month DESC);

COMMIT;
