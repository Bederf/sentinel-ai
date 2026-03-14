-- Phase 156-05: Graph traversal RPC function and entity fixture additions
-- Adds missing entity-signal associations from BRIEF.md, then creates
-- the get_cluster_graph RPC function for Cytoscape.js visualization.

-- ============================================================================
-- Missing entity rows: entities that appear in multiple signals
-- Per BRIEF.md entity table:
--   Thandi Dineka -> signals 3, 7
--   Keryn Norman  -> signals 5, 8
--   Greg Temlett  -> signals 6, 9
--   Fairlands 1   -> signals 1, 3, 4, 7
--   Block booking -> signals 3, 5, 7
--   Room availability -> signals 5, 8
-- Original fixture (20260315_001) only linked each entity to one signal.
-- ============================================================================

-- Thandi Dineka also in signal 7
INSERT INTO entity (id, entity_type, entity_value, signal_id)
VALUES ('e1000000-0000-0000-0000-000000000014', 'person', 'Thandi Dineka', 'f1000000-0000-0000-0000-000000000007')
ON CONFLICT (id) DO NOTHING;

-- Keryn Norman also in signal 8
INSERT INTO entity (id, entity_type, entity_value, signal_id)
VALUES ('e1000000-0000-0000-0000-000000000015', 'person', 'Keryn Norman', 'f1000000-0000-0000-0000-000000000008')
ON CONFLICT (id) DO NOTHING;

-- Greg Temlett also in signal 9
INSERT INTO entity (id, entity_type, entity_value, signal_id)
VALUES ('e1000000-0000-0000-0000-000000000016', 'person', 'Greg Temlett', 'f1000000-0000-0000-0000-000000000009')
ON CONFLICT (id) DO NOTHING;

-- Fairlands 1 also in signals 3, 4, 7
INSERT INTO entity (id, entity_type, entity_value, signal_id)
VALUES
  ('e1000000-0000-0000-0000-000000000017', 'building', 'Fairlands 1', 'f1000000-0000-0000-0000-000000000003'),
  ('e1000000-0000-0000-0000-000000000018', 'building', 'Fairlands 1', 'f1000000-0000-0000-0000-000000000004'),
  ('e1000000-0000-0000-0000-000000000019', 'building', 'Fairlands 1', 'f1000000-0000-0000-0000-000000000007')
ON CONFLICT (id) DO NOTHING;

-- Block booking also in signals 5, 7
INSERT INTO entity (id, entity_type, entity_value, signal_id)
VALUES
  ('e1000000-0000-0000-0000-000000000020', 'booking_ref', 'Block booking', 'f1000000-0000-0000-0000-000000000005'),
  ('e1000000-0000-0000-0000-000000000021', 'booking_ref', 'Block booking', 'f1000000-0000-0000-0000-000000000007')
ON CONFLICT (id) DO NOTHING;

-- Room availability also in signal 8
INSERT INTO entity (id, entity_type, entity_value, signal_id)
VALUES ('e1000000-0000-0000-0000-000000000022', 'work_order', 'Room availability', 'f1000000-0000-0000-0000-000000000008')
ON CONFLICT (id) DO NOTHING;


-- ============================================================================
-- Graph traversal RPC function
-- ============================================================================

CREATE OR REPLACE FUNCTION get_cluster_graph(
    p_cluster_id uuid,
    p_max_depth integer DEFAULT 3
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    result jsonb;
BEGIN
    WITH RECURSIVE graph_walk AS (
        -- Base case: the cluster itself
        SELECT
            p_cluster_id AS node_id,
            'cluster'::text AS node_type,
            0 AS depth

        UNION ALL

        -- Walk outward via relationships
        SELECT
            CASE
                WHEN r.source_id = gw.node_id THEN r.target_id
                ELSE r.source_id
            END AS node_id,
            CASE
                WHEN r.source_id = gw.node_id THEN r.target_type::text
                ELSE r.source_type::text
            END AS node_type,
            gw.depth + 1 AS depth
        FROM graph_walk gw
        JOIN relationship r ON (r.source_id = gw.node_id OR r.target_id = gw.node_id)
        WHERE gw.depth < p_max_depth
    ),
    -- Deduplicate nodes
    distinct_nodes AS (
        SELECT DISTINCT ON (node_id) node_id, node_type, depth
        FROM graph_walk
        ORDER BY node_id, depth ASC
    ),
    -- Build node details
    node_details AS (
        -- Cluster nodes
        SELECT
            dn.node_id AS id,
            dn.node_type,
            ic.title AS label,
            ic.severity::text AS severity,
            ic.cluster_state::text AS cluster_state,
            NULL::text AS signal_type,
            NULL::text AS entity_type,
            NULL::text AS entity_value
        FROM distinct_nodes dn
        JOIN issue_cluster ic ON ic.id = dn.node_id
        WHERE dn.node_type = 'cluster'

        UNION ALL

        -- Signal nodes
        SELECT
            dn.node_id AS id,
            dn.node_type,
            COALESCE(
                s.metadata->>'sender',
                s.signal_type::text
            ) || ' - ' || s.signal_type::text AS label,
            s.severity::text AS severity,
            NULL AS cluster_state,
            s.signal_type::text AS signal_type,
            NULL AS entity_type,
            NULL AS entity_value
        FROM distinct_nodes dn
        JOIN signal s ON s.id = dn.node_id
        WHERE dn.node_type = 'signal'

        UNION ALL

        -- Entity nodes
        SELECT
            dn.node_id AS id,
            dn.node_type,
            e.entity_value AS label,
            NULL AS severity,
            NULL AS cluster_state,
            NULL AS signal_type,
            e.entity_type::text AS entity_type,
            e.entity_value AS entity_value
        FROM distinct_nodes dn
        JOIN entity e ON e.id = dn.node_id
        WHERE dn.node_type = 'entity'
    ),
    -- Edges between discovered nodes
    edge_details AS (
        SELECT
            r.id,
            r.source_id AS source,
            r.target_id AS target,
            r.edge_type::text AS edge_type,
            r.confidence::float AS confidence,
            r.evidence_basis
        FROM relationship r
        WHERE r.source_id IN (SELECT node_id FROM distinct_nodes)
          AND r.target_id IN (SELECT node_id FROM distinct_nodes)
    )
    SELECT jsonb_build_object(
        'nodes', COALESCE((SELECT jsonb_agg(
            jsonb_build_object(
                'id', nd.id,
                'node_type', nd.node_type,
                'label', nd.label,
                'severity', nd.severity,
                'cluster_state', nd.cluster_state,
                'signal_type', nd.signal_type,
                'entity_type', nd.entity_type,
                'entity_value', nd.entity_value
            )
        ) FROM node_details nd), '[]'::jsonb),
        'edges', COALESCE((SELECT jsonb_agg(
            jsonb_build_object(
                'id', ed.id,
                'source', ed.source,
                'target', ed.target,
                'edge_type', ed.edge_type,
                'confidence', ed.confidence,
                'evidence_basis', ed.evidence_basis
            )
        ) FROM edge_details ed), '[]'::jsonb)
    ) INTO result;

    RETURN result;
END;
$$;
