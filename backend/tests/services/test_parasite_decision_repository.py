"""Tests for ParasiteDecisionRepository query methods.

Covers the four methods added for AEGIS Phase 0 follow-up:
- get_decision_by_id
- count_pending_measurements
- get_decisions_since
- get_decisions_by_site (with optional since)
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.database.repositories.parasite_decision_repository import (
    ParasiteDecisionRepository,
)


@pytest.fixture
def repo(tmp_path: Path) -> ParasiteDecisionRepository:
    """Create a JSON-only repo backed by a temp file."""
    r = ParasiteDecisionRepository(json_path=tmp_path / "decisions.json")
    r._use_json = True
    return r


def _make_decision(
    *,
    id: str = "d-001",
    site_id: str = "site-002",
    write_status: str = "blocked",
    outcome_measured_at=None,
    created_at: str | None = None,
    approval_outcome: str = "pending",
    **extra,
) -> dict:
    """Build a minimal decision dict for testing."""
    now = created_at or datetime.now(UTC).isoformat()
    d = {
        "id": id,
        "site_id": site_id,
        "write_status": write_status,
        "outcome_measured_at": outcome_measured_at,
        "created_at": now,
        "updated_at": now,
        "approval_outcome": approval_outcome,
    }
    d.update(extra)
    return d


@pytest.mark.asyncio
async def test_get_decision_by_id_found(repo):
    """Should return the decision when it exists."""
    dec = _make_decision(id="abc-123")
    await repo.record_decision(dec)

    result = await repo.get_decision_by_id("abc-123")
    assert result is not None
    assert result["id"] == "abc-123"


@pytest.mark.asyncio
async def test_get_decision_by_id_missing(repo):
    """Should return None when the decision does not exist."""
    result = await repo.get_decision_by_id("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_count_pending_measurements(repo):
    """Should count decisions with write_status success/blocked and no outcome."""
    # 2 pending (blocked, no outcome)
    await repo.record_decision(_make_decision(id="p1", write_status="blocked"))
    await repo.record_decision(_make_decision(id="p2", write_status="success"))

    # 1 already measured (should not count)
    await repo.record_decision(
        _make_decision(id="p3", write_status="blocked", outcome_measured_at="2026-01-01T00:00:00Z")
    )

    # 1 different status (should not count)
    await repo.record_decision(_make_decision(id="p4", write_status="skipped"))

    count = await repo.count_pending_measurements()
    assert count == 2


@pytest.mark.asyncio
async def test_get_decisions_since(repo):
    """Should return only decisions newer than the given timestamp."""
    old_ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    recent_ts = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()

    await repo.record_decision(_make_decision(id="old", created_at=old_ts))
    await repo.record_decision(_make_decision(id="new", created_at=recent_ts))

    cutoff = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    results = await repo.get_decisions_since(cutoff)

    assert len(results) == 1
    assert results[0]["id"] == "new"


@pytest.mark.asyncio
async def test_get_decisions_by_site_with_since(repo):
    """Should filter by site_id AND since timestamp."""
    old_ts = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    recent_ts = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    await repo.record_decision(_make_decision(id="s1", site_id="site-002", created_at=recent_ts))
    await repo.record_decision(_make_decision(id="s2", site_id="site-002", created_at=old_ts))
    await repo.record_decision(_make_decision(id="s3", site_id="site-003", created_at=recent_ts))

    cutoff = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    results = await repo.get_decisions_by_site("site-002", since=cutoff)

    assert len(results) == 1
    assert results[0]["id"] == "s1"

    # Without since filter, should return both site-002 records
    all_site = await repo.get_decisions_by_site("site-002")
    assert len(all_site) == 2
