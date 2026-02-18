/**
 * Phase 102: Multi-Channel Technician Notifications
 * Migration 002: Technician Notification Preferences Table
 *
 * Stores per-technician notification preferences:
 * - Which channels are enabled (send to all enabled channels simultaneously)
 * - Preferred channel (primary choice when setting default)
 * - Alert severity threshold (only notify on warning+)
 * - Quiet hours (do not disturb: 22:00-06:00 default)
 * - Emergency override (critical alerts bypass quiet hours)
 * - Low-priority batching (group non-urgent alerts)
 *
 * Date: 2026-02-18
 */

CREATE TABLE IF NOT EXISTS public.technician_notification_preferences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  technician_id UUID NOT NULL UNIQUE,

  -- Channel selection
  preferred_channel TEXT NOT NULL DEFAULT 'telegram'
    CONSTRAINT valid_preferred_channel
      CHECK (preferred_channel IN ('telegram', 'whatsapp', 'sms')),

  enabled_channels TEXT[] NOT NULL DEFAULT ARRAY['telegram']
    CONSTRAINT valid_enabled_channels
      CHECK (
        enabled_channels IS NOT NULL AND
        array_length(enabled_channels, 1) > 0 AND
        enabled_channels <@ ARRAY['telegram', 'whatsapp', 'sms']
      ),

  -- Alert severity threshold
  alert_level_min TEXT NOT NULL DEFAULT 'warning'
    CONSTRAINT valid_alert_level_min
      CHECK (alert_level_min IN ('info', 'warning', 'critical')),

  -- Quiet hours (do not disturb)
  quiet_hours_enabled BOOLEAN DEFAULT true,
  quiet_hours_start TIME DEFAULT '22:00'::time,
  quiet_hours_end TIME DEFAULT '06:00'::time,

  -- Emergency override (critical alerts bypass quiet hours)
  emergency_override_enabled BOOLEAN DEFAULT true,

  -- Low-priority batching
  batch_low_priority BOOLEAN DEFAULT false,
  batch_interval_minutes INT DEFAULT 60
    CONSTRAINT valid_batch_interval CHECK (batch_interval_minutes > 0),

  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

  -- Foreign key
  CONSTRAINT fk_technician_id
    FOREIGN KEY (technician_id)
    REFERENCES public.technicians(id)
    ON DELETE CASCADE,

  -- Constraint: quiet_hours_end must be after quiet_hours_start
  -- (or if wrapping across midnight, both constraints are valid)
  CONSTRAINT quiet_hours_logic
    CHECK (
      quiet_hours_start IS NULL OR
      quiet_hours_end IS NULL OR
      quiet_hours_start != quiet_hours_end
    )
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_technician_notification_preferences_technician_id
  ON public.technician_notification_preferences(technician_id);

CREATE INDEX IF NOT EXISTS idx_technician_notification_preferences_alert_level
  ON public.technician_notification_preferences(alert_level_min);

-- Enable RLS
ALTER TABLE public.technician_notification_preferences ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Technicians can view/edit their own preferences
CREATE POLICY IF NOT EXISTS rls_technician_prefs_self
  ON public.technician_notification_preferences
  FOR ALL
  USING (
    auth.uid() = technician_id OR
    EXISTS (
      SELECT 1 FROM public.technicians t
      WHERE t.id = technician_notification_preferences.technician_id
      AND t.user_id = auth.uid()
    )
  );

-- RLS Policy: Service role (backend) can access all
CREATE POLICY IF NOT EXISTS rls_technician_prefs_service_role
  ON public.technician_notification_preferences
  FOR ALL
  USING (auth.role() = 'service_role');

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION public.update_technician_notification_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF NOT EXISTS trg_technician_notification_preferences_updated_at
  ON public.technician_notification_preferences;

CREATE TRIGGER trg_technician_notification_preferences_updated_at
  BEFORE UPDATE ON public.technician_notification_preferences
  FOR EACH ROW
  EXECUTE FUNCTION public.update_technician_notification_preferences_updated_at();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON public.technician_notification_preferences
  TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.technician_notification_preferences
  TO service_role;
