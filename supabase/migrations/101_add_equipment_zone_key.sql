-- =====================================================
-- Migration: Add zone_key to equipment table
-- Stores normalized zone identifier for both office (numeric)
-- and hospital (alphanumeric) equipment codes.
-- =====================================================

-- Step 1: Add zone_key column to equipment
ALTER TABLE equipment ADD COLUMN IF NOT EXISTS zone_key TEXT;

-- Step 2: Index for fast zone lookups
CREATE INDEX IF NOT EXISTS idx_equipment_zone_key ON equipment(zone_key);
CREATE INDEX IF NOT EXISTS idx_equipment_site_zone ON equipment(site_id, zone_key);

-- Step 3: Backfill zone_key for existing equipment
-- Uses EquipmentIDConverter logic to normalize codes:

-- Site-002 (office): S002-AHU-101 → Zone-L1-1
-- Zone number encoding: 001-099=L0, 100-199=L1, 200-299=L2
UPDATE equipment
SET zone_key = CASE
    -- Plant equipment (explicit floor): S002-CHILLER-B1-001
    WHEN code ~ 'S002-CHILLER-B1' THEN 'Zone-B1-plant'
    WHEN code ~ 'S002-CHILLER-R'   THEN 'Zone-R-plant'
    WHEN code ~ 'S002-GEN-G'       THEN 'Zone-G-plant'
    WHEN code ~ 'S002-MTR-W'       THEN 'Zone-B1-plant'
    -- Zone-encoded office equipment: S002-VAV-101 → Zone-L1-1
    WHEN code ~ 'S002-.*-[0-9]{3}$' AND split_part(code, '-', 3) ~ '^[0-9]+$' THEN
        'Zone-' ||
        CASE
            WHEN split_part(code, '-', 3)::int BETWEEN 1 AND 99   THEN 'L0'
            WHEN split_part(code, '-', 3)::int BETWEEN 100 AND 199 THEN 'L1'
            WHEN split_part(code, '-', 3)::int BETWEEN 200 AND 299 THEN 'L2'
            ELSE 'L0'
        END ||
        '-' ||
        (split_part(code, '-', 3)::int % 100)
    ELSE NULL
END
WHERE zone_key IS NULL
  AND code LIKE 'S002-%';

-- Site-005 (hospital): site-005-UMH-AHU-L3-ICU → Zone-L3-ICU
-- Format: site-005-UMH-{TYPE}-{FLOOR}-{ZONE}
-- Zone may have suffix like .fan — strip it
UPDATE equipment
SET zone_key = 'Zone-' || split_part(code, '-', 4) || '-' || split_part(split_part(code, '-', 5), '.', 1)
WHERE zone_key IS NULL
  AND code LIKE 'site-005-UMH-%';

-- Site-003, S003, etc.
UPDATE equipment
SET zone_key = CASE
    WHEN code ~ '^[A-Z]{3}-[^-]+-[^-]+-[0-9]+$' AND split_part(code, '-', 3) ~ '^[0-9]+$' THEN
        -- Generic numeric zone encoding
        'Zone-' ||
        CASE
            WHEN split_part(code, '-', 3)::int BETWEEN 1 AND 99   THEN 'L0'
            WHEN split_part(code, '-', 3)::int BETWEEN 100 AND 199 THEN 'L1'
            WHEN split_part(code, '-', 3)::int BETWEEN 200 AND 299 THEN 'L2'
            ELSE split_part(code, '-', 3)
        END ||
        '-' ||
        (split_part(code, '-', 3)::int % 100)
    ELSE NULL
END
WHERE zone_key IS NULL
  AND code ~ '^[A-Z]{3}-[^-]+-[0-9]+$';

-- Step 4: Add NOT NULL constraint after backfill (optional, can be deferred)
-- ALTER TABLE equipment ALTER COLUMN zone_key SET NOT NULL;

-- Step 5: Function to auto-populate zone_key on INSERT/UPDATE
CREATE OR REPLACE FUNCTION populate_equipment_zone_key()
RETURNS TRIGGER AS $$
BEGIN
    -- Skip if already set
    IF NEW.zone_key IS NOT NULL AND NEW.zone_key != '' THEN
        RETURN NEW;
    END IF;

    -- Site-002 numeric encoding
    IF NEW.code LIKE 'S002-%' THEN
        IF NEW.code ~ 'S002-CHILLER-B1|S002-MTR-W' THEN
            NEW.zone_key := 'Zone-B1-plant';
        ELSIF NEW.code ~ 'S002-CHILLER-R|S002-INV-R|S002-CT-R' THEN
            NEW.zone_key := 'Zone-R-plant';
        ELSIF NEW.code ~ 'S002-GEN-G' THEN
            NEW.zone_key := 'Zone-G-plant';
        ELSIF NEW.code ~ 'S002-.*-[0-9]{3}$' AND split_part(NEW.code, '-', 3) ~ '^[0-9]+$' THEN
            DECLARE
                zone_num INT := split_part(NEW.code, '-', 3)::int;
                floor_code TEXT;
                zone_idx INT;
            BEGIN
                floor_code := CASE
                    WHEN zone_num BETWEEN 1 AND 99   THEN 'L0'
                    WHEN zone_num BETWEEN 100 AND 199 THEN 'L1'
                    WHEN zone_num BETWEEN 200 AND 299 THEN 'L2'
                    ELSE 'L0'
                END;
                zone_idx := zone_num % 100;
                IF zone_idx = 0 THEN zone_idx := 100; END IF;
                NEW.zone_key := 'Zone-' || floor_code || '-' || zone_idx;
            END;
        END IF;

    -- Site-005 hospital format: site-005-UMH-{TYPE}-{FLOOR}-{ZONE}
    -- Example: site-005-UMH-AHU-L3-ICU → Zone-L3-ICU
    -- Zone may have suffix like .fan — strip it with split_part(..., '.', 1)
    ELSIF NEW.code LIKE 'site-005-UMH-%' THEN
        NEW.zone_key := 'Zone-' ||
            split_part(NEW.code, '-', 4) || '-' ||
            split_part(split_part(NEW.code, '-', 5), '.', 1);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-populate on insert/update
DROP TRIGGER IF EXISTS trigger_populate_equipment_zone_key ON equipment;
CREATE TRIGGER trigger_populate_equipment_zone_key
    BEFORE INSERT OR UPDATE OF code ON equipment
    FOR EACH ROW
    EXECUTE FUNCTION populate_equipment_zone_key();

COMMENT ON COLUMN equipment.zone_key IS 'Normalized zone identifier e.g. Zone-L1-1 (office) or Zone-L3-ICU (hospital). Populated by EquipmentIDConverter during ingestion.';
