"""Tests for the AEGIS operations dashboard endpoint.

Endpoint: GET /api/parasite/aegis/dashboard
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.database.repositories.parasite_decision_repository import (
    ParasiteDecisionRepository,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_aegis_decision(
    *,
    id: str,
    site_id: str = "site-002",
    write_status: str = "blocked",
    execution_mode: str = "blocked",
    approval_outcome: str = "pending",
    dispatch_action_type: str = "discharge",
    created_at: str | None = None,
) -> dict:
    """Build a minimal AEGIS decision for testing."""
    ts = created_at or _now_iso()
    return {
        "id": id,
        "site_id": site_id,
        "write_status": write_status,
        "created_at": ts,
        "updated_at": ts,
        "approval_outcome": approval_outcome,
        "contributing_factors": {
            "proposal_source": "aegis",
            "created_by": "aegis",
            "execution_mode": execution_mode,
            "approval_outcome": approval_outcome,
            "dispatch_action_type": dispatch_action_type,
        },
    }


def _make_non_aegis_decision(*, id: str, site_id: str = "site-002") -> dict:
    """Build a non-AEGIS decision."""
    ts = _now_iso()
    return {
        "id": id,
        "site_id": site_id,
        "write_status": "success",
        "created_at": ts,
        "updated_at": ts,
        "contributing_factors": {
            "proposal_source": "parasite",
            "created_by": "optimizer",
        },
    }


@pytest.fixture
def isolated_repo(tmp_path: Path) -> ParasiteDecisionRepository:
    """Create an isolated JSON-backed repo."""
    r = ParasiteDecisionRepository(json_path=tmp_path / "dashboard_test.json")
    r._use_json = True
    return r


@pytest.fixture
def patch_repo(isolated_repo):
    """Patch ParasiteDecisionRepository constructor to return our isolated repo."""
    with patch(
        "app.api.parasite_decisions.ParasiteDecisionRepository",
        return_value=isolated_repo,
    ):
        yield isolated_repo


@pytest.mark.asyncio
async def test_dashboard_returns_200_empty(client, patch_repo):
    """Dashboard returns 200 with zero decisions."""
    resp = await client.get("/api/parasite/aegis/dashboard?site_id=site-002")
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_id"] == "site-002"
    assert data["period"] == "last_24h"
    assert data["kpis"]["proposals_24h"] == 0
    assert data["activity"] == []
    assert data["pending_proposals"] == []


@pytest.mark.asyncio
async def test_dashboard_filters_by_execution_mode(client, patch_repo):
    """Filter by execution_mode should narrow the activity list."""
    repo = patch_repo
    await repo.record_decision(_make_aegis_decision(id="a1", execution_mode="blocked"))
    await repo.record_decision(_make_aegis_decision(id="a2", execution_mode="live"))

    resp = await client.get("/api/parasite/aegis/dashboard?site_id=site-002&execution_mode=blocked")
    assert resp.status_code == 200
    data = resp.json()
    # KPIs should count both (unfiltered)
    assert data["kpis"]["proposals_24h"] == 2
    # Activity should only show blocked
    assert len(data["activity"]) == 1
    assert data["activity"][0]["id"] == "a1"


@pytest.mark.asyncio
async def test_dashboard_kpis_count_correctly(client, patch_repo):
    """KPIs should count approved/rejected/blocked accurately."""
    repo = patch_repo
    await repo.record_decision(_make_aegis_decision(id="k1", approval_outcome="approved", write_status="blocked"))
    await repo.record_decision(_make_aegis_decision(id="k2", approval_outcome="rejected", write_status="blocked"))
    await repo.record_decision(_make_aegis_decision(id="k3", approval_outcome="pending", write_status="blocked"))

    resp = await client.get("/api/parasite/aegis/dashboard?site_id=site-002")
    assert resp.status_code == 200
    kpis = resp.json()["kpis"]
    assert kpis["proposals_24h"] == 3
    assert kpis["approved_24h"] == 1
    assert kpis["rejected_24h"] == 1
    assert kpis["blocked_24h"] == 3  # All have write_status=blocked


@pytest.mark.asyncio
async def test_dashboard_ignores_non_aegis_decisions(client, patch_repo):
    """Non-AEGIS decisions should not appear in dashboard."""
    repo = patch_repo
    await repo.record_decision(_make_aegis_decision(id="aegis-1"))
    await repo.record_decision(_make_non_aegis_decision(id="other-1"))

    resp = await client.get("/api/parasite/aegis/dashboard?site_id=site-002")
    assert resp.status_code == 200
    data = resp.json()
    assert data["kpis"]["proposals_24h"] == 1
    assert len(data["activity"]) == 1
    assert data["activity"][0]["id"] == "aegis-1"


@pytest.mark.asyncio
async def test_dashboard_pending_only_pending(client, patch_repo):
    """pending_proposals should only contain decisions with outcome=pending."""
    repo = patch_repo
    await repo.record_decision(_make_aegis_decision(id="p1", approval_outcome="pending"))
    await repo.record_decision(_make_aegis_decision(id="p2", approval_outcome="approved"))

    resp = await client.get("/api/parasite/aegis/dashboard?site_id=site-002")
    assert resp.status_code == 200
    pending = resp.json()["pending_proposals"]
    assert len(pending) == 1
    assert pending[0]["id"] == "p1"


@pytest.mark.asyncio
async def test_existing_endpoints_unaffected(client, patch_repo):
    """Existing /decisions and /health endpoints should still work."""
    resp = await client.get("/api/parasite/decisions")
    assert resp.status_code == 200

    resp = await client.get("/api/parasite/health")
    assert resp.status_code == 200
