-- =====================================================
-- Migration 018: Commercial Schema
-- FM Commercial Intelligence - Contracts, SLAs, Budgets
-- Part of v11.0 FM Commercial Intelligence milestone
-- =====================================================

-- =====================================================
-- Organizations (FM Clients)
-- =====================================================
CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,           -- e.g., 'FNB', 'NEDBANK'
  name TEXT NOT NULL,
  trading_name TEXT,
  registration_number TEXT,
  vat_number TEXT,

  -- Contact
  primary_contact_name TEXT,
  primary_contact_email TEXT,
  primary_contact_phone TEXT,
  billing_email TEXT,

  -- Address
  physical_address TEXT,
  postal_address TEXT,

  -- Classification
  industry TEXT,
  tier TEXT CHECK (tier IN ('platinum', 'gold', 'silver', 'bronze')),

  -- Status
  status TEXT CHECK (status IN ('active', 'suspended', 'terminated')) DEFAULT 'active',

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Contracts (Links Organization to Buildings)
-- =====================================================
CREATE TABLE contracts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,           -- e.g., 'CON-FNB-2026-001'
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE RESTRICT,

  -- Contract terms
  contract_type TEXT CHECK (contract_type IN ('comprehensive', 'preventive', 'reactive', 'hybrid')),
  start_date DATE NOT NULL,
  end_date DATE,
  auto_renew BOOLEAN DEFAULT FALSE,
  notice_period_days INTEGER DEFAULT 90,

  -- Pricing
  monthly_fee_zar DECIMAL(12, 2) NOT NULL,
  annual_escalation_pct DECIMAL(5, 2) DEFAULT 6.0,
  payment_terms_days INTEGER DEFAULT 30,

  -- Coverage
  coverage_hours JSONB,                -- e.g., {"weekday": "06:00-22:00", "saturday": "08:00-14:00"}
  included_callouts_per_month INTEGER DEFAULT 0,
  callout_rate_zar DECIMAL(10, 2),
  after_hours_rate_zar DECIMAL(10, 2),

  -- Status
  status TEXT CHECK (status IN ('draft', 'pending_approval', 'active', 'suspended', 'expired', 'terminated')) DEFAULT 'draft',

  -- Approval
  approved_by TEXT,
  approved_at TIMESTAMPTZ,

  -- Notes
  notes TEXT,
  special_conditions TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- SLA Definitions (Per Contract)
-- =====================================================
CREATE TABLE sla_terms (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,

  -- SLA Type
  sla_type TEXT NOT NULL CHECK (sla_type IN (
    'uptime',           -- System availability percentage
    'response_time',    -- Time to respond to callout
    'resolution_time',  -- Time to resolve issue
    'ppm_completion',   -- Planned maintenance completion rate
    'first_fix_rate'    -- Issues fixed on first visit
  )),

  -- Target
  target_value DECIMAL(10, 2) NOT NULL,    -- e.g., 99.5 for uptime, 4 for hours
  target_unit TEXT NOT NULL,                -- e.g., 'percent', 'hours', 'minutes'

  -- Priority levels (different targets by priority)
  priority TEXT CHECK (priority IN ('critical', 'high', 'medium', 'low', 'all')) DEFAULT 'all',

  -- Measurement
  measurement_period TEXT CHECK (measurement_period IN ('monthly', 'quarterly', 'annually')) DEFAULT 'monthly',

  -- Penalties
  penalty_type TEXT CHECK (penalty_type IN ('percentage', 'fixed', 'tiered')),
  penalty_value DECIMAL(10, 2),             -- Percentage of monthly fee or fixed ZAR
  penalty_cap_pct DECIMAL(5, 2),            -- Max penalty as % of monthly fee

  -- Grace period before penalty applies
  grace_period_hours INTEGER DEFAULT 0,

  -- Active
  is_active BOOLEAN DEFAULT TRUE,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Asset Contract Links (Asset-level fee allocation)
-- =====================================================
CREATE TABLE asset_contracts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  equipment_id UUID NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,

  -- Fee allocation
  allocated_fee_zar DECIMAL(10, 2),        -- Portion of monthly fee for this asset
  fee_allocation_pct DECIMAL(5, 2),         -- Alternative: percentage of contract

  -- Asset-specific coverage
  coverage_type TEXT CHECK (coverage_type IN ('full', 'parts_only', 'labor_only', 'excluded')) DEFAULT 'full',

  -- Caps and limits
  annual_parts_cap_zar DECIMAL(12, 2),
  annual_labor_cap_zar DECIMAL(12, 2),

  -- Asset criticality affects SLA response
  criticality TEXT CHECK (criticality IN ('critical', 'high', 'medium', 'low')) DEFAULT 'medium',

  -- Notes
  exclusions TEXT,                          -- What's not covered
  notes TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(contract_id, equipment_id)
);

