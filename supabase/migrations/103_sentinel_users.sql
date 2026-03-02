-- Migration: sentinel_users table
-- Phase: Replace Demo Auth with Supabase-Backed User Management
-- Description: Stores registered SENTINEL users with roles for authentication

CREATE TABLE IF NOT EXISTS sentinel_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'auditor'
        CHECK (role IN ('admin', 'operator', 'developer', 'auditor')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sentinel_users_email ON sentinel_users (email);

-- Seed default users
INSERT INTO sentinel_users (email, full_name, role) VALUES
    ('admin@sentinel.bms', 'SENTINEL Administrator', 'admin'),
    ('operator@sentinel.bms', 'BMS Operator', 'operator'),
    ('dev@sentinel.bms', 'Developer', 'developer'),
    ('auditor@sentinel.bms', 'Compliance Auditor', 'auditor'),
    ('grant@grantdemo.co.za', 'Grant - Demo', 'operator'),
    ('bederf@protonmail.com', 'Bederf - Solar Demo', 'operator'),
    ('bederf@gmail.com', 'Bederf Admin', 'admin')
ON CONFLICT (email) DO NOTHING;
