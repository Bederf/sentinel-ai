-- Phase 156-01: Add missing signal_type_enum values for email signals
-- These types are used by the Fairlands signal fixtures.
-- ALTER TYPE ... ADD VALUE cannot run inside a transaction block.

ALTER TYPE signal_type_enum ADD VALUE IF NOT EXISTS 'observation_email';
ALTER TYPE signal_type_enum ADD VALUE IF NOT EXISTS 'intake_email';
ALTER TYPE signal_type_enum ADD VALUE IF NOT EXISTS 'action_request_email';
