-- =====================================================
-- Migration 091: User Module Access + Access Requests
-- Per-user module grants on top of site-level module activation
-- =====================================================

-- Public access requests (submitted from frontend before login)
CREATE TABLE IF NOT EXISTS access_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_email TEXT NOT NULL,
    full_name TEXT,
    company TEXT,
    phone TEXT,
    site_code TEXT NOT NULL REFERENCES buildings(code) ON DELETE CASCADE,
    requested_modules TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    request_notes TEXT,
    review_notes TEXT,
    granted_modules TEXT[],
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_access_requests_email ON access_requests (LOWER(user_email));
CREATE INDEX IF NOT EXISTS idx_access_requests_status ON access_requests (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_requests_site_code ON access_requests (site_code);

-- Prevent duplicate pending requests per user/site
CREATE UNIQUE INDEX IF NOT EXISTS idx_access_requests_pending_unique
ON access_requests (LOWER(user_email), site_code)
WHERE status = 'pending';

DROP TRIGGER IF EXISTS trigger_access_requests_updated_at ON access_requests;
CREATE TRIGGER trigger_access_requests_updated_at
    BEFORE UPDATE ON access_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Approved per-user module grants per site
CREATE TABLE IF NOT EXISTS user_module_access (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_email TEXT NOT NULL,
    site_code TEXT NOT NULL REFERENCES buildings(code) ON DELETE CASCADE,
    module_type TEXT NOT NULL,
    granted_by TEXT,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT,
    UNIQUE (user_email, site_code, module_type)
);

CREATE INDEX IF NOT EXISTS idx_user_module_access_email_site
ON user_module_access (LOWER(user_email), site_code);

CREATE INDEX IF NOT EXISTS idx_user_module_access_site_module
ON user_module_access (site_code, module_type);