-- =====================================================
-- Condition Assessments (Initial and Periodic)
-- =====================================================
CREATE TABLE condition_assessments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,               -- e.g., 'CA-001-2026-001'

  -- Scope
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  equipment_id UUID REFERENCES equipment(id) ON DELETE CASCADE,
  contract_id UUID REFERENCES contracts(id) ON DELETE SET NULL,

  -- Assessment details
  assessment_type TEXT CHECK (assessment_type IN ('initial', 'annual', 'handover', 'ad_hoc')) NOT NULL,
  assessment_date DATE NOT NULL,
  assessor_name TEXT NOT NULL,
  assessor_company TEXT,

  -- Scoring (1-5 scale)
  overall_score INTEGER CHECK (overall_score BETWEEN 1 AND 5),
  mechanical_score INTEGER CHECK (mechanical_score BETWEEN 1 AND 5),
  electrical_score INTEGER CHECK (electrical_score BETWEEN 1 AND 5),
  controls_score INTEGER CHECK (controls_score BETWEEN 1 AND 5),
  documentation_score INTEGER CHECK (documentation_score BETWEEN 1 AND 5),

  -- Detailed findings
  findings TEXT,
  defects JSONB,                            -- Array of defects with severity
  recommendations JSONB,                    -- Array of recommendations with priority
  photos JSONB,                             -- Photo references

  -- Risk assessment
  estimated_failure_risk TEXT CHECK (estimated_failure_risk IN ('low', 'medium', 'high', 'critical')),
  estimated_annual_cost_zar DECIMAL(12, 2), -- Predicted maintenance cost
  recommended_budget_zar DECIMAL(12, 2),

  -- Approval
  status TEXT CHECK (status IN ('draft', 'submitted', 'approved', 'disputed')) DEFAULT 'draft',
  approved_by TEXT,
  approved_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Either building or equipment must be set
  CONSTRAINT assessment_scope CHECK (building_id IS NOT NULL OR equipment_id IS NOT NULL)
);

-- =====================================================
-- Budgets (Templates and Allocations)
-- =====================================================
CREATE TABLE budgets (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,               -- e.g., 'BUD-FNB-SANDTON-2026'

  -- Scope
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  equipment_type TEXT,                      -- NULL = contract-wide, else specific type

  -- Period
  budget_year INTEGER NOT NULL,
  budget_month INTEGER,                     -- NULL = annual, 1-12 = monthly

  -- Budget amounts (ZAR)
  labor_budget_zar DECIMAL(12, 2) DEFAULT 0,
  parts_budget_zar DECIMAL(12, 2) DEFAULT 0,
  consumables_budget_zar DECIMAL(12, 2) DEFAULT 0,
  subcontractor_budget_zar DECIMAL(12, 2) DEFAULT 0,
  callout_budget_zar DECIMAL(12, 2) DEFAULT 0,
  total_budget_zar DECIMAL(12, 2) GENERATED ALWAYS AS (
    labor_budget_zar + parts_budget_zar + consumables_budget_zar +
    subcontractor_budget_zar + callout_budget_zar
  ) STORED,

  -- Actuals (updated by triggers from work_orders)
  labor_actual_zar DECIMAL(12, 2) DEFAULT 0,
  parts_actual_zar DECIMAL(12, 2) DEFAULT 0,
  consumables_actual_zar DECIMAL(12, 2) DEFAULT 0,
  subcontractor_actual_zar DECIMAL(12, 2) DEFAULT 0,
  callout_actual_zar DECIMAL(12, 2) DEFAULT 0,
  total_actual_zar DECIMAL(12, 2) GENERATED ALWAYS AS (
    labor_actual_zar + parts_actual_zar + consumables_actual_zar +
    subcontractor_actual_zar + callout_actual_zar
  ) STORED,

  -- Variance
  variance_zar DECIMAL(12, 2) GENERATED ALWAYS AS (
    (labor_budget_zar + parts_budget_zar + consumables_budget_zar +
     subcontractor_budget_zar + callout_budget_zar) -
    (labor_actual_zar + parts_actual_zar + consumables_actual_zar +
     subcontractor_actual_zar + callout_actual_zar)
  ) STORED,

  -- Alert thresholds
  warning_threshold_pct DECIMAL(5, 2) DEFAULT 80,   -- Alert at 80% spend
  critical_threshold_pct DECIMAL(5, 2) DEFAULT 100, -- Alert at 100% spend

  -- Status
  status TEXT CHECK (status IN ('draft', 'approved', 'locked')) DEFAULT 'draft',
  approved_by TEXT,
  approved_at TIMESTAMPTZ,

  notes TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(contract_id, equipment_type, budget_year, budget_month)
);

