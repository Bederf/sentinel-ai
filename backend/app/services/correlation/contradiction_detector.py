"""
Contradiction detection for signal correlation (Phase 156-02).

Identifies conflicting signal pairs and applies scoring penalties.
Pure logic module -- no DB access.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTRADICTION_PENALTY = -0.20

# (signal_type_a, signal_type_b, rule_name)
CONTRADICTION_RULES: list[tuple[str, str, str]] = [
    ("resolution_email", "complaint_email", "resolution_contradicts_complaint"),
    ("occupancy_normal", "occupancy_anomaly", "occupancy_normal_contradicts_anomaly"),
    ("booking_released", "booking_conflict", "booking_released_contradicts_conflict"),
]

# Signal types considered "active" for resolved-cluster contradiction
ACTIVE_SIGNAL_TYPES = frozenset(
    {
        "complaint_email",
        "escalation_email",
        "action_request_email",
    }
)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class ContradictionResult:
    """Result of contradiction detection between two signals."""

    is_contradiction: bool
    rule: str | None  # contradiction_rule_enum value if detected
    penalty: float  # -0.20 if contradiction, 0.0 otherwise
    explanation: str  # human-readable reason


# ---------------------------------------------------------------------------
# Detection function
# ---------------------------------------------------------------------------


def detect_contradiction(
    signal_a_type: str,
    signal_b_type: str,
    cluster_state: str | None = None,
) -> ContradictionResult:
    """
    Check whether two signal types form a contradiction.

    Checks bidirectionally against CONTRADICTION_RULES. Also handles the
    special case where a resolved cluster receives a new active signal.

    Parameters
    ----------
    signal_a_type : str
        Signal type of the first signal.
    signal_b_type : str
        Signal type of the second signal.
    cluster_state : str | None
        Current cluster state, if any. Used to detect resolved-cluster
        contradictions.

    Returns
    -------
    ContradictionResult
    """
    # Check signal type pairs against rules (bidirectional)
    for type_a, type_b, rule_name in CONTRADICTION_RULES:
        if (signal_a_type == type_a and signal_b_type == type_b) or (
            signal_a_type == type_b and signal_b_type == type_a
        ):
            return ContradictionResult(
                is_contradiction=True,
                rule=rule_name,
                penalty=CONTRADICTION_PENALTY,
                explanation=(f"Contradiction: {signal_a_type} vs {signal_b_type} (rule: {rule_name})"),
            )

    # Special case: resolved cluster + new active signal
    if cluster_state == "resolved" and (signal_a_type in ACTIVE_SIGNAL_TYPES or signal_b_type in ACTIVE_SIGNAL_TYPES):
        return ContradictionResult(
            is_contradiction=True,
            rule="resolved_contradicts_active",
            penalty=CONTRADICTION_PENALTY,
            explanation=(
                f"Contradiction: resolved cluster received active signal "
                f"({signal_a_type} / {signal_b_type}), triggers reopen"
            ),
        )

    return ContradictionResult(
        is_contradiction=False,
        rule=None,
        penalty=0.0,
        explanation="No contradiction detected",
    )


# ---------------------------------------------------------------------------
# Penalty application
# ---------------------------------------------------------------------------


def apply_contradiction_penalty(score: float, contradiction: ContradictionResult) -> float:
    """
    Apply contradiction penalty to a correlation score.

    Returns max(0.0, score + penalty). Only applies when contradiction
    is detected.
    """
    if not contradiction.is_contradiction:
        return score
    return max(0.0, score + contradiction.penalty)
