-- Phase: Email Heatmap
-- When 3+ occupant emails cluster around a zone, surface it as a cockpit heatmap signal.
-- n8n POSTs each parsed email to /api/emails/intake → stored here → surfaced via building-state API.

-- ============================================================================
-- email_clusters
-- One row per zone cluster. A cluster = one issue type in one zone (or adjacent zones).
-- ============================================================================
CREATE TABLE IF NOT EXISTS email_clusters (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id          TEXT        NOT NULL,
  zone_id          TEXT        NOT NULL,
  zone_name        TEXT,
  floor            TEXT,
  complaint_type   TEXT        NOT NULL,  -- hvac | thermal | fault | occupant | energy | security | water | general
  keywords         TEXT[]      NOT NULL DEFAULT '{}',
  email_count      INTEGER     NOT NULL DEFAULT 1,
  first_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status           TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'triaged', 'resolved')),
  severity         TEXT        NOT NULL DEFAULT 'low' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  summary          TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT email_clusters_site_fk FOREIGN KEY (site_id) REFERENCES sites(code) ON DELETE CASCADE
);

COMMENT ON TABLE email_clusters IS 'Zone-level complaint clusters derived from occupant email intake.';
COMMENT ON COLUMN email_clusters.complaint_type IS 'Taxonomy discipline: hvac|thermal|fault|occupant|energy|security|water|general.';
COMMENT ON COLUMN email_clusters.severity IS 'Derived from email_count: 3-5=medium, 6-10=high, 11+=critical.';

CREATE INDEX IF NOT EXISTS idx_email_clusters_site_id     ON email_clusters (site_id);
CREATE INDEX IF NOT EXISTS idx_email_clusters_zone_id     ON email_clusters (zone_id);
CREATE INDEX IF NOT EXISTS idx_email_clusters_status       ON email_clusters (status) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_email_clusters_floor        ON email_clusters (floor);

-- ============================================================================
-- email_intake_clusters
-- Junction: links each email intake to its cluster.
-- Enables evidence trail (which emails feed which cluster) and dedup.
-- ============================================================================
CREATE TABLE IF NOT EXISTS email_intake_clusters (
  intake_id   UUID NOT NULL,
  cluster_id  UUID NOT NULL,
  added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  PRIMARY KEY (intake_id, cluster_id),
  CONSTRAINT eic_intake_fk  FOREIGN KEY (intake_id)  REFERENCES email_intakes(id)  ON DELETE CASCADE,
  CONSTRAINT eic_cluster_fk  FOREIGN KEY (cluster_id) REFERENCES email_clusters(id) ON DELETE CASCADE
);

COMMENT ON TABLE email_intake_clusters IS 'Junction: email intake → complaint cluster.';
CREATE INDEX IF NOT EXISTS idx_eic_cluster_id ON email_intake_clusters (cluster_id);

-- ============================================================================
-- Auto-close: stale open clusters (no new emails in 48h) → triaged
-- Run via pg_cron or background scheduler.
-- ============================================================================
CREATE OR REPLACE FUNCTION close_stale_email_clusters()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE email_clusters
  SET
    status     = 'triaged',
    updated_at = NOW()
  WHERE
    status = 'open'
    AND last_seen < NOW() - INTERVAL '48 hours';
END;
$$;

-- Trigger to keep updated_at current
CREATE TRIGGER trg_email_clusters_updated_at
  BEFORE UPDATE ON email_clusters
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger to refresh updated_at on junction insert
CREATE TRIGGER trg_email_intake_clusters_updated_at
  BEFORE INSERT ON email_intake_clusters
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- RLS
-- ============================================================================
ALTER TABLE email_clusters       ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_intake_clusters ENABLE ROW LEVEL SECURITY;

-- Service-role (backend API) has full access via anon key.
-- Authenticated users can read their org's clusters.
CREATE POLICY "service_role_all_email_clusters"
  ON email_clusters FOR ALL
  TO service_role
  USING (true);

CREATE POLICY "service_role_all_eic"
  ON email_intake_clusters FOR ALL
  TO service_role
  USING (true);
