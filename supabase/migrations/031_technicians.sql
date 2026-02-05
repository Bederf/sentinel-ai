-- =====================================================
-- Migration 010: Technicians and Site Assignments
-- Assign technicians to sites by specialty/function
-- =====================================================

-- Technicians table
CREATE TABLE technicians (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,           -- e.g., TECH-001
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  active BOOLEAN DEFAULT TRUE,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Site technician assignments (which tech handles what specialty at which site)
CREATE TABLE site_technicians (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  technician_id UUID NOT NULL REFERENCES technicians(id) ON DELETE CASCADE,
  specialty TEXT NOT NULL CHECK (specialty IN (
    'hvac',
    'electrical',
    'plumbing',
    'dali',
    'fire',
    'security',
    'general'
  )),
  is_primary BOOLEAN DEFAULT TRUE,     -- Primary tech for this specialty at this site

  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Unique constraint: one primary tech per specialty per site
  UNIQUE (building_id, specialty, is_primary)
);

-- Indexes
CREATE INDEX idx_technicians_active ON technicians(active) WHERE active = TRUE;
CREATE INDEX idx_site_technicians_building ON site_technicians(building_id);
CREATE INDEX idx_site_technicians_specialty ON site_technicians(building_id, specialty);

-- Trigger for updated_at
CREATE TRIGGER update_technicians_updated_at BEFORE UPDATE ON technicians
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- Seed data for Sandton City (site-002)
-- =====================================================

-- Insert a default technician
INSERT INTO technicians (code, name, email, phone) VALUES
  ('TECH-001', 'John Smith', 'bederf@gmail.com', '+27-82-555-0101');

-- Assign to Sandton City for all specialties
INSERT INTO site_technicians (building_id, technician_id, specialty, is_primary)
SELECT
  b.id,
  t.id,
  specialty,
  TRUE
FROM buildings b
CROSS JOIN technicians t
CROSS JOIN (
  VALUES ('hvac'), ('electrical'), ('plumbing'), ('dali'), ('fire'), ('security'), ('general')
) AS specs(specialty)
WHERE b.code = 'site-002' AND t.code = 'TECH-001';

-- =====================================================
-- Helper function: Get technician for equipment
-- Parses equipment code to determine specialty
-- Equipment code format: {site}-{type}-{floor}-{zone}
-- Example: S002-DALI-L2-20 → type=DALI → specialty=dali
-- =====================================================

CREATE OR REPLACE FUNCTION get_technician_for_equipment(p_equipment_id UUID)
RETURNS TABLE (
  technician_id UUID,
  technician_name TEXT,
  technician_email TEXT,
  technician_phone TEXT,
  specialty TEXT
) AS $$
DECLARE
  v_equipment_code TEXT;
  v_building_id UUID;
  v_equipment_type TEXT;
  v_specialty TEXT;
BEGIN
  -- Get equipment code and building
  SELECT e.code, e.building_id INTO v_equipment_code, v_building_id
  FROM equipment e
  WHERE e.id = p_equipment_id;

  -- Parse equipment type from code (second segment)
  -- Format: {site}-{type}-{floor}-{zone} e.g., S002-DALI-L2-20
  v_equipment_type := UPPER(SPLIT_PART(v_equipment_code, '-', 2));

  -- Map equipment type to specialty
  -- Based on official naming conventions (docs/02-architecture/naming-conventions.md)
  v_specialty := CASE v_equipment_type
    -- HVAC equipment (v2.0 naming)
    WHEN 'CHILLER' THEN 'hvac'
    WHEN 'AHU' THEN 'hvac'
    WHEN 'FCU' THEN 'hvac'
    WHEN 'VAV' THEN 'hvac'
    WHEN 'SPLIT' THEN 'hvac'
    WHEN 'CT' THEN 'hvac'      -- Cooling Tower
    WHEN 'CRAC' THEN 'hvac'
    -- DALI Lighting (v2.0 naming)
    WHEN 'DALI' THEN 'dali'
    WHEN 'LUM' THEN 'dali'     -- Luminaire
    -- Energy/Electrical (v2.0 naming)
    WHEN 'GEN' THEN 'electrical'
    WHEN 'TX' THEN 'electrical'   -- Transformer
    WHEN 'UPS' THEN 'electrical'
    WHEN 'ATS' THEN 'electrical'  -- Automatic Transfer Switch
    WHEN 'MSB' THEN 'electrical'  -- Main Switchboard
    WHEN 'MTR' THEN 'electrical'  -- Power Meter
    WHEN 'PFC' THEN 'electrical'  -- Power Factor Correction
    WHEN 'FDR' THEN 'electrical'  -- Feeder
    WHEN 'MV' THEN 'electrical'   -- Medium Voltage
    WHEN 'DB' THEN 'electrical'   -- Distribution Board
    -- Sensors (monitored by general)
    WHEN 'TS' THEN 'general'      -- Temperature Sensor
    WHEN 'CO2' THEN 'general'     -- CO2 Sensor
    WHEN 'OCC' THEN 'general'     -- Occupancy Sensor
    WHEN 'DLS' THEN 'general'     -- Daylight Sensor
    -- Plumbing
    WHEN 'PUMP' THEN 'plumbing'
    WHEN 'TANK' THEN 'plumbing'
    WHEN 'BORE' THEN 'plumbing'
    -- Fire (v2.0 naming)
    WHEN 'FIRE' THEN 'fire'
    -- Security (v2.0 naming)
    WHEN 'ACC' THEN 'security'    -- Access Control
    WHEN 'CCTV' THEN 'security'
    -- Default
    ELSE 'general'
  END;

  -- Return technician for this building and specialty
  RETURN QUERY
  SELECT
    t.id,
    t.name,
    t.email,
    t.phone,
    st.specialty
  FROM site_technicians st
  JOIN technicians t ON t.id = st.technician_id
  WHERE st.building_id = v_building_id
    AND st.specialty = v_specialty
    AND st.is_primary = TRUE
    AND t.active = TRUE
  LIMIT 1;

  -- Fallback to 'general' if no specific tech found
  IF NOT FOUND THEN
    RETURN QUERY
    SELECT
      t.id,
      t.name,
      t.email,
      t.phone,
      st.specialty
    FROM site_technicians st
    JOIN technicians t ON t.id = st.technician_id
    WHERE st.building_id = v_building_id
      AND st.specialty = 'general'
      AND st.is_primary = TRUE
      AND t.active = TRUE
    LIMIT 1;
  END IF;
END;
$$ LANGUAGE plpgsql;
