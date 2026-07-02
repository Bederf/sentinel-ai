-- PLAN-162B: Create trust_history table with equipment_id support
-- Enables bulk queries of trust profiles for all points on an equipment.

CREATE TABLE IF NOT EXISTS trust_history (
  point_id                text NOT NULL,
  site_id                 text NOT NULL,
  equipment_id            text NOT NULL DEFAULT '',
  stability_days          integer NOT NULL DEFAULT 0,
  validation_runs         integer NOT NULL DEFAULT 0,
  successful_actions      integer NOT NULL DEFAULT 0,
  failed_actions          integer NOT NULL DEFAULT 0,
  last_validation_error   timestamptz,
  last_successful_action  timestamptz,
  trust_score             double precision NOT NULL DEFAULT 0.0,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (point_id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_trust_history_equipment ON trust_history (equipment_id);
