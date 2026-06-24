-- Persistent IPMVP savings results for Grafana dashboards.
-- Grafana queries this table directly via PostgreSQL datasource.
-- Populated hourly by the IPMVP data sync job.

CREATE TABLE IF NOT EXISTS public.ipmvp_savings (
    id              BIGSERIAL PRIMARY KEY,
    site_id         TEXT NOT NULL REFERENCES public.sites(code),
    period_start    DATE NOT NULL,       -- e.g. '2026-06-01'
    period_end      DATE NOT NULL,       -- e.g. '2026-06-30'
    savings_kwh     NUMERIC(12, 2) NOT NULL DEFAULT 0,
    savings_zar     NUMERIC(12, 2) NOT NULL DEFAULT 0,
    cv_rmse_pct     NUMERIC(5, 1),       -- aggregate uncertainty
    n_results       INTEGER NOT NULL DEFAULT 0,
    option          TEXT NOT NULL DEFAULT 'C',
    methodology     TEXT,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    baseline_cutoff DATE,                -- advisory promotion date used as anchor
    UNIQUE (site_id, period_start, period_end, option)
);

COMMENT ON TABLE public.ipmvp_savings IS 'Monthly IPMVP savings results for Grafana dashboards';
COMMENT ON COLUMN public.ipmvp_savings.savings_kwh IS 'Total energy savings for the period (kWh)';
COMMENT ON COLUMN public.ipmvp_savings.savings_zar IS 'Total cost savings for the period (ZAR)';
COMMENT ON COLUMN public.ipmvp_savings.cv_rmse_pct IS 'Aggregate baseline uncertainty — lower is better';
COMMENT ON COLUMN public.ipmvp_savings.baseline_cutoff IS 'Date the site entered advisory phase (baseline boundary)';

ALTER TABLE public.ipmvp_savings ENABLE ROW LEVEL SECURITY;

-- Service role can do everything; authenticated users read only
CREATE POLICY ipmvp_savings_service_role ON public.ipmvp_savings
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY ipmvp_savings_read_only ON public.ipmvp_savings
    FOR SELECT TO authenticated USING (true);
