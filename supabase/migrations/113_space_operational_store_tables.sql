-- Space operational store migration
-- Canonical Postgres tables for live room occupancy and ghost-booking workflows.

CREATE TABLE IF NOT EXISTS public.space_room_events (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    room_code TEXT NOT NULL,
    sensor_id TEXT,
    occupied BOOLEAN NOT NULL DEFAULT false,
    timestamp TIMESTAMPTZ NOT NULL,
    source TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    moving BOOLEAN,
    stationary BOOLEAN,
    distance_m DOUBLE PRECISION,
    moving_gate INTEGER,
    static_gate INTEGER
);

CREATE INDEX IF NOT EXISTS idx_space_room_events_room_timestamp
    ON public.space_room_events(room_code, timestamp);

CREATE INDEX IF NOT EXISTS idx_space_room_events_site_timestamp
    ON public.space_room_events(site_id, timestamp);

CREATE TABLE IF NOT EXISTS public.space_room_current_state (
    room_code TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    sensor_id TEXT,
    occupied BOOLEAN NOT NULL DEFAULT false,
    last_event_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    state JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_space_room_current_state_site_id
    ON public.space_room_current_state(site_id);

CREATE TABLE IF NOT EXISTS public.space_room_state_findings (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    room_code TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    finding JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_space_room_state_findings_room_resolved
    ON public.space_room_state_findings(room_code, resolved);

CREATE TABLE IF NOT EXISTS public.space_occupancy_events (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    room_code TEXT NOT NULL,
    sensor_id TEXT NOT NULL,
    occupied BOOLEAN NOT NULL DEFAULT false,
    timestamp TIMESTAMPTZ NOT NULL,
    source TEXT,
    received_at TIMESTAMPTZ NOT NULL,
    moving BOOLEAN,
    stationary BOOLEAN,
    distance_m DOUBLE PRECISION,
    moving_gate INTEGER,
    static_gate INTEGER
);

CREATE INDEX IF NOT EXISTS idx_space_occupancy_events_room_timestamp
    ON public.space_occupancy_events(room_code, timestamp);

CREATE INDEX IF NOT EXISTS idx_space_occupancy_events_site_timestamp
    ON public.space_occupancy_events(site_id, timestamp);

CREATE TABLE IF NOT EXISTS public.ghost_findings (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    room_code TEXT NOT NULL,
    room_name TEXT,
    booking_id TEXT NOT NULL,
    organiser_email TEXT,
    organiser_name TEXT,
    source_booking_flagged BOOLEAN NOT NULL DEFAULT false,
    booking_start TIMESTAMPTZ NOT NULL,
    booking_end TIMESTAMPTZ NOT NULL,
    grace_period_minutes INTEGER NOT NULL DEFAULT 0,
    detected_at TIMESTAMPTZ NOT NULL,
    notification_sent BOOLEAN NOT NULL DEFAULT false,
    notification_sent_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'open',
    resolved_at TIMESTAMPTZ,
    inspected_by TEXT,
    inspected_at TIMESTAMPTZ,
    concierge_email TEXT,
    concierge_whatsapp TEXT,
    email_notified_at TIMESTAMPTZ,
    whatsapp_notified_at TIMESTAMPTZ,
    whatsapp_message_id TEXT,
    response_message_id TEXT,
    response_text TEXT,
    reminder_sent BOOLEAN NOT NULL DEFAULT false,
    reminder_sent_at TIMESTAMPTZ,
    cost_centre TEXT,
    charge_amount DOUBLE PRECISION,
    charge_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_ghost_findings_site_status
    ON public.ghost_findings(site_id, status);

CREATE INDEX IF NOT EXISTS idx_ghost_findings_booking_id
    ON public.ghost_findings(booking_id);

CREATE INDEX IF NOT EXISTS idx_ghost_findings_concierge_whatsapp_status
    ON public.ghost_findings(concierge_whatsapp, status);

CREATE TABLE IF NOT EXISTS public.space_rightsizing_findings (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    room_code TEXT NOT NULL,
    room_name TEXT,
    room_capacity INTEGER NOT NULL DEFAULT 0,
    booking_id TEXT NOT NULL,
    organiser_email TEXT,
    organiser_name TEXT,
    booking_start TIMESTAMPTZ NOT NULL,
    booking_end TIMESTAMPTZ NOT NULL,
    booking_duration_minutes INTEGER NOT NULL DEFAULT 0,
    occupied_minutes INTEGER NOT NULL DEFAULT 0,
    vacancy_started_at TIMESTAMPTZ NOT NULL,
    consecutive_vacancy_minutes INTEGER NOT NULL DEFAULT 0,
    pattern_type TEXT,
    detected_at TIMESTAMPTZ NOT NULL,
    notification_sent BOOLEAN NOT NULL DEFAULT false,
    notification_sent_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'open'
);

CREATE INDEX IF NOT EXISTS idx_space_rightsizing_findings_site_status
    ON public.space_rightsizing_findings(site_id, status);

CREATE INDEX IF NOT EXISTS idx_space_rightsizing_findings_booking_id
    ON public.space_rightsizing_findings(booking_id);

CREATE TABLE IF NOT EXISTS public.space_focus_room_sessions (
    session_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    room_code TEXT NOT NULL,
    room_type TEXT NOT NULL DEFAULT 'focus',
    sensor_id TEXT,
    source TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    extended_use BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_space_focus_room_sessions_room_start
    ON public.space_focus_room_sessions(room_code, start_time);

CREATE INDEX IF NOT EXISTS idx_space_focus_room_sessions_site_start
    ON public.space_focus_room_sessions(site_id, start_time);
