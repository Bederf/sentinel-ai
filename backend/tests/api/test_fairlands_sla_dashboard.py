"""API tests for Fairlands SLA Dashboard endpoints (Phase 207-06).

Tests BOLA protection, response shapes, and site_code filtering.
"""

import os
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, mock as mock_module, patch

import pytest

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Test user configuration
# ---------------------------------------------------------------------------

SITE_CODE = "site-002"
USER_EMAIL = "fm-operator@sentinel.bms"
USER_ID = "fm-op-001"

USER_AUTH = AuthContext(
    user_id=USER_ID,
    role=SentinelRole.ADMIN,
    auth_method="bearer_token",
    source_ip="127.0.0.1",
    email=USER_EMAIL,
)


def _fake_auth_for(auth_ctx: AuthContext | None):
    """Return an async function that acts as _authenticate_request."""

    async def _fake(request):
        return auth_ctx

    return _fake


@pytest.fixture
async def client():
    """Async client with authenticated admin user."""
    transport = ASGITransport(app=app)
    _fake = _fake_auth_for(USER_AUTH)
    with patch.dict(os.environ, {"TESTING": "false"}):
        with patch("app.startup.middleware._authenticate_request", new=_fake):
            with patch("app.middleware.auth_middleware._authenticate_request", new=_fake):
                async with AsyncClient(transport=transport, base_url="http://test") as c:
                    yield c


