-- Correlation & Issue Intelligence Layer — Seed Fairlands Personas
-- Phase 155-01, Task 4
-- Fixed UUIDs for test reproducibility. Idempotent via ON CONFLICT DO NOTHING.

INSERT INTO role_assignment (id, person_name, role_type, location_scope, issue_domains)
VALUES
  (
    '10000000-0000-0000-0000-000000000001',
    'Thandi Dineka',
    'concierge',
    'Fairlands/*/*/*',
    ARRAY['space_optimisation', 'workplace_experience']::classification_domain_enum[]
  ),
  (
    '10000000-0000-0000-0000-000000000002',
    'Keryn Norman',
    'management',
    'Fairlands/*/*/*',
    ARRAY['space_optimisation', 'workplace_experience', 'hvac', 'maintenance']::classification_domain_enum[]
  ),
  (
    '10000000-0000-0000-0000-000000000003',
    'Greg Temlett',
    'management',
    'Fairlands/*/*/*',
    ARRAY['space_optimisation', 'workplace_experience']::classification_domain_enum[]
  ),
  (
    '10000000-0000-0000-0000-000000000004',
    'Facilities Manager Fairlands',
    'facilities',
    'Fairlands/*/*/*',
    ARRAY['hvac', 'maintenance', 'energy']::classification_domain_enum[]
  )
ON CONFLICT (id) DO NOTHING;
