-- Phase 131.2b: Email threading columns for email_intakes
-- Adds RFC 822 threading support so backend SMTP replies thread correctly.
--
-- New columns:
--   references_header    — inbound References header (for chain tracking)
--   outbound_message_id  — Message-ID of the reply we sent
--   outbound_sent_at     — timestamp when reply was sent
--   outbound_references  — References header on our outbound reply
--   reply_sent           — boolean: did backend send the reply (vs n8n fallback)

ALTER TABLE email_intakes
  ADD COLUMN IF NOT EXISTS references_header    TEXT,
  ADD COLUMN IF NOT EXISTS outbound_message_id  TEXT,
  ADD COLUMN IF NOT EXISTS outbound_sent_at     TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS outbound_references  TEXT,
  ADD COLUMN IF NOT EXISTS reply_sent           BOOLEAN DEFAULT FALSE;

-- Index on outbound_message_id for follow-up thread matching
CREATE INDEX IF NOT EXISTS idx_email_intakes_outbound_message_id
  ON email_intakes (outbound_message_id)
  WHERE outbound_message_id IS NOT NULL;

COMMENT ON COLUMN email_intakes.references_header IS 'Inbound RFC 822 References header for thread chain';
COMMENT ON COLUMN email_intakes.outbound_message_id IS 'Message-ID of SENTINEL auto-reply';
COMMENT ON COLUMN email_intakes.outbound_sent_at IS 'Timestamp when backend sent the reply';
COMMENT ON COLUMN email_intakes.outbound_references IS 'References header on outbound reply';
COMMENT ON COLUMN email_intakes.reply_sent IS 'True if backend sent threaded reply (false = n8n fallback)';
