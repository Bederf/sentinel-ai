-- Agent Memory Table
-- Persistent conversational memory for SENTINEL AI agents.
-- Stores building quirks, operator preferences, equipment notes, and seasonal patterns
-- so that Claude doesn't re-discover the same knowledge every session.

CREATE TABLE IF NOT EXISTS agent_memory (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    equipment_code TEXT,
    context_type TEXT NOT NULL CHECK (context_type IN (
        'building_quirk',
        'equipment_note',
        'operator_preference',
        'seasonal',
        'safety_note'
    )),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'system' CHECK (source IN (
        'claude', 'sentry', 'simbiot', 'operator', 'system'
    )),
    confidence REAL NOT NULL DEFAULT 1.0,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unique constraint: one memory per (site, equipment/null, key)
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memory_site_equip_key
    ON agent_memory (site_id, COALESCE(equipment_code, '__site__'), key);

-- Fast lookup by site
CREATE INDEX IF NOT EXISTS idx_agent_memory_site_id
    ON agent_memory (site_id);

-- Fast lookup by context type
CREATE INDEX IF NOT EXISTS idx_agent_memory_context_type
    ON agent_memory (context_type);

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_agent_memory_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_memory_updated_at ON agent_memory;
CREATE TRIGGER trg_agent_memory_updated_at
    BEFORE UPDATE ON agent_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_agent_memory_updated_at();

-- RLS policies
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;

CREATE POLICY agent_memory_read_all ON agent_memory
    FOR SELECT USING (true);

CREATE POLICY agent_memory_write_authenticated ON agent_memory
    FOR ALL USING (auth.role() = 'authenticated');
