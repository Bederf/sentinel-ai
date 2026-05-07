-- Add missing building config columns to sites table.
-- The buildings PUT /config endpoint references these fields but they were
-- never added after the buildings→sites rename (migration 111).

ALTER TABLE sites
  ADD COLUMN IF NOT EXISTS display_name             text,
  ADD COLUMN IF NOT EXISTS floor_labels             text[],
  ADD COLUMN IF NOT EXISTS total_desks              integer,
  ADD COLUMN IF NOT EXISTS parking_bays             integer,
  ADD COLUMN IF NOT EXISTS occupancy_capacity       integer,
  ADD COLUMN IF NOT EXISTS contact_facility_manager text,
  ADD COLUMN IF NOT EXISTS contact_emergency        text,
  ADD COLUMN IF NOT EXISTS features                 jsonb;

-- Back-fill display_name from name where null
UPDATE sites SET display_name = name WHERE display_name IS NULL;
