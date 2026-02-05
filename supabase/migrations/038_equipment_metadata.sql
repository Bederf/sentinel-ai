-- Equipment Metadata Schema
-- Adds extensible metadata storage for equipment including notes, network info, and device info
-- Supports both user-editable fields (notes) and auto-discovered data (DALI, BACnet, etc.)

-- Add metadata columns to equipment table
ALTER TABLE equipment
ADD COLUMN IF NOT EXISTS notes TEXT,
ADD COLUMN IF NOT EXISTS network_info JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS device_info JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS operating_data JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS commissioning_date DATE,
ADD COLUMN IF NOT EXISTS warranty_expiry DATE,
ADD COLUMN IF NOT EXISTS last_discovery TIMESTAMPTZ;

-- Create equipment_notes_history table for audit trail
CREATE TABLE IF NOT EXISTS equipment_notes_history (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  equipment_id UUID NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
  notes_before TEXT,
  notes_after TEXT,
  changed_by TEXT NOT NULL,
  changed_at TIMESTAMPTZ DEFAULT NOW(),
  change_reason TEXT
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_equipment_notes_history_equipment
ON equipment_notes_history(equipment_id);

CREATE INDEX IF NOT EXISTS idx_equipment_last_discovery
ON equipment(last_discovery);

-- Add GIN index for JSONB searching
CREATE INDEX IF NOT EXISTS idx_equipment_network_info
ON equipment USING GIN (network_info);

CREATE INDEX IF NOT EXISTS idx_equipment_device_info
ON equipment USING GIN (device_info);

-- Function to log notes changes
CREATE OR REPLACE FUNCTION log_equipment_notes_change()
RETURNS TRIGGER AS $$
BEGIN
  IF OLD.notes IS DISTINCT FROM NEW.notes THEN
    INSERT INTO equipment_notes_history (
      equipment_id,
      notes_before,
      notes_after,
      changed_by,
      change_reason
    ) VALUES (
      NEW.id,
      OLD.notes,
      NEW.notes,
      COALESCE(current_setting('app.current_user', true), 'system'),
      COALESCE(current_setting('app.change_reason', true), NULL)
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for notes audit
DROP TRIGGER IF EXISTS equipment_notes_audit ON equipment;
CREATE TRIGGER equipment_notes_audit
  AFTER UPDATE ON equipment
  FOR EACH ROW
  EXECUTE FUNCTION log_equipment_notes_change();

-- Comments for documentation
COMMENT ON COLUMN equipment.notes IS 'User-editable free-text notes about the equipment';
COMMENT ON COLUMN equipment.network_info IS 'Network configuration: IP, MAC, DALI address, BACnet device ID, etc.';
COMMENT ON COLUMN equipment.device_info IS 'Device identification: GTIN, serial, manufacturer, model, firmware, hardware version';
COMMENT ON COLUMN equipment.operating_data IS 'Operating statistics: lamp hours, power cycles, fault history';
COMMENT ON COLUMN equipment.commissioning_date IS 'Date equipment was commissioned/installed';
COMMENT ON COLUMN equipment.warranty_expiry IS 'Warranty expiration date';
COMMENT ON COLUMN equipment.last_discovery IS 'Last time device info was auto-discovered from network';

COMMENT ON TABLE equipment_notes_history IS 'Audit trail for equipment notes changes';
