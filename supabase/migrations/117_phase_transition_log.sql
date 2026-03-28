-- Fix audit_log.action CHECK constraint to include "phase_transition"
ALTER TABLE audit_log
  DROP CONSTRAINT IF EXISTS audit_log_action_check;

ALTER TABLE audit_log
  ADD CONSTRAINT audit_log_action_check
  CHECK (action IN (
    'create','update','delete','login','logout',
    'approve','reject','execute','phase_transition'
  ));

-- Dedicated immutable audit table for phase transitions
CREATE TABLE IF NOT EXISTS phase_transition_log (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id      TEXT NOT NULL REFERENCES sites(code),
  from_phase   TEXT,
  to_phase     TEXT NOT NULL,
  changed_by   TEXT NOT NULL,          -- user email or "system"
  reason       TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Immutability: no UPDATE or DELETE
CREATE RULE phase_transition_log_no_update AS
  ON UPDATE TO phase_transition_log DO INSTEAD NOTHING;
CREATE RULE phase_transition_log_no_delete AS
  ON DELETE TO phase_transition_log DO INSTEAD NOTHING;

-- RLS: service role only (no tenant read)
ALTER TABLE phase_transition_log ENABLE ROW LEVEL SECURITY;
