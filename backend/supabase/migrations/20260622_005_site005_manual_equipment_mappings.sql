-- Reviewed S005 manual mappings for catalog-backed non-HVAC equipment.
--
-- This maps rows where the bridge/catalog report provides enough identity and
-- location evidence, including the reviewed S005 AHU, PV, UPS, aggregate, and
-- L3 FCU allocations.

DO $$
DECLARE
    v_site_id UUID;
    rec RECORD;
BEGIN
    SELECT id INTO v_site_id
    FROM public.sites
    WHERE code = 'site-005'
    LIMIT 1;

    IF v_site_id IS NULL THEN
        RAISE NOTICE 'site-005 not found; skipping manual equipment mappings';
        RETURN;
    END IF;

    CREATE TEMP TABLE tmp_site005_room_zones (
        zone_id TEXT PRIMARY KEY,
        zone_name TEXT NOT NULL,
        floor TEXT NOT NULL,
        zone_letter TEXT NOT NULL,
        zone_type TEXT NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO tmp_site005_room_zones (zone_id, zone_name, floor, zone_letter, zone_type)
    VALUES
        ('Zone-B1-LIFT-MOTOR', 'Lift Motor Room', 'B1', 'LIFT-MOTOR', 'plant_room'),
        ('Zone-B1-BMS-ROOM', 'BMS Panel Room', 'B1', 'BMS-ROOM', 'plant_room'),
        ('Zone-G-FIRE-CONTROL', 'Fire Control Room', 'G', 'FIRE-CONTROL', 'comms_room'),
        ('Zone-G-SECURITY-CONTROL', 'Security Control Room', 'G', 'SECURITY-CONTROL', 'comms_room'),
        ('Zone-L3-ELEC-RISER', 'L3 Electrical Riser - Distribution Board Room', 'L3', 'ELEC-RISER', 'electrical'),
        ('Zone-B1-PLANT-EAST', 'Basement B1 Plant Room East', 'B1', 'PLANT-EAST', 'plant_room'),
        ('Zone-R-PV-NORTH', 'Rooftop - North Wing', 'R', 'PV-NORTH', 'mechanical'),
        ('Zone-R-PV-SOUTH', 'Rooftop - South Wing', 'R', 'PV-SOUTH', 'mechanical'),
        ('Zone-R-PV-PLANT-NORTH', 'Rooftop Plant Room - North Wing', 'R', 'PV-PLANT-NORTH', 'plant_room'),
        ('Zone-R-PV-PLANT-SOUTH', 'Rooftop Plant Room - South Wing', 'R', 'PV-PLANT-SOUTH', 'plant_room'),
        ('Zone-L3-UPS-ROOM', 'L3 Server Room / UPS Room', 'L3', 'UPS-ROOM', 'server_room'),
        ('Zone-L3-MECH-PLANT', 'L3 Mechanical Plant Room', 'L3', 'MECH-PLANT', 'plant_room'),
        ('Zone-B1-MAIN-PLANT', 'Main Plant Room', 'B1', 'MAIN-PLANT', 'plant_room'),
        ('Zone-L3-GENERAL-WARD', 'L3 General Ward Zone', 'L3', 'GENERAL-WARD', 'clinical'),
        ('Zone-L3-HDU', 'High Dependency Unit', 'L3', 'HDU', 'clinical'),
        ('Zone-L3-POSTOP', 'Post-Operative Recovery', 'L3', 'POSTOP', 'clinical'),
        ('Zone-L3-ANAES', 'Anaesthesia Prep', 'L3', 'ANAES', 'clinical'),
        ('Zone-L3-SCRUB', 'Scrub Room / Sterile Corridor', 'L3', 'SCRUB', 'clinical'),
        ('Zone-L3-STERILE', 'Sterile Supply', 'L3', 'STERILE', 'clinical'),
        ('Zone-L3-WARD-E', 'Ward East', 'L3', 'WARD-E', 'clinical'),
        ('Zone-L3-WARD-W', 'Ward West', 'L3', 'WARD-W', 'clinical'),
        ('Zone-L3-NS-E', 'Nurses Station East', 'L3', 'NS-E', 'clinical'),
        ('Zone-L3-NS-W', 'Nurses Station West', 'L3', 'NS-W', 'clinical'),
        ('Zone-L3-CORR-N', 'Corridor North', 'L3', 'CORR-N', 'corridor'),
        ('Zone-L3-CORR-S', 'Corridor South', 'L3', 'CORR-S', 'corridor'),
        ('Zone-L3-WAIT', 'Family Waiting', 'L3', 'WAIT', 'hospital_zone'),
        ('Zone-L3-STAFF', 'Staff Lounge', 'L3', 'STAFF', 'hospital_zone'),
        ('Zone-G-ER-ENTRANCE', 'Main ER Entrance', 'G', 'ER-ENTRANCE', 'corridor'),
        ('Zone-L1-PHARMACY', 'Pharmacy Controlled Area', 'L1', 'PHARMACY', 'hospital_zone'),
        ('Zone-G-STAFF-A', 'Staff Entrance A', 'G', 'STAFF-A', 'corridor'),
        ('Zone-B1-STAFF-B', 'Staff Entrance B', 'B1', 'STAFF-B', 'corridor'),
        ('Zone-G-PARKING-GATE', 'Staff Parking Entrance', 'G', 'PARKING-GATE', 'corridor')
    ON CONFLICT (zone_id) DO NOTHING;

    FOR rec IN SELECT * FROM tmp_site005_room_zones LOOP
        INSERT INTO public.zones
            (site_id, zone_id, zone_name, floor, zone_letter, zone_type)
        VALUES
            (v_site_id, rec.zone_id, rec.zone_name, rec.floor, rec.zone_letter, rec.zone_type)
        ON CONFLICT (site_id, zone_id) DO UPDATE
        SET zone_name = EXCLUDED.zone_name,
            floor = EXCLUDED.floor,
            zone_letter = EXCLUDED.zone_letter,
            zone_type = EXCLUDED.zone_type,
            updated_at = NOW();
    END LOOP;

    CREATE TEMP TABLE tmp_site005_manual_equipment_map (
        code TEXT PRIMARY KEY,
        canonical_code TEXT NOT NULL,
        canonical_zone_id TEXT,
        equipment_type TEXT NOT NULL,
        location TEXT,
        status TEXT NOT NULL,
        alias_type TEXT NOT NULL,
        relationship_type TEXT,
        manufacturer TEXT,
        model TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    ) ON COMMIT DROP;

    INSERT INTO tmp_site005_manual_equipment_map
        (code, canonical_code, canonical_zone_id, equipment_type, location, status, alias_type, relationship_type, manufacturer, model, metadata)
    VALUES
        -- Lift point stubs: point rows monitor the reviewed lift motor-room assets.
        ('site-005-UMH-LIFT-001.current', 'S005-LIFT-B1-001', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700', '{"point_role":"current_floor"}'),
        ('site-005-UMH-LIFT-001.door', 'S005-LIFT-B1-001', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700', '{"point_role":"door_status"}'),
        ('site-005-UMH-LIFT-001.in', 'S005-LIFT-B1-001', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700', '{"point_role":"car_occupied_or_in_service"}'),
        ('site-005-UMH-LIFT-002.current', 'S005-LIFT-B1-002', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700', '{"point_role":"current_floor"}'),
        ('site-005-UMH-LIFT-002.door', 'S005-LIFT-B1-002', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700', '{"point_role":"door_status"}'),
        ('site-005-UMH-LIFT-002.in', 'S005-LIFT-B1-002', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700', '{"point_role":"car_occupied_or_in_service"}'),
        ('site-005-UMH-LIFT-003.current', 'S005-LIFT-B1-003', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Schindler', '5500', '{"point_role":"current_floor"}'),
        ('site-005-UMH-LIFT-003.door', 'S005-LIFT-B1-003', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Schindler', '5500', '{"point_role":"door_status"}'),
        ('site-005-UMH-LIFT-003.in', 'S005-LIFT-B1-003', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Schindler', '5500', '{"point_role":"car_occupied_or_in_service"}'),
        ('site-005-UMH-LIFT-004.current', 'S005-LIFT-B1-004', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700 Bed', '{"point_role":"current_floor"}'),
        ('site-005-UMH-LIFT-004.door', 'S005-LIFT-B1-004', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700 Bed', '{"point_role":"door_status"}'),
        ('site-005-UMH-LIFT-004.in', 'S005-LIFT-B1-004', 'Zone-B1-LIFT-MOTOR', 'lift', 'Lift Motor Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'KONE', 'MonoSpace 700 Bed', '{"point_role":"car_occupied_or_in_service"}'),

        -- BMS controllers.
        ('site-005-UMH-JACE-001.bacnet', 'S005-JACE-B1-001', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"bacnet_status"}'),
        ('site-005-UMH-JACE-001.comms', 'S005-JACE-B1-001', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"communications_status"}'),
        ('site-005-UMH-JACE-001.cpu', 'S005-JACE-B1-001', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"cpu_load"}'),
        ('site-005-UMH-JACE-001.memory', 'S005-JACE-B1-001', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"memory_usage"}'),
        ('site-005-UMH-JACE-001.uptime', 'S005-JACE-B1-001', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"uptime"}'),
        ('site-005-UMH-JACE-002.bacnet', 'S005-JACE-B1-002', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"bacnet_status"}'),
        ('site-005-UMH-JACE-002.comms', 'S005-JACE-B1-002', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"communications_status"}'),
        ('site-005-UMH-JACE-002.cpu', 'S005-JACE-B1-002', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"cpu_load"}'),
        ('site-005-UMH-JACE-002.memory', 'S005-JACE-B1-002', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"memory_usage"}'),
        ('site-005-UMH-JACE-002.uptime', 'S005-JACE-B1-002', 'Zone-B1-BMS-ROOM', 'bms_controller', 'BMS Panel Room - Basement B1', 'point_level_source', 'point_source', 'monitors', 'Tridium', 'JACE 8000', '{"point_role":"uptime"}'),

        -- Fire panel.
        ('site-005-UMH-FIRE-001.battery', 'S005-FIRE-G-001', 'Zone-G-FIRE-CONTROL', 'fire_panel', 'Fire Control Room - Ground Floor', 'point_level_source', 'point_source', 'monitors', 'Kidde', 'VS4', '{"point_role":"battery_status"}'),
        ('site-005-UMH-FIRE-001.mains', 'S005-FIRE-G-001', 'Zone-G-FIRE-CONTROL', 'fire_panel', 'Fire Control Room - Ground Floor', 'point_level_source', 'point_source', 'monitors', 'Kidde', 'VS4', '{"point_role":"mains_status"}'),
        ('site-005-UMH-FIRE-001.system', 'S005-FIRE-G-001', 'Zone-G-FIRE-CONTROL', 'fire_panel', 'Fire Control Room - Ground Floor', 'point_level_source', 'point_source', 'monitors', 'Kidde', 'VS4', '{"point_role":"system_status"}'),
        ('site-005-UMH-FIRE-001.zones', 'S005-FIRE-G-001', 'Zone-G-FIRE-CONTROL', 'fire_panel', 'Fire Control Room - Ground Floor', 'point_level_source', 'point_source', 'monitors', 'Kidde', 'VS4', '{"point_role":"zone_fault_count"}'),

        -- Security and access.
        ('S005-CCURE-SVR', 'S005-CCURE-SVR', 'Zone-G-SECURITY-CONTROL', 'access_control_server', 'Security Control Room - Ground Floor', 'canonical', 'display', 'located_in', NULL, NULL, '{"alias_for":"site-005-UMH-CCURE-SVR"}'),
        ('site-005-UMH-CCURE-SVR', 'S005-CCURE-SVR', 'Zone-G-SECURITY-CONTROL', 'access_control_server', 'Security Control Room - Ground Floor', 'source_alias', 'source', 'located_in', NULL, NULL, '{}'),
        ('site-005-UMH-DOOR-ICU-MAIN', 'S005-DOOR-ICU-MAIN', 'Zone-300', 'access_control_point', 'ICU Level 3 - Main Entrance', 'source_alias', 'source', 'controls', NULL, NULL, '{}'),
        ('site-005-UMH-DOOR-ICU-SIBLING', 'S005-DOOR-ICU-SIBLING', 'Zone-300', 'access_control_point', 'ICU Level 3 - Sibling Entrance', 'source_alias', 'source', 'controls', NULL, NULL, '{}'),
        ('site-005-UMH-DOOR-MAIN-ER', 'S005-DOOR-MAIN-ER', 'Zone-G-ER-ENTRANCE', 'access_control_point', 'Main ER Entrance - Ground Floor', 'source_alias', 'source', 'controls', NULL, NULL, '{}'),
        ('site-005-UMH-DOOR-PHARMACY', 'S005-DOOR-PHARMACY', 'Zone-L1-PHARMACY', 'access_control_point', 'Pharmacy Level 1 - Controlled Area', 'source_alias', 'source', 'controls', NULL, NULL, '{}'),
        ('site-005-UMH-DOOR-STAFF-A', 'S005-DOOR-STAFF-A', 'Zone-G-STAFF-A', 'access_control_point', 'Staff Entrance A - Ground Floor', 'source_alias', 'source', 'controls', NULL, NULL, '{}'),
        ('site-005-UMH-DOOR-STAFF-B', 'S005-DOOR-STAFF-B', 'Zone-B1-STAFF-B', 'access_control_point', 'Staff Entrance B - Basement', 'source_alias', 'source', 'controls', NULL, NULL, '{}'),
        ('site-005-UMH-GATE-VEHICLE', 'S005-GATE-VEHICLE', 'Zone-G-PARKING-GATE', 'access_control_point', 'Staff Parking Entrance - Ground Floor', 'source_alias', 'source', 'controls', NULL, NULL, '{}'),

        -- Energy and infrastructure rows with confirmed locations or alias identity.
        ('site-005-UMH-BESS-001', 'S005-BESS-B1-001', 'Zone-B1-PLANT-EAST', 'bess', 'Basement B1 - Plant Room East', 'source_alias', 'source', 'located_in', NULL, NULL, '{}'),
        ('site-005-UMH-DB-L3-001.total', 'S005-DB-L3-001', 'Zone-L3-ELEC-RISER', 'distribution_board', 'L3 Electrical Riser - Distribution Board Room', 'point_level_source', 'point_source', 'monitors', 'Schneider', 'Acti 9', '{"point_role":"total_power"}'),
        ('site-005-UMH-DB-L3-002.total', 'S005-DB-L3-002', 'Zone-L3-ELEC-RISER', 'distribution_board', 'L3 Electrical Riser - Distribution Board Room', 'point_level_source', 'point_source', 'monitors', 'Schneider', 'Acti 9', '{"point_role":"total_power"}'),
        ('S005-WATER-MTR-001', 'S005-WATER-MTR-001', NULL, 'water_meter', 'Water Meter', 'canonical', 'display', NULL, NULL, NULL, '{"alias_for":"site-005-UMH-WATER-MTR-001"}'),
        ('site-005-UMH-WATER-MTR-001', 'S005-WATER-MTR-001', NULL, 'water_meter', 'Water Meter', 'source_alias', 'source', NULL, NULL, NULL, '{}'),

        -- PV arrays and inverters with reviewed rooftop allocations.
        ('site-005-UMH-PV-ARRAY-001', 'S005-PV-ARRAY-R-001', 'Zone-R-PV-SOUTH', 'pv_array', 'Rooftop - South Wing', 'source_alias', 'source', 'located_in', NULL, NULL, '{}'),
        ('site-005-UMH-PV-ARRAY-A', 'S005-PV-ARRAY-R-A', 'Zone-R-PV-NORTH', 'pv_array', 'Rooftop - North Wing', 'source_alias', 'source', 'located_in', NULL, NULL, '{}'),
        ('site-005-UMH-PV-ARRAY-B', 'S005-PV-ARRAY-R-B', 'Zone-R-PV-SOUTH', 'pv_array', 'Rooftop - South Wing', 'source_alias', 'source', 'located_in', NULL, NULL, '{}'),
        ('site-005-UMH-PV-INV-HUAWEI', 'S005-PV-INV-R-001', 'Zone-R-PV-PLANT-SOUTH', 'pv_inverter', 'Rooftop Plant Room - South Wing', 'source_alias', 'source', 'located_in', 'Huawei', NULL, '{}'),
        ('site-005-UMH-PV-INV-HUAWEI-1', 'S005-PV-INV-R-002', 'Zone-R-PV-PLANT-NORTH', 'pv_inverter', 'Rooftop Plant Room - North Wing', 'source_alias', 'source', 'located_in', 'Huawei', NULL, '{}'),
        ('site-005-UMH-PV-INV-HUAWEI-2', 'S005-PV-INV-R-003', 'Zone-R-PV-PLANT-SOUTH', 'pv_inverter', 'Rooftop Plant Room - South Wing', 'source_alias', 'source', 'located_in', 'Huawei', NULL, '{}'),

        -- UPS telemetry points.
        ('site-005-UMH-UPS-L3-001.input', 'S005-UPS-L3-001', 'Zone-L3-UPS-ROOM', 'ups', 'L3 Server Room / UPS Room', 'point_level_source', 'point_source', 'monitors', NULL, NULL, '{"point_role":"input_power"}'),
        ('site-005-UMH-UPS-L3-001.load', 'S005-UPS-L3-001', 'Zone-L3-UPS-ROOM', 'ups', 'L3 Server Room / UPS Room', 'point_level_source', 'point_source', 'monitors', NULL, NULL, '{"point_role":"load"}'),

        -- Reviewed L3 AHU served-zone allocations. Physical plant location is
        -- retained in metadata; canonical_zone_id is the served zone used by
        -- operating-state gates and optimizer context.
        ('S005-AHU-304', 'S005-AHU-304', 'Zone-L3-HDU', 'ahu', 'L3 - High Dependency Unit (HDU)', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-305', 'S005-AHU-305', 'Zone-L3-POSTOP', 'ahu', 'L3 - Post-Operative Recovery', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-306', 'S005-AHU-306', 'Zone-L3-ANAES', 'ahu', 'L3 - Anaesthesia Prep Room', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-307', 'S005-AHU-307', 'Zone-L3-SCRUB', 'ahu', 'L3 - Scrub Room / Sterile Corridor', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-308', 'S005-AHU-308', 'Zone-L3-STERILE', 'ahu', 'L3 - Sterile Supply / Clean Utility', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-309', 'S005-AHU-309', 'Zone-L3-WARD-E', 'ahu', 'L3 - Ward East (Rooms 309-312)', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-310', 'S005-AHU-310', 'Zone-L3-WARD-W', 'ahu', 'L3 - Ward West (Rooms 313-316)', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-311', 'S005-AHU-311', 'Zone-L3-NS-E', 'ahu', 'L3 - Nurses Station East', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-312', 'S005-AHU-312', 'Zone-L3-NS-W', 'ahu', 'L3 - Nurses Station West', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-313', 'S005-AHU-313', 'Zone-L3-CORR-N', 'ahu', 'L3 - Public Corridor North', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-314', 'S005-AHU-314', 'Zone-L3-CORR-S', 'ahu', 'L3 - Public Corridor South', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-315', 'S005-AHU-315', 'Zone-L3-WAIT', 'ahu', 'L3 - Family Waiting Area', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),
        ('S005-AHU-316', 'S005-AHU-316', 'Zone-L3-STAFF', 'ahu', 'L3 - Staff Lounge / Change Room', 'canonical', 'display', 'serves', NULL, NULL, '{"mapping_basis":"served_zone_allocation","physical_location":"L3 Mechanical Plant Room"}'),

        -- Virtual aggregate nodes.
        ('S005-CHILLER-AGG', 'S005-CHILLER-AGG', 'Zone-B1-MAIN-PLANT', 'site_aggregate', 'Main Plant Room - Basement B1', 'canonical', 'display', 'located_in', NULL, NULL, '{"aggregate_scope":"chiller"}'),
        ('S005-SITE-AGG', 'S005-SITE-AGG', NULL, 'site_aggregate', 'Site - Busamed Gateway Private Hospital', 'canonical', 'display', NULL, NULL, NULL, '{"aggregate_scope":"site"}'),

        -- Legacy FCU zone labels with approved aliases.
        ('S005-FCU-Zone-G-001', 'S005-FCU-001', 'Zone-001', 'fcu', 'Ground Zone 001', 'source_alias', 'legacy', 'serves', NULL, NULL, '{}'),
        ('S005-FCU-Zone-L1-001', 'S005-FCU-100', 'Zone-100', 'fcu', 'Level 1 Zone 001', 'source_alias', 'legacy', 'serves', NULL, NULL, '{}'),
        ('S005-FCU-Zone-L2-001', 'S005-FCU-200', 'Zone-200', 'fcu', 'Level 2 Zone 001', 'source_alias', 'legacy', 'serves', NULL, NULL, '{}'),
        ('S005-FCU-Zone-L3-001', 'S005-FCU-L3-GW-001', 'Zone-L3-GENERAL-WARD', 'fcu', 'L3 - General Ward Zone', 'source_alias', 'legacy', 'serves', NULL, NULL, '{"mapping_basis":"floor_aggregate_pattern"}');

    UPDATE public.equipment e
    SET raw_code = COALESCE(e.raw_code, e.code),
        canonical_code = m.canonical_code,
        canonical_zone_id = m.canonical_zone_id,
        zone_key = COALESCE(m.canonical_zone_id, e.zone_key),
        type = m.equipment_type,
        location = m.location,
        manufacturer = COALESCE(m.manufacturer, e.manufacturer),
        model = COALESCE(m.model, e.model),
        canonicalization_status = m.status,
        canonicalization_source = 'site005_manual_mapping_seed',
        canonicalization_metadata = jsonb_build_object(
            'reason', 'reviewed_manual_mapping',
            'source', 'bridge_site005_unmapped_report',
            'mapped_at', NOW()
        ) || m.metadata,
        updated_at = NOW()
    FROM tmp_site005_manual_equipment_map m
    WHERE e.site_id = v_site_id
      AND e.code = m.code;

    DELETE FROM public.equipment_zone_relationships ez
    USING public.equipment e, tmp_site005_manual_equipment_map m
    WHERE ez.equipment_id = e.id
      AND e.site_id = v_site_id
      AND e.code = m.code
      AND ez.source = 'site005_manual_mapping_seed'
      AND ez.zone_id <> m.canonical_zone_id;

    DELETE FROM public.equipment_zone_relationships ez
    USING public.equipment e
    WHERE ez.equipment_id = e.id
      AND e.site_id = v_site_id
      AND e.code ~ '^S005-AHU-3(0[4-9]|1[0-6])$'
      AND ez.source = 'site005_equipment_canonical_seed'
      AND ez.zone_id = 'Zone-L3-MECH-PLANT'
      AND ez.relationship_type = 'serves';

    INSERT INTO public.equipment_aliases
        (site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata)
    SELECT
        e.site_id,
        e.id,
        e.code,
        m.canonical_code,
        m.alias_type,
        'site005_manual_mapping_seed',
        CASE
            WHEN m.metadata->>'mapping_basis' = 'served_zone_allocation' THEN 0.55
            WHEN m.relationship_type = 'located_in' THEN 0.85
            ELSE 0.70
        END,
        'suggested',
        jsonb_build_object('reason', 'reviewed_manual_mapping', 'source', 'bridge_site005_unmapped_report') || m.metadata
    FROM public.equipment e
    JOIN tmp_site005_manual_equipment_map m ON m.code = e.code
    WHERE e.site_id = v_site_id
      AND e.code <> m.canonical_code
    ON CONFLICT (site_id, alias_code) DO UPDATE
    SET equipment_id = EXCLUDED.equipment_id,
        canonical_code = EXCLUDED.canonical_code,
        alias_type = EXCLUDED.alias_type,
        source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        metadata = EXCLUDED.metadata,
        updated_at = NOW();

    INSERT INTO public.equipment_zone_relationships
        (site_id, equipment_id, zone_id, relationship_type, source, confidence, review_status, metadata)
    SELECT
        e.site_id,
        e.id,
        m.canonical_zone_id,
        m.relationship_type,
        'site005_manual_mapping_seed',
        CASE
            WHEN m.metadata->>'mapping_basis' = 'served_zone_allocation' THEN 0.55
            WHEN m.relationship_type = 'located_in' THEN 0.85
            ELSE 0.70
        END,
        'suggested',
        jsonb_build_object('reason', 'reviewed_manual_mapping', 'source', 'bridge_site005_unmapped_report') || m.metadata
    FROM public.equipment e
    JOIN tmp_site005_manual_equipment_map m ON m.code = e.code
    WHERE e.site_id = v_site_id
      AND m.canonical_zone_id IS NOT NULL
      AND m.relationship_type IS NOT NULL
    ON CONFLICT (equipment_id, zone_id, relationship_type) DO UPDATE
    SET source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        metadata = EXCLUDED.metadata,
        updated_at = NOW();

    CREATE TEMP TABLE tmp_site005_equipment_relationships (
        parent_canonical_code TEXT NOT NULL,
        child_canonical_code TEXT NOT NULL,
        relationship_type TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        PRIMARY KEY (parent_canonical_code, child_canonical_code, relationship_type)
    ) ON COMMIT DROP;

    INSERT INTO tmp_site005_equipment_relationships
        (parent_canonical_code, child_canonical_code, relationship_type, metadata)
    VALUES
        -- Access control server hierarchy.
        ('S005-CCURE-SVR', 'S005-DOOR-ICU-MAIN', 'controls', '{"source_parent":"site-005-UMH-CCURE-SVR"}'),
        ('S005-CCURE-SVR', 'S005-DOOR-ICU-SIBLING', 'controls', '{"source_parent":"site-005-UMH-CCURE-SVR"}'),
        ('S005-CCURE-SVR', 'S005-DOOR-MAIN-ER', 'controls', '{"source_parent":"site-005-UMH-CCURE-SVR"}'),
        ('S005-CCURE-SVR', 'S005-DOOR-PHARMACY', 'controls', '{"source_parent":"site-005-UMH-CCURE-SVR"}'),
        ('S005-CCURE-SVR', 'S005-DOOR-STAFF-A', 'controls', '{"source_parent":"site-005-UMH-CCURE-SVR"}'),
        ('S005-CCURE-SVR', 'S005-DOOR-STAFF-B', 'controls', '{"source_parent":"site-005-UMH-CCURE-SVR"}'),
        ('S005-CCURE-SVR', 'S005-GATE-VEHICLE', 'controls', '{"source_parent":"site-005-UMH-CCURE-SVR"}'),

        -- BMS controller hierarchy.
        ('S005-JACE-B1-001', 'S005-AHU-304', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-305', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-306', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-307', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-308', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-309', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-310', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-311', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-312', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-AHU-300', 'manages', '{"source_parent":"site-005-UMH-JACE-001","source_child":"site-005-UMH-AHU-L3-ICU"}'),
        ('S005-JACE-B1-001', 'S005-AHU-301', 'manages', '{"source_parent":"site-005-UMH-JACE-001","source_child":"site-005-UMH-AHU-L3-TH1"}'),
        ('S005-JACE-B1-001', 'S005-AHU-302', 'manages', '{"source_parent":"site-005-UMH-JACE-001","source_child":"site-005-UMH-AHU-L3-TH2"}'),
        ('S005-JACE-B1-001', 'S005-AHU-303', 'manages', '{"source_parent":"site-005-UMH-JACE-001","source_child":"site-005-UMH-AHU-L3-TH3"}'),
        ('S005-JACE-B1-001', 'S005-FCU-400', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-401', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-402', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-403', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-404', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-500', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-501', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-502', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-503', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-504', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-600', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-601', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-602', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-603', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-604', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-700', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-701', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-702', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-703', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-704', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-800', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-801', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-802', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-803', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-804', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-900', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-901', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-902', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-903', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-001', 'S005-FCU-904', 'manages', '{"source_parent":"site-005-UMH-JACE-001"}'),
        ('S005-JACE-B1-002', 'S005-AHU-313', 'manages', '{"source_parent":"site-005-UMH-JACE-002"}'),
        ('S005-JACE-B1-002', 'S005-AHU-314', 'manages', '{"source_parent":"site-005-UMH-JACE-002"}'),
        ('S005-JACE-B1-002', 'S005-AHU-315', 'manages', '{"source_parent":"site-005-UMH-JACE-002"}'),
        ('S005-JACE-B1-002', 'S005-AHU-316', 'manages', '{"source_parent":"site-005-UMH-JACE-002"}'),
        ('S005-JACE-B1-002', 'S005-AHU-200', 'manages', '{"source_parent":"site-005-UMH-JACE-002","source_child":"site-005-UMH-AHU-L2-001"}'),
        ('S005-JACE-B1-002', 'S005-AHU-400', 'manages', '{"source_parent":"site-005-UMH-JACE-002","source_child":"site-005-UMH-AHU-L4-001"}'),
        ('S005-JACE-B1-002', 'S005-AHU-500', 'manages', '{"source_parent":"site-005-UMH-JACE-002","source_child":"site-005-UMH-AHU-L5-001"}'),
        ('S005-JACE-B1-002', 'S005-AHU-600', 'manages', '{"source_parent":"site-005-UMH-JACE-002","source_child":"site-005-UMH-AHU-L6-001"}'),
        ('S005-JACE-B1-002', 'S005-AHU-700', 'manages', '{"source_parent":"site-005-UMH-JACE-002","source_child":"site-005-UMH-AHU-L7-001"}'),
        ('S005-JACE-B1-002', 'S005-AHU-800', 'manages', '{"source_parent":"site-005-UMH-JACE-002","source_child":"site-005-UMH-AHU-L8-001"}'),
        ('S005-JACE-B1-002', 'S005-AHU-900', 'manages', '{"source_parent":"site-005-UMH-JACE-002","source_child":"site-005-UMH-AHU-L9-001"}'),
        ('S005-JACE-B1-002', 'S005-AHU-B1-001', 'manages', '{"source_parent":"site-005-UMH-JACE-002","source_child":"S005-site-005-UMH-AHU-B01"}'),

        -- Energy and plant hierarchy. Only catalog-present canonical children
        -- are linked here; additional generator/pump nodes can be added when
        -- their equipment rows exist.
        ('S005-SITE-AGG', 'S005-CHILLER-AGG', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-CHILLER-AGG', 'S005-CT-R-001', 'contains', '{"hierarchy":"chiller_plant"}'),
        ('S005-CHILLER-AGG', 'S005-CT-R-002', 'contains', '{"hierarchy":"chiller_plant"}'),
        ('S005-CHILLER-AGG', 'S005-PUMP-B1-001', 'contains', '{"hierarchy":"chiller_plant"}'),
        ('S005-SITE-AGG', 'S005-BESS-B1-001', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-SITE-AGG', 'S005-GEN-B1-001', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-SITE-AGG', 'S005-MSB-B1-001', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-SITE-AGG', 'S005-PV-ARRAY-R-001', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-SITE-AGG', 'S005-PV-ARRAY-R-A', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-SITE-AGG', 'S005-PV-ARRAY-R-B', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-PV-ARRAY-R-001', 'S005-PV-INV-R-001', 'feeds', '{"hierarchy":"pv_rooftop_south"}'),
        ('S005-PV-ARRAY-R-A', 'S005-PV-INV-R-002', 'feeds', '{"hierarchy":"pv_rooftop_north"}'),
        ('S005-PV-ARRAY-R-B', 'S005-PV-INV-R-003', 'feeds', '{"hierarchy":"pv_rooftop_south"}'),
        ('S005-SITE-AGG', 'S005-DB-L3-001', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-SITE-AGG', 'S005-DB-L3-002', 'contains', '{"hierarchy":"site_energy_root"}'),
        ('S005-DB-L3-001', 'S005-UPS-L3-001', 'feeds', '{"hierarchy":"l3_distribution"}'),
        ('S005-DB-L3-002', 'S005-UPS-L3-001', 'feeds', '{"hierarchy":"l3_distribution"}'),
        ('S005-SITE-AGG', 'S005-WATER-MTR-001', 'contains', '{"hierarchy":"site_utility_root"}');

    INSERT INTO public.equipment_relationships
        (site_id, parent_canonical_code, child_canonical_code, relationship_type, source, confidence, review_status, metadata)
    SELECT
        v_site_id,
        r.parent_canonical_code,
        r.child_canonical_code,
        r.relationship_type,
        'naming_inference',
        0.75,
        'suggested',
        jsonb_build_object('reason', 'reviewed_manual_hierarchy', 'source', 'bridge_site005_linkage_report') || r.metadata
    FROM tmp_site005_equipment_relationships r
    ON CONFLICT (site_id, parent_canonical_code, child_canonical_code, relationship_type) DO UPDATE
    SET source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        metadata = EXCLUDED.metadata,
        updated_at = NOW();
END $$;
