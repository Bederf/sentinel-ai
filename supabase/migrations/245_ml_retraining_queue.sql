-- Phase 241 M2.4 Plan 1: Drift-Driven Retraining queue
-- Queue of retraining requests produced when drift is detected, consumed
-- by the queue processor (Plan 2). Dedupe/rate-limit enforced in
-- app/ml/models/retraining_queue.py enqueue().

CREATE TABLE IF NOT EXISTS ml_retraining_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL,
  equipment_type TEXT NOT NULL,
  model_type TEXT NOT NULL,           -- 'lstm' | 'autoencoder'
  trigger_reason TEXT NOT NULL,       -- 'drift_detected' | 'unevaluable' | 'age_stale'
  drift_verdict TEXT,
  baseline_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','completed','failed','escalated')),
  attempts INT NOT NULL DEFAULT 0,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ml_retraining_queue_pending
  ON ml_retraining_queue(status, created_at) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_ml_retraining_queue_dedupe
  ON ml_retraining_queue(site_id, equipment_type, model_type, status);
