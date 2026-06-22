ALTER TABLE documents ADD COLUMN IF NOT EXISTS technician_name text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS contractor_vendor text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS sign_off_name text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS inspector_name text;
