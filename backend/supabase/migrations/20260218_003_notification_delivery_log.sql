/**
 * Phase 102: Multi-Channel Technician Notifications
 * Migration 003: Notification Delivery Log Table
 *
 * Audit trail for all notifications sent:
 * - What: notification type, title, body
 * - How: channel type, recipient
 * - When: sent_at, delivered_at timestamps
 * - Status: pending, sent, delivered, failed
 * - Error tracking: error_message, error_code, retry_count
 * - Provider integration: external_message_id, provider_response
 *
 * Used for:
 * - Debugging delivery failures
 * - Audit compliance (who was notified when)
 * - Delivery statistics (success rate per channel)
 * - Retry logic (failed notifications can be retried)
 *
 * Date: 2026-02-18
 */

CREATE TABLE IF NOT EXISTS public.notification_delivery_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- References (optional for orphan handling)
  work_order_id UUID,
  technician_id UUID NOT NULL,

  -- Notification content
  notification_type TEXT NOT NULL,  -- 'work_order_assigned', 'alert', 'update', 'test'
  title TEXT NOT NULL,
  body TEXT NOT NULL,

  -- Delivery method
  channel_type TEXT NOT NULL
    CONSTRAINT valid_channel_type CHECK (channel_type IN ('telegram', 'whatsapp', 'sms')),

  recipient_identifier TEXT NOT NULL,  -- Phone number, Telegram ID, etc.

  -- Delivery status
  status TEXT NOT NULL DEFAULT 'pending'
    CONSTRAINT valid_status CHECK (status IN ('pending', 'sent', 'delivered', 'failed')),

  error_message TEXT,
  error_code TEXT,  -- Provider error code ('invalid_number', 'rate_limit', 'auth_failed', etc.)

  -- Tracking
  external_message_id TEXT,         -- Provider's message ID for future lookups
  sent_at TIMESTAMP WITH TIME ZONE,
  delivered_at TIMESTAMP WITH TIME ZONE,

  -- Provider details
  provider TEXT,                    -- 'sentrybot', 'meta', 'twilio', 'bulksms'
  provider_response JSONB,          -- Full response from provider

  -- Retry tracking
  retry_count INT DEFAULT 0,
  last_retry_at TIMESTAMP WITH TIME ZONE,
  max_retries INT DEFAULT 3,

  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

  -- Foreign key constraints
  CONSTRAINT fk_work_order_id
    FOREIGN KEY (work_order_id)
    REFERENCES public.work_orders(id)
    ON DELETE SET NULL,

  CONSTRAINT fk_technician_id
    FOREIGN KEY (technician_id)
    REFERENCES public.technicians(id)
    ON DELETE CASCADE
);

-- Create indexes for query performance
CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_work_order_id
  ON public.notification_delivery_log(work_order_id);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_technician_id
  ON public.notification_delivery_log(technician_id);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_status
  ON public.notification_delivery_log(status);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_channel_type
  ON public.notification_delivery_log(channel_type);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_created_at
  ON public.notification_delivery_log(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_notification_type
  ON public.notification_delivery_log(notification_type);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_technician_status_created
  ON public.notification_delivery_log(technician_id, status, created_at DESC);

-- Enable RLS
-- Note: Simplified for dev environment. Production will use more restrictive policies.
ALTER TABLE public.notification_delivery_log ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Service role (backend) can do everything
DROP POLICY IF EXISTS rls_delivery_log_service_role ON public.notification_delivery_log;
CREATE POLICY rls_delivery_log_service_role
  ON public.notification_delivery_log
  FOR ALL
  USING (auth.role() = 'service_role');

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION public.update_notification_delivery_log_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notification_delivery_log_updated_at
  ON public.notification_delivery_log;

CREATE TRIGGER trg_notification_delivery_log_updated_at
  BEFORE UPDATE ON public.notification_delivery_log
  FOR EACH ROW
  EXECUTE FUNCTION public.update_notification_delivery_log_updated_at();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON public.notification_delivery_log
  TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.notification_delivery_log
  TO service_role;

-- View for delivery statistics (useful for dashboards)
CREATE OR REPLACE VIEW public.notification_delivery_stats_hourly AS
SELECT
  date_trunc('hour', created_at) as hour,
  channel_type,
  status,
  COUNT(*) as count,
  COUNT(CASE WHEN error_code IS NOT NULL THEN 1 END) as error_count
FROM public.notification_delivery_log
GROUP BY date_trunc('hour', created_at), channel_type, status;

GRANT SELECT ON public.notification_delivery_stats_hourly TO authenticated, service_role;
