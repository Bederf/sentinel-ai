-- Phase 68-03: ML Model Registry and Confidence Thresholds
--
-- Creates database-driven ML model registry to support:
-- - Equipment-specific model assignment
-- - Confidence threshold enforcement (Tier 2: advisory, Tier 3: auto-execute)
-- - Model versioning and status tracking
-- - Per-equipment-type configuration without code changes
--
-- Architecture:
-- - ml_models: Global trained model versions (one LSTM_CHILLER shared by all buildings)
-- - model_thresholds: Confidence thresholds (equipment_type → tier minimums)
-- - Equipment links to models via equipment_type

-- ============================================================================
-- TABLE: ml_models
-- Purpose: Store trained ML model versions with metrics and paths
-- ============================================================================

CREATE TABLE IF NOT EXISTS ml_models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Model identification
  model_id TEXT UNIQUE NOT NULL,
    -- e.g., "lstm_chiller_20260209_212308"
    -- Format: {model_type}_{equipment_type}_{timestamp}
  model_type TEXT NOT NULL,
    -- e.g., "lstm", "autoencoder", "prophet"
    CHECK (model_type IN ('lstm', 'autoencoder', 'prophet', 'other')),
  equipment_type TEXT NOT NULL,
    -- e.g., "chiller", "ahu", "vav", "fcu", "ups", "generator", "dali"
    -- This is the link: equipment.type → ml_models.equipment_type

  -- Model file paths
  model_path TEXT NOT NULL,
    -- Full path to model file, e.g., "/opt/bms-intelligence/backend/ml/models/lstm/chiller_lstm_20260209_212308.h5"
  scaler_path TEXT,
    -- Optional path to feature scaler, e.g., ".../chiller_lstm_20260209_212308_scaler.joblib"

  -- Performance metrics
  r_squared_24h FLOAT,
    -- R² score for 24-hour forecast
  r_squared_48h FLOAT,
    -- R² score for 48-hour forecast
  r_squared_72h FLOAT,
    -- R² score for 72-hour forecast
  r_squared_avg FLOAT,
    -- Average R² across all forecast horizons (use for overall performance)

  -- Model status and lifecycle
  status TEXT NOT NULL DEFAULT 'active',
    -- "active": Currently used for inference
    -- "inactive": Previous version, not used
    -- "degraded": Model underperforming, requires higher confidence threshold
    -- "disabled": Model disabled (insufficient data, poor performance)
    -- "unavailable": Model not trained yet
    CHECK (status IN ('active', 'inactive', 'degraded', 'disabled', 'unavailable')),

  -- Metadata
  training_samples INTEGER,
    -- Number of samples used in training
  validation_samples INTEGER,
    -- Number of samples used in validation
  feature_names TEXT[] DEFAULT '{}',
    -- Array of input feature names, e.g., '["temp", "pressure", "flow"]'
  target_name TEXT,
    -- Target variable name, e.g., "setpoint_temperature"
  forecast_horizons INTEGER[] DEFAULT '{24, 48, 72}',
    -- Forecast horizons in hours, e.g., '{24, 48, 72}'

  -- Audit trail
  registered_at TIMESTAMP DEFAULT now(),
  registered_by TEXT DEFAULT 'system',
  notes TEXT,
    -- e.g., "Retrained with 6 months additional data, R² improved from 0.54 to 0.82"

  -- Uniqueness constraint: one active model per equipment type per model type
  UNIQUE (equipment_type, model_type, status)
    -- Allows multiple versions, but only one active per combination
);

CREATE INDEX idx_ml_models_equipment_type ON ml_models(equipment_type);
CREATE INDEX idx_ml_models_status ON ml_models(status);
CREATE INDEX idx_ml_models_active ON ml_models(equipment_type, status)
  WHERE status = 'active';

