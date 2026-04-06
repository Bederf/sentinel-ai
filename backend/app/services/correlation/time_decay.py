"""
Time decay service for the correlation engine.

Applies exponential decay to signal confidence based on age.
Formula: decayed = confidence * exp(-lambda * days_elapsed)

Default lambda = 0.01 gives a half-life of ~69 days (ln(2)/0.01 = 69.3).
"""

import math
from datetime import UTC, datetime

from app.services.correlation.candidate_generator import CandidateSignal

DEFAULT_LAMBDA_RATE = 0.01


def apply_time_decay(
    confidence: float,
    days_elapsed: float,
    lambda_rate: float = DEFAULT_LAMBDA_RATE,
) -> float:
    """Apply exponential time decay to a confidence value.

    Args:
        confidence: Original confidence value (0.0 to 1.0).
        days_elapsed: Number of days since the signal was created.
        lambda_rate: Decay rate constant (default 0.01, half-life ~69 days).

    Returns:
        Decayed confidence value clamped to [0.0, 1.0].
    """
    if confidence <= 0:
        return 0.0
    if days_elapsed <= 0:
        return confidence

    decayed = confidence * math.exp(-lambda_rate * days_elapsed)
    return max(0.0, min(1.0, decayed))


def compute_days_elapsed(
    signal_created_at: datetime,
    reference_date: datetime | None = None,
) -> float:
    """Compute the number of days between a signal's creation and a reference date.

    Args:
        signal_created_at: When the signal was created.
        reference_date: The reference point (default: now UTC).

    Returns:
        Days elapsed as a float.
    """
    if reference_date is None:
        reference_date = datetime.now(UTC)

    # If signal_created_at is naive, assume UTC
    if signal_created_at.tzinfo is None:
        signal_created_at = signal_created_at.replace(tzinfo=UTC)

    return (reference_date - signal_created_at).total_seconds() / 86400.0


def decay_candidate_confidence(
    candidate: CandidateSignal,
    reference_date: datetime | None = None,
    lambda_rate: float = DEFAULT_LAMBDA_RATE,
) -> float:
    """Convenience wrapper: compute decayed confidence for a CandidateSignal.

    Args:
        candidate: The candidate signal to decay.
        reference_date: The reference point (default: now UTC).
        lambda_rate: Decay rate constant.

    Returns:
        Decayed confidence value.
    """
    days = compute_days_elapsed(candidate.created_at, reference_date)
    return apply_time_decay(float(candidate.confidence), days, lambda_rate)
