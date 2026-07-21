CREATE TABLE IF NOT EXISTS public.consent_records (
  record_id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  data_subject_id text NOT NULL,
  platform text NOT NULL CHECK (platform IN ('whatsapp', 'telegram', 'web', 'withdrawal')),
  consent_type text NOT NULL CHECK (consent_type IN ('pi_processing', 'data_retention', 'cross_border_transfer')),
  consent_given boolean NOT NULL,
  consent_text text NOT NULL,
  given_at timestamptz NOT NULL,
  expires_at timestamptz,
  withdrawn_at timestamptz,
  ip_address text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_consent_records_subject_id
  ON public.consent_records(data_subject_id);

CREATE INDEX IF NOT EXISTS idx_consent_records_subject_type
  ON public.consent_records(data_subject_id, consent_type);

CREATE INDEX IF NOT EXISTS idx_consent_records_given_at
  ON public.consent_records(given_at DESC);

CREATE INDEX IF NOT EXISTS idx_consent_records_withdrawn
  ON public.consent_records(withdrawn_at)
  WHERE withdrawn_at IS NOT NULL;

COMMENT ON TABLE public.consent_records IS
  'POPIA-compliant immutable consent records. Withdrawals create new records (do not mutate existing ones).';
COMMENT ON COLUMN public.consent_records.record_id IS 'UUID v4, immutable record identifier';
COMMENT ON COLUMN public.consent_records.data_subject_id IS 'SHA-256 hashed phone number or user identifier (plain text never stored)';
COMMENT ON COLUMN public.consent_records.platform IS 'Originating platform: whatsapp, telegram, web, or withdrawal';
COMMENT ON COLUMN public.consent_records.consent_type IS 'pi_processing, data_retention, or cross_border_transfer';
COMMENT ON COLUMN public.consent_records.consent_given IS 'True if consented, False if declined or withdrawn';
COMMENT ON COLUMN public.consent_records.consent_text IS 'Exact text the data subject agreed to at time of consent';
COMMENT ON COLUMN public.consent_records.given_at IS 'ISO 8601 timestamp when the consent decision was made';
COMMENT ON COLUMN public.consent_records.expires_at IS 'Optional expiry date for time-limited consent';
COMMENT ON COLUMN public.consent_records.withdrawn_at IS 'Set when the consent is withdrawn (new record created)';
COMMENT ON COLUMN public.consent_records.ip_address IS 'IP address of the data subject at time of consent';
COMMENT ON COLUMN public.consent_records.metadata IS 'Platform-specific metadata (device info, session ID, etc.)';
