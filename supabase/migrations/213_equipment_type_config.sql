-- =====================================================
-- Migration 213: Equipment type config (health scoreability)
-- Runtime overrides for health scoring by equipment type.
-- Empty by default — falls back to hardcoded config.
-- =====================================================

CREATE TABLE IF NOT EXISTS equipment_type_config (
  equipment_type text PRIMARY KEY,
  scoreable boolean NOT NULL,
  scoring_method text,
  reason text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);
