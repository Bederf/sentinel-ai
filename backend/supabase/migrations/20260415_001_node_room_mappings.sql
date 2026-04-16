-- Phase 161-01: node_room_mappings — Supabase authority for ESP32→room mapping
-- Replaces backend/app/data/space/node_room_mapping.json
-- Nodes: node_001 (MR27 meeting room), node_002 (FR25 focus room)
-- Applied: 2026-04-15

CREATE TABLE IF NOT EXISTS node_room_mappings (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id           text NOT NULL UNIQUE,
  room_code         text NOT NULL,
  site_id           text NOT NULL,
  room_type         text NOT NULL DEFAULT 'meeting',
  active            boolean NOT NULL DEFAULT true,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_node_room_mappings_node_id ON node_room_mappings (node_id);
CREATE INDEX IF NOT EXISTS idx_node_room_mappings_site ON node_room_mappings (site_id);

ALTER TABLE node_room_mappings ENABLE ROW LEVEL SECURITY;

CREATE POLICY node_room_mappings_read ON node_room_mappings FOR SELECT USING (true);
CREATE POLICY node_room_mappings_admin ON node_room_mappings FOR ALL USING (true);

-- Seed existing nodes
INSERT INTO node_room_mappings (node_id, room_code, site_id, room_type) VALUES
  ('node_001', 'FA2-1Q4-MR27', 'site-002', 'meeting'),
  ('node_002', 'FA2-1Q4-FR25', 'site-002', 'focus')
ON CONFLICT (node_id) DO NOTHING;
