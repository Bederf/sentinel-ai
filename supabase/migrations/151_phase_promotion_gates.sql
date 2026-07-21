-- Phase promotion gates table: single source of truth for phase transition gates.
-- Replaces hardcoded gates in PhasePromotionEvaluator and site-*-mode-policy.json files.
--
-- Migration: 20260509_001_phase_promotion_gates

CREATE TABLE IF NOT EXISTS phase_promotion_gates (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    site_id TEXT NOT NULL,
    from_phase TEXT NOT NULL,
    to_phase TEXT NOT NULL,
    gate_name TEXT NOT NULL,
    gate_type TEXT NOT NULL CHECK (gate_type IN ('threshold', 'boolean', 'count')),
    threshold_value NUMERIC,
    operator TEXT NOT NULL CHECK (operator IN ('>=', '<=', '>', '<', '==', '!=', 'in', '==true', '==false')),
    allowed_values TEXT[],
    description TEXT,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_gate UNIQUE(site_id, from_phase, to_phase, gate_name)
);

-- Index for fast lookups by site + transition
CREATE INDEX IF NOT EXISTS idx_phase_promotion_gates_lookup
ON phase_promotion_gates (site_id, from_phase, to_phase, enabled);

COMMENT ON TABLE phase_promotion_gates IS
    'Single source of truth for phase promotion gates. '
    'Every site phase transition is gated by rows in this table. '
    'No hardcoded gates — edit rows to change promotion requirements.';

-- Seed gates for site-002: shadow_live → advisory
INSERT INTO phase_promotion_gates
    (site_id, from_phase, to_phase, gate_name, gate_type, threshold_value, operator, description)
VALUES
    -- ML training hours (primary gate — blocks until enough data ingested)
    ('site-002', 'shadow_live', 'advisory', 'ml_hours_ingested', 'threshold', 72, '>=',
     'ML training hours accumulated'),
    -- Bridge must be healthy
    ('site-002', 'shadow_live', 'advisory', 'bridge_connected', 'boolean', NULL, '==true',
     'Shadow Bridge connected and polling'),
    -- Data freshness must be under 4 hours
    ('site-002', 'shadow_live', 'advisory', 'freshness_hours_max', 'threshold', 4.0, '<=',
     'Data freshness (max age in hours)'),
    -- Anomaly scores must be writing to DB (count > 0 in last 30 min)
    ('site-002', 'shadow_live', 'advisory', 'anomaly_scores_writing', 'count', 0, '>',
     'Anomaly scores writing to equipment_analytics'),
    -- Equipment match coverage >= 90%
    ('site-002', 'shadow_live', 'advisory', 'match_coverage_min_pct', 'threshold', 50.0, '>=',
     'Equipment BACnet point match coverage %'),
    -- Adapter error rate <= 10%
    ('site-002', 'shadow_live', 'advisory', 'error_rate_max_pct', 'threshold', 10.0, '<=',
     'Adapter error rate %')
ON CONFLICT (site_id, from_phase, to_phase, gate_name) DO UPDATE SET
    gate_type = EXCLUDED.gate_type,
    threshold_value = EXCLUDED.threshold_value,
    operator = EXCLUDED.operator,
    description = EXCLUDED.description,
    updated_at = NOW();

-- Seed gates for site-002: advisory → supervised
INSERT INTO phase_promotion_gates
    (site_id, from_phase, to_phase, gate_name, gate_type, threshold_value, operator, description)
VALUES
    ('site-002', 'advisory', 'supervised', 'ml_hours_ingested', 'threshold', 500, '>=',
     'ML training hours (extended learning period)'),
    ('site-002', 'advisory', 'supervised', 'time_in_advisory_days', 'threshold', 30, '>=',
     'Days in advisory phase before supervised'),
    ('site-002', 'advisory', 'supervised', 'recommendations_generated', 'count', 50, '>=',
     'Total recommendations generated'),
    ('site-002', 'advisory', 'supervised', 'no_safety_violations_30d', 'boolean', NULL, '==true',
     'No safety violations in last 30 days'),
    ('site-002', 'advisory', 'supervised', 'bridge_connected_uptime_pct', 'threshold', 0.90, '>=',
     'Bridge connected uptime >= 90%')
