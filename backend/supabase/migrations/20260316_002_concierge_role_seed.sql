-- Concierge role assignment update for Thandi Dineka (Phase 161)
-- Expands her issue_domains to include hvac and maintenance for concierge dashboard.
-- Uses the fixed UUID from Phase 155 seed (20260314_004).

UPDATE role_assignment
SET issue_domains = ARRAY['space_optimisation', 'workplace_experience', 'hvac', 'maintenance']::classification_domain_enum[],
    is_active = true
WHERE id = '10000000-0000-0000-0000-000000000001';

-- Fallback: insert if seed migration was not run
INSERT INTO role_assignment
  (id, person_name, role_type, location_scope, issue_domains, is_active)
VALUES (
  '10000000-0000-0000-0000-000000000001',
  'Thandi Dineka',
  'concierge',
  'Fairlands/*/*/*',
  ARRAY['space_optimisation', 'workplace_experience', 'hvac', 'maintenance']::classification_domain_enum[],
  true
)
ON CONFLICT (id) DO NOTHING;
