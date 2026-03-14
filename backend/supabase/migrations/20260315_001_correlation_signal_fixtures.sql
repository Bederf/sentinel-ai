-- Phase 156-01: Seed 9 Fairlands email signals and 13 entities as test fixtures.
-- Idempotent: ON CONFLICT (id) DO NOTHING.

-- ============================================================================
-- 9 Fairlands signals (f1000000-0000-0000-0000-000000000001 .. 009)
-- ============================================================================

INSERT INTO signal (id, source_module, signal_type, severity, confidence, location_ref, resolution_state, is_managed, site_resolution_status, raw_content, metadata, created_at)
VALUES
  -- Signal 1: Shaun Grose complaint about room booking difficulty
  ('f1000000-0000-0000-0000-000000000001', 'email_helpdesk', 'complaint_email', 'medium', 0.85,
   'Fairlands/FA1/1Q4/MR10', 'active', false, 'unresolved',
   'Initial complaint about room booking difficulty at FA1-1Q4-MR10 from Shaun Grose.',
   '{"sender": "Shaun Grose", "recipients": ["helpdesk@fairlands.co.za"], "subject": "Room booking difficulty"}'::jsonb,
   '2026-01-05 09:00:00+02'),

  -- Signal 2: Lisa Moyo complaint about booking rooms
  ('f1000000-0000-0000-0000-000000000002', 'email_helpdesk', 'complaint_email', 'medium', 0.82,
   'Fairlands/FA2/2Q1/MR03', 'active', false, 'unresolved',
   'Second complaint about inability to book meeting rooms at FA2-2Q1-MR03 from Lisa Moyo.',
   '{"sender": "Lisa Moyo", "recipients": ["helpdesk@fairlands.co.za"], "subject": "Cannot book meeting rooms"}'::jsonb,
   '2026-01-12 10:30:00+02'),

  -- Signal 3: Thandi Dineka observation about block bookings
  ('f1000000-0000-0000-0000-000000000003', 'email_helpdesk', 'observation_email', 'low', 0.78,
   'Fairlands/FA1/1Q4/*', 'active', false, 'unresolved',
   'Concierge Thandi Dineka confirms pattern of block bookings observed at FA1 Floor 1 Quadrant 4.',
   '{"sender": "Thandi Dineka", "recipients": ["helpdesk@fairlands.co.za"], "subject": "Pattern observed - block bookings"}'::jsonb,
   '2026-01-15 14:00:00+02'),

  -- Signal 4: James Naidoo complaint about training room
  ('f1000000-0000-0000-0000-000000000004', 'email_helpdesk', 'complaint_email', 'medium', 0.80,
   'Fairlands/FA1/1Q2/TR01', 'active', false, 'unresolved',
   'Complaint about training room unavailability at FA1-1Q2-TR01 from James Naidoo.',
   '{"sender": "James Naidoo", "recipients": ["helpdesk@fairlands.co.za"], "subject": "Training room unavailable"}'::jsonb,
   '2026-01-28 11:15:00+02'),

  -- Signal 5: Keryn Norman escalation to Greg Temlett
  ('f1000000-0000-0000-0000-000000000005', 'email_escalation', 'escalation_email', 'high', 0.92,
   'Fairlands/*/*/*', 'active', false, 'unresolved',
   'Management escalation from Keryn Norman to Greg Temlett about room booking crisis across Fairlands campus.',
   '{"sender": "Keryn Norman", "recipients": ["Greg Temlett", "helpdesk@fairlands.co.za"], "subject": "Escalation: Room booking crisis"}'::jsonb,
   '2026-02-03 08:30:00+02'),

  -- Signal 6: Greg Temlett intake requesting investigation
  ('f1000000-0000-0000-0000-000000000006', 'email_helpdesk', 'intake_email', 'medium', 0.75,
   'Fairlands/*/*/*', 'active', false, 'unresolved',
   'Greg Temlett acknowledges escalation and requests investigation into room booking issues.',
   '{"sender": "Greg Temlett", "recipients": ["Keryn Norman", "helpdesk@fairlands.co.za"], "subject": "Re: Escalation - requesting investigation"}'::jsonb,
   '2026-02-05 16:45:00+02'),

  -- Signal 7: Thandi Dineka follow-up with specific bookers identified
  ('f1000000-0000-0000-0000-000000000007', 'email_helpdesk', 'observation_email', 'medium', 0.88,
   'Fairlands/FA1/1Q4/*', 'active', false, 'unresolved',
   'Follow-up from Thandi Dineka identifying specific block bookers at FA1 Floor 1 Quadrant 4.',
   '{"sender": "Thandi Dineka", "recipients": ["helpdesk@fairlands.co.za"], "subject": "Follow-up: specific block bookers identified"}'::jsonb,
   '2026-02-10 09:20:00+02'),

  -- Signal 8: Keryn Norman action request for policy change
  ('f1000000-0000-0000-0000-000000000008', 'email_escalation', 'action_request_email', 'high', 0.90,
   'Fairlands/*/*/*', 'active', false, 'unresolved',
   'Keryn Norman requests booking policy change to address room availability issues.',
   '{"sender": "Keryn Norman", "recipients": ["Greg Temlett", "facilities@fairlands.co.za"], "subject": "Request: booking policy change"}'::jsonb,
   '2026-02-20 13:00:00+02'),

  -- Signal 9: Greg Temlett executive escalation
  ('f1000000-0000-0000-0000-000000000009', 'email_escalation', 'escalation_email', 'critical', 0.95,
   'Fairlands/*/*/*', 'active', false, 'unresolved',
   'Executive escalation from Greg Temlett about unresolved room booking issue across Fairlands.',
   '{"sender": "Greg Temlett", "recipients": ["executive@fairlands.co.za", "Keryn Norman"], "subject": "Executive escalation: unresolved room booking issue"}'::jsonb,
   '2026-03-06 14:20:00+02')

ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- 13 entities linked to signals (e1000000-0000-0000-0000-000000000001 .. 013)
-- ============================================================================