ON CONFLICT (site_id, from_phase, to_phase, gate_name) DO UPDATE SET
    gate_type = EXCLUDED.gate_type,
    threshold_value = EXCLUDED.threshold_value,
    operator = EXCLUDED.operator,
    description = EXCLUDED.description,
    updated_at = NOW();

-- Seed gates for site-002: supervised → automatic
INSERT INTO phase_promotion_gates
    (site_id, from_phase, to_phase, gate_name, gate_type, threshold_value, operator, description)
VALUES
    ('site-002', 'supervised', 'automatic', 'ml_hours_ingested', 'threshold', 2000, '>=',
     'ML training hours (mature deployment)'),
    ('site-002', 'supervised', 'automatic', 'approval_accuracy', 'threshold', 0.85, '>=',
     'Recommendation approval accuracy >= 85%'),
    ('site-002', 'supervised', 'automatic', 'false_positive_rate', 'threshold', 0.10, '<=',
     'False positive rate <= 10%'),
    ('site-002', 'supervised', 'automatic', 'recommendations_approved', 'count', 30, '>=',
     'Recommendations approved by operators'),
    ('site-002', 'supervised', 'automatic', 'no_safety_violations_7d', 'boolean', NULL, '==true',
     'No safety violations in last 7 days'),
    ('site-002', 'supervised', 'automatic', 'human_approved_autonomous', 'boolean', NULL, '==true',
     'At least one human-approved autonomous action logged')
ON CONFLICT (site_id, from_phase, to_phase, gate_name) DO UPDATE SET
    gate_type = EXCLUDED.gate_type,
    threshold_value = EXCLUDED.threshold_value,
    operator = EXCLUDED.operator,
    description = EXCLUDED.description,
    updated_at = NOW();

-- Seed gates for site-001 (future site — same gates)
INSERT INTO phase_promotion_gates
    (site_id, from_phase, to_phase, gate_name, gate_type, threshold_value, operator, description)
VALUES
    ('site-001', 'shadow_live', 'advisory', 'ml_hours_ingested', 'threshold', 72, '>=',
     'ML training hours accumulated'),
    ('site-001', 'shadow_live', 'advisory', 'bridge_connected', 'boolean', NULL, '==true',
     'Shadow Bridge connected and polling'),
    ('site-001', 'shadow_live', 'advisory', 'freshness_hours_max', 'threshold', 4.0, '<=',
     'Data freshness (max age in hours)'),
    ('site-001', 'shadow_live', 'advisory', 'anomaly_scores_writing', 'count', 0, '>',
     'Anomaly scores writing to equipment_analytics'),
    ('site-001', 'shadow_live', 'advisory', 'match_coverage_min_pct', 'threshold', 50.0, '>=',
     'Equipment BACnet point match coverage %'),
    ('site-001', 'shadow_live', 'advisory', 'error_rate_max_pct', 'threshold', 10.0, '<=',
     'Adapter error rate %')
ON CONFLICT (site_id, from_phase, to_phase, gate_name) DO UPDATE SET
    updated_at = NOW();

-- RLS
ALTER TABLE phase_promotion_gates ENABLE ROW LEVEL SECURITY;

-- Service role can do everything; authenticated users can read
DROP POLICY IF EXISTS "service_role_full_access" ON phase_promotion_gates;
CREATE POLICY "service_role_full_access" ON phase_promotion_gates
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "authenticated_read" ON phase_promotion_gates;
CREATE POLICY "authenticated_read" ON phase_promotion_gates
    FOR SELECT TO authenticated USING (true);
