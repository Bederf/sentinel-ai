-- =====================================================
-- Migration: Add site_thresholds table
-- Unified per-site health + risk thresholds.
-- single row per site (site_id PK), one global fallback row.
-- Replaces fragmented system_settings keys
--   (healthThresholds, riskThresholds, healthThresholds_{site})
-- =====================================================

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

-- Backfill existing per-site health thresholds from system_settings
INSERT INTO site_thresholds (site_id, health, risk)
SELECT
    REPLACE(s.key, 'healthThresholds_', ''),
    s.value AS health,
    COALESCE(r.value, '{"medium": 31, "high": 61, "critical": 81}') AS risk
FROM system_settings s
LEFT JOIN LATERAL (
    SELECT value FROM system_settings
    WHERE key = REPLACE(s.key, 'healthThresholds_', 'riskThresholds_')
) r ON TRUE
WHERE s.key LIKE 'healthThresholds_%'
ON CONFLICT (site_id) DO UPDATE SET
    health = EXCLUDED.health,
    risk = EXCLUDED.risk;

-- Backfill global from system_settings
UPDATE site_thresholds
SET health = COALESCE(
    (SELECT value FROM system_settings WHERE key = 'healthThresholds')::jsonb,
    health
),
    risk = COALESCE(
    (SELECT value FROM system_settings WHERE key = 'riskThresholds')::jsonb,
    risk
)
WHERE site_id = '__global__';

COMMENT ON TABLE site_thresholds IS 'Unified per-site health and risk thresholds. site_id = ''__global__'' is the fallback default.';
COMMENT ON COLUMN site_thresholds.health IS 'Health score boundaries: {healthy, warning, critical} with healthy > warning > critical ordering';
COMMENT ON COLUMN site_thresholds.risk IS 'Risk score boundaries: {medium, high, critical} with medium < high < critical ordering';
