-- Preserve the latest health-check failure reason in the current adapter snapshot.
-- The history table already stores error_message; this keeps dashboards/API
-- from needing to query history to explain an unhealthy current adapter.

ALTER TABLE adapter_health_current
    ADD COLUMN IF NOT EXISTS error_message text;
