-- Space registry/settings canonical store migration
-- Moves remaining operational Space module state off JSON and into Postgres.

CREATE TABLE IF NOT EXISTS public.room_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    room_id TEXT NOT NULL UNIQUE,
    building TEXT NOT NULL,
    quadrant TEXT,
    room_type TEXT NOT NULL,
    room_number TEXT NOT NULL,
    capacity INTEGER,
    floor TEXT,
    friendly_name TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_room_registry_site
    ON public.room_registry(site_id);

CREATE INDEX IF NOT EXISTS idx_room_registry_building
    ON public.room_registry(building);

CREATE INDEX IF NOT EXISTS idx_room_registry_room_type
    ON public.room_registry(room_type);

CREATE TABLE IF NOT EXISTS public.space_concierges (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    site_id TEXT NOT NULL DEFAULT '',
    building_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    floor_assignments JSONB NOT NULL DEFAULT '{}'::jsonb,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_space_concierges_site_id
    ON public.space_concierges(site_id);

CREATE TABLE IF NOT EXISTS public.space_sensor_devices (
    sensor_id TEXT PRIMARY KEY,
    device_token TEXT NOT NULL UNIQUE,
    room_code TEXT NOT NULL,
    site_id TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    firmware_version TEXT,
    last_seen_at TIMESTAMPTZ,
    last_rssi INTEGER,
    uptime_seconds INTEGER,
    sensor_online BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_space_sensor_devices_site_id
    ON public.space_sensor_devices(site_id);

ALTER TABLE public.space_room_events
    ADD COLUMN IF NOT EXISTS event_type TEXT,
    ADD COLUMN IF NOT EXISTS rssi INTEGER,
    ADD COLUMN IF NOT EXISTS uptime_seconds INTEGER,
    ADD COLUMN IF NOT EXISTS firmware_version TEXT;
