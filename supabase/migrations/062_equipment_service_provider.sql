-- Add service provider fields to equipment table
-- This enables tracking which service provider is responsible for each piece of equipment

ALTER TABLE equipment
  ADD COLUMN IF NOT EXISTS service_provider_name TEXT,
  ADD COLUMN IF NOT EXISTS service_provider_email TEXT,
  ADD COLUMN IF NOT EXISTS service_provider_phone TEXT,
  ADD COLUMN IF NOT EXISTS service_provider_specialty TEXT;

-- Add comment for clarity
COMMENT ON COLUMN equipment.service_provider_name IS 'Name of the assigned service provider/technician';
COMMENT ON COLUMN equipment.service_provider_email IS 'Email address of the assigned service provider';
COMMENT ON COLUMN equipment.service_provider_phone IS 'Phone number of the assigned service provider';
COMMENT ON COLUMN equipment.service_provider_specialty IS 'Specialty of the service provider (hvac, electrical, plumbing, dali, fire, security, general)';

-- Create index for faster lookups by service provider
CREATE INDEX IF NOT EXISTS idx_equipment_service_provider_email
  ON equipment(service_provider_email);

CREATE INDEX IF NOT EXISTS idx_equipment_service_provider_specialty
  ON equipment(service_provider_specialty);
