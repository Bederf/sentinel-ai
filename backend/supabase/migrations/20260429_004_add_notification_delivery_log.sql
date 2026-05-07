-- Migration 20260429_004: Add notification_delivery_log table
-- Required by: NotificationRepository.create_delivery_log() and get_delivery_logs()

BEGIN;

CREATE TABLE IF NOT EXISTS notification_delivery_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id UUID NOT NULL,
    technician_id UUID NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'sms', 'telegram', 'push')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'delivered', 'failed', 'read')),
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for technician lookup
CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_technician
    ON notification_delivery_log(technician_id, created_at DESC);

-- Index for notification lookup
CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_notification
    ON notification_delivery_log(notification_id);

-- Index for status filtering
CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_status
    ON notification_delivery_log(status, created_at DESC);

COMMENT ON TABLE notification_delivery_log IS 'Audit trail for every notification sent to technicians';

COMMIT;
