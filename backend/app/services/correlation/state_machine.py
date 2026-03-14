"""
State machine for issue cluster lifecycle (Phase 156-03).

Evaluates state transitions based on signal count, signal types,
severity, and escalation indicators. Follows the Fairlands progression:
emerging(1-2) -> active(3+) -> escalated(escalation_email) -> stays escalated.
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_TRANSITIONS = {
    "emerging_to_active": {
        "from": "emerging",
        "to": "active",
    },
    "active_to_escalated": {
        "from": "active",
        "to": "escalated",
    },
    "escalated_to_resolved": {
        "from": "escalated",
        "to": "resolved",
    },
    "resolved_to_active": {
        "from": "resolved",
        "to": "active",
    },
}

ESCALATION_SIGNAL_TYPES = {"escalation_email", "action_request_email"}

ACTIVE_SIGNAL_TYPES = {
    "complaint_email",
    "escalation_email",
    "action_request_email",
    "observation_email",
    "intake_email",
}


# ---------------------------------------------------------------------------
# State evaluation
# ---------------------------------------------------------------------------


def evaluate_state_transition(
    conn,
    cluster_id: uuid.UUID,
) -> tuple[str, str | None]:
    """
    Evaluate whether a cluster should transition to a new state.

    Returns (new_state, transition_name). If no transition applies,
    returns (current_state, None).
    """
    cur = conn.cursor()
    try:
        # Fetch current cluster state and signal_count
        cur.execute(
            "SELECT cluster_state, signal_count, escalation_level FROM issue_cluster WHERE id = %s",
            (str(cluster_id),),
        )
        row = cur.fetchone()
        if not row:
            return ("emerging", None)

        current_state = row[0]
        signal_count = row[1]

        # Fetch all signal types, severities, and metadata for this cluster
        cur.execute(
            "SELECT signal_type, severity, metadata FROM signal WHERE issue_cluster_id = %s",
            (str(cluster_id),),
        )
        signals = [{"signal_type": r[0], "severity": r[1], "metadata": r[2] or {}} for r in cur.fetchall()]

        signal_types = {s["signal_type"] for s in signals}
        signal_severities = {s["severity"] for s in signals}

        # Apply rules in priority order

        # Rule 1: emerging -> active (signal_count >= 3)
        if current_state == "emerging" and signal_count >= 3:
            cur.execute(
                "UPDATE issue_cluster SET cluster_state = 'active', "
                "escalation_level = 'operational', updated_at = now() "
                "WHERE id = %s",
                (str(cluster_id),),
            )
            # Also update escalation level based on signals
            update_escalation_level(conn, cluster_id, signals)
            conn.commit()
            return ("active", "emerging_to_active")

        # Rule 2: active -> escalated (escalation signal or critical severity)
        if current_state == "active":
            has_escalation = bool(signal_types & ESCALATION_SIGNAL_TYPES)
            has_critical = "critical" in signal_severities

            if has_escalation or has_critical:
                cur.execute(
                    "UPDATE issue_cluster SET cluster_state = 'escalated', updated_at = now() WHERE id = %s",
                    (str(cluster_id),),
                )
                update_escalation_level(conn, cluster_id, signals)
                conn.commit()
                return ("escalated", "active_to_escalated")

        # Rule 3: escalated -> resolved (resolution + all resolved)
        if current_state == "escalated":
            has_resolution = "resolution_email" in signal_types
            if has_resolution:
                cur.execute(
                    "SELECT count(*) FROM signal WHERE issue_cluster_id = %s AND resolution_state != 'resolved'",
                    (str(cluster_id),),
                )
                unresolved = cur.fetchone()[0]
                if unresolved == 0:
                    cur.execute(
                        "UPDATE issue_cluster SET cluster_state = 'resolved', "
                        "resolved_at = now(), updated_at = now() WHERE id = %s",
                        (str(cluster_id),),
                    )
                    conn.commit()
                    return ("resolved", "escalated_to_resolved")

        # Rule 4: resolved -> active (reopen on new active signal)
        if current_state == "resolved":
            has_active_signal = bool(signal_types & ACTIVE_SIGNAL_TYPES)
            if has_active_signal:
                cur.execute(
                    "UPDATE issue_cluster SET cluster_state = 'active', "
                    "resolved_at = NULL, updated_at = now() WHERE id = %s",
                    (str(cluster_id),),
                )
                update_escalation_level(conn, cluster_id, signals)
                conn.commit()
                return ("active", "resolved_to_active")

        # If escalated, still update escalation level (e.g. new critical signal)
        if current_state == "escalated":
            update_escalation_level(conn, cluster_id, signals)
            conn.commit()

        return (current_state, None)

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Escalation level
# ---------------------------------------------------------------------------


def update_escalation_level(
    conn,
    cluster_id: uuid.UUID,
    signals: list[dict],
) -> str:
    """
    Update escalation_level based on signal content.

    Priority order (highest first):
    1. ANY signal severity='critical' -> 'executive'
    2. escalation_email from executive role -> 'executive'
    3. escalation_email from management role -> 'management'
    4. ANY escalation_email -> 'management'
    5. Default -> 'operational'
    """
    # Rule 1: Critical severity always -> executive
    severities = {s.get("severity") for s in signals}
    if "critical" in severities:
        _set_escalation_level(conn, cluster_id, "executive")
        return "executive"

    # Rules 2-4: Check escalation emails
    has_escalation_email = any(s.get("signal_type") == "escalation_email" for s in signals)

    if has_escalation_email:
        # For simplicity: check signal metadata for sender role
        # In fixture data, we check metadata.sender_name against known executives
        # Greg Temlett = executive, Keryn Norman = management
        for s in signals:
            if s.get("signal_type") != "escalation_email":
                continue
            metadata = s.get("metadata", {}) or {}
            sender = metadata.get("sender", "") or metadata.get("sender_name", "")
            # Check role_assignment table for sender role
            role = _get_sender_role(conn, sender)
            if role == "executive":
                _set_escalation_level(conn, cluster_id, "executive")
                return "executive"

        # Default escalation_email -> management
        _set_escalation_level(conn, cluster_id, "management")
        return "management"

    _set_escalation_level(conn, cluster_id, "operational")
    return "operational"


def _get_sender_role(conn, sender_name: str) -> str | None:
    """Look up role_type for a person by name in role_assignment."""
    if not sender_name:
        return None
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT role_type FROM role_assignment WHERE person_name = %s LIMIT 1",
            (sender_name,),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


def _set_escalation_level(conn, cluster_id: uuid.UUID, level: str) -> None:
    """Update the escalation_level on a cluster.

    Commits immediately so the change is not lost if the caller returns
    early without committing.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE issue_cluster SET escalation_level = %s WHERE id = %s",
            (level, str(cluster_id)),
        )
        conn.commit()
    finally:
        cur.close()
