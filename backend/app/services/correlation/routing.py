"""
Routing layer for the correlation engine (Phase 156-04).

Matches clusters to responsible role holders via location scope
wildcard matching and domain overlap.
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Location scope matching
# ---------------------------------------------------------------------------


def match_location_scope(
    cluster_location_refs: list[str],
    scope_pattern: str,
) -> bool:
    """
    Check whether a role_assignment's location_scope pattern matches any
    of the cluster's signal location references.

    Pattern matching rules:
    - Split both on '/' into segments
    - '*' matches anything at that level
    - Exact string match required otherwise
    - If scope pattern has fewer segments, pad with '*'
    - Returns True if at least one location_ref matches
    """
    scope_segments = scope_pattern.split("/")

    for location_ref in cluster_location_refs:
        ref_segments = location_ref.split("/")

        # Pad scope with wildcards if shorter
        padded_scope = list(scope_segments)
        while len(padded_scope) < len(ref_segments):
            padded_scope.append("*")

        # Compare segment by segment (up to the length of the ref)
        match = True
        for i in range(len(ref_segments)):
            if i >= len(padded_scope):
                break
            scope_seg = padded_scope[i]
            ref_seg = ref_segments[i]
            if scope_seg == "*" or ref_seg == "*":
                continue
            if scope_seg != ref_seg:
                match = False
                break

        if match:
            return True

    return False


# ---------------------------------------------------------------------------
# Routing target resolution
# ---------------------------------------------------------------------------


def get_routing_targets(
    conn,
    cluster_id: uuid.UUID,
) -> list[dict]:
    """
    Find all role_assignments that should receive a card for this cluster.

    A role_assignment matches when BOTH conditions are met:
    1. Location match: the role's location_scope matches at least one
       signal location in the cluster
    2. Domain overlap: at least one domain in the role's issue_domains
       appears in the cluster's issue_classification records

    Returns list of dicts with id, person_name, role_type, location_scope,
    issue_domains.
    """
    cur = conn.cursor()
    try:
        # 1. Fetch distinct signal locations for the cluster
        cur.execute(
            "SELECT DISTINCT location_ref FROM signal WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        cluster_locations = [row[0] for row in cur.fetchall() if row[0]]

        if not cluster_locations:
            return []

        # 2. Fetch cluster classification domains
        cur.execute(
            "SELECT domain FROM issue_classification WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        cluster_domains = {row[0] for row in cur.fetchall()}

        if not cluster_domains:
            return []

        # 3. Fetch all active role_assignments
        cur.execute(
            """
            SELECT id, person_name, role_type, location_scope, issue_domains
            FROM role_assignment WHERE is_active = true
            """
        )
        role_rows = cur.fetchall()

        # 4. Match each role_assignment
        targets: list[dict] = []
        for row in role_rows:
            role_id, person_name, role_type, location_scope, issue_domains = row

            # Check location match
            if not match_location_scope(cluster_locations, location_scope):
                continue

            # Parse issue_domains — psycopg2 returns enum arrays as strings
            # like '{space_optimisation,workplace_experience}'
            if isinstance(issue_domains, str):
                cleaned = issue_domains.strip("{}")
                parsed_domains = [d.strip() for d in cleaned.split(",") if d.strip()]
            elif isinstance(issue_domains, (list, tuple)):
                parsed_domains = list(issue_domains)
            else:
                parsed_domains = []

            # Check domain overlap
            role_domain_set = set(parsed_domains)
            if not role_domain_set.intersection(cluster_domains):
                continue

            targets.append(
                {
                    "id": role_id,
                    "person_name": person_name,
                    "role_type": role_type,
                    "location_scope": location_scope,
                    "issue_domains": parsed_domains,
                }
            )

        return targets

    finally:
        cur.close()
