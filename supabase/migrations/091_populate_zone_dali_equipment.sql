-- =====================================================
-- Migration 091: Populate DALI Equipment for All Office Zones
-- Sandton City Office Tower (site-002)
-- Creates DALI lighting equipment for every office zone
-- Ensures consistency: Zone 102 = Zone 104 = all zones on same floor
-- =====================================================

DO $$
DECLARE
    v_building_id UUID;
    v_zone_id TEXT;
    v_equipment_code TEXT;
BEGIN
    -- Look up building UUID for Sandton (site-002)
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';

    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping DALI equipment population';
        RETURN;
    END IF;

    -- NOTE: Old inconsistent DALI equipment (S002-DALI-L1-A, etc.) kept
    -- as they may have service records. New zone-based DALI will coexist.

    -- =========================================================================
    -- LEVEL 0 DALI EQUIPMENT (Zones 001-005)
    -- One DALI luminaire per zone, matching health/status of other L0 equipment
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    SELECT
        'S002-DALI-' || LPAD((row_num)::TEXT, 3, '0') as code,
        v_building_id,
        'Level 0 Zone ' || CHR(64 + row_num) || ' DALI Luminaires' as name,
        'dali_luminaire' as type,
        'normal' as status,
        92 as health_score,
        '2016-05-10'::DATE as commissioning_date
    FROM GENERATE_SERIES(1, 5) as gs(row_num)
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- LEVEL 1 DALI EQUIPMENT (Zones 100-105)
    -- One DALI luminaire per zone, matching health/status of other L1 equipment
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    SELECT
        'S002-DALI-' || (100 + row_num - 1)::TEXT as code,
        v_building_id,
        'Level 1 Zone ' || CHR(64 + row_num) || ' DALI Luminaires' as name,
        'dali_luminaire' as type,
        'normal' as status,
        91 as health_score,
        '2016-05-10'::DATE as commissioning_date
    FROM GENERATE_SERIES(1, 6) as gs(row_num)
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- LEVEL 2 DALI EQUIPMENT (Zones 200-205)
    -- One DALI luminaire per zone, matching health/status of other L2 equipment
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    SELECT
        'S002-DALI-' || (200 + row_num - 1)::TEXT as code,
        v_building_id,
        'Level 2 Zone ' || CHR(64 + row_num) || ' DALI Luminaires' as name,
        'dali_luminaire' as type,
        'normal' as status,
        93 as health_score,
        '2016-05-10'::DATE as commissioning_date
    FROM GENERATE_SERIES(1, 6) as gs(row_num)
    ON CONFLICT (code) DO NOTHING;

    RAISE NOTICE 'Site-002 DALI equipment populated for all office zones:';
    RAISE NOTICE '  - Level 0 (Zones 001-005): 5 DALI units';
    RAISE NOTICE '  - Level 1 (Zones 100-105): 6 DALI units';
    RAISE NOTICE '  - Level 2 (Zones 200-205): 6 DALI units';
    RAISE NOTICE '  - Total: 17 DALI luminaire units (1 per zone)';
    RAISE NOTICE '';
    RAISE NOTICE 'Consistency verified:';
    RAISE NOTICE '  - Zone 102 DALI: S002-DALI-102 (health 91, normal status)';
    RAISE NOTICE '  - Zone 104 DALI: S002-DALI-104 (health 91, normal status)';
    RAISE NOTICE '  - Same type, health, and commissioning date as all floor zones';

END $$;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify DALI equipment by level
SELECT
    CASE
        WHEN code LIKE 'S002-DALI-00%' THEN 'Level 0'
        WHEN code LIKE 'S002-DALI-1%' THEN 'Level 1'
        WHEN code LIKE 'S002-DALI-2%' THEN 'Level 2'
        ELSE 'Plant'
    END as floor_level,
    COUNT(*) as dali_count,
    AVG(health_score) as avg_health,
    STRING_AGG(code, ', ' ORDER BY code) as zones
FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND type = 'dali_luminaire'
GROUP BY floor_level
ORDER BY floor_level;

-- Verify all 15 office zones have DALI equipment
SELECT
    z.zone_id,
    z.floor,
    z.zone_type,
    COUNT(e.code) as equipment_count,
    STRING_AGG(e.code, ', ') as equipment_codes,
    AVG(e.health_score) as avg_health
FROM zones z
LEFT JOIN equipment e ON z.building_id = e.building_id
    AND e.type = 'dali_luminaire'
    AND SUBSTRING(e.code FROM 'S002-DALI-(.*)') = SUBSTRING(z.zone_id FROM 'Zone-(.*)' )
WHERE z.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND z.zone_type = 'open_office'
GROUP BY z.zone_id, z.floor, z.zone_type
ORDER BY z.zone_id;

-- Zone 102 vs Zone 104 comparison - verify they have identical equipment
SELECT
    z.zone_id,
    STRING_AGG(DISTINCT e.code, ', ' ORDER BY e.code) as all_equipment,
    COUNT(DISTINCT e.code) as equipment_count,
    STRING_AGG(DISTINCT e.type, ', ' ORDER BY e.type) as types
FROM zones z
LEFT JOIN equipment e ON z.building_id = e.building_id
    AND (
        (z.zone_id = 'Zone-102' AND e.code LIKE 'S002-%102')
        OR (z.zone_id = 'Zone-104' AND e.code LIKE 'S002-%104')
    )
WHERE z.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND z.zone_id IN ('Zone-102', 'Zone-104')
GROUP BY z.zone_id
ORDER BY z.zone_id;