-- =====================================================
-- SLA Performance Tracking
-- =====================================================
CREATE TABLE sla_performance (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  sla_term_id UUID NOT NULL REFERENCES sla_terms(id) ON DELETE CASCADE,

  -- Period
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,

  -- Performance
  target_value DECIMAL(10, 2) NOT NULL,
  actual_value DECIMAL(10, 2) NOT NULL,
  met_target BOOLEAN GENERATED ALWAYS AS (actual_value >= target_value) STORED,

  -- Penalty calculation
  penalty_applied BOOLEAN DEFAULT FALSE,
  penalty_amount_zar DECIMAL(10, 2),
  penalty_waived BOOLEAN DEFAULT FALSE,
  waiver_reason TEXT,

  -- Supporting data
  incidents_count INTEGER DEFAULT 0,
  total_downtime_hours DECIMAL(10, 2),
  details JSONB,                            -- Breakdown of incidents/events

  -- Status
  status TEXT CHECK (status IN ('pending', 'calculated', 'invoiced', 'disputed', 'resolved')) DEFAULT 'pending',

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(contract_id, sla_term_id, period_start)
);

-- =====================================================
-- Profitability Records (Monthly Roll-up)
-- =====================================================
CREATE TABLE contract_profitability (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,

  -- Period
  period_year INTEGER NOT NULL,
  period_month INTEGER NOT NULL,

  -- Revenue
  contract_fee_zar DECIMAL(12, 2) NOT NULL,
  callout_revenue_zar DECIMAL(12, 2) DEFAULT 0,
  parts_markup_zar DECIMAL(12, 2) DEFAULT 0,
  other_revenue_zar DECIMAL(12, 2) DEFAULT 0,
  total_revenue_zar DECIMAL(12, 2) GENERATED ALWAYS AS (
    contract_fee_zar + callout_revenue_zar + parts_markup_zar + other_revenue_zar
  ) STORED,

  -- Direct costs
  labor_cost_zar DECIMAL(12, 2) DEFAULT 0,
  parts_cost_zar DECIMAL(12, 2) DEFAULT 0,
  subcontractor_cost_zar DECIMAL(12, 2) DEFAULT 0,
  travel_cost_zar DECIMAL(12, 2) DEFAULT 0,
  other_direct_cost_zar DECIMAL(12, 2) DEFAULT 0,
  total_direct_cost_zar DECIMAL(12, 2) GENERATED ALWAYS AS (
    labor_cost_zar + parts_cost_zar + subcontractor_cost_zar + travel_cost_zar + other_direct_cost_zar
  ) STORED,

  -- Margins
  gross_margin_zar DECIMAL(12, 2) GENERATED ALWAYS AS (
    (contract_fee_zar + callout_revenue_zar + parts_markup_zar + other_revenue_zar) -
    (labor_cost_zar + parts_cost_zar + subcontractor_cost_zar + travel_cost_zar + other_direct_cost_zar)
  ) STORED,

  -- Penalties applied
  sla_penalties_zar DECIMAL(12, 2) DEFAULT 0,

  -- Net margin (after penalties)
  net_margin_zar DECIMAL(12, 2) GENERATED ALWAYS AS (
    (contract_fee_zar + callout_revenue_zar + parts_markup_zar + other_revenue_zar) -
    (labor_cost_zar + parts_cost_zar + subcontractor_cost_zar + travel_cost_zar + other_direct_cost_zar) -
    sla_penalties_zar
  ) STORED,

  -- KPIs
  work_order_count INTEGER DEFAULT 0,
  callout_count INTEGER DEFAULT 0,
  ppm_completion_pct DECIMAL(5, 2),
  sla_compliance_pct DECIMAL(5, 2),

  -- Status
  status TEXT CHECK (status IN ('preliminary', 'final', 'audited')) DEFAULT 'preliminary',
  finalized_by TEXT,
  finalized_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(contract_id, period_year, period_month)
);

-- =====================================================
-- Indexes
-- =====================================================

-- Organizations
CREATE INDEX idx_organizations_status ON organizations(status);
CREATE INDEX idx_organizations_tier ON organizations(tier);

-- Contracts
CREATE INDEX idx_contracts_organization ON contracts(organization_id);
CREATE INDEX idx_contracts_building ON contracts(building_id);
CREATE INDEX idx_contracts_status ON contracts(status);
CREATE INDEX idx_contracts_dates ON contracts(start_date, end_date);
CREATE INDEX idx_contracts_active ON contracts(building_id, status) WHERE status = 'active';

-- SLA Terms
CREATE INDEX idx_sla_terms_contract ON sla_terms(contract_id);
CREATE INDEX idx_sla_terms_type ON sla_terms(sla_type);

