-- 046_water_data.sql
-- Create water consumption and alerts tables with sample data for site-002

-- ============================================================================
-- Water Consumption Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS water_consumption (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meter_id TEXT NOT NULL,
    site TEXT NOT NULL,
    volume_liters FLOAT NOT NULL,
    flow_rate_lpm FLOAT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pulse_count INTEGER DEFAULT 0,
    temperature FLOAT,
    pressure FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_water_consumption_site_timestamp ON water_consumption(site, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_water_consumption_meter_timestamp ON water_consumption(meter_id, timestamp DESC);

-- ============================================================================
-- Water Alerts Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS water_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id TEXT NOT NULL UNIQUE,
    meter_id TEXT NOT NULL,
    site TEXT NOT NULL,
    alert_type TEXT NOT NULL CHECK (alert_type IN ('continuous_flow', 'unusual_pattern', 'spike', 'night_flow')),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'acknowledged', 'resolved', 'false_positive')),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    flow_rate_lpm FLOAT,
    threshold_lpm FLOAT,
    duration_minutes FLOAT,
    description TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for alert queries
CREATE INDEX IF NOT EXISTS idx_water_alerts_site_status ON water_alerts(site, status, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_water_alerts_severity ON water_alerts(severity, timestamp DESC);

-- ============================================================================
-- Sample Water Consumption Data for site-002
-- Generates 7 days of realistic water consumption data with daily patterns
-- ============================================================================

DO $$
DECLARE
    v_base_volume FLOAT := 150000; -- Starting cumulative volume (liters)
    v_date TIMESTAMPTZ;
    v_hour INTEGER;
    v_flow_rate FLOAT;
    v_daily_volume FLOAT;
BEGIN
    -- Generate data for the last 7 days
    FOR day_offset IN 0..6 LOOP
        v_date := NOW() - INTERVAL '7 days' + (day_offset || ' days')::INTERVAL;
        v_daily_volume := 0;

        -- Generate hourly readings with daily water usage patterns
        FOR hour_offset IN 0..23 LOOP
            v_hour := hour_offset;

            -- Simulate daily water usage pattern for an office building
            -- Night (0-5): Low baseline flow (restrooms, cooling tower make-up)
            -- Morning (6-9): High flow (facility cleaning, morning restroom use)
            -- Business hours (9-17): Moderate flow (restroom, kitchen)
            -- Evening (17-23): Low flow (cleaning, reduced occupancy)

            CASE
                WHEN v_hour BETWEEN 0 AND 5 THEN
                    v_flow_rate := 2 + (random() * 1.5); -- 2-3.5 LPM baseline
                WHEN v_hour BETWEEN 6 AND 8 THEN
                    v_flow_rate := 15 + (random() * 10); -- 15-25 LPM (morning peak)
                WHEN v_hour BETWEEN 9 AND 16 THEN
                    v_flow_rate := 8 + (random() * 6); -- 8-14 LPM (business hours)
                WHEN v_hour BETWEEN 17 AND 20 THEN
                    v_flow_rate := 5 + (random() * 4); -- 5-9 LPM (evening cleaning)
                ELSE
                    v_flow_rate := 2 + (random() * 2); -- 2-4 LPM (night)
            END CASE;

            -- Add some random variation
            v_flow_rate := v_flow_rate * (0.8 + (random() * 0.4));

            -- Update cumulative volume (volume increases over time)
            v_base_volume := v_base_volume + (v_flow_rate * 60); -- Add hour's consumption

            -- Insert hourly reading
            INSERT INTO water_consumption (
                meter_id,
                site,
                volume_liters,
                flow_rate_lpm,
                timestamp,
                pulse_count,
                temperature,
                pressure
            ) VALUES (
                'S002-MTR-W-MAIN',
                'site-002',
                ROUND(v_base_volume, 2),
                ROUND(v_flow_rate, 2),
                v_date + (v_hour || ' hours')::INTERVAL,
                FLOOR(v_base_volume / 10)::INTEGER, -- 10 liters per pulse
                18 + (random() * 4), -- 18-22°C water temperature
                280 + (random() * 20) -- 280-300 kPa water pressure
            );
        END LOOP;

        RAISE NOTICE 'Generated water consumption data for day: day offset %', day_offset;
    END LOOP;

    RAISE NOTICE 'Water consumption data seeded for site-002: 7 days x 24 hours = 168 records';
END;
$$;

-- ============================================================================
-- Sample Water Alerts for site-002
-- Creates realistic leak detection scenarios
-- ============================================================================

DO $$
BEGIN
    -- Alert 1: Continuous flow alert (critical) - active
    -- Simulates a leak detected during off-hours (night flow)
    INSERT INTO water_alerts (
        alert_id,
        meter_id,
        site,
        alert_type,
        severity,
        status,
        timestamp,
        flow_rate_lpm,
        threshold_lpm,
        duration_minutes,
        description
    ) VALUES (
        gen_random_uuid()::TEXT,
        'S002-MTR-W-MAIN',
        'site-002',
        'continuous_flow',
        'critical',
        'active',
        NOW() - INTERVAL '2 hours',
        45.2,
        5.0, -- 5 LPM threshold for night flow
        120, -- 2 hours
        'Continuous flow detected during off-hours (02:00-04:00). Possible underground leak or stuck valve.'
    );

    -- Alert 2: Unusual pattern alert (medium) - active
    -- Simulates statistical anomaly - usage 180% above baseline
    INSERT INTO water_alerts (
        alert_id,
        meter_id,
        site,
        alert_type,
        severity,
        status,
        timestamp,
        flow_rate_lpm,
        threshold_lpm,
        duration_minutes,
        description
    ) VALUES (
        gen_random_uuid()::TEXT,
        'S002-MTR-W-MAIN',
        'site-002',
        'unusual_pattern',
        'medium',
        'active',
        NOW() - INTERVAL '3 hours',
        22.5,
        12.0, -- Baseline threshold
        45,
        'Water consumption 180% above baseline for this time of day. Unusual usage pattern detected.'
    );

    -- Alert 3: Spike alert (high) - resolved
    -- Simulates a temporary spike that was investigated and resolved
    INSERT INTO water_alerts (
        alert_id,
        meter_id,
        site,
        alert_type,
        severity,
        status,
        timestamp,
        flow_rate_lpm,
        threshold_lpm,
        duration_minutes,
        description,
        resolved_at,
        resolved_by,
        resolution_notes
    ) VALUES (
        gen_random_uuid()::TEXT,
        'S002-MTR-W-MAIN',
        'site-002',
        'spike',
        'high',
        'resolved',
        NOW() - INTERVAL '2 days',
        38.7,
        25.0,
        15,
        'Sudden flow spike detected. Short-duration event (<20 min).',
        NOW() - INTERVAL '2 days' + INTERVAL '1 hour',
        'admin',
        'Investigated: Cooling tower fill cycle. Normal operation, no issue found.'
    );

    -- Alert 4: Night flow alert (medium) - acknowledged
    -- Simulates elevated minimum night flow
    INSERT INTO water_alerts (
        alert_id,
        meter_id,
        site,
        alert_type,
        severity,
        status,
        timestamp,
        flow_rate_lpm,
        threshold_lpm,
        duration_minutes,
        description
    ) VALUES (
        gen_random_uuid()::TEXT,
        'S002-MTR-W-MAIN',
        'site-002',
        'night_flow',
        'medium',
        'acknowledged',
        NOW() - INTERVAL '5 hours',
        8.5,
        5.0,
        240, -- 4 hours
        'Minimum night flow exceeded. Expected baseline: 2-3 LPM, actual: 8.5 LPM. Possible slow leak.'
    );

    RAISE NOTICE 'Water alerts seeded for site-002: 4 alerts (2 active, 1 resolved, 1 acknowledged)';
END;
$$;

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS
ALTER TABLE water_consumption ENABLE ROW LEVEL SECURITY;
ALTER TABLE water_alerts ENABLE ROW LEVEL SECURITY;

-- Policy: All authenticated users can read water data
CREATE POLICY "Authenticated users can view water consumption"
    ON water_consumption FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Authenticated users can view water alerts"
    ON water_alerts FOR SELECT
    TO authenticated
    USING (true);

-- Policy: Service role can insert/update water data
CREATE POLICY "Service role can manage water consumption"
    ON water_consumption FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role can manage water alerts"
    ON water_alerts FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- Summary
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Water Meter Data Migration Complete';
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - water_consumption (168 sample records for site-002)';
    RAISE NOTICE '  - water_alerts (4 sample alerts for site-002)';
    RAISE NOTICE '';
    RAISE NOTICE 'Sample data includes:';
    RAISE NOTICE '  - 7 days of hourly consumption readings';
    RAISE NOTICE '  - Realistic daily usage patterns for office building';
    RAISE NOTICE '  - 4 leak detection alerts (mixed severity and status)';
    RAISE NOTICE '';
    RAISE NOTICE 'Main water meter: S002-MTR-W-MAIN';
    RAISE NOTICE 'Site: Sandton City Office Tower (site-002)';
    RAISE NOTICE '============================================================';
END;
$$;
