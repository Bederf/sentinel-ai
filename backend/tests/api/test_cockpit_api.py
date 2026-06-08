from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api import cockpit as cockpit_api
from app.api.cockpit import (
    CockpitActionRequest,
    CockpitIssue,
    CockpitIssueEvidenceRef,
    CockpitIssueLocation,
    CockpitSourceStatus,
)

# ---------------------------------------------------------------------------
# Shared helpers for API-level tests
# ---------------------------------------------------------------------------


def _make_jwt_headers() -> dict:
    """Generate a minimal valid JWT for cockpit API tests using settings."""
    import jwt as pyjwt
    from app.config.settings import settings

    secret = settings.jwt_secret_key or os.environ.get(
        "JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars"
    )
    payload = {
        "sub": "operator-test-user",
        "email": "operator@test.sentinel.local",
        "role": "operator",
        "iss": "sentinel.bms",
        "aud": "sentinel.bms",
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = pyjwt.encode(payload, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _make_issue(issue_id: str = "issue-bms-s002-chiller-001") -> CockpitIssue:
    now = datetime.now(UTC)
    sla_due = now + timedelta(minutes=20)
    return CockpitIssue(
        id=issue_id,
        title="Boardroom cooling resilience slipping",
        summary="Lead chiller loading is climbing while boardroom drift accelerates.",
        severity="critical",
        source="bms",
        status="new",
        owner=None,
        owner_team="operations",
        opened_at=now,
        updated_at=now,
        sla_due_at=sla_due,
        impact_summary="Occupied executive meeting space will breach comfort bounds.",
        cause_hypothesis="Compressor load rise plus thermal drift indicates reduced standby resilience.",
        recommended_action="Acknowledge, assign, create work order, inspect standby path.",
        confidence=0.83,
        confidence_label="High confidence",
        location=CockpitIssueLocation(
            zone_ids=["Zone-L4-Boardroom-A", "Zone-L4-Boardroom-B"],
            asset_ids=["S002-CHILLER-B1-001"],
            floor_id="L4",
        ),
        evidence_refs=[
            CockpitIssueEvidenceRef(
                id="telemetry:S002-CHILLER-B1-001:compressor_load",
                kind="telemetry",
                label="Compressor load trend",
                source="bms",
            )
        ],
        source_record_id="telemetry-event-9911",
    )


def _seed_issue(issue: CockpitIssue, site_id: str = "S002") -> CockpitIssue:
    cockpit_api._cache_site_issues(site_id, [issue])
    return issue


@pytest.fixture(autouse=True)
def reset_state() -> None:
    cockpit_api._ISSUE_STORE.clear()
    cockpit_api._AUDIT_LOG_STORE.clear()
    cockpit_api._ISSUE_SITE_LOOKUP.clear()


@pytest.mark.asyncio
async def test_get_decision_returns_payload(monkeypatch):
    issue = _make_issue()
    now = datetime.now(UTC)
    statuses = [
        CockpitSourceStatus(
            source="bms",
            label="BMS",
            state="healthy",
            badge_tone="normal",
            last_updated_at=now,
            freshness_seconds=30,
            stale_after_seconds=90,
            degraded_after_seconds=45,
            degraded_confidence=False,
            message="Telemetry current",
        )
    ]

    async def _mock_phase(site_id: str) -> str:
        return "advisory"

    monkeypatch.setattr(cockpit_api, "_fetch_site_phase", _mock_phase)
    monkeypatch.setattr(
        cockpit_api.cockpit_issue_service,
        "aggregate",
        lambda site_id, **kwargs: ([issue], [], statuses, [], issue.id),
    )

    response = await cockpit_api.get_cockpit_decision("S002")
    payload = response["payload"]

    assert payload is not None
    assert payload.building_id == "S002"
    assert payload.selected_issue_id == issue.id
    assert payload.issues[0].id == issue.id
    assert payload.source_health == statuses


@pytest.mark.asyncio
async def test_get_decision_returns_null_when_no_issues(monkeypatch):
    async def _mock_phase(site_id: str) -> str:
        return "advisory"

    monkeypatch.setattr(cockpit_api, "_fetch_site_phase", _mock_phase)
    monkeypatch.setattr(
        cockpit_api.cockpit_issue_service,
        "aggregate",
        lambda site_id, **kwargs: ([], [], [], [], None),
    )

    response = await cockpit_api.get_cockpit_decision("S002")
    assert response["payload"] is None


def test_acknowledge_transitions_status_and_logs_audit():
    issue = _seed_issue(_make_issue())
    request = CockpitActionRequest(
        action="acknowledge",
        actor_id="operator-1",
        actor_label="Operator 1",
        evidence_refs=[ref.id for ref in issue.evidence_refs],
    )
    result, status_after, message = cockpit_api._apply_action(issue, request)
    audit = cockpit_api._record_audit(issue, request, result, "new", status_after, message)

    assert result == "accepted"
    assert issue.status == "triaged"
    assert status_after == "triaged"
    assert audit.status_before == "new"
    assert audit.status_after == "triaged"
    assert audit.issue_id == issue.id


def test_create_work_order_rejected_when_issue_new():
    issue = _seed_issue(_make_issue())
    request = CockpitActionRequest(
        action="create_work_order",
        actor_id="operator-1",
        actor_label="Operator 1",
        work_order_title="Repair path",
        evidence_refs=[],
    )
    result, status_after, message = cockpit_api._apply_action(issue, request)

    assert result == "rejected"
    assert status_after == "new"
    assert "triaged or in_progress" in message


def test_assign_requires_assignee_or_team():
    issue = _seed_issue(_make_issue())
    request = CockpitActionRequest(
        action="assign",
        actor_id="operator-1",
        actor_label="Operator 1",
        evidence_refs=[],
    )
    result, _, message = cockpit_api._apply_action(issue, request)

    assert result == "rejected"
    assert "assign_to or assign_team required" in message


def test_available_actions_reflect_issue_state():
    issue = _seed_issue(_make_issue())
    request = CockpitActionRequest(
        action="assign",
        actor_id="operator-1",
        actor_label="Operator 1",
        assign_team="operations",
        evidence_refs=[],
    )
    result, status_after, _ = cockpit_api._apply_action(issue, request)

    assert result == "accepted"
    assert status_after == "triaged"
    next_actions = cockpit_api._available_actions(issue.status)
    assert "create_work_order" in next_actions
    assert "assign" in next_actions


@pytest.mark.asyncio
async def test_decision_payload_uses_cached_issue_state(monkeypatch):
    issue = _make_issue()
    now = datetime.now(UTC)
    statuses = [
        CockpitSourceStatus(
            source="bms",
            label="BMS",
            state="healthy",
            badge_tone="normal",
            last_updated_at=now,
            freshness_seconds=30,
            stale_after_seconds=90,
            degraded_after_seconds=45,
            degraded_confidence=False,
            message="Telemetry current",
        )
    ]

    async def _mock_phase(site_id: str) -> str:
        return "advisory"

    monkeypatch.setattr(cockpit_api, "_fetch_site_phase", _mock_phase)

    override_issue = CockpitIssue(**issue.dict())
    override_issue.status = "triaged"
    override_issue.updated_at = now
    cockpit_api._ISSUE_STORE["S002"] = [override_issue]

    monkeypatch.setattr(
        cockpit_api.cockpit_issue_service,
        "aggregate",
        lambda site_id, **kwargs: ([issue], [], statuses, [], issue.id),
    )

    payload = await cockpit_api._build_cockpit_payload("S002")

    assert payload is not None
    assert payload.issues[0].status == "triaged"


# ===========================================================================
# API-level integration tests (httpx AsyncClient + ASGITransport)
# ===========================================================================


@pytest.mark.asyncio
async def test_api_get_decision_with_issues(monkeypatch):
    """API-level: GET /cockpit/decision/S002 returns issue payload."""
    from httpx import ASGITransport, AsyncClient

    from app.api import cockpit as c
    from app.main import app as fastapi_app

    issue = _make_issue()
    now = datetime.now(UTC)
    source = CockpitSourceStatus(
        source="bms",
        label="BMS",
        state="healthy",
        badge_tone="normal",
        last_updated_at=now,
        freshness_seconds=30,
        stale_after_seconds=90,
        degraded_after_seconds=45,
        degraded_confidence=False,
        message="Current",
    )

    async def _mock_phase(site_id: str) -> str:
        return "advisory"

    monkeypatch.setattr(c, "_fetch_site_phase", _mock_phase)
    monkeypatch.setattr(
        c.cockpit_issue_service,
        "aggregate",
        lambda site_id, **kw: ([issue], [], [source], [], issue.id),
    )

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            "/api/cockpit/decision/S002",
            headers=_make_jwt_headers(),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["payload"] is not None
    assert data["payload"]["building_id"] == "S002"
    assert len(data["payload"]["issues"]) == 1
    assert data["payload"]["selected_issue_id"] == issue.id


@pytest.mark.asyncio
async def test_api_get_decision_null_in_commissioning(monkeypatch):
    """Phase gate: commissioning phase returns null payload."""
    from httpx import ASGITransport, AsyncClient

    from app.api import cockpit as c
    from app.main import app as fastapi_app

    async def _mock_phase(site_id: str) -> str:
        return "commissioning"

    monkeypatch.setattr(c, "_fetch_site_phase", _mock_phase)

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            "/api/cockpit/decision/S002",
            headers=_make_jwt_headers(),
        )

    assert resp.status_code == 200
    assert resp.json()["payload"] is None


@pytest.mark.asyncio
async def test_api_get_decision_null_in_shadow_live(monkeypatch):
    """Phase gate: shadow_live phase returns null payload."""
    from httpx import ASGITransport, AsyncClient

    from app.api import cockpit as c
    from app.main import app as fastapi_app

    async def _mock_phase(site_id: str) -> str:
        return "shadow_live"

    monkeypatch.setattr(c, "_fetch_site_phase", _mock_phase)

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            "/api/cockpit/decision/S002",
            headers=_make_jwt_headers(),
        )

    assert resp.status_code == 200
    assert resp.json()["payload"] is None


