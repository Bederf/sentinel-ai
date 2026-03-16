-- Room Registry for Concierge Intelligence Dashboard (Phase 161)

CREATE TABLE IF NOT EXISTS room_registry (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id           text NOT NULL,
  room_id           text NOT NULL UNIQUE,
  building          text NOT NULL,
  quadrant          text,
  room_type         text NOT NULL,
  room_number       text NOT NULL,
  capacity          integer,
  floor             text,
  friendly_name     text,
  active            boolean NOT NULL DEFAULT true,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_room_registry_site ON room_registry (site_id);
CREATE INDEX idx_room_registry_building ON room_registry (building);
CREATE INDEX idx_room_registry_room_type ON room_registry (room_type);

-- Seed S001 Fairlands rooms (from Concept booking system)
INSERT INTO room_registry (site_id, room_id, building, quadrant, room_type, room_number, capacity, floor)
VALUES
  ('S001', 'FA2-1Q1-MR-01', 'FA2', '1Q1', 'MR', '01', null, 'Level 1'),
  ('S001', 'FA2-1Q1-MR-02', 'FA2', '1Q1', 'MR', '02', null, 'Level 1'),
  ('S001', 'FA2-1Q1-MR-05', 'FA2', '1Q1', 'MR', '05', null, 'Level 1'),
  ('S001', 'FA2-1Q1-MR-06', 'FA2', '1Q1', 'MR', '06', null, 'Level 1'),
  ('S001', 'FA2-1Q1-PR-01', 'FA2', '1Q1', 'PR', '01', null, 'Level 1'),
  ('S001', 'FA2-1Q2-MR-08', 'FA2', '1Q2', 'MR', '08', null, 'Level 1'),
  ('S001', 'FA2-1Q2-MR-10', 'FA2', '1Q2', 'MR', '10', null, 'Level 1')
ON CONFLICT (room_id) DO NOTHING;

-- RLS policy
ALTER TABLE room_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY room_registry_read ON room_registry FOR SELECT USING (true);
