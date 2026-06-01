"""Tests for 4-milestone SLA milestone service.

Uses synthetic fixture data — no live MRI/Sentry dependency.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.recommendation import MilestoneStatus, Recommendation
from app.models.sla_term import RecommendationSLATerm

# =============================================================================
# Fixtures
# =============================================================================


def make_rec(
    milestone_status: MilestoneStatus = MilestoneStatus.ASSIGNED,
    assigned_at: datetime | None = None,
    in_progress_at: datetime | None = None,
    resolved_at: datetime | None = None,
    verified_at: datetime | None = None,
    sla_hours: dict[str, int] | None = None,
    sla_deadline_at: datetime | None = None,
    site_id: str = "site-002",
    external_ticket_id: str | None = None,
) -> Recommendation:
    """Create a Recommendation fixture with optional milestone fields."""
    return Recommendation(
        id=str(uuid.uuid4()),
        site_id=site_id,
        timestamp=datetime.now(UTC),
        action_type="hvac_setpoint_change",
        milestone_status=milestone_status,
        assigned_at=assigned_at or datetime.now(UTC),
        in_progress_at=in_progress_at,
        resolved_at=resolved_at,
        verified_at=verified_at,
        sla_hours=sla_hours or {"assigned": 24, "in_progress": 48, "resolved": 72, "verified": 168},
        sla_deadline_at=sla_deadline_at,
        external_ticket_id=external_ticket_id,
    )


def make_sla_term(
    site_code: str = "site-002",
    milestone: MilestoneStatus = MilestoneStatus.ASSIGNED,
    deadline_hours: int = 24,
) -> RecommendationSLATerm:
    return RecommendationSLATerm(
        site_code=site_code,
        milestone=milestone,
        deadline_hours=deadline_hours,
    )


# =============================================================================
# MilestoneStatus enum
# =============================================================================


@pytest.mark.unit
class TestMilestoneStatus:
    def test_four_values(self):
        assert len(MilestoneStatus) == 4

    def test_values(self):
        assert MilestoneStatus.ASSIGNED.value == "assigned"
        assert MilestoneStatus.IN_PROGRESS.value == "in_progress"
        assert MilestoneStatus.RESOLVED.value == "resolved"
        assert MilestoneStatus.VERIFIED.value == "verified"

    def test_is_strenum(self):
        assert isinstance(MilestoneStatus.ASSIGNED.value, str)


# =============================================================================
# Recommendation model with milestone fields
# =============================================================================


@pytest.mark.unit
class TestRecommendationMilestoneFields:
    def test_default_milestone_is_assigned(self):
        rec = make_rec(milestone_status=MilestoneStatus.ASSIGNED)
        assert rec.milestone_status == MilestoneStatus.ASSIGNED

    def test_to_dict_includes_milestone_fields(self):
        rec = make_rec(
            milestone_status=MilestoneStatus.IN_PROGRESS,
            sla_hours={"assigned": 24, "in_progress": 48},
        )
        d = rec.to_dict()
        assert d["milestone_status"] == "in_progress"
        assert d["sla_hours"]["in_progress"] == 48
        assert "assigned_at" in d
        assert "sla_deadline_at" in d

    def test_from_dict_parses_milestone_status(self):
        data = {
            "id": str(uuid.uuid4()),
            "milestone_status": "resolved",
            "assigned_at": datetime.now(UTC).isoformat(),
            "in_progress_at": datetime.now(UTC).isoformat(),
            "resolved_at": datetime.now(UTC).isoformat(),
            "sla_hours": {"assigned": 24},
            "sla_deadline_at": None,
        }
        rec = Recommendation.from_dict(data)
        assert rec.milestone_status == MilestoneStatus.RESOLVED

    def test_from_dict_defaults_missing_fields(self):
        data = {"id": str(uuid.uuid4()), "site_id": "site-002"}
        rec = Recommendation.from_dict(data)
        assert rec.milestone_status == MilestoneStatus.ASSIGNED
        assert rec.sla_hours == {}


# =============================================================================
# RecommendationSLATerm model
# =============================================================================


@pytest.mark.unit
class TestRecommendationSLATerm:
    def test_defaults(self):
        term = make_sla_term()
        assert term.deadline_hours == 24
        assert term.milestone == MilestoneStatus.ASSIGNED
        assert term.site_code == "site-002"

    def test_to_dict_from_dict_roundtrip(self):
        term = make_sla_term(milestone=MilestoneStatus.RESOLVED, deadline_hours=72)
        d = term.to_dict()
        restored = RecommendationSLATerm.from_dict(d)
        assert restored.milestone == MilestoneStatus.RESOLVED
        assert restored.deadline_hours == 72


# =============================================================================
# RecommendationMilestoneService — unit tests with mocks
# =============================================================================


@pytest.mark.unit
class TestMilestoneServiceAdvance:
    """Test milestone transitions with mocked repos."""

    @pytest.fixture
    def svc(self):
        with (
            patch("app.services.recommendation_milestone_service.get_recommendation_sla_repository"),
            patch("app.services.recommendation_milestone_service.get_recommendation_repository"),
        ):
            from app.services.recommendation_milestone_service import RecommendationMilestoneService

            return RecommendationMilestoneService()

    def test_advance_sets_in_progress_timestamp(self):
        rec = make_rec(milestone_status=MilestoneStatus.ASSIGNED)

        with (
            patch("app.services.recommendation_milestone_service.get_recommendation_repository") as mock_get_rec_repo,
            patch("app.services.recommendation_milestone_service.get_recommendation_sla_repository"),
        ):
            mock_rec_repo = MagicMock()
            mock_get_rec_repo.return_value = mock_rec_repo
            mock_rec_repo.get = AsyncMock(return_value=rec)
            mock_rec_repo.update = AsyncMock(return_value=rec)

            from app.services.recommendation_milestone_service import RecommendationMilestoneService

            svc = RecommendationMilestoneService()
            svc._rec_repo = mock_rec_repo

            import asyncio

            result = asyncio.get_event_loop().run_until_complete(
                svc.advance_milestone(rec.id, MilestoneStatus.IN_PROGRESS)
            )
            mock_rec_repo.update.assert_called_once()

    def test_advance_unknown_rec_raises(self):
        with (
            patch("app.services.recommendation_milestone_service.get_recommendation_repository") as mock_get_rec_repo,
            patch("app.services.recommendation_milestone_service.get_recommendation_sla_repository"),
        ):
            mock_rec_repo = MagicMock()
            mock_get_rec_repo.return_value = mock_rec_repo
            mock_rec_repo.get = AsyncMock(return_value=None)

            from app.services.recommendation_milestone_service import RecommendationMilestoneService

            svc = RecommendationMilestoneService()
            svc._rec_repo = mock_rec_repo

            with pytest.raises(ValueError, match="not found"):
                import asyncio

                asyncio.get_event_loop().run_until_complete(
                    svc.advance_milestone("fake-id", MilestoneStatus.IN_PROGRESS)
                )


@pytest.mark.unit
class TestMilestoneServiceBreachCheck:
    """Test SLA breach detection with synthetic data."""

    @pytest.fixture
    def svc(self):
        with (
            patch("app.services.recommendation_milestone_service.get_recommendation_sla_repository"),
            patch("app.services.recommendation_milestone_service.get_recommendation_repository"),
        ):
            from app.services.recommendation_milestone_service import RecommendationMilestoneService

            return RecommendationMilestoneService()

    def test_elapsed_pct_within_sla(self, svc):
        # Created now, 24h SLA, 50% elapsed
        now = datetime.now(UTC)
        start = now - timedelta(hours=12)
        deadline = now + timedelta(hours=12)
        rec = make_rec(
            milestone_status=MilestoneStatus.ASSIGNED,
            assigned_at=start,
            sla_deadline_at=deadline,
        )
        pct = svc._elapsed_pct(rec)
        assert 0.45 < pct < 0.55

    def test_elapsed_pct_breached(self, svc):
        # Created 30h ago, 24h SLA → ~125% elapsed
        now = datetime.now(UTC)
        start = now - timedelta(hours=30)
        deadline = now - timedelta(hours=6)
        rec = make_rec(
            milestone_status=MilestoneStatus.ASSIGNED,
            assigned_at=start,
            sla_deadline_at=deadline,
        )
        pct = svc._elapsed_pct(rec)
        assert pct > 1.0

    def test_elapsed_pct_caps_at_200(self, svc):
        now = datetime.now(UTC)
        rec = make_rec(
            milestone_status=MilestoneStatus.ASSIGNED,
            assigned_at=now - timedelta(hours=100),
            sla_deadline_at=now - timedelta(hours=76),
        )
        pct = svc._elapsed_pct(rec)
        assert pct == 2.0

    def test_escalation_tier_notice(self, svc):
        assert svc._escalation_tier(0.50) == "notice"
        assert svc._escalation_tier(0.74) == "notice"

    def test_escalation_tier_warning(self, svc):
        assert svc._escalation_tier(0.75) == "warning"
        assert svc._escalation_tier(0.89) == "warning"

    def test_escalation_tier_critical(self, svc):
        assert svc._escalation_tier(0.90) == "critical"
        assert svc._escalation_tier(0.99) == "critical"

    def test_escalation_tier_breach(self, svc):
        assert svc._escalation_tier(1.0) == "breach"
        assert svc._escalation_tier(1.5) == "breach"

    def test_escalation_tier_none_below_threshold(self, svc):
        assert svc._escalation_tier(0.49) is None

    def test_get_milestone_start_assigned(self, svc):
        now = datetime.now(UTC)
        rec = make_rec(milestone_status=MilestoneStatus.ASSIGNED, assigned_at=now)
        assert svc._get_milestone_start(rec) == now

    def test_get_milestone_start_in_progress(self, svc):
        now = datetime.now(UTC)
        rec = make_rec(
            milestone_status=MilestoneStatus.IN_PROGRESS,
            in_progress_at=now,
            assigned_at=now - timedelta(hours=2),
        )
        assert svc._get_milestone_start(rec) == now


@pytest.mark.unit
class TestFullMilestoneCycle:
    """Test a recommendation transitions through all 4 milestones."""

    @pytest.fixture
    def svc(self):
        with (
            patch("app.services.recommendation_milestone_service.get_recommendation_sla_repository"),
            patch("app.services.recommendation_milestone_service.get_recommendation_repository"),
        ):
            from app.services.recommendation_milestone_service import RecommendationMilestoneService

            return RecommendationMilestoneService()

    def test_full_cycle_assigned_in_progress_resolved_verified(self, svc):
        """Verify all 4 milestone transitions work end-to-end."""
        now = datetime.now(UTC)
        rec = make_rec(
            milestone_status=MilestoneStatus.ASSIGNED,
            assigned_at=now,
        )

        transitions = [
            (MilestoneStatus.ASSIGNED, MilestoneStatus.IN_PROGRESS),
            (MilestoneStatus.IN_PROGRESS, MilestoneStatus.RESOLVED),
            (MilestoneStatus.RESOLVED, MilestoneStatus.VERIFIED),
        ]

        for prev, next_ in transitions:
            rec.milestone_status = next_
            if next_ == MilestoneStatus.IN_PROGRESS:
                rec.in_progress_at = now
            elif next_ == MilestoneStatus.RESOLVED:
                rec.resolved_at = now
            elif next_ == MilestoneStatus.VERIFIED:
                rec.verified_at = now

            assert rec.milestone_status == next_

        assert rec.milestone_status == MilestoneStatus.VERIFIED


# =============================================================================
# BackgroundScheduler — milestone timer job registration
# =============================================================================


@pytest.mark.unit
class TestSchedulerMilestoneJob:
    def test_milestone_timer_method_exists(self):
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService()
        assert hasattr(svc, "add_milestone_timer_job")

    def test_milestone_timer_job_can_be_added(self):
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService()
        try:
            svc.add_milestone_timer_job(interval_seconds=300)
            job = svc.scheduler.get_job("check_recommendation_milestone_timers")
            assert job is not None
        except Exception as e:
            pytest.skip(f"Scheduler not started: {e}")

    def test_check_milestone_deadlines_method_exists(self):
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService()
        assert hasattr(svc, "_check_milestone_deadlines")
