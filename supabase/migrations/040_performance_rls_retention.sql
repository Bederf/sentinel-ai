-- Migration 040: RLS Policies, Data Retention, and View Optimization
-- Generated: 2026-02-05
-- Purpose: Security hardening, automatic data cleanup, and query optimization

-- ==============================================================================
-- PART 1: ROW LEVEL SECURITY (RLS) FOR SENSITIVE TABLES
-- ==============================================================================

-- Enable RLS on audit_log
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Audit log: Users can see their own actions, admins see all
CREATE POLICY audit_log_select_own ON audit_log
    FOR SELECT
    USING (
        auth.role() = 'service_role'
        OR auth.jwt() ->> 'role' = 'ADMIN'
        OR user_id = auth.uid()::text
        OR user_name = auth.jwt() ->> 'email'
    );

-- Audit log: Only service role can insert (backend writes)
CREATE POLICY audit_log_insert_service ON audit_log
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

-- Enable RLS on login_audit
ALTER TABLE login_audit ENABLE ROW LEVEL SECURITY;

-- Login audit: Users see their own logins, admins see all
CREATE POLICY login_audit_select_own ON login_audit
    FOR SELECT
    USING (
        auth.role() = 'service_role'
        OR auth.jwt() ->> 'role' = 'ADMIN'
        OR user_email = auth.jwt() ->> 'email'
    );

-- Login audit: Only service role can insert
CREATE POLICY login_audit_insert_service ON login_audit
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

-- Enable RLS on mfa_secrets (highly sensitive)
ALTER TABLE mfa_secrets ENABLE ROW LEVEL SECURITY;

-- MFA secrets: Users can only access their own
CREATE POLICY mfa_secrets_select_own ON mfa_secrets
    FOR SELECT
    USING (
        auth.role() = 'service_role'
        OR user_email = (auth.jwt()->>'email')
    );

-- MFA secrets: Users can update their own, service role can do all
CREATE POLICY mfa_secrets_update_own ON mfa_secrets
    FOR UPDATE
    USING (
        auth.role() = 'service_role'
        OR user_email = (auth.jwt()->>'email')
    );

-- MFA secrets: Only service role can insert/delete
CREATE POLICY mfa_secrets_insert_service ON mfa_secrets
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY mfa_secrets_delete_service ON mfa_secrets
    FOR DELETE
    USING (auth.role() = 'service_role');

-- ==============================================================================
-- PART 2: DATA RETENTION FUNCTIONS
-- ==============================================================================

-- Function: Cleanup old audit logs (keep 1 year by default)
CREATE OR REPLACE FUNCTION cleanup_old_audit_logs(days_to_keep INT DEFAULT 365)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM audit_log
    WHERE timestamp < NOW() - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Log the cleanup action
    INSERT INTO audit_log (action, user_name, metadata, timestamp)
    VALUES (
        'SYSTEM_CLEANUP',
        'system',
        jsonb_build_object(
            'table', 'audit_log',
            'rows_deleted', deleted_count,
            'days_retained', days_to_keep
        ),
        NOW()
    );

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Cleanup old sensor readings (keep 1 year by default)
CREATE OR REPLACE FUNCTION cleanup_old_sensor_readings(days_to_keep INT DEFAULT 365)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM sensor_readings
    WHERE time < NOW() - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Log the cleanup
    INSERT INTO audit_log (action, user_name, metadata, timestamp)
    VALUES (
        'SYSTEM_CLEANUP',
        'system',
        jsonb_build_object(
            'table', 'sensor_readings',
            'rows_deleted', deleted_count,
            'days_retained', days_to_keep
        ),
        NOW()
    );

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Cleanup old equipment sensor readings (keep 90 days by default)
CREATE OR REPLACE FUNCTION cleanup_old_equipment_sensor_readings(days_to_keep INT DEFAULT 90)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM equipment_sensor_readings
    WHERE recorded_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Cleanup old anomalies (keep resolved anomalies for 180 days)
CREATE OR REPLACE FUNCTION cleanup_old_anomalies(days_to_keep INT DEFAULT 180)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM anomalies
    WHERE status = 'resolved'
    AND updated_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Archive old alerts to separate table (optional - creates if not exists)
CREATE OR REPLACE FUNCTION archive_old_alerts(days_to_keep INT DEFAULT 365)
RETURNS INT AS $$
DECLARE
    archived_count INT;
BEGIN
    -- Create archive table if it doesn't exist
    CREATE TABLE IF NOT EXISTS alerts_archive (LIKE alerts INCLUDING ALL);

    -- Move old resolved alerts to archive
    WITH moved AS (
        DELETE FROM alerts
        WHERE status = 'resolved'
        AND updated_at < NOW() - (days_to_keep || ' days')::INTERVAL
        RETURNING *
    )
    INSERT INTO alerts_archive SELECT * FROM moved;

    GET DIAGNOSTICS archived_count = ROW_COUNT;

    RETURN archived_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==============================================================================
-- PART 3: OPTIMIZED MATERIALIZED VIEWS (Replace Cartesian Joins)
-- ==============================================================================

