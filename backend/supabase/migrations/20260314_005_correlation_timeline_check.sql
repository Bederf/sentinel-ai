-- Correlation & Issue Intelligence Layer — Timeline consistency check
-- Phase 155-01, Paranoid review fix
-- Prevents resolved_at being set before first_seen_at

ALTER TABLE issue_cluster
  ADD CONSTRAINT chk_issue_cluster_timeline CHECK (resolved_at IS NULL OR resolved_at >= first_seen_at);
