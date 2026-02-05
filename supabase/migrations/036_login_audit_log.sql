-- =====================================================
-- Migration 036: Login Audit Log
-- Track all user login events for security auditing
-- =====================================================

-- Login audit log table
CREATE TABLE IF NOT EXISTS login_audit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_email TEXT NOT NULL,
    user_id TEXT,
    user_role TEXT,
    source_ip TEXT,
    user_agent TEXT,
    login_at TIMESTAMPTZ DEFAULT NOW(),
    is_new_user BOOLEAN DEFAULT FALSE,
    success BOOLEAN DEFAULT TRUE,
    failure_reason TEXT
);

-- Indexes for efficient queries
CREATE INDEX idx_login_audit_email ON login_audit(user_email);
CREATE INDEX idx_login_audit_time ON login_audit(login_at DESC);
CREATE INDEX idx_login_audit_ip ON login_audit(source_ip);

-- Cleanup old logs (keep 90 days by default)
-- Run manually or via cron: SELECT cleanup_old_login_logs(90);
CREATE OR REPLACE FUNCTION cleanup_old_login_logs(days_to_keep INT DEFAULT 90)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM login_audit
    WHERE login_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
