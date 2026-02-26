-- Phase 52-03: Historical benchmarking and renewal pricing tracking
-- Creates tables for quote history, performance tracking, win/loss analysis, and market benchmarks

-- Table: pricing_history - Track all quotes generated
CREATE TABLE IF NOT EXISTS pricing_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    quote_fee_zar DECIMAL(10, 2) NOT NULL,
    accepted_fee_zar DECIMAL(10, 2),
    quote_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decision_date TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'accepted', 'rejected', 'expired')),
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pricing_history_contract ON pricing_history(contract_id);
CREATE INDEX IF NOT EXISTS idx_pricing_history_date ON pricing_history(quote_date);
CREATE INDEX IF NOT EXISTS idx_pricing_history_status ON pricing_history(status);

-- Table: quote_performance - Compare quoted vs actual costs
CREATE TABLE IF NOT EXISTS quote_performance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quote_id UUID NOT NULL REFERENCES pricing_history(id) ON DELETE CASCADE,
    actual_costs_zar DECIMAL(10, 2),
    variance_pct DECIMAL(5, 2),
    outcome VARCHAR(50) CHECK (outcome IN ('favorable', 'neutral', 'unfavorable')),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_quote_performance_quote ON quote_performance(quote_id);

-- Table: win_loss_analysis - Track quote acceptance/rejection
CREATE TABLE IF NOT EXISTS win_loss_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quote_id UUID NOT NULL REFERENCES pricing_history(id) ON DELETE CASCADE,
    outcome VARCHAR(20) NOT NULL CHECK (outcome IN ('won', 'lost', 'pending')),
    reason VARCHAR(255),
    client_feedback TEXT,
    lost_to_competitor VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_win_loss_quote ON win_loss_analysis(quote_id);
CREATE INDEX IF NOT EXISTS idx_win_loss_outcome ON win_loss_analysis(outcome);

-- Table: benchmarks - Market data for comparables
CREATE TABLE IF NOT EXISTS benchmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_type VARCHAR(100) NOT NULL,
    sla_tier VARCHAR(50) NOT NULL,
    avg_fee_zar DECIMAL(10, 2) NOT NULL,
    min_fee_zar DECIMAL(10, 2),
    max_fee_zar DECIMAL(10, 2),
    market_sample_size INT DEFAULT 0,
    confidence_pct INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(equipment_type, sla_tier)
);

CREATE INDEX IF NOT EXISTS idx_benchmarks_equipment ON benchmarks(equipment_type);
CREATE INDEX IF NOT EXISTS idx_benchmarks_sla ON benchmarks(sla_tier);

-- Enable Row Level Security
ALTER TABLE pricing_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE quote_performance ENABLE ROW LEVEL SECURITY;
ALTER TABLE win_loss_analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE benchmarks ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for service role
CREATE POLICY "pricing_history_service_read" ON pricing_history
    FOR SELECT USING (auth.role() = 'service_role');

CREATE POLICY "pricing_history_service_write" ON pricing_history
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "pricing_history_service_update" ON pricing_history
    FOR UPDATE USING (auth.role() = 'service_role');

CREATE POLICY "quote_performance_service_read" ON quote_performance
    FOR SELECT USING (auth.role() = 'service_role');

CREATE POLICY "quote_performance_service_write" ON quote_performance
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "win_loss_service_read" ON win_loss_analysis
    FOR SELECT USING (auth.role() = 'service_role');

CREATE POLICY "win_loss_service_write" ON win_loss_analysis
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "benchmarks_service_read" ON benchmarks
    FOR SELECT USING (auth.role() = 'service_role');

CREATE POLICY "benchmarks_service_write" ON benchmarks
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "benchmarks_service_update" ON benchmarks
    FOR UPDATE USING (auth.role() = 'service_role');

-- Create materialized view for portfolio benchmarking
CREATE MATERIALIZED VIEW IF NOT EXISTS portfolio_pricing_summary AS
SELECT
    c.id as contract_id,
    c.monthly_fee_zar as current_fee,
    ph.quote_fee_zar as last_quoted_fee,
    ph.accepted_fee_zar as accepted_fee,
    b.avg_fee_zar as market_average_fee,
    ((c.monthly_fee_zar - b.avg_fee_zar) / b.avg_fee_zar * 100)::DECIMAL(5, 2) as variance_pct,
    wl.outcome as last_outcome,
    ph.status as quote_status,
    COALESCE(ph.quote_date, c.created_at) as last_pricing_date
FROM contracts c
LEFT JOIN pricing_history ph ON c.id = ph.contract_id AND ph.decision_date = (
    SELECT MAX(decision_date) FROM pricing_history WHERE contract_id = c.id
)
LEFT JOIN benchmarks b ON b.equipment_type = 'all'
LEFT JOIN win_loss_analysis wl ON ph.id = wl.quote_id;

-- Create index on materialized view for performance
CREATE INDEX IF NOT EXISTS idx_portfolio_pricing_variance ON portfolio_pricing_summary(variance_pct);
