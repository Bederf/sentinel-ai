-- =====================================================
-- Migration 092: Seed User Module Access for Demo Users
-- Grants specific paid add-on modules to demo users on site-002
-- =====================================================
--
-- Access model:
--   bederf@gmail.com    → admin role → sees ALL modules (no grants needed)
--   grant@wardew.co.za  → operator   → base + control + lighting
--   bederf@protonmail.com → operator → base + control + solar
--
-- Base modules (hvac, energy, ml, notifications, integrations) are
-- automatically included for all authenticated users via BASE_MODULES
-- in module_access_repository.py — no grants needed for those.
--
-- Only PAID ADD-ON modules need explicit grants here.
-- =====================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM buildings WHERE code = 'site-002') THEN
        -- Clear any existing grants for these users on site-002 to avoid conflicts
        DELETE FROM user_module_access
        WHERE site_code = 'site-002'
          AND user_email IN ('grant@wardew.co.za', 'bederf@protonmail.com');

        -- Grant: grant@wardew.co.za on site-002
        -- Paid add-ons: control + lighting (occupancy)
        INSERT INTO user_module_access (user_email, site_code, module_type, granted_by, notes)
        VALUES
          ('grant@wardew.co.za', 'site-002', 'control', 'bederf@gmail.com', 'Wardew demo: building controls for lighting automation'),
          ('grant@wardew.co.za', 'site-002', 'lighting', 'bederf@gmail.com', 'Wardew demo: DALI lighting & occupancy module')
        ON CONFLICT (user_email, site_code, module_type) DO NOTHING;

        -- Grant: bederf@protonmail.com on site-002
        -- Paid add-ons: control + solar
        INSERT INTO user_module_access (user_email, site_code, module_type, granted_by, notes)
        VALUES
          ('bederf@protonmail.com', 'site-002', 'control', 'bederf@gmail.com', 'Bederf demo: building controls for solar/BESS management'),
          ('bederf@protonmail.com', 'site-002', 'solar', 'bederf@gmail.com', 'Bederf demo: Solar PV & Battery Energy Storage module')
        ON CONFLICT (user_email, site_code, module_type) DO NOTHING;

        -- Grant: ntaote.moshoeshoe@fnb.co.za on site-002
        -- Paid add-ons: control + lighting + solar
        INSERT INTO user_module_access (user_email, site_code, module_type, granted_by, notes)
        VALUES
          ('ntaote.moshoeshoe@fnb.co.za', 'site-002', 'control', 'bederf@gmail.com', 'FNB demo: building controls'),
          ('ntaote.moshoeshoe@fnb.co.za', 'site-002', 'lighting', 'bederf@gmail.com', 'FNB demo: DALI lighting & occupancy'),
          ('ntaote.moshoeshoe@fnb.co.za', 'site-002', 'solar', 'bederf@gmail.com', 'FNB demo: Solar PV & BESS')
        ON CONFLICT (user_email, site_code, module_type) DO NOTHING;
    ELSE
        RAISE NOTICE 'Building site-002 not found, skipping demo user module access seeding';
    END IF;
END $$;