-- Drop and recreate v_dashboard_summary with optimized CTEs
DROP MATERIALIZED VIEW IF EXISTS v_dashboard_summary CASCADE;

CREATE MATERIALIZED VIEW v_dashboard_summary AS
WITH building_stats AS (
    SELECT COUNT(*) as total_buildings FROM buildings
),
equipment_stats AS (
    SELECT
        COUNT(*) as total_equipment,
        COUNT(*) FILTER (WHERE status = 'critical') as critical_equipment,
        COUNT(*) FILTER (WHERE status = 'warning') as warning_equipment,
        COUNT(*) FILTER (WHERE status = 'normal') as normal_equipment,
        COALESCE(AVG(health_score), 0) as avg_health_score
    FROM equipment
),
alert_stats AS (
    SELECT
        COUNT(*) FILTER (WHERE status = 'active') as active_alerts,
        COUNT(*) FILTER (WHERE status = 'active' AND severity = 'critical') as critical_alerts
    FROM alerts
    WHERE created_at >= NOW() - INTERVAL '30 days'
),
prediction_stats AS (
    SELECT COUNT(*) FILTER (WHERE status = 'active') as active_predictions
    FROM predictions
    WHERE created_at >= NOW() - INTERVAL '30 days'
),
work_order_stats AS (
    SELECT COUNT(*) as pending_work_orders
    FROM work_orders
    WHERE status IN ('scheduled', 'in_progress')
),
anomaly_stats AS (
    SELECT COUNT(*) as active_anomalies
    FROM anomalies
    WHERE status = 'active'
)
SELECT
    bs.total_buildings,
    es.total_equipment,
    es.critical_equipment,
    es.warning_equipment,
    es.normal_equipment,
    es.avg_health_score,
    COALESCE(als.active_alerts, 0) as active_alerts,
    COALESCE(als.critical_alerts, 0) as critical_alerts,
    COALESCE(ps.active_predictions, 0) as active_predictions,
    COALESCE(wos.pending_work_orders, 0) as pending_work_orders,
    COALESCE(ans.active_anomalies, 0) as active_anomalies
FROM building_stats bs, equipment_stats es, alert_stats als,
     prediction_stats ps, work_order_stats wos, anomaly_stats ans;

-- Recreate index
CREATE INDEX idx_dashboard_summary_building_count ON v_dashboard_summary(total_buildings);

-- Drop and recreate v_equipment_health with optimized subqueries
DROP MATERIALIZED VIEW IF EXISTS v_equipment_health CASCADE;

CREATE MATERIALIZED VIEW v_equipment_health AS
SELECT
    e.id,
    e.code,
    e.name,
    e.type,
    e.status,
    e.health_score,
    b.id as building_id,
    b.code as building_code,
    b.name as building_name,
    b.region,
    COALESCE(alert_counts.cnt, 0) as active_alerts,
    COALESCE(prediction_counts.cnt, 0) as active_predictions,
    COALESCE(anomaly_counts.cnt, 0) as active_anomalies,
    COALESCE(work_order_counts.cnt, 0) as pending_work_orders,
    CASE
        WHEN e.status = 'critical' OR COALESCE(critical_alert_counts.cnt, 0) > 0 THEN 'critical'
        WHEN e.status = 'warning' OR COALESCE(alert_counts.cnt, 0) > 0 THEN 'warning'
        ELSE 'normal'
    END as computed_status,
    e.updated_at
FROM equipment e
JOIN buildings b ON e.building_id = b.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt
    FROM alerts WHERE status = 'active'
    GROUP BY equipment_id
) alert_counts ON alert_counts.equipment_id = e.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt
    FROM alerts WHERE status = 'active' AND severity = 'critical'
    GROUP BY equipment_id
) critical_alert_counts ON critical_alert_counts.equipment_id = e.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt
    FROM predictions WHERE status = 'active'
    GROUP BY equipment_id
) prediction_counts ON prediction_counts.equipment_id = e.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt
    FROM anomalies WHERE status = 'active'
    GROUP BY equipment_id
) anomaly_counts ON anomaly_counts.equipment_id = e.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt
    FROM work_orders WHERE status IN ('scheduled', 'in_progress')
    GROUP BY equipment_id
) work_order_counts ON work_order_counts.equipment_id = e.id;

-- Recreate indexes on v_equipment_health
CREATE INDEX idx_equipment_health_building_id ON v_equipment_health(building_id);
CREATE INDEX idx_equipment_health_computed_status ON v_equipment_health(computed_status);
CREATE INDEX idx_equipment_health_type ON v_equipment_health(type);
CREATE INDEX idx_equipment_health_score ON v_equipment_health(health_score DESC);

-- ==============================================================================
-- PART 4: ATOMIC WORK ORDER CODE GENERATION (Fix Race Condition)
-- ==============================================================================

-- Create sequence for work order codes
CREATE SEQUENCE IF NOT EXISTS work_order_code_seq START 1;

-- Replace function with atomic version using advisory lock
CREATE OR REPLACE FUNCTION generate_work_order_code()
RETURNS TRIGGER AS $$
DECLARE
    v_year TEXT := EXTRACT(YEAR FROM CURRENT_DATE)::TEXT;
    v_seq_num INTEGER;
