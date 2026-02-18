/**
 * Phase 102: Multi-Channel Technician Notifications
 * Migration 001: Technician Notification Channels Table
 *
 * Stores contact information for each notification channel per technician.
 * - One row per technician per channel (Telegram, WhatsApp, SMS)
 * - Contact details stored based on channel type
 * - is_verified tracks technician confirmation
 * - Technicians self-onboard via Settings UI
 *
 * Date: 2026-02-18
 */

-- Create technician_notification_channels table
CREATE TABLE IF NOT EXISTS public.technician_notification_channels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  technician_id UUID NOT NULL,
  channel_type TEXT NOT NULL,

  -- Contact details (one per channel type)
  telegram_id TEXT,                           -- Telegram user ID (e.g., "123456789")
  whatsapp_number TEXT,                       -- WhatsApp phone (e.g., "+27123456789")
  sms_number TEXT,                            -- SMS phone (e.g., "+27123456789")

  -- Verification & status
  is_verified BOOLEAN DEFAULT false,          -- Technician confirmed this channel works?
  verified_at TIMESTAMP WITH TIME ZONE,       -- When was it verified?
  verification_attempts INT DEFAULT 0,        -- How many times tried to verify?

  -- Channel-specific settings
  settings JSONB DEFAULT '{}'::jsonb,         -- Future: do_not_disturb, preferences, etc.

  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

  -- Foreign key constraint
  CONSTRAINT fk_technician_id
    FOREIGN KEY (technician_id)
    REFERENCES public.technicians(id)
    ON DELETE CASCADE,

  -- Constraints
  CONSTRAINT valid_channel_type
    CHECK (channel_type IN ('telegram', 'whatsapp', 'sms')),

  -- One entry per technician per channel
  CONSTRAINT unique_technician_channel
    UNIQUE (technician_id, channel_type),

  -- At least one contact detail must be present
  CONSTRAINT contact_detail_required
    CHECK (
      (channel_type = 'telegram' AND telegram_id IS NOT NULL) OR
      (channel_type = 'whatsapp' AND whatsapp_number IS NOT NULL) OR
      (channel_type = 'sms' AND sms_number IS NOT NULL)
    )
);

-- Create indexes for query performance
CREATE INDEX IF NOT EXISTS idx_technician_notification_channels_technician_id
  ON public.technician_notification_channels(technician_id);

CREATE INDEX IF NOT EXISTS idx_technician_notification_channels_channel_type
  ON public.technician_notification_channels(channel_type);

CREATE INDEX IF NOT EXISTS idx_technician_notification_channels_verified
  ON public.technician_notification_channels(is_verified);

-- Enable RLS (Row Level Security)
ALTER TABLE public.technician_notification_channels ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Technicians can view/edit their own channels
CREATE POLICY IF NOT EXISTS rls_technician_channels_self
  ON public.technician_notification_channels
  FOR ALL
  USING (
    -- Technician can access their own channels
    auth.uid() = technician_id OR
    -- Or if user is the technician (join with technicians table)
    EXISTS (
      SELECT 1 FROM public.technicians t
      WHERE t.id = technician_notification_channels.technician_id
      AND t.user_id = auth.uid()
    )
  );

-- RLS Policy: Service role (backend) can access all
CREATE POLICY IF NOT EXISTS rls_technician_channels_service_role
  ON public.technician_notification_channels
  FOR ALL
  USING (auth.role() = 'service_role');

-- Add trigger to update updated_at on changes
CREATE OR REPLACE FUNCTION public.update_technician_notification_channels_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF NOT EXISTS trg_technician_notification_channels_updated_at
  ON public.technician_notification_channels;

CREATE TRIGGER trg_technician_notification_channels_updated_at
  BEFORE UPDATE ON public.technician_notification_channels
  FOR EACH ROW
  EXECUTE FUNCTION public.update_technician_notification_channels_updated_at();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON public.technician_notification_channels
  TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.technician_notification_channels
  TO service_role;
