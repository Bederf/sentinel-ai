-- =====================================================
-- Migration 034: Add Telegram ID to Technicians
-- Enables Telegram bot notifications for work orders
-- =====================================================

-- Add telegram_id column to technicians
ALTER TABLE technicians ADD COLUMN IF NOT EXISTS telegram_id TEXT;

-- Update the seed data technician with Telegram ID (if known)
-- The actual Telegram ID needs to be set manually after the technician
-- sends a message to the bot (Telegram IDs are numeric strings)
COMMENT ON COLUMN technicians.telegram_id IS 'Telegram user ID for work order notifications via Clawd bot';

-- =====================================================
-- Update the helper function to include telegram_id
-- =====================================================

CREATE OR REPLACE FUNCTION get_technician_for_equipment(p_equipment_id UUID)
RETURNS TABLE (
  technician_id UUID,
  technician_name TEXT,
  technician_email TEXT,
  technician_phone TEXT,
  technician_telegram_id TEXT,
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
    t.telegram_id,
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
      t.telegram_id,
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
