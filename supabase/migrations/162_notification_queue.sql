-- Phase 228: Notification Queue — decouple alert creation from CLI latency
-- Migration: 20260612_001
-- Purpose: Database-backed queue so POST /api/alerts returns <500ms
--          while CLI execution runs asynchronously via APScheduler worker.

CREATE TABLE IF NOT EXISTS notification_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    alert_id TEXT,
    notification_type TEXT NOT NULL DEFAULT 'alert',
    payload JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    scheduled_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ
);

-- Index for the worker: fetch oldest pending notifications quickly
CREATE INDEX IF NOT EXISTS idx_notification_queue_pending
    ON notification_queue (created_at ASC)
    WHERE status = 'pending';

-- Index for monitoring queue depth per status
CREATE INDEX IF NOT EXISTS idx_notification_queue_status
    ON notification_queue (status);

COMMENT ON TABLE notification_queue IS 'Async notification queue — alerts enqueued by API, processed by APScheduler worker';
COMMENT ON COLUMN notification_queue.id IS 'Unique identifier for each queued notification';
COMMENT ON COLUMN notification_queue.alert_id IS 'Optional reference to the originating alert';
COMMENT ON COLUMN notification_queue.notification_type IS 'Type of notification (alert, reminder, etc.)';
COMMENT ON COLUMN notification_queue.payload IS 'JSON payload passed to the notification provider';
COMMENT ON COLUMN notification_queue.status IS 'Lifecycle: pending → processing → sent | failed';
COMMENT ON COLUMN notification_queue.attempts IS 'Number of delivery attempts so far';
COMMENT ON COLUMN notification_queue.max_attempts IS 'Maximum delivery attempts before permanent failure';
COMMENT ON COLUMN notification_queue.last_error IS 'Error message from the last failed attempt';
COMMENT ON COLUMN notification_queue.scheduled_at IS 'When the notification should be sent (null = immediate)';
COMMENT ON COLUMN notification_queue.processed_at IS 'When the notification was actually processed';
