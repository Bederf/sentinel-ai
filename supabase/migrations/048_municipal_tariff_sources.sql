-- 049_municipal_tariff_sources.sql
-- Add source file path for tariff schedules

ALTER TABLE municipal_tariff_schedules
ADD COLUMN IF NOT EXISTS source_file_path TEXT;
