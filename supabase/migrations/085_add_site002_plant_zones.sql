-- =====================================================
-- Migration 090: Add Site-002 Plant/Infrastructure Zones
-- Sandton City Office Tower - Building Systems Areas
-- Adds B1 (Basement) and R (Roof) infrastructure zones
-- =====================================================

DO $$
DECLARE
    v_building_id UUID;
BEGIN
    -- Look up building UUID for Sandton (site-002)
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';

    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping plant zones';
        RETURN;
    END IF;

    -- =========================================================================
    -- BASEMENT INFRASTRUCTURE ZONE (B1)
    -- Located: Basement Level 1
    -- Equipment: Chillers, pumps, UPS, generators, main switchboards, DALI controller
    -- =========================================================================

    INSERT INTO zones (zone_id, zone_name, building_id, floor, zone_letter, zone_type, typical_occupancy)
    VALUES
        ('Zone-B1', 'Basement 1 - HVAC & Power Plant', v_building_id, 'B1', 'B1', 'mechanical', 2)
    ON CONFLICT (building_id, zone_id) DO NOTHING;

    -- =========================================================================
    -- ROOF INFRASTRUCTURE ZONE (R)
    -- Located: Rooftop
    -- Equipment: Air handling units, cooling tower, solar inverters, rooftop AHU
    -- =========================================================================

    INSERT INTO zones (zone_id, zone_name, building_id, floor, zone_letter, zone_type, typical_occupancy)
    VALUES
        ('Zone-R', 'Rooftop - Solar & Cooling', v_building_id, 'R', 'R', 'mechanical', 1)
    ON CONFLICT (building_id, zone_id) DO NOTHING;

    -- =========================================================================
    -- LEVEL 2 INFRASTRUCTURE ZONE (L2-Plant)
    -- Located: Level 2 plant/mechanical room
    -- Equipment: Secondary AHUs, zone controllers
    -- =========================================================================

    INSERT INTO zones (zone_id, zone_name, building_id, floor, zone_letter, zone_type, typical_occupancy)
    VALUES
        ('Zone-L2-Plant', 'Level 2 - Mechanical Room', v_building_id, 'L2', 'L2', 'mechanical', 2)
    ON CONFLICT (building_id, zone_id) DO NOTHING;

    RAISE NOTICE 'Site-002 plant infrastructure zones added:';
    RAISE NOTICE '  - Zone-B1: Basement 1 (chillers, pumps, generators, UPS, HVAC plant)';
    RAISE NOTICE '  - Zone-R: Rooftop (AHU, cooling tower, solar inverters)';
    RAISE NOTICE '  - Zone-L2-Plant: Level 2 mechanical room (secondary systems)';
    RAISE NOTICE '';
    RAISE NOTICE 'Complete Zone Structure for Site-002:';
    RAISE NOTICE '  OFFICE ZONES (serving desks): 001-005, 100-105, 200-205 (15 zones)';
    RAISE NOTICE '  PLANT ZONES (infrastructure): B1, R, L2-Plant (3 zones)';
    RAISE NOTICE '  Total: 18 zones';

END $$;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify all zone types
SELECT
    zone_id,
    zone_name,
    floor,
    zone_type,
    typical_occupancy
FROM zones
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
ORDER BY floor, zone_id;

-- Count zones by type
SELECT
    zone_type,
    COUNT(*) as zone_count
FROM zones
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
GROUP BY zone_type
ORDER BY zone_type;

-- Summary
SELECT
    'Total Zones for Site-002' as description,
    COUNT(*) as count
FROM zones
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002');
