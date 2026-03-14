"""
Dashboard card generator for the correlation engine (Phase 156-04).

Creates role-aware dashboard cards with affected rooms, people involved,
recommended actions, and advisory labels.
"""

from __future__ import annotations

import json
import uuid

# ---------------------------------------------------------------------------
# Role-specific card templates
# ---------------------------------------------------------------------------

CARD_TEMPLATES: dict[str, dict] = {
    "concierge": {
        "focus": "ground-level impact and immediate actions",
        "actions": [
            "Review block bookings for rooms under your management",
            "Cancel confirmed unoccupied slots",
            "Monitor no-show patterns this week",
            "Report recurring offenders to management",
        ],
    },
    "management": {
        "focus": "policy and process decisions",
        "actions": [
            "Review booking policy for affected areas",
            "Consider limiting block booking duration",
            "Escalate to executive if policy change needed",
            "Request utilisation report for affected rooms",
        ],
    },
    "facilities": {
        "focus": "physical space and equipment",
        "actions": [
            "Check room sensor data for affected areas",
            "Verify booking system accuracy",
            "Review room capacity configurations",
            "Schedule maintenance inspection if needed",
        ],
    },
    "executive": {
        "focus": "strategic decisions and resource allocation",
        "actions": [
            "Review escalation history and timeline",
            "Approve or reject proposed policy changes",
            "Allocate budget for space optimisation",
            "Set resolution deadline",
        ],
    },
    "technician": {
        "focus": "technical investigation",
        "actions": [
            "Inspect affected equipment",
            "Run diagnostic tests",
            "Report findings to facilities manager",
        ],
    },
    "external": {
        "focus": "external stakeholder communication",
        "actions": [
            "Review issue summary",
            "Provide input on affected areas",
        ],
    },
}

DEFAULT_ADVISORY_LABEL = "These actions are suggestions. Human decision required."


# ---------------------------------------------------------------------------
# Card generation
# ---------------------------------------------------------------------------


def generate_cards(
    conn,
    cluster_id: uuid.UUID,
    routing_targets: list[dict],
) -> list[uuid.UUID]:
    """
    Generate dashboard cards for each routing target.

    For each target, builds role-appropriate card content with cluster data,
    classifications, affected rooms, people involved, and recommended actions.

    Returns list of card UUIDs (created or updated).
    """
    cur = conn.cursor()
    try:
        # 1. Fetch cluster data
        cur.execute(
            """
            SELECT title, cluster_state, severity, escalation_level, confidence_score,
                   likely_root_cause, first_seen_at, last_seen_at, duration_days, signal_count
            FROM issue_cluster WHERE id = %s
            """,
            (str(cluster_id),),
        )
        cluster_row = cur.fetchone()
        if not cluster_row:
            return []

        cluster = {
            "title": cluster_row[0],
            "cluster_state": cluster_row[1],
            "severity": cluster_row[2],
            "escalation_level": cluster_row[3],
            "confidence_score": float(cluster_row[4]) if cluster_row[4] else 0.0,
            "likely_root_cause": cluster_row[5],
            "first_seen_at": str(cluster_row[6]) if cluster_row[6] else None,
            "last_seen_at": str(cluster_row[7]) if cluster_row[7] else None,
            "duration_days": cluster_row[8],
            "signal_count": cluster_row[9],
        }

        # 2. Fetch classifications
        cur.execute(
            """
            SELECT domain, confidence FROM issue_classification
            WHERE issue_cluster_id = %s ORDER BY confidence DESC
            """,
            (str(cluster_id),),
        )
        classifications = [{"domain": row[0], "confidence": float(row[1])} for row in cur.fetchall()]

        # 3. Fetch affected rooms (entity_type = 'room')
        cur.execute(
            """
            SELECT DISTINCT entity_value FROM entity
            WHERE issue_cluster_id = %s AND entity_type = 'room'
            """,
            (str(cluster_id),),
        )
        affected_rooms = [row[0] for row in cur.fetchall()]

        # 4. Fetch people involved (entity_type = 'person')
        cur.execute(
            """
            SELECT DISTINCT entity_value FROM entity
            WHERE issue_cluster_id = %s AND entity_type = 'person'
            """,
            (str(cluster_id),),
        )
        people_involved = [row[0] for row in cur.fetchall()]

        # 5. Generate cards for each routing target
        card_ids: list[uuid.UUID] = []

        for target in routing_targets:
            role_type = target["role_type"]
            role_assignment_id = target["id"]
            template = CARD_TEMPLATES.get(role_type, CARD_TEMPLATES["external"])

            # Build card content
            summary_parts = []
            if cluster["likely_root_cause"]:
                summary_parts.append(cluster["likely_root_cause"])
            else:
                summary_parts.append(cluster["title"])
            summary_parts.append(f"{cluster['signal_count']} signals over {cluster['duration_days'] or 0} days.")
            summary_parts.append(f"Focus: {template['focus']}.")

            card_content = {
                "summary": " ".join(summary_parts),
                "classifications": classifications,
                "affected_rooms": affected_rooms,
                "people_involved": people_involved,
                "recommended_actions": template["actions"],
                "confidence_score": cluster["confidence_score"],
                "cluster_state": cluster["cluster_state"],
                "severity": cluster["severity"],
                "escalation_level": cluster["escalation_level"],
                "signal_count": cluster["signal_count"],
                "duration_days": cluster["duration_days"] or 0,
            }

            card_title = f"[{role_type.upper()}] {cluster['title']}"

            # Check for existing card (idempotency)
            cur.execute(
                """
                SELECT id FROM dashboard_card
                WHERE issue_cluster_id = %s
                  AND recipient_role_assignment_id = %s
                  AND dismissed_at IS NULL
                """,
                (str(cluster_id), str(role_assignment_id)),
            )
            existing = cur.fetchone()

            if existing:
                # Update existing card
                cur.execute(
                    """
                    UPDATE dashboard_card
                    SET card_content = %s, title = %s, surfaced_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps(card_content), card_title, str(existing[0])),
                )
                card_ids.append(existing[0])
            else:
                # Insert new card
                cur.execute(
                    """
                    INSERT INTO dashboard_card (
                        issue_cluster_id, recipient_role_assignment_id,
                        title, card_content, advisory_label
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        str(cluster_id),
                        str(role_assignment_id),
                        card_title,
                        json.dumps(card_content),
                        DEFAULT_ADVISORY_LABEL,
                    ),
                )
                card_ids.append(cur.fetchone()[0])

        conn.commit()
        return card_ids

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Card retrieval
# ---------------------------------------------------------------------------


def get_cards_for_person(
    conn,
    role_assignment_id: uuid.UUID,
) -> list[dict]:
    """
    Fetch all non-dismissed cards for a role_assignment.

    Returns list of dicts with card fields.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT dc.id, dc.issue_cluster_id, dc.title, dc.card_content,
                   dc.advisory_label, dc.surfaced_at, dc.acknowledged_at
            FROM dashboard_card dc
            WHERE dc.recipient_role_assignment_id = %s AND dc.dismissed_at IS NULL
            ORDER BY dc.surfaced_at DESC
            """,
            (str(role_assignment_id),),
        )
        rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "issue_cluster_id": row[1],
                "title": row[2],
                "card_content": row[3],
                "advisory_label": row[4],
                "surfaced_at": str(row[5]) if row[5] else None,
                "acknowledged_at": str(row[6]) if row[6] else None,
            }
            for row in rows
        ]
    finally:
        cur.close()
