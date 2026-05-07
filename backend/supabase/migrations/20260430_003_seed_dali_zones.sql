-- =============================================================================
-- Lighting Zone Seeding for site-002 (Sandton City Office Tower)
-- =============================================================================
-- SIMBIOT principle: SENTINEL is brand-agnostic. DALI is one protocol.
-- Tables use 'lighting_' prefix (protocol-neutral) not 'dali_'.
--
-- Existing tables:
--   dali_zones       → rename to lighting_zones
--   dali_sensors     → lighting_sensors (empty, needs correct schema)
--   dali_luminaires  → lighting_luminaires (empty, needs correct schema)
--   lighting_energy  → keep as-is (already correctly named)
--
-- After migration, /api/lighting/live returns real zone data.
-- =============================================================================

BEGIN;

-- =============================================================================
-- Step 1: Add composite unique constraint for site+zone to dali_zones
-- (zone_id alone is globally unique, but we need site_id too for proper upserts)
-- =============================================================================

-- Drop the existing zone_id-only unique constraint
ALTER TABLE dali_zones DROP CONSTRAINT IF EXISTS dali_zones_zone_id_key;

-- Add proper site+zone unique constraint
ALTER TABLE dali_zones ADD CONSTRAINT lighting_zones_site_zone_key
  UNIQUE (site_id, zone_id);

-- =============================================================================
-- Step 2: Rename dali_* tables to lighting_* (brand-neutral)
-- =============================================================================

ALTER TABLE dali_zones RENAME TO lighting_zones;
ALTER TABLE dali_sensors RENAME TO lighting_sensors;
ALTER TABLE dali_luminaires RENAME TO lighting_luminaires;

-- =============================================================================
-- Step 3: Fix lighting_sensors schema if needed
-- =============================================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'lighting_sensors' AND column_name = 'sensor_id') THEN

    DROP TABLE IF EXISTS lighting_sensors CASCADE;

    CREATE TABLE lighting_sensors (
      id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      site_id         TEXT NOT NULL,
      zone_id         TEXT NOT NULL,
      sensor_id       TEXT NOT NULL,
      sensor_type     TEXT DEFAULT 'pir_daylight',
      location        TEXT DEFAULT 'ceiling_mounted',
      occupancy       BOOLEAN DEFAULT false,
      lux_level       REAL DEFAULT 0,
      last_updated    TIMESTAMPTZ,
      created_at      TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE(site_id, zone_id, sensor_id)
    );

    COMMENT ON TABLE lighting_sensors IS 'Lighting occupancy + lux sensors per zone. Protocol-neutral.';

    ALTER TABLE lighting_sensors ENABLE ROW LEVEL SECURITY;
    CREATE POLICY lighting_sensors_select ON lighting_sensors FOR SELECT USING (true);
  END IF;
END $$;

-- =============================================================================
-- Step 4: Fix lighting_luminaires schema if needed
-- =============================================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'lighting_luminaires' AND column_name = 'luminaire_id') THEN

    DROP TABLE IF EXISTS lighting_luminaires CASCADE;

    CREATE TABLE lighting_luminaires (
      id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      site_id             TEXT NOT NULL,
      zone_id             TEXT NOT NULL,
      luminaire_id        TEXT NOT NULL,
      name                TEXT,
      current_level       REAL DEFAULT 0,
      power_consumption   REAL DEFAULT 0,
      fault_status        BOOLEAN DEFAULT false,
      last_updated        TIMESTAMPTZ,
      created_at          TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE(site_id, zone_id, luminaire_id)
    );

    COMMENT ON TABLE lighting_luminaires IS 'Lighting luminaires per zone. Protocol-neutral.';

    ALTER TABLE lighting_luminaires ENABLE ROW LEVEL SECURITY;
    CREATE POLICY lighting_luminaires_select ON lighting_luminaires FOR SELECT USING (true);
  END IF;
END $$;

