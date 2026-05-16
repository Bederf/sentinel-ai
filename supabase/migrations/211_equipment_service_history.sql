-- =====================================================
-- Migration: Equipment Service History for Baseline Health
-- Creates the service history table and links to equipment
-- =====================================================

CREATE TABLE IF NOT EXISTS equipment_service_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id text NOT NULL,
  equipment_code text NOT NULL,
  equipment_type text NOT NULL,
  commissioning_date date,
  manufacturer text,
  model text,
  last_service_date date,
  service_interval_months int,
  runtime_hours numeric,
  baseline_calculation_method text NOT NULL DEFAULT 'age_only',
  confidence_notes text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  UNIQUE(site_id, equipment_code)
);

-- Link equipment to service history
ALTER TABLE equipment ADD COLUMN IF NOT EXISTS service_history_id uuid REFERENCES equipment_service_history(id);
ALTER TABLE equipment ADD COLUMN IF NOT EXISTS baseline_sourced_from text;
ALTER TABLE equipment ADD COLUMN IF NOT EXISTS health_score_confidence numeric;
