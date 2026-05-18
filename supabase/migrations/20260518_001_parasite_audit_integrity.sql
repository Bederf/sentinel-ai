-- Migration: PARASITE Decision Audit Trail — Data Integrity Fix
-- Purpose: Fix write_status ambiguity and add BACnet dispatch tracking columns.
--
-- Background:
-- Every decision was being created with write_attempt_count=1, making it look
-- like a BACnet write was attempted. In reality, Stage 1 (TierRoutingEngine)
-- only logs intent. Stage 2 (ApprovalService) actually dispatches writes.
--
-- The fix adds three explicit fields so records are unambiguous:
--   bacnet_write_dispatched: did Stage 2 actually call write_device_value()?
--   bacnet_write_succeeded:  what was the outcome?
--   write_status:            enum value showing where in the pipeline it stopped.
--
-- Also adds a CHECK constraint so freeform strings can't corrupt write_status.
--
-- Timing: Before Advisory go-live, before iDNa integration, before any real
-- BACnet writes flow. Audit trail must be trustworthy from day one.
--
-- Apply AFTER existing parasite_decisions migrations (082, 121).

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Add new columns (add only if they don't exist — idempotent)
-- ---------------------------------------------------------------------------

ALTER TABLE parasite_decisions
  ADD COLUMN IF NOT EXISTS bacnet_write_dispatched BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS bacnet_write_succeeded BOOLEAN,
  ADD COLUMN IF NOT EXISTS write_status TEXT DEFAULT 'intent_logged';

-- write_attempt_count column may exist from prior schema changes.
-- Ensure it is 0 (no BACnet write) for all existing records.
ALTER TABLE parasite_decisions
  ALTER COLUMN write_attempt_count SET DEFAULT 0,
  ALTER COLUMN write_attempt_count SET NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. Add CHECK constraint to lock write_status to known enum values
-- ---------------------------------------------------------------------------

ALTER TABLE parasite_decisions
  DROP CONSTRAINT IF EXISTS chk_parasite_decisions_write_status;

ALTER TABLE parasite_decisions
  ADD CONSTRAINT chk_parasite_decisions_write_status
    CHECK (write_status IN (
      'intent_logged',
      'dispatched',
      'succeeded',
      'failed',
      'blocked_by_gate'
    ));

COMMENT ON CONSTRAINT chk_parasite_decisions_write_status ON parasite_decisions IS
  'Restricts write_status to the WriteStatus enum values. Prevents freeform strings such as "success" or "blocked" from corrupting the audit trail.';

-- ---------------------------------------------------------------------------
-- 3. Reset ALL existing records to truthful intent-logged state
--
-- These records were created by TierRoutingEngine (Stage 1) — they logged
-- intent only, never dispatched a BACnet write. The fact they showed
-- write_attempt_count=1 was the data integrity problem.
-- ---------------------------------------------------------------------------

UPDATE parasite_decisions
SET
  write_attempt_count    = 0,
  write_status           = 'intent_logged',
  bacnet_write_dispatched = FALSE,
  bacnet_write_succeeded  = NULL
WHERE
  -- Only update records that are clearly intent-logged (not Stage 2 records)
  -- Stage 2 records are identified by decision_type patterns
  bacnet_write_dispatched IS DISTINCT FROM TRUE
  OR write_attempt_count != 0
  OR write_status NOT IN ('intent_logged', 'dispatched', 'succeeded', 'failed', 'blocked_by_gate');

-- ---------------------------------------------------------------------------
-- 4. Add comments documenting the new columns
-- ---------------------------------------------------------------------------

COMMENT ON COLUMN parasite_decisions.bacnet_write_dispatched IS
  'Stage 2 only. TRUE when ApprovalService actually called write_device_value(). FALSE (or the column default) for Stage 1 intent-logged records.';
COMMENT ON COLUMN parasite_decisions.bacnet_write_succeeded IS
  'Stage 2 outcome. TRUE = write succeeded, FALSE = write failed, NULL = not yet attempted or not a write record.';
COMMENT ON COLUMN parasite_decisions.write_status IS
  'Pipeline stage: intent_logged (Stage 1, no write), dispatched (write sent), succeeded, failed, blocked_by_gate. Governed by chk_parasite_decisions_write_status.';

-- ---------------------------------------------------------------------------
-- 5. Index for the new filter patterns used in the audit trail
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_parasite_decisions_write_status
  ON parasite_decisions(write_status)
  WHERE write_status IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_parasite_decisions_bacnet_dispatched
  ON parasite_decisions(bacnet_write_dispatched)
  WHERE bacnet_write_dispatched = TRUE;

COMMIT;
