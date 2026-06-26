"""Tests for the AEGIS operations dashboard endpoint.

Endpoint: GET /api/parasite/aegis/dashboard
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.database.repositories.parasite_decision_repository import (
    ParasiteDecisionRepository,
)


@pytest.fixture
def site_id() -> str:
    return "test-site-001"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_aegis_decision(
    *,
    id: str,
    site_id: str = "test-site-001",
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


def _make_non_aegis_decision(*, id: str, site_id: str = "test-site-001") -> dict:
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


class _MemoryParasiteDecisionRepository(ParasiteDecisionRepository):
    """In-memory repo for tests — no Supabase, no JSON file."""

    def __init__(self):
        super().__init__()
        self._store: list[dict] = []

    async def record_decision(self, decision: dict) -> dict:
        self._validate_record(decision)
        self._normalize_point_name(decision)
        if "id" not in decision:
            import uuid

            decision["id"] = str(uuid.uuid4())
        if "created_at" not in decision:
            decision["created_at"] = datetime.utcnow().isoformat()
        if "updated_at" not in decision:
            decision["updated_at"] = datetime.utcnow().isoformat()
        self._store.append(decision)
        return decision

    async def get_decisions_by_site(self, site_id: str, since: str | None = None, limit: int = 1000) -> list[dict]:
        rows = [d for d in self._store if d.get("site_id") == site_id]
        if since:
            rows = [d for d in rows if d.get("created_at", "") > since]
        return rows[:limit]

    async def get_recent_decisions(self, limit: int = 100) -> list[dict]:
        return self._store[-limit:]

    async def get_decisions_since(self, since_iso: str, limit: int = 500) -> list[dict]:
        rows = [d for d in self._store if d.get("created_at", "") > since_iso]
        return rows[:limit]

    async def count_pending_measurements(self) -> int:
        return 0

    async def get_decision_by_id(self, decision_id: str) -> dict | None:
        return next((d for d in self._store if d.get("id") == decision_id), None)


@pytest.fixture
def isolated_repo() -> _MemoryParasiteDecisionRepository:
    """Create an isolated in-memory repo."""
    return _MemoryParasiteDecisionRepository()


@pytest.fixture
def patch_repo(isolated_repo):
    """Patch ParasiteDecisionRepository constructor to return our isolated repo."""
    with patch(
        "app.api.parasite_decisions.ParasiteDecisionRepository",
        return_value=isolated_repo,
    ):
        yield isolated_repo


@pytest.mark.asyncio
async def test_dashboard_returns_200_empty(client, patch_repo, auth_headers_operator, site_id):
    """Dashboard returns 200 with zero decisions."""
    resp = await client.get(
        f"/api/parasite/aegis/dashboard?site_id={site_id}",
        headers=auth_headers_operator,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_id"] == site_id
    assert data["period"] == "last_24h"
    assert data["kpis"]["proposals_24h"] == 0
    assert data["activity"] == []
    assert data["pending_proposals"] == []


@pytest.mark.asyncio
async def test_dashboard_filters_by_execution_mode(client, patch_repo, auth_headers_operator, site_id):
    """Filter by execution_mode should narrow the activity list."""
    repo = patch_repo
    await repo.record_decision(_make_aegis_decision(id="a1", site_id=site_id, execution_mode="blocked"))
    await repo.record_decision(_make_aegis_decision(id="a2", site_id=site_id, execution_mode="live"))

    resp = await client.get(
        f"/api/parasite/aegis/dashboard?site_id={site_id}&execution_mode=blocked",
        headers=auth_headers_operator,
    )
    assert resp.status_code == 200
    data = resp.json()
    # KPIs should count both (unfiltered)
    assert data["kpis"]["proposals_24h"] == 2
    # Activity should only show blocked
    assert len(data["activity"]) == 1
    assert data["activity"][0]["id"] == "a1"


@pytest.mark.asyncio
async def test_dashboard_kpis_count_correctly(client, patch_repo, auth_headers_operator, site_id):
    """KPIs should count approved/rejected/blocked accurately."""
    repo = patch_repo
    await repo.record_decision(
        _make_aegis_decision(id="k1", site_id=site_id, approval_outcome="approved", write_status="blocked")
    )
    await repo.record_decision(
        _make_aegis_decision(id="k2", site_id=site_id, approval_outcome="rejected", write_status="blocked")
    )
    await repo.record_decision(
        _make_aegis_decision(id="k3", site_id=site_id, approval_outcome="pending", write_status="blocked")
    )

    resp = await client.get(
        f"/api/parasite/aegis/dashboard?site_id={site_id}",
        headers=auth_headers_operator,
    )
    assert resp.status_code == 200
    kpis = resp.json()["kpis"]
    assert kpis["proposals_24h"] == 3
    assert kpis["approved_24h"] == 1
    assert kpis["rejected_24h"] == 1
    assert kpis["blocked_24h"] == 3  # All have write_status=blocked


@pytest.mark.asyncio
async def test_dashboard_ignores_non_aegis_decisions(client, patch_repo, auth_headers_operator, site_id):
    """Non-AEGIS decisions should not appear in dashboard."""
    repo = patch_repo
    await repo.record_decision(_make_aegis_decision(id="aegis-1", site_id=site_id))
    await repo.record_decision(_make_non_aegis_decision(id="other-1", site_id=site_id))

    resp = await client.get(
        f"/api/parasite/aegis/dashboard?site_id={site_id}",
        headers=auth_headers_operator,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kpis"]["proposals_24h"] == 1
    assert len(data["activity"]) == 1
    assert data["activity"][0]["id"] == "aegis-1"


@pytest.mark.asyncio
async def test_dashboard_pending_only_pending(client, patch_repo, auth_headers_operator, site_id):
    """pending_proposals should only contain decisions with outcome=pending."""
    repo = patch_repo
    await repo.record_decision(_make_aegis_decision(id="p1", site_id=site_id, approval_outcome="pending"))
    await repo.record_decision(_make_aegis_decision(id="p2", site_id=site_id, approval_outcome="approved"))

    resp = await client.get(
        f"/api/parasite/aegis/dashboard?site_id={site_id}",
        headers=auth_headers_operator,
    )
    assert resp.status_code == 200
    pending = resp.json()["pending_proposals"]
    assert len(pending) == 1
    assert pending[0]["id"] == "p1"


@pytest.mark.asyncio
async def test_existing_endpoints_unaffected(client, patch_repo, auth_headers_operator):
    """Existing /decisions and /health endpoints should still work."""
    resp = await client.get("/api/parasite/decisions", headers=auth_headers_operator)
    assert resp.status_code == 200

    resp = await client.get("/api/parasite/health", headers=auth_headers_operator)
    assert resp.status_code == 200
