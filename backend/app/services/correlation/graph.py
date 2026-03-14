"""
Graph traversal service for the correlation engine (Phase 156-05).

Calls the get_cluster_graph RPC function and returns nodes + edges
for Cytoscape.js visualization.
"""

from __future__ import annotations

import json
import uuid

import psycopg2.extras


def get_cluster_graph(conn, cluster_id: uuid.UUID, max_depth: int = 3) -> dict:
    """Call the get_cluster_graph RPC function and return the result.

    Args:
        conn: psycopg2 connection object.
        cluster_id: UUID of the cluster to traverse.
        max_depth: Maximum traversal depth (default 3).

    Returns:
        Dict with 'nodes' and 'edges' arrays for Cytoscape.js.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT get_cluster_graph(%s, %s) AS graph",
            (str(cluster_id), max_depth),
        )
        row = cur.fetchone()
        if row is None:
            return {"nodes": [], "edges": []}
        result = row["graph"]
        # psycopg2 may return string or dict depending on version
        if isinstance(result, str):
            result = json.loads(result)
        return result
    finally:
        cur.close()