BEGIN
    -- Only generate code for new work orders without one
    IF NEW.code IS NOT NULL OR TG_OP != 'INSERT' THEN
        RETURN NEW;
    END IF;

    -- Advisory lock ensures atomicity across concurrent inserts
    PERFORM pg_advisory_xact_lock(hashtext('work_order_code_gen'));

    -- Get next sequence number for this year
    SELECT COALESCE(MAX(CAST(SPLIT_PART(code, '-', 3) AS INTEGER)), 0) + 1
    INTO v_seq_num
    FROM work_orders
    WHERE code LIKE 'WO-' || v_year || '-%';

    -- Generate code: WO-2026-0001
    NEW.code := 'WO-' || v_year || '-' || LPAD(v_seq_num::TEXT, 4, '0');

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- PART 5: TECHNICIAN LOOKUP FUNCTION (Single Query Instead of 2)
-- ==============================================================================

CREATE OR REPLACE FUNCTION get_technician_for_equipment_code(p_equipment_code TEXT)
RETURNS TABLE (
    technician_id UUID,
    technician_name TEXT,
    technician_email TEXT,
    technician_phone TEXT,
    technician_telegram_id TEXT,
    specialty TEXT,
    building_id UUID
) AS $$
DECLARE
    v_building_id UUID;
    v_specialty TEXT;
    v_type_segment TEXT;
BEGIN
    -- Get building_id for equipment
    SELECT e.building_id INTO v_building_id
    FROM equipment e
    WHERE e.code = p_equipment_code;

    IF v_building_id IS NULL THEN
        RETURN;
    END IF;

    -- Parse equipment type from code (second segment)
    v_type_segment := UPPER(SPLIT_PART(p_equipment_code, '-', 2));

    -- Map type to specialty
    v_specialty := CASE
        WHEN v_type_segment IN ('CHILLER', 'AHU', 'FCU', 'VAV', 'SPLIT', 'CT', 'CRAC', 'PUMP', 'ZONE') THEN 'hvac'
        WHEN v_type_segment IN ('DALI', 'LUM') THEN 'dali'
        WHEN v_type_segment IN ('GEN', 'TX', 'UPS', 'ATS', 'MSB', 'MTR', 'PFC', 'FDR', 'MV', 'DB') THEN 'electrical'
        WHEN v_type_segment = 'FIRE' THEN 'fire'
        WHEN v_type_segment IN ('ACC', 'CCTV') THEN 'security'
        ELSE 'general'
    END;

    -- Return technician with single query
    RETURN QUERY
    SELECT
        t.id,
        t.name,
        t.email,
        t.phone,
        t.telegram_id,
        st.specialty,
        st.building_id
    FROM site_technicians st
    JOIN technicians t ON st.technician_id = t.id
    WHERE st.building_id = v_building_id
    AND st.specialty = v_specialty
    AND st.is_primary = TRUE
    LIMIT 1;

    -- Fallback to general if no match
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            t.id,
            t.name,
            t.email,
            t.phone,
            t.telegram_id,
            st.specialty,
            st.building_id
        FROM site_technicians st
        JOIN technicians t ON st.technician_id = t.id
        WHERE st.building_id = v_building_id
        AND st.specialty = 'general'
        AND st.is_primary = TRUE
        LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;

-- ==============================================================================
-- PART 6: REFRESH MATERIALIZED VIEWS FUNCTION
-- ==============================================================================

CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_dashboard_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_equipment_health;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_building_status;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_active_alerts;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==============================================================================
-- PART 7: COMMENTS FOR DOCUMENTATION
-- ==============================================================================

COMMENT ON FUNCTION cleanup_old_audit_logs IS 'Cleanup audit logs older than N days (default 365). Called by pg_cron or manually.';
COMMENT ON FUNCTION cleanup_old_sensor_readings IS 'Cleanup sensor readings older than N days (default 365). Prevents unbounded growth.';
-- cleanup_old_login_logs not created in this migration; skipping comment
COMMENT ON FUNCTION get_technician_for_equipment_code IS 'Single-query technician lookup by equipment code. Maps equipment type to specialty.';
COMMENT ON FUNCTION refresh_all_materialized_views IS 'Refresh all dashboard materialized views. Schedule via pg_cron for nightly refresh.';

-- ==============================================================================
-- SCHEDULING NOTES (Requires pg_cron extension - run manually if not available)
-- ==============================================================================

-- To enable automatic cleanup, run these commands if pg_cron is available:
-- SELECT cron.schedule('cleanup_audit_logs', '0 2 * * 0', 'SELECT cleanup_old_audit_logs(365)');
-- SELECT cron.schedule('cleanup_sensor_readings', '0 3 * * 0', 'SELECT cleanup_old_sensor_readings(365)');
-- SELECT cron.schedule('cleanup_login_logs', '0 4 * * *', 'SELECT cleanup_old_login_logs(90)');
-- SELECT cron.schedule('refresh_views', '0 5 * * *', 'SELECT refresh_all_materialized_views()');
