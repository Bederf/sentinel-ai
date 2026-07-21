-- =====================================================
-- Migration: ML Model Baselines (Plan 1 - Phase 239 M2.2)
--
-- Persists trained model statistics to enable drift detection.
-- Baseline records are immutable (trigger prevents updates).
-- Feature schema hashing ensures silent substitution detection.
-- Provenance fields enable audit trail and model governance.
-- =====================================================

CREATE TABLE IF NOT EXISTS ml_model_baselines (
  model_id TEXT NOT NULL UNIQUE PRIMARY KEY,
  site_id TEXT,
  equipment_type TEXT NOT NULL,

  -- LSTM metrics (per forecast horizon + averages)
  mae_24h NUMERIC,
  mae_48h NUMERIC,
  mae_72h NUMERIC,
  mae_avg NUMERIC,
  rmse_24h NUMERIC,
  rmse_48h NUMERIC,
  rmse_72h NUMERIC,
  r2_24h NUMERIC,
  r2_48h NUMERIC,
  r2_72h NUMERIC,
  r2_avg NUMERIC,

  -- Autoencoder metrics
  threshold NUMERIC,
  val_error_mean NUMERIC,
  val_error_std NUMERIC,
  val_error_max NUMERIC,
  val_error_p95 NUMERIC,
  val_error_p99 NUMERIC,
  precision NUMERIC,
  recall NUMERIC,
  f1_score NUMERIC,

  -- Feature schema & provenance
  feature_schema_hash TEXT NOT NULL,
  feature_schema JSONB NOT NULL,
  training_dataset_hash TEXT NOT NULL,
  training_dataset_details JSONB,
  model_version TEXT NOT NULL,
  equipment_fingerprint TEXT,

  -- Lifecycle
  training_timestamp TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  provenance_status TEXT DEFAULT 'valid' CHECK (provenance_status IN ('valid', 'invalid', 'revoked', 'expired')),
  revoked_reason TEXT,

  -- Audit
  created_by TEXT DEFAULT 'system',
  updated_by TEXT,
  updated_at TIMESTAMPTZ
);

-- Index for baseline lookup: find latest valid baseline for site/equipment_type
CREATE INDEX IF NOT EXISTS idx_ml_model_baselines_lookup
  ON ml_model_baselines (site_id, equipment_type, created_at DESC)
  WHERE provenance_status = 'valid';

-- Immutability trigger: prevent updates to core training fields
CREATE OR REPLACE FUNCTION enforce_ml_model_baselines_immutability()
RETURNS TRIGGER AS $$
BEGIN
  -- Allow status changes and revocation, but not training/provenance fields
  IF OLD.training_timestamp IS DISTINCT FROM NEW.training_timestamp THEN
    RAISE EXCEPTION 'Cannot modify training_timestamp on baseline model_id=%', NEW.model_id;
  END IF;
  IF OLD.feature_schema_hash IS DISTINCT FROM NEW.feature_schema_hash THEN
    RAISE EXCEPTION 'Cannot modify feature_schema_hash on baseline model_id=%', NEW.model_id;
  END IF;
  IF OLD.training_dataset_hash IS DISTINCT FROM NEW.training_dataset_hash THEN
    RAISE EXCEPTION 'Cannot modify training_dataset_hash on baseline model_id=%', NEW.model_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ml_model_baselines_immutability ON ml_model_baselines;
CREATE TRIGGER ml_model_baselines_immutability
  BEFORE UPDATE ON ml_model_baselines
  FOR EACH ROW
  EXECUTE FUNCTION enforce_ml_model_baselines_immutability();

-- ML training audit log: track every training run
CREATE TABLE IF NOT EXISTS ml_training_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id TEXT NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('train_started', 'train_complete', 'baseline_written', 'error')),
  error_msg TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  FOREIGN KEY (model_id) REFERENCES ml_model_baselines(model_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ml_training_audit_model_id
  ON ml_training_audit_log (model_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ml_training_audit_status
  ON ml_training_audit_log (status, created_at DESC);
