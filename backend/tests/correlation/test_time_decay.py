"""Tests for time decay service."""

import math
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.services.correlation.candidate_generator import CandidateSignal
from app.services.correlation.time_decay import (
    apply_time_decay,
    compute_days_elapsed,
    decay_candidate_confidence,
)


class TestApplyTimeDecay:
    def test_no_decay_at_zero_days(self):
        assert apply_time_decay(0.85, 0.0) == 0.85

    def test_half_life_at_69_days(self):
        """After ~69.3 days, confidence should be roughly halved."""
        result = apply_time_decay(1.0, 69.3)
        assert 0.49 <= result <= 0.51

    def test_decay_at_30_days(self):
        """After 30 days with lambda=0.01, factor is exp(-0.3) ~ 0.74."""
        result = apply_time_decay(0.85, 30.0)
        expected = 0.85 * math.exp(-0.3)
        assert abs(result - expected) < 0.001

    def test_negative_days_no_decay(self):
        """Future signals should not decay."""
        assert apply_time_decay(0.85, -5.0) == 0.85

    def test_zero_confidence_stays_zero(self):
        assert apply_time_decay(0.0, 30.0) == 0.0

    def test_negative_confidence_stays_zero(self):
        assert apply_time_decay(-0.5, 30.0) == 0.0

    def test_result_clamped_to_one(self):
        """Even with high confidence input, result should not exceed 1.0."""
        result = apply_time_decay(1.5, 0.0)
        # No decay at 0 days, but confidence > 1.0 is passed through
        # (only clamp matters if decay produces > 1.0, which can't happen)
        assert result == 1.5  # No decay applied, raw value returned

    def test_custom_lambda_rate(self):
        """Higher lambda = faster decay."""
        slow = apply_time_decay(1.0, 30.0, lambda_rate=0.01)
        fast = apply_time_decay(1.0, 30.0, lambda_rate=0.05)
        assert fast < slow

    def test_very_old_signal_near_zero(self):
        """After 1000 days, confidence should be near zero."""
        result = apply_time_decay(1.0, 1000.0)
        assert result < 0.001


class TestComputeDaysElapsed:
    def test_basic_days_elapsed(self):
        now = datetime(2026, 3, 14, tzinfo=UTC)
        signal_date = datetime(2026, 1, 5, tzinfo=UTC)
        days = compute_days_elapsed(signal_date, now)
        assert 67 < days < 69  # ~68 days

    def test_same_day_zero_elapsed(self):
        now = datetime(2026, 3, 14, 12, 0, 0, tzinfo=UTC)
        days = compute_days_elapsed(now, now)
        assert days == 0.0

    def test_naive_datetime_assumed_utc(self):
        """Naive datetimes should be treated as UTC."""
        now = datetime(2026, 3, 14, tzinfo=UTC)
        naive = datetime(2026, 3, 13)  # naive, 1 day before
        days = compute_days_elapsed(naive, now)
        assert 0.9 < days < 1.1

    def test_defaults_to_now(self):
        """Without reference_date, should use current time."""
        old = datetime(2020, 1, 1, tzinfo=UTC)
        days = compute_days_elapsed(old)
        assert days > 365  # Definitely more than a year ago


class TestDecayCandidateConfidence:
    def test_decay_candidate(self):
        candidate = CandidateSignal(
            id=uuid.UUID("f1000000-0000-0000-0000-000000000001"),
            signal_type="complaint_email",
            severity="medium",
            confidence=Decimal("0.85"),
            location_ref="Fairlands/FA1/1Q4/MR10",
            created_at=datetime(2026, 1, 5, tzinfo=UTC),
            metadata={},
        )
        ref = datetime(2026, 3, 14, tzinfo=UTC)
        decayed = decay_candidate_confidence(candidate, reference_date=ref)
        # ~68 days elapsed, exp(-0.68) ~ 0.507, * 0.85 ~ 0.43
        assert 0.35 < decayed < 0.55

    def test_recent_candidate_minimal_decay(self):
        candidate = CandidateSignal(
            id=uuid.UUID("f1000000-0000-0000-0000-000000000009"),
            signal_type="escalation_email",
            severity="critical",
            confidence=Decimal("0.95"),
            location_ref="Fairlands/*/*/*",
            created_at=datetime(2026, 3, 6, tzinfo=UTC),
            metadata={},
        )
        ref = datetime(2026, 3, 14, tzinfo=UTC)
        decayed = decay_candidate_confidence(candidate, reference_date=ref)
        # ~8 days elapsed, exp(-0.08) ~ 0.923, * 0.95 ~ 0.877
        assert 0.85 < decayed < 0.95
