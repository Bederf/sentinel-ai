-- Canonical CapEx analysis store for SENTINEL operational data.
-- JSON may exist for import/export only, not as the runtime system of record.

CREATE TABLE IF NOT EXISTS public.capex_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_code TEXT NOT NULL,
    equipment_type TEXT,
    recommendation TEXT,
    confidence_pct DECIMAL(5, 2),
    npv_replace_zar DECIMAL(14, 2),
    npv_repair_zar DECIMAL(14, 2),
    npv_advantage_zar DECIMAL(14, 2),
    replacement_cost_zar DECIMAL(14, 2),
    repair_cost_zar DECIMAL(14, 2),
    failure_probability DECIMAL(6, 4),
    payback_months INTEGER,
    risk_reduction_pct DECIMAL(5, 2),
    discount_rate DECIMAL(6, 4),
    horizon_years INTEGER,
    analysis_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_capex_analyses_equipment_code
    ON public.capex_analyses (equipment_code);

CREATE INDEX IF NOT EXISTS idx_capex_analyses_created_at
    ON public.capex_analyses (created_at DESC);
