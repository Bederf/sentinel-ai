-- Phase 187: Filter health page adapters to only configured ones
-- Prevents showing DOWN status for phantom adapters (BACnetAdapter, DALIAdapter, etc.)
-- that don't run on this stack — only Shadow Bridge runs.

CREATE TABLE IF NOT EXISTS site_adapter_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, adapter_name)
);

-- Seed S002: only adapters that actually run on this stack
INSERT INTO site_adapter_config (site_id, adapter_name, enabled)
VALUES
    ('site-002', 'ShadowBridge', true),
    ('site-002', 'supervisor', true),
    ('site-002', 'field_network', true)
ON CONFLICT (site_id, adapter_name) DO NOTHING;

-- Also seed site-001 as inactive (won't show on health page for this stack)
INSERT INTO site_adapter_config (site_id, adapter_name, enabled)
VALUES ('site-001', 'ShadowBridge', false)
ON CONFLICT (site_id, adapter_name) DO NOTHING;
