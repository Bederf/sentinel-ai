-- Migration: ml_model_baselines table for Plan 1 (Phase 239 M2.2 Real Drift Detection)
-- Captures trained model statistics for drift detection

CREATE TABLE IF NOT EXISTS ml_model_baselines (
    model_id TEXT PRIMARY KEY,
    site_id TEXT,  -- NULL for global models, site code for site-scoped models
    equipment_type TEXT NOT NULL,

    -- Feature and training metadata
    feature_schema_hash TEXT NOT NULL,  -- MD5(sorted(features + target))
    feature_schema JSONB,  -- ["chw_supply_temp", "chw_return_temp", ...]
    training_dataset_hash TEXT,  -- MD5 of training dataset metadata
    training_dataset_details JSONB,  -- data_source, real_data_start/end, real_hours_available, etc.
    model_version TEXT,  -- Git commit hash or "demo"
    equipment_fingerprint TEXT,  -- MD5(equipment_type + features + target)
    training_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by TEXT DEFAULT 'system',
    provenance_status TEXT DEFAULT 'valid',  -- valid, archived, invalidated

    -- LSTM-specific metrics (NULL for non-LSTM models)
    mae_24h FLOAT,
    mae_48h FLOAT,
    mae_72h FLOAT,
    mae_avg FLOAT,
    rmse_24h FLOAT,
    rmse_48h FLOAT,
    rmse_72h FLOAT,
    r2_24h FLOAT,
    r2_48h FLOAT,
    r2_72h FLOAT,
    r2_avg FLOAT,

    -- Autoencoder-specific metrics (NULL for non-AE models)
    threshold FLOAT,
    val_error_mean FLOAT,
    val_error_std FLOAT,
    val_error_max FLOAT,
    val_error_p95 FLOAT,
    val_error_p99 FLOAT,
    precision FLOAT,
    recall FLOAT,
    f1_score FLOAT
);

-- Index for queries by equipment_type + site_id + provenance_status, ordered by creation
CREATE INDEX IF NOT EXISTS idx_ml_baselines_lookup
    ON ml_model_baselines(equipment_type, site_id, provenance_status, created_at DESC);

-- Composite index for common drift detection query patterns
CREATE INDEX IF NOT EXISTS idx_ml_baselines_site_equipment
    ON ml_model_baselines(site_id, equipment_type, created_at DESC)
    WHERE provenance_status = 'valid';

-- Enable row-level security if needed
ALTER TABLE ml_model_baselines ENABLE ROW LEVEL SECURITY;

-- Create immutability trigger: prevent updates to provenance_status after insertion
CREATE OR REPLACE FUNCTION trigger_prevent_baseline_update()
RETURNS TRIGGER AS $$
BEGIN
    -- Allow initial insertion, but prevent updates
    IF TG_OP = 'UPDATE' THEN
        IF OLD.provenance_status IS DISTINCT FROM NEW.provenance_status THEN
            RAISE EXCEPTION 'Cannot modify provenance_status after insertion. Use new baseline instead.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS baseline_immutability_trigger ON ml_model_baselines;
CREATE TRIGGER baseline_immutability_trigger
    BEFORE UPDATE ON ml_model_baselines
    FOR EACH ROW
    EXECUTE FUNCTION trigger_prevent_baseline_update();

-- Add comment documenting the table
COMMENT ON TABLE ml_model_baselines IS 'Trained model baseline statistics for drift detection. Immutable after creation (provenance_status cannot be updated). Used by Plan 2 (Phase 239 M2.2) to compare inference errors against trained baselines.';
COMMENT ON COLUMN ml_model_baselines.feature_schema_hash IS 'MD5(sorted(features + target)) to detect feature schema changes. Mismatch triggers FEATURE_MISMATCH verdict.';
COMMENT ON COLUMN ml_model_baselines.provenance_status IS 'valid = current baseline; archived = superseded; invalidated = schema mismatch detected. Immutable after insertion.';
