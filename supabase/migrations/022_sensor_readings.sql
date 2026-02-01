-- Phase 42: Sensor Readings Time-Series Table
-- Uses Supabase (PostgreSQL) for time-series data
-- InfluxDB can be added later for production scale

-- Sensor readings table for ML training data
CREATE TABLE IF NOT EXISTS sensor_readings (
    id BIGSERIAL PRIMARY KEY,
    equipment_id TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    unit TEXT,
    recorded_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    building_id TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_sensor_readings_equipment_time 
    ON sensor_readings (equipment_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_lookup 
    ON sensor_readings (equipment_id, sensor_type, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_building 
    ON sensor_readings (building_id, recorded_at DESC);

-- Hourly aggregates materialized view (for ML features)
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_readings_hourly AS
SELECT 
    equipment_id,
    sensor_type,
    building_id,
    date_trunc('hour', recorded_at) AS hour,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS reading_count
FROM sensor_readings
GROUP BY equipment_id, sensor_type, building_id, date_trunc('hour', recorded_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_hourly_lookup 
    ON sensor_readings_hourly (equipment_id, sensor_type, hour);

-- Daily aggregates materialized view
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_readings_daily AS
SELECT 
    equipment_id,
    sensor_type,
    building_id,
    date_trunc('day', recorded_at) AS day,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS reading_count
FROM sensor_readings
GROUP BY equipment_id, sensor_type, building_id, date_trunc('day', recorded_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_daily_lookup 
    ON sensor_readings_daily (equipment_id, sensor_type, day);

-- Function to refresh materialized views (call via cron job)
CREATE OR REPLACE FUNCTION refresh_sensor_aggregates()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY sensor_readings_hourly;
    REFRESH MATERIALIZED VIEW CONCURRENTLY sensor_readings_daily;
END;
$$ LANGUAGE plpgsql;

-- Comment for documentation
COMMENT ON TABLE sensor_readings IS 'Time-series sensor data for ML training. For production scale (millions/day), migrate to InfluxDB.';
