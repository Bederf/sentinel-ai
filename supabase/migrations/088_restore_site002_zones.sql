-- =====================================================
-- Migration 088: Restore Site-002 Zones (Data Recovery)
-- Restores 15 zones for Sandton City Office Tower
-- Fixes lost zone information in Supabase
-- =====================================================

DO $$
DECLARE
    v_building_id UUID;
BEGIN
    -- Look up building UUID for Sandton (site-002)
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';

    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping zones restoration';
        RETURN;
    END IF;

    -- DELETE OLD/INCOMPLETE ZONES
    DELETE FROM zones WHERE building_id = v_building_id;

    -- =========================================================================
    -- LEVEL 0 ZONES (001-005) - 20 desks each
    -- =========================================================================

    INSERT INTO zones (zone_id, zone_name, building_id, floor, zone_letter, zone_type, typical_occupancy)
    VALUES
        ('Zone-001', 'Level 0 Zone A', v_building_id, 'L0', 'A', 'open_office', 20),
        ('Zone-002', 'Level 0 Zone B', v_building_id, 'L0', 'B', 'open_office', 20),
        ('Zone-003', 'Level 0 Zone C', v_building_id, 'L0', 'C', 'open_office', 20),
        ('Zone-004', 'Level 0 Zone D', v_building_id, 'L0', 'D', 'open_office', 20),
        ('Zone-005', 'Level 0 Zone E', v_building_id, 'L0', 'E', 'open_office', 20)
    ON CONFLICT (building_id, zone_id) DO NOTHING;

    -- =========================================================================
    -- LEVEL 1 ZONES (101-105) - 20 desks each
    -- =========================================================================

    INSERT INTO zones (zone_id, zone_name, building_id, floor, zone_letter, zone_type, typical_occupancy)
    VALUES
        ('Zone-101', 'Level 1 Zone A', v_building_id, 'L1', 'A', 'open_office', 20),
        ('Zone-102', 'Level 1 Zone B', v_building_id, 'L1', 'B', 'open_office', 20),
        ('Zone-103', 'Level 1 Zone C', v_building_id, 'L1', 'C', 'open_office', 20),
        ('Zone-104', 'Level 1 Zone D', v_building_id, 'L1', 'D', 'open_office', 20),
        ('Zone-105', 'Level 1 Zone E', v_building_id, 'L1', 'E', 'open_office', 20)
    ON CONFLICT (building_id, zone_id) DO NOTHING;

    -- =========================================================================
    -- LEVEL 2 ZONES (201-205) - 20 desks each
    -- =========================================================================

    INSERT INTO zones (zone_id, zone_name, building_id, floor, zone_letter, zone_type, typical_occupancy)
    VALUES
        ('Zone-201', 'Level 2 Zone A', v_building_id, 'L2', 'A', 'open_office', 20),
        ('Zone-202', 'Level 2 Zone B', v_building_id, 'L2', 'B', 'open_office', 20),
        ('Zone-203', 'Level 2 Zone C', v_building_id, 'L2', 'C', 'open_office', 20),
        ('Zone-204', 'Level 2 Zone D', v_building_id, 'L2', 'D', 'open_office', 20),
        ('Zone-205', 'Level 2 Zone E', v_building_id, 'L2', 'E', 'open_office', 20)
    ON CONFLICT (building_id, zone_id) DO NOTHING;

    RAISE NOTICE 'Site-002 zones restored:';
    RAISE NOTICE '  - Level 0 (L0): 5 zones (001-005)';
    RAISE NOTICE '  - Level 1 (L1): 5 zones (101-105)';
    RAISE NOTICE '  - Level 2 (L2): 5 zones (201-205)';
    RAISE NOTICE '  - Total: 15 zones, 300 desks capacity';

END $$;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify zones were created
SELECT COUNT(*) as zone_count FROM zones WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002');

-- List all zones
SELECT zone_id, floor, zone_letter, typical_occupancy
FROM zones
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
ORDER BY zone_id;
