-- Add certified notification fields to notification_delivery_log
-- Supports: acknowledgement button + escalation timeout + escalation tracking

ALTER TABLE notification_delivery_log
ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS acknowledged_by TEXT,
ADD COLUMN IF NOT EXISTS escalated BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS timeout_minutes INTEGER NOT NULL DEFAULT 15,
ADD COLUMN IF NOT EXISTS notification_id TEXT;  -- Certified notification tracking ID

-- Index for fast lookup by notification_id (used in acknowledgement callbacks)
CREATE INDEX IF NOT EXISTS idx_delivery_log_notification_id
ON notification_delivery_log(notification_id)
WHERE notification_id IS NOT NULL;

-- Index for escalation queries (unacknowledged after timeout)
CREATE INDEX IF NOT EXISTS idx_delivery_log_escalate_candidate
ON notification_delivery_log(created_at)
WHERE escalated = false AND acknowledged_at IS NULL;
