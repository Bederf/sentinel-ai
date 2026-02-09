-- =====================================================
-- Migration 050: Budget Variance Alerts
-- =====================================================

CREATE TABLE IF NOT EXISTS budget_alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  budget_id UUID REFERENCES budgets(id) ON DELETE SET NULL,

  period_year INTEGER NOT NULL,
  period_month INTEGER NOT NULL,

  spend_percentage DECIMAL(6, 2) DEFAULT 0,
  total_budget_zar DECIMAL(12, 2) DEFAULT 0,
  total_actual_zar DECIMAL(12, 2) DEFAULT 0,
  variance_zar DECIMAL(12, 2) DEFAULT 0,

  severity TEXT CHECK (severity IN ('warning', 'critical')) NOT NULL,
  message TEXT,
  status TEXT CHECK (status IN ('open', 'acknowledged', 'resolved')) DEFAULT 'open',

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_alerts_unique
  ON budget_alerts(contract_id, period_year, period_month, severity);

CREATE INDEX IF NOT EXISTS idx_budget_alerts_contract
  ON budget_alerts(contract_id, period_year, period_month);
