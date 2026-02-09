-- =====================================================
-- Migration 052: Budget Alerts Equipment Type
-- =====================================================

ALTER TABLE budget_alerts
ADD COLUMN IF NOT EXISTS equipment_type TEXT;

DROP INDEX IF EXISTS idx_budget_alerts_unique;

CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_alerts_unique
  ON budget_alerts(contract_id, period_year, period_month, severity, equipment_type);

CREATE INDEX IF NOT EXISTS idx_budget_alerts_equipment_type
  ON budget_alerts(equipment_type);
