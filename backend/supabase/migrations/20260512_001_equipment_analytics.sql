-- Migration: equipment_analytics (Phase 193+)
-- Stores ML anomaly scores (Isolation Forest, LSTM, Autoencoder) per equipment.
-- Powers anomaly_scores_writing promotion gate in phase_promotion_evaluator.

BEGIN;

CREATE TABLE IF NOT EXISTS equipment_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    equipment_id UUID NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    anomaly_score REAL NOT NULL DEFAULT 0.0,
    lstm_anomaly_score REAL,
    autoencoder_anomaly_score REAL,
    model_version TEXT,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for gate queries: recent scores per site
CREATE INDEX IF NOT EXISTS idx_equipment_analytics_site_scored
    ON equipment_analytics (site_id, scored_at DESC);

-- Index for per-equipment lookups
CREATE INDEX IF NOT EXISTS idx_equipment_analytics_equipment
    ON equipment_analytics (equipment_id, scored_at DESC);

COMMENT ON TABLE equipment_analytics IS
    'ML-generated anomaly scores per equipment. anomaly_score: Isolation Forest z-score [0,1]. lstm_anomaly_score: LSTM prediction error [0,1]. autoencoder_anomaly_score: reconstruction error [0,1]. Used for phase promotion gates and ML health blending.';

COMMIT;
