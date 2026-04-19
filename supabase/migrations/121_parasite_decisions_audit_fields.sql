-- Migration 121: Parasite Decision Audit Fields
-- Adds forensic audit columns to parasite_decisions for Tier3 auto-execute accountability:
--   - audit_level: classifies routine vs. critical decisions
--   - context_snapshot: full LLM input context for critical decisions
--
-- Routine decisions: metadata only (timestamp, value, confidence)
-- Critical decisions: full context snapshot (system prompt, active COVs, safety rules evaluated)
--
-- Apply AFTER 120_ml_hours_persist.sql

BEGIN;

ALTER TABLE parasite_decisions
ADD COLUMN IF NOT EXISTS audit_level TEXT
  CHECK (audit_level IN ('routine', 'critical')),
ADD COLUMN IF NOT EXISTS context_snapshot JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN parasite_decisions.audit_level IS
  'Decision sensitivity: routine (metadata only) or critical (full context snapshot preserved)';
COMMENT ON COLUMN parasite_decisions.context_snapshot IS
  'Full LLM input context at decision time for critical actions: system prompt, active COVs, virtual views, safety rules evaluated';

COMMIT;
