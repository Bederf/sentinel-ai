BEGIN;

CREATE TABLE IF NOT EXISTS public.block_booking_records (
    id uuid PRIMARY KEY,
    site_id text NOT NULL,
    organiser_email text NOT NULL,
    organiser_name text NOT NULL DEFAULT '',
    room_id text NOT NULL DEFAULT '',
    room_name text NOT NULL DEFAULT '',
    booking_date date NOT NULL,
    start_time timestamptz NOT NULL,
    end_time timestamptz NOT NULL,
    raw_email_hash text NOT NULL UNIQUE,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    flagged boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_block_booking_records_site_date
    ON public.block_booking_records(site_id, booking_date);

CREATE INDEX IF NOT EXISTS idx_block_booking_records_site_created
    ON public.block_booking_records(site_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_block_booking_records_site_organiser_date
    ON public.block_booking_records(site_id, organiser_email, booking_date);


CREATE TABLE IF NOT EXISTS public.block_booking_alerts (
    id uuid PRIMARY KEY,
    site_id text NOT NULL,
    organiser_email text NOT NULL,
    organiser_name text NOT NULL DEFAULT '',
    overlap_window_start timestamptz NOT NULL,
    overlap_window_end timestamptz NOT NULL,
    rooms jsonb NOT NULL DEFAULT '[]'::jsonb,
    room_count integer NOT NULL DEFAULT 0,
    booking_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    detected_at timestamptz NOT NULL DEFAULT now(),
    notification_sent boolean NOT NULL DEFAULT false,
    notification_sent_at timestamptz NULL,
    dismissed boolean NOT NULL DEFAULT false,
    dismissed_at timestamptz NULL,
    dismissed_by text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_block_booking_alerts_site_dismissed
    ON public.block_booking_alerts(site_id, dismissed, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_block_booking_alerts_site_organiser_window
    ON public.block_booking_alerts(site_id, organiser_email, overlap_window_start, overlap_window_end);

COMMIT;
