-- Phase 206: Multi-Site Adapter Configuration
-- Add connection_config JSONB to site_adapter_config
-- Rename adapter_name -> protocol (more generic, supports BACnet/Modbus/oBix/Bridge)
-- Add poll_interval_seconds for per-adapter polling tuning

BEGIN;

-- Rename adapter_name column to protocol
ALTER TABLE site_adapter_config RENAME COLUMN adapter_name TO protocol;

-- Add connection_config JSONB - stores per-site per-protocol connection credentials
-- Schema per protocol:
--   bridge:   {"base_url": "http://10.99.0.1:8080", "token": "...", "poll_interval_seconds": 300}
--   bacnet:   {"host": "192.168.1.50", "port": 47808, "device_instance": 1234}
--   obix:     {"host": "192.168.1.50", "port": 8080, "use_https": false, "username": "...", "password": "..."}
--   modbus:   {"host": "192.168.1.50", "port": 502, "slave_id": 1}
ALTER TABLE site_adapter_config
    ADD COLUMN IF NOT EXISTS connection_config JSONB;

-- Add poll_interval_seconds with default
ALTER TABLE site_adapter_config
    ADD COLUMN IF NOT EXISTS poll_interval_seconds INTEGER NOT NULL DEFAULT 300;

-- Backfill existing rows with empty config
UPDATE site_adapter_config SET connection_config = '{}'::jsonb WHERE connection_config IS NULL;

-- Make NOT NULL after backfill
ALTER TABLE site_adapter_config ALTER COLUMN connection_config SET NOT NULL;

COMMIT;

-- Seed S001 bridge config (Fairlands/Wesbank - bridge-based, inactive)
INSERT INTO site_adapter_config (site_id, protocol, enabled, connection_config, poll_interval_seconds)
VALUES ('site-001', 'bridge', false, '{"base_url": "http://10.99.0.1:8080", "poll_interval_seconds": 300}'::jsonb, 300)
ON CONFLICT (site_id, protocol) DO NOTHING;

-- Seed S002 bridge config (Sandton City Tower - bridge-based, active)
INSERT INTO site_adapter_config (site_id, protocol, enabled, connection_config, poll_interval_seconds)
VALUES ('site-002', 'bridge', true, '{"base_url": "http://10.99.0.1:8080", "poll_interval_seconds": 300}'::jsonb, 300)
ON CONFLICT (site_id, protocol) DO NOTHING;
