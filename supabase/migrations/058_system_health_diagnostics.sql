-- Phase 1: System Health & Diagnostics Schema
-- Tables for historical health snapshots, error logs, and diagnostic results

-- System health snapshots (5-minute intervals, 90-day retention)
-- Stores point-in-time snapshots of overall system health for trend analysis
CREATE TABLE IF NOT EXISTS system_health_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    overall_status TEXT NOT NULL CHECK (overall_status IN ('healthy', 'degraded', 'critical')),
    overall_score INTEGER NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
    component_scores JSONB NOT NULL,  -- { bms_connectivity: 85, api_health: 92, ... }
    details JSONB NOT NULL,            -- Component-level detail
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_health_snapshots_timestamp ON system_health_snapshots(timestamp DESC);
CREATE INDEX idx_health_snapshots_overall_status ON system_health_snapshots(overall_status);

COMMENT ON TABLE system_health_snapshots IS 'Historical system health snapshots stored every 5 minutes for trend analysis and historical reporting';
COMMENT ON COLUMN system_health_snapshots.timestamp IS 'Snapshot timestamp (collection time)';
COMMENT ON COLUMN system_health_snapshots.overall_status IS 'Overall system health status: healthy (score >=80), degraded (60-79), critical (<40)';
COMMENT ON COLUMN system_health_snapshots.overall_score IS 'Weighted overall health score 0-100';
COMMENT ON COLUMN system_health_snapshots.component_scores IS 'Individual component scores with weighted percentages';
COMMENT ON COLUMN system_health_snapshots.details IS 'Detailed information per component';


-- System error logs (integration errors, service failures)
-- Tracks all system-level errors with resolution workflow
CREATE TABLE IF NOT EXISTS system_error_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category TEXT NOT NULL CHECK (category IN ('bms', 'api', 'database', 'service', 'other')),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'error', 'critical')),
    component TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_error_logs_timestamp ON system_error_logs(timestamp DESC);
CREATE INDEX idx_error_logs_resolved ON system_error_logs(resolved);
CREATE INDEX idx_error_logs_category ON system_error_logs(category);
CREATE INDEX idx_error_logs_severity ON system_error_logs(severity);
CREATE INDEX idx_error_logs_component ON system_error_logs(component);

COMMENT ON TABLE system_error_logs IS 'Integration errors and service failures with resolution tracking for audit trail';
COMMENT ON COLUMN system_error_logs.category IS 'Error category: bms (connectivity), api (endpoint failure), database (query/connection), service (background task)';
COMMENT ON COLUMN system_error_logs.severity IS 'Error severity: warning (non-blocking), error (degraded operation), critical (service down)';
COMMENT ON COLUMN system_error_logs.component IS 'Component that generated error (e.g., niagara, database, device_manager)';
COMMENT ON COLUMN system_error_logs.resolved IS 'Whether error has been resolved';


-- System diagnostics (SIMBIOT diagnostic results cache)
-- Caches diagnostic results from SIMBIOT MCP server for polling
CREATE TABLE IF NOT EXISTS system_diagnostics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnostic_id TEXT UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    target TEXT NOT NULL,  -- 'full_system', 'building:{code}', 'component:{name}'
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    duration_seconds INTEGER,
    results JSONB,  -- Detailed results from all diagnostic tools
    recommendations TEXT[],
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_diagnostics_diagnostic_id ON system_diagnostics(diagnostic_id);
CREATE INDEX idx_diagnostics_timestamp ON system_diagnostics(timestamp DESC);
CREATE INDEX idx_diagnostics_status ON system_diagnostics(status);

COMMENT ON TABLE system_diagnostics IS 'SIMBIOT diagnostic results cache for async polling workflow';
COMMENT ON COLUMN system_diagnostics.diagnostic_id IS 'Unique diagnostic request ID (returned to client)';
COMMENT ON COLUMN system_diagnostics.target IS 'Diagnostic scope: full_system, building:code, or component:name';
COMMENT ON COLUMN system_diagnostics.status IS 'Diagnostic execution status: pending -> running -> completed/failed';
COMMENT ON COLUMN system_diagnostics.results IS 'Results from each diagnostic tool (device_inventory, alarms, health_scores, etc.)';
COMMENT ON COLUMN system_diagnostics.recommendations IS 'Array of actionable recommendations from diagnostics';


-- Auto-cleanup function for old health snapshots (90-day retention)
CREATE OR REPLACE FUNCTION cleanup_old_health_snapshots()
RETURNS void AS $$
BEGIN
    DELETE FROM system_health_snapshots
    WHERE timestamp < NOW() - INTERVAL '90 days';
    
    -- Also cleanup old error logs (keep 180 days)
    DELETE FROM system_error_logs
    WHERE created_at < NOW() - INTERVAL '180 days' AND resolved = TRUE;
    
    -- Cleanup old diagnostics (keep 30 days)
    DELETE FROM system_diagnostics
    WHERE created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_health_snapshots() IS 'Scheduled cleanup to maintain data retention policies: 90 days for snapshots, 180 days for resolved errors, 30 days for diagnostics';
