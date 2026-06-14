-- Phase 227: SENTRY-MULTISITE: Site-Scoped Bot Access
-- Create bot_users table for site-scoped access control

CREATE TABLE IF NOT EXISTS bot_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    site_id TEXT NOT NULL,
    bot_role TEXT NOT NULL,
    display_name TEXT,
    email TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by BIGINT,
    CONSTRAINT bot_users_role_chk CHECK (bot_role IN ('manager', 'technician', 'staff')),
    CONSTRAINT bot_users_unique UNIQUE(telegram_id, site_id, bot_role)
);

CREATE INDEX IF NOT EXISTS idx_bot_users_lookup
    ON bot_users(telegram_id, active);

CREATE INDEX IF NOT EXISTS idx_bot_users_site_role
    ON bot_users(site_id, bot_role, active);

COMMENT ON TABLE bot_users IS 'Site-scoped access control for Sentry bots (manager/technician/staff)';
COMMENT ON COLUMN bot_users.telegram_id IS 'Telegram user ID (BIGINT from TELEGRAM_USER_ID env)';
COMMENT ON COLUMN bot_users.site_id IS 'Normalized site ID, e.g. site-002';
COMMENT ON COLUMN bot_users.bot_role IS 'Bot role: manager, technician, or staff';
COMMENT ON COLUMN bot_users.active IS 'Soft delete flag — DELETE sets this FALSE, never hard delete';
COMMENT ON COLUMN bot_users.created_by IS 'Telegram ID of the manager who provisioned this user';
