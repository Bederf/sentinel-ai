-- Staff roster for Sentry Staff bot self-registration

CREATE TABLE IF NOT EXISTS staff_roster (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_number TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    desk TEXT NOT NULL,
    site_id TEXT NOT NULL DEFAULT 'site-002',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT staff_roster_site_staff_unique UNIQUE(site_id, staff_number)
);

CREATE INDEX IF NOT EXISTS idx_staff_roster_site_active
    ON staff_roster(site_id, active);

CREATE INDEX IF NOT EXISTS idx_staff_roster_phone
    ON staff_roster(phone);

COMMENT ON TABLE staff_roster IS 'Canonical staff roster used for Sentry Staff bot first-use registration';
COMMENT ON COLUMN staff_roster.staff_number IS 'Canonical HR/staff number, not a channel-specific ID';
COMMENT ON COLUMN staff_roster.desk IS 'Desk number/location context used for work order routing';
COMMENT ON COLUMN staff_roster.source IS 'Source of roster row: manual, csv_import, hr_connector, etc.';
