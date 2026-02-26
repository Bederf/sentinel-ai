-- Migration: PARASITE Decision Audit Trail
-- Purpose: Record every autonomous decision PARASITE makes, including confidence scores, contributing factors, execution details, and outcomes
-- Phase: 80-parasite-implementation-gaps

-- Create parasite_decisions table (complete decision audit trail)
CREATE TABLE IF NOT EXISTS parasite_decisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recommendation_id UUID,  -- Foreign key to recommendations table if from recommendation
  site_id TEXT NOT NULL,
  equipment_code TEXT NOT NULL,
  decision_type TEXT NOT NULL CHECK (decision_type IN ('tier1_advisory', 'tier2_supervised', 'tier3_auto_execute', 'auto_rollback', 'cov_failure', 'outcome_negative')),
  tier TEXT NOT NULL CHECK (tier IN ('tier1', 'tier2', 'tier3')),

  -- AI Confidence and Context
  confidence_score FLOAT,  -- ML confidence that triggered this tier routing (0.0 - 1.0)
  contributing_factors JSONB DEFAULT '{}',  -- What the AI saw (equipment health, alerts, conditions, thresholds)
  decision_details JSONB DEFAULT '{}',  -- What it decided (target_value, control_point, reason, options considered)

  -- Device Write Details
  control_point TEXT,  -- Point name (e.g., 'chw_setpoint', 'discharge_temp')
  original_value TEXT,  -- Value before change (for rollback)
  target_value TEXT,  -- Value PARASITE wants to set
  actual_value TEXT,  -- Value read back after change (COV verification)
  cov_verified BOOLEAN DEFAULT FALSE,  -- Did device accept the change?

  -- Outcome Measurement
  outcome JSONB DEFAULT '{}',  -- Measured outcome after measurement window (e.g., energy saved, comfort impact)
  outcome_matched_prediction BOOLEAN,  -- Did outcome match what AI expected?

  -- Timing
  executed_at TIMESTAMPTZ,  -- When device write happened
  outcome_measured_at TIMESTAMPTZ,  -- When outcome was evaluated (executed_at + outcome_window)

  -- Rollback Tracking
  rolled_back BOOLEAN DEFAULT FALSE,
  rollback_reason TEXT,
  rollback_at TIMESTAMPTZ,

  -- Standard timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_parasite_decisions_site ON parasite_decisions(site_id);
CREATE INDEX IF NOT EXISTS idx_parasite_decisions_equipment ON parasite_decisions(equipment_code);
CREATE INDEX IF NOT EXISTS idx_parasite_decisions_tier ON parasite_decisions(tier);
CREATE INDEX IF NOT EXISTS idx_parasite_decisions_created ON parasite_decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_parasite_decisions_type ON parasite_decisions(decision_type);

-- Add composite indexes for common filter combinations
CREATE INDEX IF NOT EXISTS idx_parasite_decisions_site_tier ON parasite_decisions(site_id, tier);
CREATE INDEX IF NOT EXISTS idx_parasite_decisions_equipment_tier ON parasite_decisions(equipment_code, tier);
CREATE INDEX IF NOT EXISTS idx_parasite_decisions_site_created ON parasite_decisions(site_id, created_at DESC);

-- Add table documentation
COMMENT ON TABLE parasite_decisions IS 'Complete audit trail of autonomous PARASITE decisions including confidence scores, execution details, COV verification, and outcome measurement for compliance and ML training';
COMMENT ON COLUMN parasite_decisions.recommendation_id IS 'Optional foreign key to recommendations table if decision originated from a recommendation';
COMMENT ON COLUMN parasite_decisions.decision_type IS 'Type of decision: tier1_advisory (read-only), tier2_supervised (needs approval), tier3_auto_execute (autonomous), auto_rollback (initiated by system), cov_failure (COV verification failed), outcome_negative (outcome did not match prediction)';
COMMENT ON COLUMN parasite_decisions.tier IS 'Tier level: tier1 (advisory only), tier2 (supervised with approval), tier3 (autonomous execution)';
COMMENT ON COLUMN parasite_decisions.confidence_score IS 'ML confidence score (0.0-1.0) that triggered this tier routing decision';
COMMENT ON COLUMN parasite_decisions.contributing_factors IS 'Context the AI considered: equipment health score, active alerts, recent prediction history, current temperature, setpoint, occupancy, tariff, etc.';
COMMENT ON COLUMN parasite_decisions.decision_details IS 'What the AI decided and why: target_value, control_point, reasoning, alternative options considered and rejected';
COMMENT ON COLUMN parasite_decisions.original_value IS 'Device value before write - stored for potential rollback';
COMMENT ON COLUMN parasite_decisions.actual_value IS 'Value read back from device after write (COV verification result)';
COMMENT ON COLUMN parasite_decisions.cov_verified IS 'Boolean: did device read-back confirm the write was accepted?';
COMMENT ON COLUMN parasite_decisions.outcome IS 'Measured outcomes after measurement window (e.g., energy_saved_kwh, temperature_achieved, comfort_index, peak_demand_reduction)';
COMMENT ON COLUMN parasite_decisions.outcome_matched_prediction IS 'Did actual outcome match what AI predicted when making the decision?';
