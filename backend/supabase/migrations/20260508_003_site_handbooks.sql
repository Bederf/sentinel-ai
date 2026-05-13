-- Site-specific building handbooks (markdown) for staff bot
-- Stores uploaded BUILDING_HANDBOOK.md content per site

CREATE TABLE IF NOT EXISTS site_handbooks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id       text NOT NULL,
    content       text NOT NULL,
    version       integer NOT NULL DEFAULT 1,
    uploaded_by   text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT site_handbooks_one_per_site UNIQUE (site_id)
);

ALTER TABLE site_handbooks ENABLE ROW LEVEL SECURITY;

-- Anyone authenticated can read
CREATE POLICY site_handbooks_read ON site_handbooks FOR SELECT USING (true);

-- Only authenticated users with OPERATOR role or higher can insert/update
CREATE POLICY site_handbooks_write ON site_handbooks FOR INSERT
    WITH CHECK (true);
CREATE POLICY site_handbooks_update ON site_handbooks FOR UPDATE
    USING (true);