INSERT INTO entity (id, entity_type, entity_value, signal_id)
VALUES
  -- People
  ('e1000000-0000-0000-0000-000000000001', 'person', 'Shaun Grose',   'f1000000-0000-0000-0000-000000000001'),
  ('e1000000-0000-0000-0000-000000000002', 'person', 'Lisa Moyo',     'f1000000-0000-0000-0000-000000000002'),
  ('e1000000-0000-0000-0000-000000000003', 'person', 'Thandi Dineka', 'f1000000-0000-0000-0000-000000000003'),
  ('e1000000-0000-0000-0000-000000000004', 'person', 'James Naidoo',  'f1000000-0000-0000-0000-000000000004'),
  ('e1000000-0000-0000-0000-000000000005', 'person', 'Keryn Norman',  'f1000000-0000-0000-0000-000000000005'),
  ('e1000000-0000-0000-0000-000000000006', 'person', 'Greg Temlett',  'f1000000-0000-0000-0000-000000000006'),

  -- Rooms
  ('e1000000-0000-0000-0000-000000000007', 'room', 'FA1-1Q4-MR10',   'f1000000-0000-0000-0000-000000000001'),
  ('e1000000-0000-0000-0000-000000000008', 'room', 'FA2-2Q1-MR03',   'f1000000-0000-0000-0000-000000000002'),
  ('e1000000-0000-0000-0000-000000000009', 'room', 'FA1-1Q2-TR01',   'f1000000-0000-0000-0000-000000000004'),

  -- Buildings
  ('e1000000-0000-0000-0000-000000000010', 'building', 'Fairlands 1', 'f1000000-0000-0000-0000-000000000001'),
  ('e1000000-0000-0000-0000-000000000011', 'building', 'Fairlands 2', 'f1000000-0000-0000-0000-000000000002'),

  -- Booking ref
  ('e1000000-0000-0000-0000-000000000012', 'booking_ref', 'Block booking', 'f1000000-0000-0000-0000-000000000003'),

  -- Work order
  ('e1000000-0000-0000-0000-000000000013', 'work_order', 'Room availability', 'f1000000-0000-0000-0000-000000000005')

ON CONFLICT (id) DO NOTHING;
