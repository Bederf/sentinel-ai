-- Migration: 215_add_technicians_site_id
-- Add site_id to technicians table and populate from Supabase
-- Removes need for JSON fallback files

ALTER TABLE technicians ADD COLUMN IF NOT EXISTS site_id TEXT;
ALTER TABLE technicians ADD COLUMN IF NOT EXISTS specialty TEXT;
ALTER TABLE technicians ADD COLUMN IF NOT EXISTS whatsapp_number TEXT;

-- Update John Smith (TECH-001) with site_id for S002
UPDATE technicians SET site_id = 'site-002', specialty = 'electrical' WHERE code = 'TECH-001';

NOTIFY pgrst, 'reload schema';
