-- =====================================================
-- Migration 003: AI Predictions Table
-- =====================================================

-- AI Predictions table (linked to equipment)
CREATE TABLE predictions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,
  equipment_id UUID NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,

  -- Prediction details
  prediction_type TEXT NOT NULL,
  probability_percent INTEGER CHECK (probability_percent BETWEEN 0 AND 100),
  confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
  predicted_failure_date DATE,
  timeframe_days INTEGER,

  -- Evidence and analysis
  evidence JSONB NOT NULL,
  contributing_factors JSONB,
  similar_failures JSONB,

  -- Financial impact
  repair_cost_zar DECIMAL(12, 2),
  replacement_cost_zar DECIMAL(12, 2),
  downtime_cost_per_hour_zar DECIMAL(12, 2),
  potential_loss_zar DECIMAL(12, 2),

  -- Status and urgency
  severity TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low')),
  recommended_action TEXT,
  parts_required TEXT[],
  urgency TEXT,
  status TEXT CHECK (status IN ('active', 'acknowledged', 'resolved', 'false_positive')),

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for prediction queries
CREATE INDEX idx_predictions_equipment ON predictions(equipment_id);
CREATE INDEX idx_predictions_building ON predictions(building_id);
CREATE INDEX idx_predictions_severity ON predictions(severity, probability_percent);
CREATE INDEX idx_predictions_status ON predictions(status);
CREATE INDEX idx_predictions_date ON predictions(predicted_failure_date);

-- Trigger for updated_at
CREATE TRIGGER update_predictions_updated_at BEFORE UPDATE ON predictions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
