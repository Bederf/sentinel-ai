CREATE TABLE IF NOT EXISTS telemetry_hourly (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    site_id text NOT NULL,
    equipment_id text NOT NULL,
    point_name text NOT NULL,
    hour_bucket timestamptz NOT NULL,
    value_min numeric,
    value_max numeric,
    value_avg numeric,
    value_count integer,
    unit text,
    created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_telemetry_hourly_site_equip_hour
    ON telemetry_hourly (site_id, equipment_id, hour_bucket DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_telemetry_hourly_unique
    ON telemetry_hourly (site_id, equipment_id, point_name, hour_bucket);

CREATE TABLE IF NOT EXISTS telemetry_daily (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    site_id text NOT NULL,
    equipment_id text NOT NULL,
    point_name text NOT NULL,
    day_bucket date NOT NULL,
    value_min numeric,
    value_max numeric,
    value_avg numeric,
    value_count integer,
    unit text,
    created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_telemetry_daily_site_equip_day
    ON telemetry_daily (site_id, equipment_id, day_bucket DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_telemetry_daily_unique
    ON telemetry_daily (site_id, equipment_id, point_name, day_bucket);

CREATE TABLE IF NOT EXISTS telemetry_events (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    site_id text NOT NULL,
    equipment_id text NOT NULL,
    event_type text NOT NULL,
    event_data jsonb NOT NULL,
    severity text,
    source text,
    occurred_at timestamptz NOT NULL,
    created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_telemetry_events_site_equip
    ON telemetry_events (site_id, equipment_id, occurred_at DESC);

ALTER TABLE equipment_sensor_readings ADD COLUMN IF NOT EXISTS quality_flag text DEFAULT 'ok';
