-- =====================================================
-- Migration 210: Provision bederf@gmail.com + remove seeds
-- =====================================================

-- Grant bederf@gmail.com access to all sites
INSERT INTO user_site_access (user_email, site_id, granted_by)
SELECT 'bederf@gmail.com', id, 'system'
FROM sites
ON CONFLICT (user_email, site_id) DO NOTHING;

-- Remove seed users
DELETE FROM user_site_access
WHERE user_email IN (
    'admin@sentinel.bms',
    'operator@sentinel.bms',
    'dev@sentinel.bms',
    'auditor@sentinel.bms',
    'ntaote.moshoeshoe@fnb.co.za'
);