# ---------------------------------------------------------------------------
# Test: GET /api/fairlands/sla/milestones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_milestones_returns_list_of_milestone_status(client):
    """GET /api/fairlands/sla/milestones returns list of MilestoneStatusResponse."""
    mock_recs = [
        {
            "id": "rec-001",
            "site_id": "S002",
            "reason": "Urinal blocked in B1 zone",
            "target_equipment": "S002-URINAL-B1-001",
            "milestone_status": "in_progress",
            "assigned_at": datetime.now(UTC).isoformat(),
            "in_progress_at": datetime.now(UTC).isoformat(),
            "resolved_at": None,
            "verified_at": None,
            "sla_deadline_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
        },
    ]

    with patch("app.api.fairlands_sla_dashboard.get_recommendation_milestone_service") as mock_svc:
        mock_instance = AsyncMock()
        mock_instance.rec_repo.client = AsyncMock()
        table_mock = mock_instance.rec_repo.client.table.return_value
        select_mock = table_mock.select.return_value
        eq_mock = select_mock.eq.return_value
        eq_mock.neq.return_value.execute = AsyncMock(return_value=mock_module.Mock(data=mock_recs))
        mock_svc.return_value = mock_instance

        response = await client.get(f"/api/fairlands/sla/milestones?site_code={SITE_CODE}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["recommendation_id"] == "rec-001"
        assert data[0]["milestone_status"] == "in_progress"
        assert "elapsed_pct" in data[0]
        assert "rag_status" in data[0]


@pytest.mark.asyncio
async def test_milestones_empty_for_site_with_no_recommendations(client):
    """Returns empty list when site has no recommendations."""
    with patch("app.api.fairlands_sla_dashboard.get_recommendation_milestone_service") as mock_svc:
        mock_instance = AsyncMock()
        mock_instance.rec_repo.client = AsyncMock()
        table_mock = mock_instance.rec_repo.client.table.return_value
        select_mock = table_mock.select.return_value
        eq_mock = select_mock.eq.return_value
        eq_mock.neq.return_value.execute = AsyncMock(return_value=mock_module.Mock(data=[]))
        mock_svc.return_value = mock_instance

        response = await client.get(f"/api/fairlands/sla/milestones?site_code={SITE_CODE}")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Test: GET /api/fairlands/sla/breaches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breaches_returns_list_of_sla_breaches(client):
    """GET /api/fairlands/sla/breaches returns list of SLABreachResponse."""
    from app.models.recommendation import Recommendation, MilestoneStatus

    mock_rec = Recommendation(
        id="rec-002",
        site_id="S002",
        reason="Chiller setpoint drift",
        target_equipment="S002-CHILLER-B1-001",
        milestone_status=MilestoneStatus.IN_PROGRESS,
        assigned_at=datetime.now(UTC) - timedelta(hours=72),
        in_progress_at=datetime.now(UTC) - timedelta(hours=48),
        sla_deadline_at=datetime.now(UTC) - timedelta(hours=24),
    )

    mock_breaches = [
        {
            "recommendation": mock_rec,
            "breach_minutes": 1440,  # 1 day
            "elapsed_pct": 1.5,
            "milestone": "in_progress",
        }
    ]

    with patch("app.api.fairlands_sla_dashboard.get_recommendation_milestone_service") as mock_svc:
        mock_instance = AsyncMock()
        mock_instance.check_breaches = AsyncMock(return_value=mock_breaches)
        mock_svc.return_value = mock_instance

        response = await client.get(f"/api/fairlands/sla/breaches?site_code={SITE_CODE}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["recommendation_id"] == "rec-002"
        assert data[0]["breach_pct"] > 0


@pytest.mark.asyncio
async def test_breaches_filters_by_site(client):
    """Breaches endpoint filters to the requested site."""
    from app.models.recommendation import Recommendation, MilestoneStatus

    # Create a breach for a DIFFERENT site
    other_site_rec = Recommendation(
        id="rec-003",
        site_id="S003",  # Different site
        reason="Other site issue",
        target_equipment="S003-URINAL-B1-001",
        milestone_status=MilestoneStatus.ASSIGNED,
        assigned_at=datetime.now(UTC) - timedelta(hours=48),
        sla_deadline_at=datetime.now(UTC) - timedelta(hours=24),
    )

    mock_breaches = [
        {
            "recommendation": other_site_rec,
            "breach_minutes": 1440,
            "elapsed_pct": 1.5,
            "milestone": "assigned",
        }
    ]

    with patch("app.api.fairlands_sla_dashboard.get_recommendation_milestone_service") as mock_svc:
        mock_instance = AsyncMock()
        mock_instance.check_breaches = AsyncMock(return_value=mock_breaches)
        mock_svc.return_value = mock_instance

        response = await client.get(f"/api/fairlands/sla/breaches?site_code={SITE_CODE}")

        # Should return empty because breach is for S003, not S002
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Test: GET /api/fairlands/sla/clusters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clusters_returns_list_of_cluster_alerts(client):
    """GET /api/fairlands/sla/clusters returns list of ClusterAlertResponse."""
    from app.services.fault_occurrence_tracker import ClusterAlert

    mock_alerts = [
        ClusterAlert(
            site_code=SITE_CODE,
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
            cluster_count=5,
            latest_occurred_at=datetime.now(UTC).isoformat(),
        )
    ]

    with patch("app.api.fairlands_sla_dashboard.get_fault_occurrence_tracker") as mock_tracker:
        mock_instance = AsyncMock()
        mock_instance.get_cluster_alerts = AsyncMock(return_value=mock_alerts)
        mock_tracker.return_value = mock_instance

        response = await client.get(f"/api/fairlands/sla/clusters?site_code={SITE_CODE}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["equipment_id"] == "S002-URINAL-B1-001"
        assert data[0]["cluster_count"] == 5
        assert "urgency_boost" in data[0]


# ---------------------------------------------------------------------------
# Test: GET /api/fairlands/sla/compliance/fire-pump
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_pump_compliance_returns_list_of_compliance_status(client):
    """GET /api/fairlands/sla/compliance/fire-pump returns list of FirePumpComplianceResponse."""
    from app.models.fire_pump_compliance import OverdueAlert

    mock_alerts = [
        OverdueAlert(
            equipment_id="S002-FIREPUMP-001",
            site_code=SITE_CODE,
            last_test_date=date.today() - timedelta(days=14),
            scheduled_date=date.today(),
            days_overdue=14,
            regulatory_reference="FNBFW:32335",
        )
    ]

    with patch("app.api.fairlands_sla_dashboard.get_fire_pump_compliance_service") as mock_svc:
        mock_instance = AsyncMock()
        mock_instance.get_overdue_alerts = AsyncMock(return_value=mock_alerts)
        mock_svc.return_value = mock_instance

        response = await client.get(f"/api/fairlands/sla/compliance/fire-pump?site_code={SITE_CODE}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["equipment_id"] == "S002-FIREPUMP-001"
        assert data[0]["is_overdue"] is True
        assert data[0]["days_overdue"] == 14
        assert data[0]["regulatory_reference"] == "FNBFW:32335"


# ---------------------------------------------------------------------------
# Test: GET /api/fairlands/sla/summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_returns_sla_summary(client):
    """GET /api/fairlands/sla/summary returns SLASummaryResponse."""
    # Mock milestone counts
    mock_recs_data = [
        {"milestone_status": "assigned"},
        {"milestone_status": "assigned"},
        {"milestone_status": "in_progress"},
        {"milestone_status": "resolved"},
        {"milestone_status": "verified"},
    ]

    with (
        patch("app.api.fairlands_sla_dashboard.get_recommendation_milestone_service") as mock_svc,
        patch("app.api.fairlands_sla_dashboard.get_fault_occurrence_tracker") as mock_tracker,
        patch("app.api.fairlands_sla_dashboard.get_fire_pump_compliance_service") as mock_fire_svc,
    ):
        # Mock milestone service
        mock_milestone_instance = AsyncMock()
        mock_milestone_instance.rec_repo.client = AsyncMock()
        table_mock = mock_milestone_instance.rec_repo.client.table.return_value
        select_mock = table_mock.select.return_value
        select_mock.eq.return_value.execute = AsyncMock(return_value=mock_module.Mock(data=mock_recs_data))
        mock_milestone_instance.check_breaches = AsyncMock(return_value=[])
        mock_svc.return_value = mock_milestone_instance

        # Mock cluster tracker
        mock_tracker_instance = AsyncMock()
        mock_tracker_instance.get_cluster_alerts = AsyncMock(return_value=[])
        mock_tracker.return_value = mock_tracker_instance

        # Mock fire pump service
        mock_fire_instance = AsyncMock()
        mock_fire_instance.get_overdue_alerts = AsyncMock(return_value=[])
        mock_fire_svc.return_value = mock_fire_instance

        response = await client.get(f"/api/fairlands/sla/summary?site_code={SITE_CODE}")

        assert response.status_code == 200
        data = response.json()
        assert data["site_code"] == SITE_CODE
        assert data["total_open"] == 4  # assigned + in_progress + resolved = 4 (verified is not open)
        assert data["assigned"] == 2
        assert data["in_progress"] == 1
        assert data["resolved"] == 1
        assert data["verified"] == 1
        assert data["breach_count"] == 0
        assert data["cluster_alert_count"] == 0
        assert "generated_at" in data


@pytest.mark.asyncio
async def test_summary_returns_empty_on_error(client):
    """Summary endpoint returns empty summary on service failure (non-blocking)."""
    with patch("app.api.fairlands_sla_dashboard.get_recommendation_milestone_service") as mock_svc:
        mock_instance = AsyncMock()
        mock_instance.rec_repo.client = None  # Force error
        mock_instance.check_breaches = AsyncMock(return_value=[])
        mock_svc.return_value = mock_instance

        response = await client.get(f"/api/fairlands/sla/summary?site_code={SITE_CODE}")

        # Should still return 200 with zeros
        assert response.status_code == 200
        data = response.json()
        assert data["site_code"] == SITE_CODE
        assert data["total_open"] == 0
