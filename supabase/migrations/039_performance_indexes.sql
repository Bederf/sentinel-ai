-- Migration 039: Performance Optimization Indexes
-- Generated: 2026-02-05
-- Purpose: Add missing composite indexes identified through query pattern analysis

-- ==============================================================================
-- CRITICAL: Composite Indexes for Common Query Patterns
-- ==============================================================================

-- User site access covering index (building lookup by email)
CREATE INDEX IF NOT EXISTS idx_user_site_access_email_building
ON user_site_access(user_email, building_id);

-- Alert queries by equipment and status (frequently used in dashboards, resolution)
CREATE INDEX IF NOT EXISTS idx_alerts_equipment_status
ON alerts(equipment_id, status);

-- Alert queries by building and status (building health dashboard)
CREATE INDEX IF NOT EXISTS idx_alerts_building_status
ON alerts(building_id, status, severity);

-- Prediction queries by equipment and status
CREATE INDEX IF NOT EXISTS idx_predictions_equipment_status
ON predictions(equipment_id, status);

-- Anomaly queries by equipment and status
CREATE INDEX IF NOT EXISTS idx_anomalies_equipment_status
ON anomalies(equipment_id, status);

-- Work order queries by equipment and status
CREATE INDEX IF NOT EXISTS idx_work_orders_equipment_status
ON work_orders(equipment_id, status, priority DESC);

-- Work order queries by technician assignment
CREATE INDEX IF NOT EXISTS idx_work_orders_assigned_status
ON work_orders(assigned_to, status, scheduled_date DESC)
WHERE assigned_to IS NOT NULL;

-- Work order queries for scheduled/in-progress work
CREATE INDEX IF NOT EXISTS idx_work_orders_scheduled_active
ON work_orders(scheduled_date, status, priority)
WHERE status IN ('scheduled', 'in_progress');

-- ==============================================================================
-- HIGH: Audit Log Composite Indexes (Compliance & Debugging)
-- ==============================================================================

-- Correlation ID queries always need timestamp ordering
CREATE INDEX IF NOT EXISTS idx_audit_log_correlation_timestamp
ON audit_log(correlation_id, timestamp DESC);

-- Device action history queries
CREATE INDEX IF NOT EXISTS idx_audit_log_device_action_timestamp
ON audit_log(device_id, action, timestamp DESC)
WHERE device_id IS NOT NULL;

-- User activity timeline
CREATE INDEX IF NOT EXISTS idx_audit_log_user_timestamp
ON audit_log(user_id, timestamp DESC)
WHERE user_id IS NOT NULL;

-- ==============================================================================
-- HIGH: Login Audit Temporal Index
-- ==============================================================================

-- Time-range queries on login audit (security monitoring)
CREATE INDEX IF NOT EXISTS idx_login_audit_login_at
ON login_audit(login_at DESC);

-- Failed login monitoring by IP
CREATE INDEX IF NOT EXISTS idx_login_audit_ip_failed
ON login_audit(source_ip, login_at DESC)
WHERE success = FALSE;

-- User login history
CREATE INDEX IF NOT EXISTS idx_login_audit_user_time
ON login_audit(user_email, login_at DESC);

-- ==============================================================================
-- MEDIUM: Equipment and Baseline Indexes
-- ==============================================================================

-- Equipment by building and type (common filter)
CREATE INDEX IF NOT EXISTS idx_equipment_building_type
ON equipment(building_id, type);

-- Equipment by status (health dashboard)
CREATE INDEX IF NOT EXISTS idx_equipment_status_health
ON equipment(status, health_score DESC);

-- Baseline queries by equipment and status
CREATE INDEX IF NOT EXISTS idx_equipment_baselines_equipment_status
ON equipment_baselines(equipment_id, status);

-- ==============================================================================
-- MEDIUM: Sensor Readings Optimization
-- ==============================================================================

-- Recent readings partial index (most queries target last 7 days)
CREATE INDEX IF NOT EXISTS idx_equipment_sensor_readings_recent
ON equipment_sensor_readings(equipment_id, recorded_at DESC)
WHERE recorded_at > NOW() - INTERVAL '7 days';

-- Building sensor readings for dashboard aggregation
CREATE INDEX IF NOT EXISTS idx_equipment_sensor_readings_building_time
ON equipment_sensor_readings(building_id, recorded_at DESC);

-- ==============================================================================
-- LOW: Optimization Support Indexes
-- ==============================================================================

-- Site technicians by specialty (technician lookup)
CREATE INDEX IF NOT EXISTS idx_site_technicians_building_specialty
ON site_technicians(building_id, specialty, is_primary);

-- MFA lookup optimization
CREATE INDEX IF NOT EXISTS idx_mfa_secrets_user_enabled
ON mfa_secrets(user_id, is_enabled)
WHERE is_enabled = TRUE;

-- ==============================================================================
-- CLEANUP: Drop redundant indexes (if they exist)
-- These are subsets of other indexes, providing no additional benefit
-- ==============================================================================

-- Note: Only drop if confirmed redundant after analyzing pg_stat_user_indexes
-- DROP INDEX IF EXISTS idx_alerts_status;  -- Subset of idx_alerts_equipment_status
-- DROP INDEX IF EXISTS idx_work_orders_status;  -- Subset of idx_work_orders_equipment_status

-- ==============================================================================
-- DIAGNOSTIC: Query to verify index usage after deployment
-- Run this after some time to confirm indexes are being used:
-- ==============================================================================

-- SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
-- FROM pg_stat_user_indexes
-- WHERE indexname LIKE 'idx_%'
-- ORDER BY idx_scan DESC;

COMMENT ON INDEX idx_alerts_equipment_status IS 'Performance: Alert resolution and dashboard queries';
COMMENT ON INDEX idx_work_orders_equipment_status IS 'Performance: Work order lookups by equipment';
COMMENT ON INDEX idx_audit_log_correlation_timestamp IS 'Performance: Correlation trace debugging';
