-- Phase 208: Advisory Outcome Verification Pipeline
-- Add columns for capturing baseline at recommendation creation and outcome validation
-- Migration: 20250523_phase208_outcome_verification.sql

-- ============================================================================
-- RECOMMENDATIONS table additions
-- ============================================================================

-- Track baseline at creation (used for outcome verification)
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS power_at_creation_kw FLOAT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS tariff_rate_at_creation FLOAT;

-- Execution tracking
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS actual_value_set TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS actual_saving_zar FLOAT;

-- Outcome validation
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS outcome_validated BOOLEAN DEFAULT FALSE;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS outcome_notes TEXT;

-- ============================================================================
-- WORK_ORDERS table additions (link to recommendations)
-- ============================================================================

ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS recommendation_id UUID REFERENCES recommendations(id);
ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS closed_by TEXT;
ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

-- Verification queries (for reference):
-- SELECT target_equipment, outcome_validated, actual_saving_zar, executed_at FROM recommendations WHERE site_id = 'site-002' AND outcome_validated = TRUE;
-- SELECT id, recommendation_id, status FROM work_orders WHERE recommendation_id IS NOT NULL;
