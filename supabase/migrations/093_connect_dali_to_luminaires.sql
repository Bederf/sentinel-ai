-- =====================================================
-- Migration 093: Connect DALI Controllers to Luminaires
-- Sandton City Office Tower (site-002)
-- Creates actual lighting fixtures controlled by DALI
-- Each zone: 1 DALI controller + 20 luminaire fixtures
-- =====================================================

DO $$
DECLARE
    v_building_id UUID;
    v_zone_num INTEGER;
    v_lum_num INTEGER;
BEGIN
    -- Look up building UUID for Sandton (site-002)
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';
    
    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping DALI-luminaire linking';
        RETURN;
    END IF;

    -- =========================================================================
    -- CREATE LUMINAIRE FIXTURES FOR EACH OFFICE ZONE
    -- Level 0: Zones 001-005 (100 luminaires = 20 per zone)
    -- Level 1: Zones 100-105 (120 luminaires = 20 per zone)
    -- Level 2: Zones 200-205 (120 luminaires = 20 per zone)
    -- =========================================================================
    
    -- LEVEL 0 LUMINAIRES (Zones 001-005)
    INSERT INTO equipment 
        (code, building_id, name, type, status, health_score, commissioning_date, device_info)
    SELECT
        'S002-LUM-' || LPAD(zone_num::TEXT, 3, '0') || '-' || LPAD(lum_seq::TEXT, 2, '0') as code,
        v_building_id,
        'Level 0 Zone ' || CHR(64 + zone_num) || ' Luminaire ' || lum_seq as name,
        'luminaire' as type,
        'normal' as status,
        92 as health_score,
        '2016-05-10'::DATE as commissioning_date,
        jsonb_build_object(
            'dali_controller', 'S002-DALI-' || LPAD(zone_num::TEXT, 3, '0'),
            'zone', 'Zone-' || LPAD(zone_num::TEXT, 3, '0'),
            'address', lum_seq::TEXT
        ) as device_info
    FROM GENERATE_SERIES(1, 5) as z(zone_num),
         GENERATE_SERIES(1, 20) as l(lum_seq)
    ON CONFLICT (code) DO NOTHING;

    -- LEVEL 1 LUMINAIRES (Zones 100-105)
    INSERT INTO equipment 
        (code, building_id, name, type, status, health_score, commissioning_date, device_info)
    SELECT
        'S002-LUM-' || LPAD((100 + zone_num - 1)::TEXT, 3, '0') || '-' || LPAD(lum_seq::TEXT, 2, '0') as code,
        v_building_id,
        'Level 1 Zone ' || CHR(64 + zone_num) || ' Luminaire ' || lum_seq as name,
        'luminaire' as type,
        'normal' as status,
        91 as health_score,
        '2016-05-10'::DATE as commissioning_date,
        jsonb_build_object(
            'dali_controller', 'S002-DALI-' || LPAD((100 + zone_num - 1)::TEXT, 3, '0'),
            'zone', 'Zone-' || LPAD((100 + zone_num - 1)::TEXT, 3, '0'),
            'address', lum_seq::TEXT
        ) as device_info
    FROM GENERATE_SERIES(1, 6) as z(zone_num),
         GENERATE_SERIES(1, 20) as l(lum_seq)
    ON CONFLICT (code) DO NOTHING;

    -- LEVEL 2 LUMINAIRES (Zones 200-205)
    INSERT INTO equipment 
        (code, building_id, name, type, status, health_score, commissioning_date, device_info)
    SELECT
        'S002-LUM-' || LPAD((200 + zone_num - 1)::TEXT, 3, '0') || '-' || LPAD(lum_seq::TEXT, 2, '0') as code,
        v_building_id,
        'Level 2 Zone ' || CHR(64 + zone_num) || ' Luminaire ' || lum_seq as name,
        'luminaire' as type,
        'normal' as status,
        93 as health_score,
        '2016-05-10'::DATE as commissioning_date,
        jsonb_build_object(
            'dali_controller', 'S002-DALI-' || LPAD((200 + zone_num - 1)::TEXT, 3, '0'),
            'zone', 'Zone-' || LPAD((200 + zone_num - 1)::TEXT, 3, '0'),
            'address', lum_seq::TEXT
        ) as device_info
    FROM GENERATE_SERIES(1, 6) as z(zone_num),
         GENERATE_SERIES(1, 20) as l(lum_seq)
    ON CONFLICT (code) DO NOTHING;

    RAISE NOTICE 'DALI-to-Luminaire connections created:';
    RAISE NOTICE '  - Level 0: 5 zones × 20 luminaires = 100 fixtures';
    RAISE NOTICE '  - Level 1: 6 zones × 20 luminaires = 120 fixtures';
    RAISE NOTICE '  - Level 2: 6 zones × 20 luminaires = 120 fixtures';
    RAISE NOTICE '  ──────────────────────────────────────────────';
    RAISE NOTICE '  - TOTAL: 340 luminaire fixtures';
    RAISE NOTICE '';
    RAISE NOTICE 'Each luminaire is linked to its DALI controller via device_info:';
    RAISE NOTICE '  Format: {"dali_controller": "S002-DALI-ZZZ", "zone": "Zone-ZZZ", "address": "N"}';
    RAISE NOTICE '  Example: S002-LUM-102-01 controlled by S002-DALI-102';

END $$;

-- =====================================================
-- VERIFICATION: DALI-LUMINAIRE CONNECTIONS
-- =====================================================

-- Count luminaires per DALI zone
SELECT 
    (e.device_info->>'dali_controller') as controller,
    COUNT(*) as luminaire_count,
    MIN(e.code) as first_luminaire,
    MAX(e.code) as last_luminaire
FROM equipment e
WHERE e.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND e.type = 'luminaire'
GROUP BY e.device_info->>'dali_controller'
ORDER BY e.device_info->>'dali_controller';

-- Verify connectivity example: Zone-102
SELECT
    'DALI Controller' as device_role,
    code,
    type,
    name,
    health_score
FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND code = 'S002-DALI-102'

UNION ALL

SELECT
    'Luminaire (' || ROW_NUMBER() OVER (ORDER BY code) || '/' || 
    (SELECT COUNT(*) FROM equipment WHERE device_info->>'dali_controller' = 'S002-DALI-102' 
     AND building_id = (SELECT id FROM buildings WHERE code = 'site-002')) || ')',
    code,
    type,
    SUBSTRING(name FROM 1, 40) as name,
    health_score
FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND device_info->>'dali_controller' = 'S002-DALI-102'
ORDER BY code
LIMIT 5;

-- Summary statistics
SELECT 
    'DALI Lighting Infrastructure' as description,
    (SELECT COUNT(*) FROM equipment WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002') AND type = 'dali_luminaire' OR type = 'DALI') as dali_controllers,
    (SELECT COUNT(*) FROM equipment WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002') AND type = 'luminaire') as luminaire_fixtures,
    (SELECT COUNT(*) FROM equipment WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002') AND type = 'luminaire') / 
    NULLIF((SELECT COUNT(*) FROM equipment WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002') AND (type = 'dali_luminaire' OR type = 'DALI')), 0) as avg_luminaires_per_controller;
