"""Tests for candidate generation service."""

import os
import uuid

import psycopg2
import psycopg2.extras
import pytest

from app.services.correlation.candidate_generator import CandidateSignal, get_candidates

DB_DSN = os.environ.get(
    "CORRELATION_TEST_DSN",
    "postgresql://postgres:postgres@localhost:55322/postgres",
)

SIGNAL_1 = uuid.UUID("f1000000-0000-0000-0000-000000000001")  # Jan 5
SIGNAL_2 = uuid.UUID("f1000000-0000-0000-0000-000000000002")  # Jan 12
SIGNAL_3 = uuid.UUID("f1000000-0000-0000-0000-000000000003")  # Jan 15
SIGNAL_4 = uuid.UUID("f1000000-0000-0000-0000-000000000004")  # Jan 28
SIGNAL_5 = uuid.UUID("f1000000-0000-0000-0000-000000000005")  # Feb 3
SIGNAL_9 = uuid.UUID("f1000000-0000-0000-0000-000000000009")  # Mar 6


@pytest.fixture(scope="module")
def conn():
    connection = psycopg2.connect(DB_DSN)
    connection.autocommit = True
    yield connection
    connection.close()


def test_candidates_for_signal_1_returns_nearby_signals(conn):
    """Signal 1 (Jan 5) should find signals 2-4 within 30 days, maybe 5."""
    candidates = get_candidates(conn, SIGNAL_1)
    assert len(candidates) >= 2  # At least signals 2 and 3 are within 30 days
    assert all(isinstance(c, CandidateSignal) for c in candidates)
    # Signal 1 should not be in its own candidates
    assert all(c.id != SIGNAL_1 for c in candidates)


def test_candidates_same_campus_only(conn):
    """All candidates should be from Fairlands campus."""
    candidates = get_candidates(conn, SIGNAL_1)
    assert all(c.location_ref.startswith("Fairlands/") for c in candidates)


def test_candidates_exclude_self(conn):
    """Anchor signal must not appear in its own candidate list."""
    for signal_id in [SIGNAL_1, SIGNAL_5, SIGNAL_9]:
        candidates = get_candidates(conn, signal_id)
        assert all(c.id != signal_id for c in candidates)


def test_candidates_respect_time_window(conn):
    """With a 10-day window, Signal 1 (Jan 5) should only find Signal 2 (Jan 12)."""
    candidates = get_candidates(conn, SIGNAL_1, time_window_days=10)
    candidate_ids = {c.id for c in candidates}
    assert SIGNAL_2 in candidate_ids  # Jan 12, 7 days away
    assert SIGNAL_4 not in candidate_ids  # Jan 28, 23 days away


def test_candidates_wider_window_finds_more(conn):
    """With a 90-day window, Signal 1 should find most/all other signals."""
    candidates = get_candidates(conn, SIGNAL_1, time_window_days=90)
    assert len(candidates) >= 7  # Should find most of signals 2-9


def test_candidate_fields_populated(conn):
    """All CandidateSignal fields should be populated."""
    candidates = get_candidates(conn, SIGNAL_5)
    assert len(candidates) > 0
    c = candidates[0]
    assert c.id is not None
    assert c.signal_type is not None
    assert c.severity is not None
    assert c.confidence is not None
    assert c.location_ref is not None
    assert c.created_at is not None
    assert c.metadata is not None


def test_nonexistent_signal_returns_empty(conn):
    """A non-existent anchor signal should return empty list."""
    fake_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    candidates = get_candidates(conn, fake_id)
    assert candidates == []


def test_candidates_ordered_by_created_at(conn):
    """Candidates should be ordered by created_at ascending."""
    candidates = get_candidates(conn, SIGNAL_5, time_window_days=60)
    dates = [c.created_at for c in candidates]
    assert dates == sorted(dates)
