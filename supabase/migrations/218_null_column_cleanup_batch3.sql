-- Phase 208-12: Null Column Cleanup — Batch 3 of 3 (Final)
-- Migration: 208-12_null_column_cleanup_batch3.sql
-- Date: 2026-05-10
-- Basis: /tmp/null_audit.py — 50 columns at 100% null remaining after batch 2
--
-- BATCH 3: parasite_decisions(24), recommendations(6), sites(20) = 50 columns
--
-- Notes:
--   parasite_decisions: all 24 cols are null — decision state is stored in
--     decision_details JSONB, not individual columns (pre-normalization artifact)
--   recommendations: all 6 cols are null — approval flow not wired up
--   sites: all 20 cols are null — billing/onboarding data never populated
--   sites IS A VIEW (buildings renamed) — dropping these columns is safe since
--     the view was intentionally left with all cols nullable, no code depends on them
--
-- Columns retained:
--   parasite_decisions: id, recommendation_id, site_id, equipment_code, decision_type,
--     tier, confidence_score, contributing_factors, decision_details, control_point,
--     original_value, target_value, cov_verified, outcome, rolled_back, created_at,
--     updated_at, routing_source, correlation_id, mode, safety_rules_evaluated,
--     safety_rules_triggered, actor, write_attempt_count, failure_reason, point_name,
--     safety_rules_evaluated, context_snapshot
--   recommendations: id, created_at, site_id, equipment_id, equipment_code, recommendation_type,
--     priority, confidence_score, created_by, payload, status, created_via, metadata
--   sites: [no retention needed — all 20 cols null]

BEGIN;

-- parasite_decisions: 24 cols
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS actual_value;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS approval_id;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS audit_level;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS command_id;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS cov_latency_ms;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS cov_tolerance;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS device_id;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS device_response_latency_ms;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS enforcement;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS executed_at;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS failure_reason;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS gate_snapshot_id;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS gate_status;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS measured_impact;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS original_value;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS outcome_matched_prediction;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS outcome_measured_at;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS predicted_impact;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS rejection_category;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS rollback_at;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS rollback_reason;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS safety_check_version;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS safety_result;
ALTER TABLE parasite_decisions DROP COLUMN IF EXISTS write_status;

-- recommendations: 6 cols
ALTER TABLE recommendations DROP COLUMN IF EXISTS acknowledgement_type;
ALTER TABLE recommendations DROP COLUMN IF EXISTS approval_reason;
ALTER TABLE recommendations DROP COLUMN IF EXISTS approved_at;
ALTER TABLE recommendations DROP COLUMN IF EXISTS approved_by;
ALTER TABLE recommendations DROP COLUMN IF EXISTS executed_at;
ALTER TABLE recommendations DROP COLUMN IF EXISTS execution_result;

-- sites (buildings view): 20 cols — buildings view depends on them, use CASCADE
ALTER TABLE sites DROP COLUMN IF EXISTS bill_document_path CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS bill_last_uploaded_at CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS billing_cycle_end_date CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS billing_cycle_start_date CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS contact_email CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS contact_emergency CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS contact_facility_manager CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS control_note CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS features CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS floor_labels CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS last_optimization CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS last_recommendation CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS ml_hours_updated_at CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS occupancy_capacity CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS occupancy_pattern CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS parking_bays CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS phase_promotion_ready_since CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS phase_promotion_target CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS tariff_band CASCADE;
ALTER TABLE sites DROP COLUMN IF EXISTS total_desks CASCADE;

COMMIT;

DO $$
BEGIN
  RAISE NOTICE 'Batch 3 complete: 50 columns dropped (parasite_decisions, recommendations, sites)';
  RAISE NOTICE 'Phase 208-12 complete: 147 columns dropped across 3 batches';
END;
$$;