-- =============================================================================
-- Step 5: Fix lighting_energy schema if needed
-- =============================================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'lighting_energy' AND column_name = 'energy_kwh') THEN

    DROP TABLE IF EXISTS lighting_energy CASCADE;

    CREATE TABLE lighting_energy (
      id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      site_id     TEXT NOT NULL,
      zone_id     TEXT NOT NULL,
      time        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      energy_kwh  REAL NOT NULL DEFAULT 0,
      power_w     REAL DEFAULT 0,
      created_at  TIMESTAMPTZ DEFAULT NOW()
    );

    COMMENT ON TABLE lighting_energy IS 'Hourly lighting energy consumption per zone.';

    ALTER TABLE lighting_energy ENABLE ROW LEVEL SECURITY;
    CREATE POLICY lighting_energy_select ON lighting_energy FOR SELECT USING (true);
  END IF;
END $$;

-- =============================================================================
-- Step 6: Seed lighting_zones (8 logical zones across 4 DALI controllers)
-- Zone IDs match Z-{FLOOR}-{SECTION}-{NUM} pattern from dali_service.py
-- =============================================================================

DO $$
DECLARE
  ctrl_l2b_id UUID;
  ctrl_l1a_id UUID;
  ctrl_l1c_id UUID;
  ctrl_b1_id  UUID;
  r           INT;
BEGIN
  ctrl_l2b_id := (SELECT id FROM equipment WHERE code = 'S002-DALI-L2-B');
  ctrl_l1a_id := (SELECT id FROM equipment WHERE code = 'S002-DALI-L1-A');
  ctrl_l1c_id := (SELECT id FROM equipment WHERE code = 'S002-DALI-L1-CTR');
  ctrl_b1_id  := (SELECT id FROM equipment WHERE code = 'S002-DALI-B1-001');

  IF ctrl_l2b_id IS NULL THEN
    RAISE WARNING 'DALI controllers not found - skipping lighting zone seed';
    RETURN;
  END IF;

  -- Clear stale data
  DELETE FROM lighting_zones WHERE site_id = 'S002';

  INSERT INTO lighting_zones (id, zone_id, name, floor, site_id, area_sqm, desk_count, created_at, updated_at)
  VALUES
    (ctrl_l2b_id, 'Z-L2-S-01', 'Level 2 South Zone 1', 'L2', 'S002', 450, 25, NOW(), NOW()),
    (gen_random_uuid(), 'Z-L2-S-02', 'Level 2 South Zone 2', 'L2', 'S002', 450, 25, NOW(), NOW()),
    (ctrl_l1a_id, 'Z-L1-N-01', 'Level 1 North Zone 1', 'L1', 'S002', 500, 30, NOW(), NOW()),
    (gen_random_uuid(), 'Z-L1-N-02', 'Level 1 North Zone 2', 'L1', 'S002', 500, 30, NOW(), NOW()),
    (ctrl_l1c_id, 'Z-L1-C-01', 'Level 1 Central Zone 1', 'L1', 'S002', 350, 20, NOW(), NOW()),
    (gen_random_uuid(), 'Z-L1-C-02', 'Level 1 Central Zone 2', 'L1', 'S002', 200, 10, NOW(), NOW()),
    (ctrl_b1_id,  'Z-B1-01', 'Basement Zone 1', 'B1', 'S002', 300,  5, NOW(), NOW()),
    (gen_random_uuid(), 'Z-B1-02', 'Basement Zone 2', 'B1', 'S002', 300,  5, NOW(), NOW())
  ON CONFLICT (site_id, zone_id) DO UPDATE SET
    name = EXCLUDED.name, floor = EXCLUDED.floor,
    area_sqm = EXCLUDED.area_sqm, desk_count = EXCLUDED.desk_count,
    updated_at = NOW();

  GET DIAGNOSTICS r = ROW_COUNT;
  RAISE NOTICE 'lighting_zones: % rows inserted/updated', r;
END $$;

-- =============================================================================
-- Step 7: Seed lighting_sensors (1 PIR+lux sensor per zone)
-- =============================================================================

DELETE FROM lighting_sensors WHERE site_id = 'S002';

INSERT INTO lighting_sensors (id, site_id, zone_id, sensor_id, sensor_type, location, occupancy, lux_level, last_updated, created_at)
SELECT
  gen_random_uuid(), 'S002', zone_id,
  'SNS-' || zone_id || '-01',
  'pir_daylight', 'ceiling_mounted', false, 0, NOW(), NOW()