-- ============================================================================
-- TABLE: model_thresholds
-- Purpose: Store confidence thresholds for recommendations (Tier 2 and Tier 3)
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_thresholds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  equipment_type TEXT UNIQUE NOT NULL,
    -- e.g., "chiller", "ahu", "vav"
    -- Links to equipment.type and ml_models.equipment_type
    -- FOREIGN KEY implied but not enforced due to dynamic schema

  -- Tier 2: Advisory Recommendations (shown to user for approval)
  tier2_confidence_min FLOAT NOT NULL DEFAULT 0.70,
    -- Minimum confidence (0.0-1.0) for showing recommendations
    -- Default 70% = recommendation must be at least 70% confident
    -- Set to 1.0 to disable recommendations for this equipment type
    CHECK (tier2_confidence_min >= 0.0 AND tier2_confidence_min <= 1.0),

  -- Tier 3: Auto-Execute Recommendations (automatically applied in future)
  tier3_confidence_min FLOAT NOT NULL DEFAULT 0.85,
    -- Minimum confidence for auto-executing without approval
    -- Typically higher than Tier 2 (default 85%)
    -- Set to 1.0 to disable auto-execute (require manual approval)
    CHECK (tier3_confidence_min >= 0.0 AND tier3_confidence_min <= 1.0),

  -- Status and reason
  status TEXT NOT NULL DEFAULT 'active',
    -- "active": Thresholds are being used
    -- "disabled": Equipment type disabled (no recommendations shown)
    CHECK (status IN ('active', 'disabled')),

  reason TEXT,
    -- Why these thresholds are set this way
    -- e.g., "VAV model underperforming (R²=0.317), elevated threshold to prevent poor recommendations"
    -- e.g., "UPS model not trained, recommendations disabled until model available"

  -- Audit trail
  updated_at TIMESTAMP DEFAULT now(),
  updated_by TEXT DEFAULT 'system',
  notes TEXT,

  CONSTRAINT tier2_less_than_tier3
    CHECK (tier2_confidence_min <= tier3_confidence_min)
    -- Tier 2 threshold must be <= Tier 3 (advisory easier than auto-execute)
);

CREATE INDEX idx_model_thresholds_equipment_type ON model_thresholds(equipment_type);

-- ============================================================================
-- INSERT: Initial Threshold Configuration
-- ============================================================================

INSERT INTO model_thresholds (equipment_type, tier2_confidence_min, tier3_confidence_min, status, reason, notes)
VALUES
  -- Active models with standard thresholds
  ('chiller', 0.70, 0.85, 'active',
   'CHILLER model performing well (R²=0.654 avg)',
   'Standard thresholds for reliable model'),

  ('ahu', 0.70, 0.85, 'active',
   'AHU model performing adequately (R²=0.550 avg)',
   'Standard thresholds'),

  ('fcu', 0.70, 0.85, 'active',
   'FCU model performing well (R²=0.628 avg)',
   'Standard thresholds'),

  ('ups', 0.70, 0.85, 'active',
   'UPS model available (R²=0.670 avg)',
   'Standard thresholds'),

  ('generator', 0.85, 0.95, 'active',
   'GENERATOR model with variable performance (R²=0.631 avg), elevated threshold applied',
   'Higher confidence required due to model variability'),

  -- Disabled models (no equipment in current database)
  ('vav', 1.0, 1.0, 'disabled',
   'VAV model disabled (no VAV equipment in database, insufficient retraining data available)',
   'Defer retraining to Phase 69 when equipment available'),

  -- Unavailable model (not trained)
  ('dali', 0.70, 0.85, 'active',
   'DALI lighting control model (placeholder for future training)',
   'Ready for recommendations once model trained')

ON CONFLICT (equipment_type) DO NOTHING;
-- Don't fail if thresholds already exist

-- ============================================================================
-- NOTES FOR INTEGRATION
-- ============================================================================

/*
Integration with Equipment and ML Models:

1. When SIMBIOT ingests equipment from BMS:
   - Equipment is inserted into equipment table with type (e.g., "chiller")
   - equipment.type links to ml_models.equipment_type and model_thresholds.equipment_type
   - Inference service queries ml_models WHERE equipment_type = equipment.type AND status = 'active'
   - Confidence thresholds loaded from model_thresholds WHERE equipment_type = equipment.type

2. When generating predictions:
   - Get equipment.type
   - Look up active model: SELECT * FROM ml_models WHERE equipment_type = ? AND status = 'active'
   - Load thresholds: SELECT tier2_confidence_min, tier3_confidence_min FROM model_thresholds WHERE equipment_type = ?
   - Run inference with model
   - Filter by confidence: confidence >= tier2_confidence_min for Tier 2 recommendations
   - Filter by confidence: confidence >= tier3_confidence_min for Tier 3 auto-execution

3. When retraining models:
   - Register new model in ml_models table
   - Update model_thresholds if needed (e.g., if model performance improved/degraded)
   - Can adjust tier2_confidence_min and tier3_confidence_min without code changes

4. When new equipment type discovered:
   - Add row to model_thresholds with appropriate thresholds
   - Once model trained, add to ml_models table
   - Recommendations will automatically start flowing for that equipment type
*/

-- ============================================================================
-- MIGRATION INFO
-- ============================================================================
-- Phase: 68-03 (ML Integration & Multi-System Grouping)
-- Tables Created: ml_models, model_thresholds
-- Purpose: Database-driven ML model registry with confidence thresholds
-- Rows Inserted: 7 (initial threshold configuration)
--
-- Depends on: Nothing (new schema)
-- Required by: Phase 68-03 Task 1 (ML Inference Pipeline)
