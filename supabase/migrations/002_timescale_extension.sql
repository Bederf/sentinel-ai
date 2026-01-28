-- =====================================================
-- Migration 002: TimescaleDB Extension + Sensor Readings
-- =====================================================

-- Try to enable TimescaleDB extension for time-series sensor readings
-- This will work in production but fall back gracefully in local dev
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS timescaledb;
EXCEPTION
  WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB not available, using regular table';
END $$;

-- Hypertable for sensor readings (time-series data)
-- This will handle the 24MB+ of time-series data efficiently
CREATE TABLE IF NOT EXISTS sensor_readings (
  time TIMESTAMPTZ NOT NULL,
  sensor_id UUID NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
  value DECIMAL(12, 4) NOT NULL,
  quality TEXT CHECK (quality IN ('good', 'uncertain', 'bad', 'maintenance')),
  metadata JSONB DEFAULT '{}',
  CONSTRAINT sensor_readings_pkey PRIMARY KEY (time, sensor_id)
);

-- Try to convert to hypertable if TimescaleDB is available
DO $$
BEGIN
  PERFORM create_hypertable('sensor_readings', 'time', chunk_time_interval => INTERVAL '1 day');
  RAISE NOTICE 'Created TimescaleDB hypertable';
EXCEPTION
  WHEN OTHERS THEN
    RAISE NOTICE 'Using regular table (TimescaleDB not available)';
END $$;

-- Create indexes for common time-range queries
CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_time ON sensor_readings(sensor_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_time ON sensor_readings(time DESC);
