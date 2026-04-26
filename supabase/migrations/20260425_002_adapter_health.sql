-- Per-adapter heartbeat tracking for SLI Tier 1: Adapter Heartbeat
-- Tracks BMS adapter health: BACnet, Niagara, OBIX, ShadowModePolling bridge per site

CREATE TABLE IF NOT EXISTS adapter_health (
    id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL,                      -- 'site-002' internal format
    adapter_name TEXT NOT NULL,                 -- e.g. 'shadow_bridge', 'bacnet_niagara', 'obix_client'
    adapter_type TEXT NOT NULL,                 -- 'shadow_bridge', 'bacnet', 'niagara', 'obix', 'dali'
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    is_healthy BOOLEAN NOT NULL,
    latency_ms FLOAT,
    consecutive_failures INT DEFAULT 0,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

-- Unique constraint: one record per adapter per second (prevents double-writes on rapid polling)
ALTER TABLE adapter_health
    DROP CONSTRAINT IF EXISTS unique_adapter_health_per_second;
ALTER TABLE adapter_health
    ADD CONSTRAINT unique_adapter_health_per_second
    UNIQUE (site_id, adapter_name, timestamp);

CREATE INDEX IF NOT EXISTS idx_adapter_health_site_recent
    ON adapter_health (site_id, adapter_name, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_adapter_health_type_time
    ON adapter_health (site_id, adapter_type, timestamp DESC);

-- Aggregate current health state (upserted by monitor, queried by API)
CREATE TABLE IF NOT EXISTS adapter_health_current (
    site_id TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    adapter_type TEXT NOT NULL,
    is_healthy BOOLEAN,
    last_check TIMESTAMPTZ,
    consecutive_failures INT DEFAULT 0,
    uptime_1h_percent FLOAT,
    uptime_24h_percent FLOAT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (site_id, adapter_name)
);

-- Alert history for adapter failures/recoveries
CREATE TABLE IF NOT EXISTS adapter_health_alerts (
    id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    alert_type TEXT NOT NULL,                   -- 'failure', 'recovery'
    severity TEXT NOT NULL,                     -- 'warning', 'critical'
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT
);

-- Only one unacknowledged failure alert per adapter at a time (prevents alert storms)
-- Uses partial unique index instead of constraint (PostgreSQL requires index for WHERE clause)
DROP INDEX IF EXISTS idx_adapter_health_alerts_unique_failure;
CREATE UNIQUE INDEX idx_adapter_health_alerts_unique_failure
    ON adapter_health_alerts (site_id, adapter_name, created_at)
    WHERE alert_type = 'failure';

CREATE INDEX IF NOT EXISTS idx_adapter_health_alerts_unacked
    ON adapter_health_alerts (site_id, acknowledged_at)
    WHERE acknowledged_at IS NULL;
