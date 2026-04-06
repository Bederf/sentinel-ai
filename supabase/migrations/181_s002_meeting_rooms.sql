-- Add S002 (Sandton) meeting rooms for concierge intelligence
-- L0, L1, L2 floors — 2 meeting rooms per floor

INSERT INTO public.room_registry (site_id, room_id, building, quadrant, room_type, room_number, capacity, floor, friendly_name, active)
VALUES
  ('site-002', 'L0-MR01', 'Sandton', NULL, 'meeting', 'L0-MR01', NULL, 'L0', 'L0 Meeting Room 1', true),
  ('site-002', 'L0-MR02', 'Sandton', NULL, 'meeting', 'L0-MR02', NULL, 'L0', 'L0 Meeting Room 2', true),
  ('site-002', 'L1-MR01', 'Sandton', NULL, 'meeting', 'L1-MR01', NULL, 'L1', 'L1 Meeting Room 1', true),
  ('site-002', 'L1-MR02', 'Sandton', NULL, 'meeting', 'L1-MR02', NULL, 'L1', 'L1 Meeting Room 2', true),
  ('site-002', 'L2-MR01', 'Sandton', NULL, 'meeting', 'L2-MR01', NULL, 'L2', 'L2 Meeting Room 1', true),
  ('site-002', 'L2-MR02', 'Sandton', NULL, 'meeting', 'L2-MR02', NULL, 'L2', 'L2 Meeting Room 2', true)
ON CONFLICT (room_id) DO UPDATE
  SET friendly_name = EXCLUDED.friendly_name,
      floor        = EXCLUDED.floor,
      active       = EXCLUDED.active;
