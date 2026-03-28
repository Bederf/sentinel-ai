-- Migration 112: Add routing_source to parasite_decisions
-- Tracks which execution path created each decision:
--   'recommendation_graph' = RecommendationGraph → TierRoutingEngine path
--   'optimization_api'     = POST /optimization/... → OptimizationTierRouter path (Phase 2)
--
-- DEFAULT NULL: existing rows have unknown source.
-- Use DEFAULT 'recommendation_graph' once Phase 2 integration is complete and
-- all new optimization writes go through ApprovalService.

ALTER TABLE parasite_decisions
  ADD COLUMN IF NOT EXISTS routing_source TEXT DEFAULT NULL;

COMMENT ON COLUMN parasite_decisions.routing_source IS
  'Execution path that created this decision: recommendation_graph | optimization_api | NULL (pre-migration)';
