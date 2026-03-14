-- Correlation & Issue Intelligence Layer — Indexes, Foreign Keys, and Triggers
-- Phase 155-01, Task 3

-- ============================================================================
-- FOREIGN KEYS
-- ============================================================================

-- signal FKs
ALTER TABLE signal
  ADD CONSTRAINT fk_signal_issue_cluster
    FOREIGN KEY (issue_cluster_id) REFERENCES issue_cluster(id) ON DELETE SET NULL;

ALTER TABLE signal
  ADD CONSTRAINT fk_signal_email_thread
    FOREIGN KEY (email_thread_id) REFERENCES email_thread(id) ON DELETE SET NULL;

ALTER TABLE signal
  ADD CONSTRAINT fk_signal_parent
    FOREIGN KEY (parent_signal_id) REFERENCES signal(id) ON DELETE SET NULL;

ALTER TABLE signal
  ADD CONSTRAINT fk_signal_site
    FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE SET NULL;

-- issue_cluster FKs
ALTER TABLE issue_cluster
  ADD CONSTRAINT fk_issue_cluster_site
    FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE SET NULL;

-- issue_classification FKs
ALTER TABLE issue_classification
  ADD CONSTRAINT fk_issue_classification_cluster
    FOREIGN KEY (issue_cluster_id) REFERENCES issue_cluster(id) ON DELETE CASCADE;

-- entity FKs
ALTER TABLE entity
  ADD CONSTRAINT fk_entity_signal
    FOREIGN KEY (signal_id) REFERENCES signal(id) ON DELETE SET NULL;

ALTER TABLE entity
  ADD CONSTRAINT fk_entity_cluster
    FOREIGN KEY (issue_cluster_id) REFERENCES issue_cluster(id) ON DELETE SET NULL;

-- issue_evidence FKs
ALTER TABLE issue_evidence
  ADD CONSTRAINT fk_issue_evidence_cluster
    FOREIGN KEY (issue_cluster_id) REFERENCES issue_cluster(id) ON DELETE CASCADE;

-- dashboard_card FKs
ALTER TABLE dashboard_card
  ADD CONSTRAINT fk_dashboard_card_cluster
    FOREIGN KEY (issue_cluster_id) REFERENCES issue_cluster(id) ON DELETE CASCADE;

ALTER TABLE dashboard_card
  ADD CONSTRAINT fk_dashboard_card_role
    FOREIGN KEY (recipient_role_assignment_id) REFERENCES role_assignment(id) ON DELETE CASCADE;

-- ============================================================================
-- INDEXES
-- ============================================================================

-- signal indexes
CREATE INDEX idx_signal_location_ref ON signal (location_ref);
CREATE INDEX idx_signal_created_at ON signal (created_at);
CREATE INDEX idx_signal_resolution_state ON signal (resolution_state);
CREATE INDEX idx_signal_signal_type ON signal (signal_type);
CREATE INDEX idx_signal_issue_cluster_id ON signal (issue_cluster_id);
CREATE INDEX idx_signal_site_id ON signal (site_id);
CREATE INDEX idx_signal_is_managed ON signal (is_managed);
CREATE INDEX idx_signal_email_thread_id ON signal (email_thread_id);

-- pgvector index — cosine metric explicitly (NOT L2 default)
CREATE INDEX idx_signal_embedding ON signal USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- issue_cluster indexes
CREATE INDEX idx_issue_cluster_state ON issue_cluster (cluster_state);
CREATE INDEX idx_issue_cluster_severity ON issue_cluster (severity);
CREATE INDEX idx_issue_cluster_site_id ON issue_cluster (site_id);
CREATE INDEX idx_issue_cluster_first_seen_at ON issue_cluster (first_seen_at DESC);

-- relationship indexes
CREATE INDEX idx_relationship_source_id ON relationship (source_id);
CREATE INDEX idx_relationship_target_id ON relationship (target_id);
CREATE INDEX idx_relationship_edge_type ON relationship (edge_type);
CREATE INDEX idx_relationship_source_target ON relationship (source_id, target_id);

-- entity indexes
CREATE INDEX idx_entity_issue_cluster_id ON entity (issue_cluster_id);
CREATE INDEX idx_entity_type_value ON entity (entity_type, entity_value);

-- role_assignment indexes
CREATE INDEX idx_role_assignment_person_name ON role_assignment (person_name);
CREATE INDEX idx_role_assignment_location_scope ON role_assignment (location_scope);

-- dashboard_card indexes
CREATE INDEX idx_dashboard_card_recipient ON dashboard_card (recipient_role_assignment_id);
CREATE INDEX idx_dashboard_card_cluster ON dashboard_card (issue_cluster_id);
CREATE INDEX idx_dashboard_card_surfaced_at ON dashboard_card (surfaced_at DESC);

-- ============================================================================
-- SITE DELETION CLEANUP TRIGGER
-- ============================================================================

-- When a site is deleted, ON DELETE SET NULL sets site_id to NULL.
-- But is_managed and site_resolution_status must also be updated
-- to prevent logical contradictions (is_managed=true with no site).
CREATE OR REPLACE FUNCTION cleanup_orphaned_site_refs()
RETURNS TRIGGER AS $$
BEGIN
  -- When site_id becomes NULL via ON DELETE SET NULL, fix related fields
  UPDATE signal
    SET is_managed = false, site_resolution_status = 'unresolved'
    WHERE site_id IS NULL AND (is_managed = true OR site_resolution_status != 'unresolved');

  UPDATE issue_cluster
    SET is_managed = false
    WHERE site_id IS NULL AND is_managed = true;

  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Fire after any DELETE on sites table
CREATE TRIGGER trg_cleanup_orphaned_site_refs
  AFTER DELETE ON sites
  FOR EACH STATEMENT
  EXECUTE FUNCTION cleanup_orphaned_site_refs();