-- Asset Contracts
CREATE INDEX idx_asset_contracts_contract ON asset_contracts(contract_id);
CREATE INDEX idx_asset_contracts_equipment ON asset_contracts(equipment_id);
CREATE INDEX idx_asset_contracts_criticality ON asset_contracts(criticality);

-- Condition Assessments
CREATE INDEX idx_condition_assessments_building ON condition_assessments(building_id);
CREATE INDEX idx_condition_assessments_equipment ON condition_assessments(equipment_id);
CREATE INDEX idx_condition_assessments_contract ON condition_assessments(contract_id);
CREATE INDEX idx_condition_assessments_date ON condition_assessments(assessment_date DESC);
CREATE INDEX idx_condition_assessments_risk ON condition_assessments(estimated_failure_risk);

-- Budgets
CREATE INDEX idx_budgets_contract ON budgets(contract_id);
CREATE INDEX idx_budgets_year ON budgets(budget_year, budget_month);
CREATE INDEX idx_budgets_variance ON budgets(contract_id, budget_year) WHERE variance_zar < 0;

-- SLA Performance
CREATE INDEX idx_sla_performance_contract ON sla_performance(contract_id);
CREATE INDEX idx_sla_performance_term ON sla_performance(sla_term_id);
CREATE INDEX idx_sla_performance_period ON sla_performance(period_start, period_end);
CREATE INDEX idx_sla_performance_missed ON sla_performance(contract_id, period_start) WHERE met_target = FALSE;

-- Profitability
CREATE INDEX idx_profitability_contract ON contract_profitability(contract_id);
CREATE INDEX idx_profitability_period ON contract_profitability(period_year, period_month);
CREATE INDEX idx_profitability_margin ON contract_profitability(contract_id, period_year)
  WHERE net_margin_zar < 0;

-- =====================================================
-- Triggers
-- =====================================================

CREATE TRIGGER update_organizations_updated_at BEFORE UPDATE ON organizations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_contracts_updated_at BEFORE UPDATE ON contracts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sla_terms_updated_at BEFORE UPDATE ON sla_terms
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_asset_contracts_updated_at BEFORE UPDATE ON asset_contracts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_condition_assessments_updated_at BEFORE UPDATE ON condition_assessments
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_budgets_updated_at BEFORE UPDATE ON budgets
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sla_performance_updated_at BEFORE UPDATE ON sla_performance
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_profitability_updated_at BEFORE UPDATE ON contract_profitability
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- Add contract_id to work_orders for linking
-- =====================================================
ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS contract_id UUID REFERENCES contracts(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_work_orders_contract ON work_orders(contract_id);

-- =====================================================
-- Views for Common Queries
-- =====================================================

-- Active contracts with organization details
CREATE OR REPLACE VIEW v_active_contracts AS
SELECT
  c.id,
  c.code,
  c.building_id,
  b.name AS building_name,
  o.id AS organization_id,
  o.code AS organization_code,
  o.name AS organization_name,
  c.contract_type,
  c.monthly_fee_zar,
  c.start_date,
  c.end_date,
  c.status
FROM contracts c
JOIN buildings b ON c.building_id = b.id
JOIN organizations o ON c.organization_id = o.id
WHERE c.status = 'active';

-- Budget vs actual summary by contract
CREATE OR REPLACE VIEW v_budget_summary AS
SELECT
  c.code AS contract_code,
  b.budget_year,
  SUM(b.total_budget_zar) AS total_budget_zar,
  SUM(b.total_actual_zar) AS total_actual_zar,
  SUM(b.variance_zar) AS variance_zar,
  CASE
    WHEN SUM(b.total_budget_zar) > 0
    THEN ROUND((SUM(b.total_actual_zar) / SUM(b.total_budget_zar)) * 100, 2)
    ELSE 0
  END AS spend_percentage
FROM budgets b
JOIN contracts c ON b.contract_id = c.id
GROUP BY c.code, b.budget_year;

-- Contract profitability dashboard
CREATE OR REPLACE VIEW v_contract_profitability_dashboard AS
SELECT
  c.code AS contract_code,
  o.name AS organization_name,
  b.name AS building_name,
  cp.period_year,
  cp.period_month,
  cp.total_revenue_zar,
  cp.total_direct_cost_zar,
  cp.gross_margin_zar,
  cp.sla_penalties_zar,
  cp.net_margin_zar,
  CASE
    WHEN cp.total_revenue_zar > 0
    THEN ROUND((cp.net_margin_zar / cp.total_revenue_zar) * 100, 2)
    ELSE 0
  END AS margin_percentage,
  cp.sla_compliance_pct,
  cp.work_order_count
FROM contract_profitability cp
JOIN contracts c ON cp.contract_id = c.id
JOIN organizations o ON c.organization_id = o.id
JOIN buildings b ON c.building_id = b.id
ORDER BY cp.period_year DESC, cp.period_month DESC;
