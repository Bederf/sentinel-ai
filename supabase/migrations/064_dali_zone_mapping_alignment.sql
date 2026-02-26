-- =====================================================================
-- Migration 064: DALI Zone Mapping Alignment
-- Align DALI zones with desk-based zone standard
-- Problem: DALI zones (e.g., Zone-L12-N) don't match desk zones (Zone-L0-A)
-- Solution: Create mapping and update DALI equipment zone references
-- =====================================================================

-- Create mapping table: DALI zones to desk-based zones
CREATE TABLE IF NOT EXISTS dali_zone_mapping (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,

    -- DALI zone (old/legacy naming)
    dali_zone_id TEXT NOT NULL,                  -- e.g., "Zone-L12-N"
    dali_floor TEXT NOT NULL,                    -- e.g., "L12"

    -- Desk-based zone (new standard)
    desk_zone_id TEXT NOT NULL,                  -- e.g., "Zone-L0-A"
    desk_floor TEXT NOT NULL,                    -- e.g., "L0"

    -- Mapping metadata
    mapping_confidence DECIMAL(3,2) DEFAULT 1.0, -- 0.0 to 1.0 (1.0 = exact, <1.0 = approximate)
    mapping_method TEXT,                         -- e.g., "floor_standard", "spatial_proximity", "manual"
    notes TEXT,                                  -- e.g., "L10→L0, L11→L1, L12→L2"

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_dali_to_desk_mapping UNIQUE(building_id, dali_zone_id),
    CONSTRAINT valid_mapping_confidence CHECK (mapping_confidence >= 0 AND mapping_confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_dali_zone_mapping_building ON dali_zone_mapping(building_id);
CREATE INDEX IF NOT EXISTS idx_dali_zone_mapping_dali_zone ON dali_zone_mapping(dali_zone_id);
CREATE INDEX IF NOT EXISTS idx_dali_zone_mapping_desk_zone ON dali_zone_mapping(desk_zone_id);

-- Enable RLS
ALTER TABLE dali_zone_mapping ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable read for authenticated users" ON dali_zone_mapping
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Enable write for authenticated users" ON dali_zone_mapping
    FOR INSERT WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Enable update for authenticated users" ON dali_zone_mapping
    FOR UPDATE USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_dali_zone_mapping_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_dali_zone_mapping_updated_at
    BEFORE UPDATE ON dali_zone_mapping
    FOR EACH ROW
    EXECUTE FUNCTION update_dali_zone_mapping_updated_at();

-- =====================================================================
-- INSERT MAPPING DATA for site-002 (Sandton City)
-- Floor mapping: L10→L0, L11→L1, L12→L2
-- Zone mapping: Each DALI controller zone maps to desk-based zones A-E
-- =====================================================================

-- Get site-002 building ID and insert mappings
WITH site_002_building AS (
    SELECT id FROM buildings WHERE code = 'site-002'
)
INSERT INTO dali_zone_mapping (
    building_id, dali_zone_id, dali_floor, desk_zone_id, desk_floor,
    mapping_confidence, mapping_method, notes
)
SELECT
    sb.id,
    zone_data.dali_zone_id,
    zone_data.dali_floor,
    zone_data.desk_zone_id,
    zone_data.desk_floor,
    zone_data.confidence,
    zone_data.method,
    zone_data.notes
FROM site_002_building sb
CROSS JOIN (
    VALUES
        -- L10 (Legacy) → L0 (Ground) mappings
        ('Zone-L10-A', 'L10', 'Zone-L0-A', 'L0', 1.0::DECIMAL(3,2), 'floor_standard', 'L10→L0: Zone A'),
        ('Zone-L10-B', 'L10', 'Zone-L0-B', 'L0', 1.0::DECIMAL(3,2), 'floor_standard', 'L10→L0: Zone B'),
        ('Zone-L10-C', 'L10', 'Zone-L0-C', 'L0', 1.0::DECIMAL(3,2), 'floor_standard', 'L10→L0: Zone C'),
        ('Zone-L10-D', 'L10', 'Zone-L0-D', 'L0', 1.0::DECIMAL(3,2), 'floor_standard', 'L10→L0: Zone D'),
        ('Zone-L10-E', 'L10', 'Zone-L0-E', 'L0', 1.0::DECIMAL(3,2), 'floor_standard', 'L10→L0: Zone E'),
        ('Zone-L10-N', 'L10', 'Zone-L0-A', 'L0', 0.8::DECIMAL(3,2), 'floor_standard', 'L10→L0: Legacy N zone mapped to A'),

        -- L11 (Legacy) → L1 (Level 1) mappings
        ('Zone-L11-A', 'L11', 'Zone-L1-A', 'L1', 1.0::DECIMAL(3,2), 'floor_standard', 'L11→L1: Zone A'),
        ('Zone-L11-B', 'L11', 'Zone-L1-B', 'L1', 1.0::DECIMAL(3,2), 'floor_standard', 'L11→L1: Zone B'),
        ('Zone-L11-C', 'L11', 'Zone-L1-C', 'L1', 1.0::DECIMAL(3,2), 'floor_standard', 'L11→L1: Zone C'),
        ('Zone-L11-D', 'L11', 'Zone-L1-D', 'L1', 1.0::DECIMAL(3,2), 'floor_standard', 'L11→L1: Zone D'),
        ('Zone-L11-E', 'L11', 'Zone-L1-E', 'L1', 1.0::DECIMAL(3,2), 'floor_standard', 'L11→L1: Zone E'),
        ('Zone-L11-N', 'L11', 'Zone-L1-A', 'L1', 0.8::DECIMAL(3,2), 'floor_standard', 'L11→L1: Legacy N zone mapped to A'),

        -- L12 (Legacy) → L2 (Level 2) mappings
        ('Zone-L12-A', 'L12', 'Zone-L2-A', 'L2', 1.0::DECIMAL(3,2), 'floor_standard', 'L12→L2: Zone A'),
        ('Zone-L12-B', 'L12', 'Zone-L2-B', 'L2', 1.0::DECIMAL(3,2), 'floor_standard', 'L12→L2: Zone B'),
        ('Zone-L12-C', 'L12', 'Zone-L2-C', 'L2', 1.0::DECIMAL(3,2), 'floor_standard', 'L12→L2: Zone C'),
        ('Zone-L12-D', 'L12', 'Zone-L2-D', 'L2', 1.0::DECIMAL(3,2), 'floor_standard', 'L12→L2: Zone D'),
        ('Zone-L12-E', 'L12', 'Zone-L2-E', 'L2', 1.0::DECIMAL(3,2), 'floor_standard', 'L12→L2: Zone E'),
        ('Zone-L12-N', 'L12', 'Zone-L2-A', 'L2', 0.8::DECIMAL(3,2), 'floor_standard', 'L12→L2: Legacy N zone mapped to A')
) AS zone_data(dali_zone_id, dali_floor, desk_zone_id, desk_floor, confidence, method, notes)
ON CONFLICT (building_id, dali_zone_id) DO UPDATE
SET desk_zone_id = EXCLUDED.desk_zone_id,
    desk_floor = EXCLUDED.desk_floor,
    updated_at = NOW()
WHERE dali_zone_mapping.mapping_confidence < EXCLUDED.mapping_confidence;

-- =====================================================================
-- UPDATE DALI SENSORS to use mapped zones
-- This updates the zone_id in dali_sensors to reference desk-based zones
-- =====================================================================

UPDATE dali_sensors ds
SET zone_id = dzm.desk_zone_id,
    last_updated = NOW()
FROM dali_zone_mapping dzm
WHERE dzm.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND ds.zone_id = dzm.dali_zone_id
  AND ds.zone_id != dzm.desk_zone_id;

-- =====================================================================
-- UPDATE DALI LUMINAIRES to use mapped zones
-- This updates the zone_id in dali_luminaires to reference desk-based zones
-- =====================================================================

UPDATE dali_luminaires dl
SET zone_id = dzm.desk_zone_id,
    last_updated = NOW()
FROM dali_zone_mapping dzm
WHERE dzm.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND dl.zone_id = dzm.dali_zone_id
  AND dl.zone_id != dzm.desk_zone_id;

-- =====================================================================
-- CREATE VIEW: DALI Zone Alignment Status
-- Shows current state of DALI zone mapping and migration progress
-- =====================================================================

DROP VIEW IF EXISTS dali_zone_alignment_status CASCADE;

CREATE VIEW dali_zone_alignment_status AS
SELECT
    b.code AS building_code,
    b.name AS building_name,

    -- DALI zone info
    dzm.dali_zone_id,
    dzm.dali_floor,

    -- Desk zone info
    dzm.desk_zone_id,
    dzm.desk_floor,

    -- Zone configuration
    z.zone_name,
    z.zone_type,
    z.area_sqm,

    -- Mapping quality
    dzm.mapping_confidence,
    dzm.mapping_method,

    -- Equipment counts
    (SELECT COUNT(*) FROM dali_sensors WHERE zone_id = dzm.desk_zone_id) AS sensor_count,
    (SELECT COUNT(*) FROM dali_luminaires WHERE zone_id = dzm.desk_zone_id) AS luminaire_count,
    (SELECT COUNT(*) FROM desks WHERE zone_id = dzm.desk_zone_id AND building_id = b.id) AS desk_count,

    dzm.created_at,
    dzm.updated_at
FROM dali_zone_mapping dzm
LEFT JOIN buildings b ON dzm.building_id = b.id
LEFT JOIN zones z ON z.building_id = dzm.building_id AND z.zone_id = dzm.desk_zone_id
WHERE b.code = 'site-002'
ORDER BY dzm.desk_floor, dzm.desk_zone_id;

COMMENT ON VIEW dali_zone_alignment_status IS 'Shows DALI zone mapping status, desk zone configuration, equipment counts per zone, and migration progress';

-- =====================================================================
-- DOCUMENTATION
-- =====================================================================

COMMENT ON TABLE dali_zone_mapping IS 'Maps DALI zones (legacy naming) to desk-based zones (modern standard). Enables alignment of lighting control zones with workspace layout.';

COMMENT ON COLUMN dali_zone_mapping.dali_zone_id IS 'Legacy DALI zone identifier (e.g., Zone-L12-N from old naming convention)';

COMMENT ON COLUMN dali_zone_mapping.desk_zone_id IS 'Modern desk-based zone identifier (e.g., Zone-L0-A, Zone-L1-B) following standard naming convention';

COMMENT ON COLUMN dali_zone_mapping.mapping_confidence IS 'Confidence in mapping (1.0 = verified exact match, 0.5-0.9 = approximate/inferred)';

COMMENT ON COLUMN dali_zone_mapping.mapping_method IS 'How mapping was determined: floor_standard (standard floor renumbering), spatial_proximity (location-based), manual (human review)';
