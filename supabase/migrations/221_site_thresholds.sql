-- =====================================================
-- Migration: Add site_thresholds table
-- Unified per-site health + risk thresholds.
-- Single row per site (site_id PK), one global fallback row.
-- Replaces fragmented system_settings keys
--   (healthThresholds/health_thresholds, riskThresholds/risk_thresholds)
-- =====================================================
--
-- ROLLBACK:
--   DROP TABLE IF EXISTS site_thresholds;
--   DROP FUNCTION IF EXISTS update_site_thresholds_timestamp();

CREATE TABLE IF NOT EXISTS site_thresholds (
    site_id TEXT NOT NULL,
    health JSONB NOT NULL DEFAULT '{"healthy": 85, "warning": 65, "critical": 40}',
    risk JSONB NOT NULL DEFAULT '{"medium": 31, "high": 61, "critical": 81}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT site_thresholds_pkey PRIMARY KEY (site_id),
    CONSTRAINT valid_health CHECK (
        (health->>'healthy')::int > (health->>'warning')::int
        AND (health->>'warning')::int > (health->>'critical')::int
        AND (health->>'critical')::int >= 0
        AND (health->>'healthy')::int <= 100
    ),
    CONSTRAINT valid_risk CHECK (
        (risk->>'medium')::int >= 0
        AND (risk->>'high')::int > (risk->>'medium')::int
        AND (risk->>'critical')::int > (risk->>'high')::int
        AND (risk->>'critical')::int <= 100
    )
);

-- RLS: enable + allow authenticated reads, admin writes
ALTER TABLE site_thresholds ENABLE ROW LEVEL SECURITY;

CREATE POLICY site_thresholds_select ON site_thresholds
    FOR SELECT
    USING (true);  -- all authenticated users can read thresholds

CREATE POLICY site_thresholds_insert ON site_thresholds
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');  -- API-level auth handles admin enforcement

CREATE POLICY site_thresholds_update ON site_thresholds
    FOR UPDATE
    USING (auth.role() = 'authenticated');

-- Index for site_id lookups (already covered by PK, but explicit for clarity)
CREATE INDEX IF NOT EXISTS idx_site_thresholds_site_id ON site_thresholds(site_id);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_site_thresholds_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS site_thresholds_updated ON site_thresholds;
CREATE TRIGGER site_thresholds_updated
    BEFORE UPDATE ON site_thresholds
    FOR EACH ROW
    EXECUTE FUNCTION update_site_thresholds_timestamp();

-- Seed global defaults row
INSERT INTO site_thresholds (site_id, health, risk)
VALUES ('__global__', '{"healthy": 85, "warning": 65, "critical": 40}', '{"medium": 31, "high": 61, "critical": 81}')
ON CONFLICT (site_id) DO NOTHING;

-- ── Backfill per-site from legacy system_settings ──────────────────────
-- Handles both camelCase (settings.py) and snake_case (settings_db.py) keys.

INSERT INTO site_thresholds (site_id, health, risk)
SELECT
    REPLACE(REPLACE(s.key, 'healthThresholds_', ''), 'health_thresholds_', ''),
    s.value::jsonb AS health,
    COALESCE(
        (SELECT value::jsonb FROM system_settings
         WHERE key = REPLACE(REPLACE(s.key, 'healthThresholds', 'riskThresholds'), 'health_thresholds', 'risk_thresholds')
         LIMIT 1),
        '{"medium": 31, "high": 61, "critical": 81}'::jsonb
    ) AS risk
FROM system_settings s
WHERE s.key LIKE 'healthThresholds_%' OR s.key LIKE 'health_thresholds_%'
ON CONFLICT (site_id) DO UPDATE SET
    health = EXCLUDED.health,
    risk = EXCLUDED.risk;

-- Backfill global defaults from system_settings
UPDATE site_thresholds
SET
    health = COALESCE(
        (SELECT value::jsonb FROM system_settings WHERE key = 'healthThresholds' LIMIT 1),
        (SELECT value::jsonb FROM system_settings WHERE key = 'health_thresholds' LIMIT 1),
        health
    ),
    risk = COALESCE(
        (SELECT value::jsonb FROM system_settings WHERE key = 'riskThresholds' LIMIT 1),
        (SELECT value::jsonb FROM system_settings WHERE key = 'risk_thresholds' LIMIT 1),
        risk
    )
WHERE site_id = '__global__';

COMMENT ON TABLE site_thresholds IS 'Unified per-site health and risk thresholds. site_id = ''__global__'' is the fallback default.';
COMMENT ON COLUMN site_thresholds.health IS 'Health score boundaries: {healthy, warning, critical} with healthy > warning > critical ordering';
COMMENT ON COLUMN site_thresholds.risk IS 'Risk score boundaries: {medium, high, critical} with medium < high < critical ordering';
