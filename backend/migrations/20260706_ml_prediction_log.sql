-- Phase 236-03: real model drift signal.
-- ml_prediction_log: every site-scoped LSTM forecast / AE score at inference
-- time, joinable to telemetry_hourly actuals on (equipment_id, point_name,
-- target_hour). target_hour is UTC date_trunc('hour', predicted_at + horizon)
-- computed at log time. NOTE: telemetry_hourly.hour_bucket is
-- date_trunc('hour', recorded_at) in the DB session tz; the equality join is
-- exact only because SAST is a whole-hour offset (UTC+2). A sub-hour-offset
-- deployment would need both sides truncated in the same tz.
-- Retention: 60 days (2x the 30d accuracy window) — registered explicitly in
-- supabase_retention_service, never the 10-day default.

CREATE TABLE IF NOT EXISTS ml_prediction_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id text NOT NULL,
    model_kind text NOT NULL CHECK (model_kind IN ('lstm_forecast', 'ae_score')),
    site_id text,
    equipment_id text NOT NULL,
    equipment_type text NOT NULL,
    point_name text,                    -- LSTM target feature; NULL for AE
    predicted_at timestamptz NOT NULL DEFAULT now(),
    target_hour timestamptz,            -- UTC hour the forecast refers to; NULL for AE
    horizon_hours integer,              -- 24/48/72; NULL for AE
    predicted_value numeric,            -- forecast value, or AE reconstruction score
    threshold numeric,                  -- AE threshold at inference time
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ml_prediction_log_model_target
    ON ml_prediction_log (model_id, target_hour);
CREATE INDEX IF NOT EXISTS idx_ml_prediction_log_predicted_at
    ON ml_prediction_log (predicted_at);

-- ml_model_accuracy: rolling measured accuracy per model, written daily by
-- the accuracy job. Drift verdicts derive ONLY from these measured rows vs
-- the model's own registered training metrics — no verdict without data.
CREATE TABLE IF NOT EXISTS ml_model_accuracy (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id text NOT NULL,
    site_id text,                       -- carried from ml_prediction_log; no string-parsing of model_id
    model_kind text NOT NULL,
    window_days integer NOT NULL,
    n_samples integer NOT NULL,
    mae numeric,
    r2 numeric,
    score_median numeric,               -- AE score distribution stability
    score_p95 numeric,
    baseline_mae numeric,               -- training-time reference from registry
    baseline_threshold numeric,
    drift_verdict text NOT NULL DEFAULT 'insufficient_data'
        CHECK (drift_verdict IN ('ok', 'drift_suspected', 'insufficient_data')),
    computed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ml_model_accuracy_model
    ON ml_model_accuracy (model_id, computed_at DESC);