FROM lighting_zones WHERE site_id = 'S002'
ON CONFLICT (site_id, zone_id, sensor_id) DO NOTHING;

-- =============================================================================
-- Step 8: Seed lighting_luminaires (8 per office zone, 4 per storage zone)
-- 35W LED panel, 70% brightness = 24.5W typical consumption
-- =============================================================================

DELETE FROM lighting_luminaires WHERE site_id = 'S002';

DO $$
DECLARE
  zone_rec RECORD;
  lum_count INT;
BEGIN
  FOR zone_rec IN SELECT zone_id, name FROM lighting_zones WHERE site_id = 'S002' LOOP
    lum_count := CASE
      WHEN zone_rec.name ILIKE '%storage%' OR zone_rec.name ILIKE '%corridor%' THEN 4
      ELSE 8
    END;

    FOR i IN 1..lum_count LOOP
      INSERT INTO lighting_luminaires (
        id, site_id, zone_id, luminaire_id, name,
        current_level, power_consumption, fault_status, last_updated, created_at
      ) VALUES (
        gen_random_uuid(), 'S002', zone_rec.zone_id,
        'LM-' || zone_rec.zone_id || '-' || LPAD(i::TEXT, 2, '0'),
        'LM-' || zone_rec.zone_id || '-' || LPAD(i::TEXT, 2, '0'),
        70.0, 35.0, false, NOW(), NOW()
      ) ON CONFLICT (site_id, zone_id, luminaire_id) DO NOTHING;
    END LOOP;
  END LOOP;
END $$;

-- =============================================================================
-- Step 9: Seed 24h of lighting_energy (hourly records per zone)
-- =============================================================================

DELETE FROM lighting_energy WHERE site_id = 'S002';

DO $$
DECLARE
  zone_rec RECORD;
  h   INT;
  kwh FLOAT;
BEGIN
  FOR zone_rec IN SELECT zone_id FROM lighting_zones WHERE site_id = 'S002' LOOP
    FOR h IN 0..23 LOOP
      kwh := CASE WHEN h BETWEEN 7 AND 18
             THEN (0.35 + random() * 0.15)::REAL
             ELSE (0.05 + random() * 0.05)::REAL END;

      INSERT INTO lighting_energy (id, site_id, zone_id, time, energy_kwh, power_w, created_at)
      VALUES (gen_random_uuid(), 'S002', zone_rec.zone_id,
              NOW() - (h || ' hours')::INTERVAL, kwh, ROUND(kwh * 1000)::REAL, NOW())
      ON CONFLICT DO NOTHING;
    END LOOP;
  END LOOP;
END $$;

-- =============================================================================
-- Verify
-- =============================================================================

DO $$
DECLARE
  z INT; s INT; l INT; e INT;
BEGIN
  SELECT COUNT(*) INTO z FROM lighting_zones WHERE site_id = 'S002';
  SELECT COUNT(*) INTO s FROM lighting_sensors WHERE site_id = 'S002';
  SELECT COUNT(*) INTO l FROM lighting_luminaires WHERE site_id = 'S002';
  SELECT COUNT(*) INTO e FROM lighting_energy WHERE site_id = 'S002';
  RAISE NOTICE '';
  RAISE NOTICE '=== Lighting Zone Seed Summary (S002) ===';
  RAISE NOTICE 'lighting_zones:     % (expected 8)', z;
  RAISE NOTICE 'lighting_sensors:  % (expected 8)', s;
  RAISE NOTICE 'lighting_luminaires: % (expected ~52)', l;
  RAISE NOTICE 'lighting_energy:    % (expected ~192)', e;
END $$;

COMMIT;

-- =============================================================================
-- Step 10: Update dali_service.py and lighting_service.py
-- to use lighting_* table names instead of dali_*
-- Run after migration:
-- =============================================================================
-- find /opt/bms-intelligence/backend/app/services -name "*.py" \
--   -exec sed -i 's/dali_sensors/lighting_sensors/g; s/dali_luminaires/lighting_luminaires/g' {} \;
