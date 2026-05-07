-- Migration: hourly energy consumption (recorded_at primary time key)
-- Replaces midnight-only flush with hourly upsert on (site_id, recorded_at)
-- Run: psql $SUPABASE_DB_URL -f backend/supabase/migrations/20260429_003_hourly_energy_recorded_at.sql

-- Step 1: Add recorded_at column (nullable initially)
ALTER TABLE energy_consumption_history
  ADD COLUMN recorded_at TIMESTAMPTZ;

-- Step 2: Backfill recorded_at from date field
-- All existing records are midnight of their date (from legacy midnight flush)
UPDATE energy_consumption_history
  SET recorded_at = (date::DATE || ' 00:00:00')::TIMESTAMPTZ
  WHERE recorded_at IS NULL;

-- Step 3: Set NOT NULL now that all rows have values
ALTER TABLE energy_consumption_history
  ALTER COLUMN recorded_at SET NOT NULL;

-- Step 4: Create new unique index for hourly upsert
CREATE UNIQUE INDEX CONCURRENTLY energy_consumption_history_site_id_recorded_at_idx
  ON energy_consumption_history (site_id, recorded_at);

-- Step 5: Drop old (site_id, date) unique index (not a constraint)
DROP INDEX IF EXISTS idx_energy_consumption_history_building_date_unique;

-- Step 6: Notify PGRST to refresh cache
NOTIFY pgrst, 'reload';