@pytest.mark.asyncio
async def test_api_action_acknowledge(monkeypatch):
    """POST /cockpit/issues/.../action — acknowledge transitions new→triaged."""
    from httpx import ASGITransport, AsyncClient

    from app.api import cockpit as c
    from app.main import app as fastapi_app

    issue = _seed_issue(_make_issue())

    async def _mock_phase(site_id: str) -> str:
        return "supervised"

    async def _mock_control(site_id: str) -> bool:
        return True

    monkeypatch.setattr(c, "_fetch_site_phase", _mock_phase)
    monkeypatch.setattr(c, "_fetch_control_enabled", _mock_control)

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            f"/api/cockpit/issues/S002/{issue.id}/action",
            json={
                "action": "acknowledge",
                "actor_id": "op-1",
                "actor_label": "Operator 1",
                "evidence_refs": [],
            },
            headers=_make_jwt_headers(),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "accepted"
    assert data["status_before"] == "new"
    assert data["status_after"] == "triaged"


@pytest.mark.asyncio
async def test_api_action_blocked_in_advisory(monkeypatch):
    """Advisory posture blocks create_work_order (403)."""
    from httpx import ASGITransport, AsyncClient

    from app.api import cockpit as c
    from app.main import app as fastapi_app

    issue = _seed_issue(_make_issue())
    issue.status = "triaged"

    async def _mock_phase(site_id: str) -> str:
        return "advisory"

    async def _mock_control(site_id: str) -> bool:
        return False

    monkeypatch.setattr(c, "_fetch_site_phase", _mock_phase)
    monkeypatch.setattr(c, "_fetch_control_enabled", _mock_control)

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            f"/api/cockpit/issues/S002/{issue.id}/action",
            json={
                "action": "create_work_order",
                "actor_id": "op-1",
                "actor_label": "Op 1",
                "work_order_title": "Fix chiller",
                "evidence_refs": [],
            },
            headers=_make_jwt_headers(),
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_action_blocked_when_control_disabled(monkeypatch):
    """control_enabled=False blocks create_work_order even in supervised phase (403)."""
    from httpx import ASGITransport, AsyncClient

    from app.api import cockpit as c
    from app.main import app as fastapi_app

    issue = _seed_issue(_make_issue())
    issue.status = "triaged"

    async def _mock_phase(site_id: str) -> str:
        return "supervised"

    async def _mock_control(site_id: str) -> bool:
        return False

    monkeypatch.setattr(c, "_fetch_site_phase", _mock_phase)
    monkeypatch.setattr(c, "_fetch_control_enabled", _mock_control)

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            f"/api/cockpit/issues/S002/{issue.id}/action",
            json={
                "action": "create_work_order",
                "actor_id": "op-1",
                "actor_label": "Op 1",
                "work_order_title": "Fix chiller",
                "evidence_refs": [],
            },
            headers=_make_jwt_headers(),
        )

    assert resp.status_code == 403
    assert "Control not enabled" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_approve_rejected_in_advisory(monkeypatch):
    """POST /cockpit/decision/approve/{site_id} blocked in advisory phase (400)."""
    from httpx import ASGITransport, AsyncClient

    from app.api import cockpit as c
    from app.main import app as fastapi_app

    async def _mock_phase(site_id: str) -> str:
        return "advisory"

    monkeypatch.setattr(c, "_fetch_site_phase", _mock_phase)

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/cockpit/decision/approve/S002",
            headers=_make_jwt_headers(),
        )

    assert resp.status_code == 400
    assert "advisory" in resp.json()["detail"]
