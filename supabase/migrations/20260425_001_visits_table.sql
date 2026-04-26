-- Visitor intake table for Google Calendar + Outlook meeting invite pipeline
-- Creates PENDING visits when external attendees are added to calendar events
-- Transitions to CREATED + sends QR code when visitor accepts the invite

CREATE TABLE IF NOT EXISTS visits (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    token         UUID        NOT NULL UNIQUE,  -- Primary lookup for QR payload
    pin           TEXT        NOT NULL UNIQUE,  -- 6-digit fallback for reception scan

    visitor_email TEXT        NOT NULL,
    visitor_name  TEXT,
    visitor_photo TEXT,                             -- base64 encoded
    visitor_vehicle TEXT,
    visitor_id_number TEXT,

    host_email    TEXT        NOT NULL,
    host_name     TEXT,
    host_mobile   TEXT,

    building_id   TEXT        NOT NULL,  -- Maps to sites.code

    meeting_subject TEXT,
    meeting_start  TIMESTAMPTZ NOT NULL,
    meeting_end    TIMESTAMPTZ NOT NULL,

    status         TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending', 'created', 'arrived', 'registered',
                        'approved', 'denied', 'active', 'expired', 'cancelled'
                    )),

    access_card_id TEXT,

    qr_code        TEXT,  -- base64 PNG

    external_event_id TEXT,  -- gcal-{event_id} for idempotency

    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common lookups
CREATE INDEX IF NOT EXISTS idx_visits_token       ON visits (token);
CREATE INDEX IF NOT EXISTS idx_visits_pin        ON visits (pin);
CREATE INDEX IF NOT EXISTS idx_visits_external    ON visits (external_event_id);
CREATE INDEX IF NOT EXISTS idx_visits_visitor     ON visits (visitor_email);
CREATE INDEX IF NOT EXISTS idx_visits_status      ON visits (status);
CREATE INDEX IF NOT EXISTS idx_visits_building   ON visits (building_id);
CREATE INDEX IF NOT EXISTS idx_visits_meeting_start ON visits (meeting_start DESC);

-- Auto-expire old visits
CREATE OR REPLACE FUNCTION expire_old_visits()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'active'
       AND NEW.meeting_end < NOW() - INTERVAL '1 hour'
       AND TG_OP = 'UPDATE' THEN
        NEW.status = 'expired';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_expire_old_visits
    BEFORE UPDATE ON visits
    FOR EACH ROW EXECUTE FUNCTION expire_old_visits();

-- Updated-at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_visits_updated_at
    BEFORE UPDATE ON visits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMENT ON TABLE visits IS 'Google Calendar + Outlook visitor intake pipeline';
