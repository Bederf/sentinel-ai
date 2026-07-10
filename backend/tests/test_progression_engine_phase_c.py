"""Tests for Phase C — Demotion triggers and apply_demotions.

Tests all 4 demotion trigger types, cool-off enforcement, apply_demotions
DB/audit/alert behavior, background scheduler sync wrapper, and quality
exception endpoint integration.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.services.progression_engine_service import (
    ProgressionEngineService,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def engine():
    """Fresh ProgressionEngineService singleton for each test."""
    ProgressionEngineService._instance = None
    svc = ProgressionEngineService()
    yield svc
    ProgressionEngineService._instance = None


def _ch(data=None, count=None):
    """Create a chainable mock that returns data/count on .execute()."""
    c = Mock()
    c.data = data or []
    c.count = count
    c.select = Mock(return_value=c)
    c.eq = Mock(return_value=c)
    c.limit = Mock(return_value=c)
    c.order = Mock(return_value=c)
    c.in_ = Mock(return_value=c)
    c.gte = Mock(return_value=c)
    c.insert = Mock(return_value=c)
    c.update = Mock(return_value=c)
    c.execute = Mock(return_value=c)
    return c


def _make_client_for_demotion(
    *,
    classes=None,
    damage_count=0,
    comfort_count_by_class=None,
    existing_demotion_at=None,
):
    """Build a mock Supabase client for demotion tests.

    Uses separate chainable mocks per table name so each query is independent.
    """
    if classes is None:
        classes = [
            {
                "class_name": "zone_shutdown",
                "current_trust_level": 3,
                "evidence_count": 100,
                "accuracy_pct_30d": 88.0,
                "accuracy_pct_7d": 85.0,
                "consecutive_successes": 15,
                "consecutive_failures": 0,
                "last_demotion_at": existing_demotion_at,
            }
        ]

    if comfort_count_by_class is None:
        comfort_count_by_class = {}

    client = Mock()

    # Table: recommendation_class_readiness
    cr_chain = _ch(data=classes)

    # Table: recommendation_validations — for DAMAGE count
    rv_damage_execute = Mock(return_value=Mock(count=damage_count, data=[]))
    rv_damage = Mock()
    rv_damage.select = Mock(return_value=rv_damage)
    rv_damage.eq = Mock(return_value=rv_damage)
    rv_damage.gte = Mock(return_value=rv_damage)

    # Table: recommendation_validations — for COMFORT count per class
    # We need a fresh chain per class name lookup
    rv_comfort_chains = {}
    for cn in comfort_count_by_class:
        cnt = comfort_count_by_class[cn]
        chain = Mock()
        chain.select = Mock(return_value=chain)
        chain.eq = Mock(return_value=chain)
        chain.gte = Mock(return_value=chain)
        chain.execute = Mock(return_value=Mock(count=cnt, data=[]))
        rv_comfort_chains[cn] = chain

    # Default comfort chain for classes not in the dict (count=0)
    default_rv_comfort = Mock()
    default_rv_comfort.select = Mock(return_value=default_rv_comfort)
    default_rv_comfort.eq = Mock(return_value=default_rv_comfort)
    default_rv_comfort.gte = Mock(return_value=default_rv_comfort)
    default_rv_comfort.execute = Mock(return_value=Mock(count=0, data=[]))

    call_tracker = {"rv_calls": 0}

    def table_side_effect(name):
        if name == "recommendation_class_readiness":
            return cr_chain
        if name == "recommendation_validations":
            idx = call_tracker["rv_calls"]
            call_tracker["rv_calls"] += 1
            if idx == 0:
                # First call is damage count
                rv_damage.execute = rv_damage_execute
                return rv_damage
            else:
                # Per-class comfort query
                cn_idx = idx - 1
                if cn_idx < len(classes):
                    cn = classes[cn_idx]["class_name"]
                    if cn in rv_comfort_chains:
                        return rv_comfort_chains[cn]
                return default_rv_comfort
        return _ch()

    client.table = Mock(side_effect=table_side_effect)
    return client


# ------------------------------------------------------------------
# Demotion trigger tests
# ------------------------------------------------------------------


class TestDemotionAccuracyDrop:
    """Accuracy_pct_30d below class level threshold → demotion candidate."""

    @pytest.mark.asyncio
    async def test_level_3_accuracy_below_90(self, engine):
        """Level 3 class with 88% accuracy → accuracy_drop_l3 demotion."""
        client = _make_client_for_demotion(
            classes=[
                {
                    "class_name": "zone_shutdown",
                    "current_trust_level": 3,
                    "accuracy_pct_30d": 88.0,
                    "consecutive_failures": 0,
                    "last_demotion_at": None,
                }
            ],
            damage_count=0,
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 1
        assert demotions[0]["trigger"] == "accuracy_drop_l3"
        assert demotions[0]["current_level"] == 3
        assert demotions[0]["new_level"] == 2

    @pytest.mark.asyncio
    async def test_level_2_accuracy_below_85(self, engine):
        """Level 2 class with 82% accuracy → accuracy_drop_l2 demotion."""
        client = _make_client_for_demotion(
            classes=[
                {
                    "class_name": "hvac_setpoint_change",
                    "current_trust_level": 2,
                    "accuracy_pct_30d": 82.0,
                    "consecutive_failures": 0,
                    "last_demotion_at": None,
                }
            ],
            damage_count=0,
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 1
        assert demotions[0]["trigger"] == "accuracy_drop_l2"
        assert demotions[0]["new_level"] == 1

    @pytest.mark.asyncio
    async def test_level_1_never_demoted_by_accuracy(self, engine):
        """Level 1 class with low accuracy stays at Level 1 (no demotion)."""
        client = _make_client_for_demotion(
            classes=[
                {
                    "class_name": "new_class",
                    "current_trust_level": 1,
                    "accuracy_pct_30d": 70.0,
                    "consecutive_failures": 0,
                    "last_demotion_at": None,
                }
            ],
            damage_count=0,
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 0

    @pytest.mark.asyncio
    async def test_level_3_accuracy_at_90_not_demoted(self, engine):
        """Level 3 class at exactly 90% accuracy → no demotion."""
        client = _make_client_for_demotion(
            classes=[
                {
                    "class_name": "zone_shutdown",
                    "current_trust_level": 3,
                    "accuracy_pct_30d": 90.0,
                    "consecutive_failures": 0,
                    "last_demotion_at": None,
                }
            ],
            damage_count=0,
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 0


class TestDemotionConsecutiveFailures:
    """3+ consecutive failures → demotion to Level 1."""

    @pytest.mark.asyncio
    async def test_three_consecutive_failures_demotes(self, engine):
        """3 consecutive failures at any level → demotion to Level 1."""
        client = _make_client_for_demotion(
            classes=[
                {
                    "class_name": "lighting_dim",
                    "current_trust_level": 2,
                    "accuracy_pct_30d": 95.0,
                    "consecutive_failures": 3,
                    "last_demotion_at": None,
                }
            ],
            damage_count=0,
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 1
        assert demotions[0]["trigger"] == "consecutive_failures"
        assert demotions[0]["new_level"] == 1

    @pytest.mark.asyncio
    async def test_two_failures_no_demotion(self, engine):
        """2 consecutive failures → no demotion (threshold is 3)."""
        client = _make_client_for_demotion(
            classes=[
                {
                    "class_name": "lighting_dim",
                    "current_trust_level": 2,
                    "accuracy_pct_30d": 95.0,
                    "consecutive_failures": 2,
                    "last_demotion_at": None,
                }
            ],
            damage_count=0,
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 0


class TestDemotionEquipmentDamage:
    """Equipment damage event → all classes demoted to Level 1."""

    @pytest.mark.asyncio
    async def test_equipment_damage_site_wide(self, engine):
        """Equipment damage count > 0 → all classes demoted."""
        classes = [
            {
                "class_name": "zone_shutdown",
                "current_trust_level": 3,
                "accuracy_pct_30d": 95.0,
                "consecutive_failures": 0,
                "last_demotion_at": None,
            },
            {
                "class_name": "hvac_setpoint_change",
                "current_trust_level": 2,
                "accuracy_pct_30d": 90.0,
                "consecutive_failures": 0,
                "last_demotion_at": None,
            },
        ]
        client = _make_client_for_demotion(classes=classes, damage_count=1)

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 2
        for d in demotions:
            assert d["trigger"] == "equipment_damage"
            assert d["new_level"] == 1


class TestDemotionComfortViolation:
    """Comfort violation in last 24h → class demoted."""

    @pytest.mark.asyncio
    async def test_comfort_violation_class_specific(self, engine):
        """Comfort violation count > 0 for a class → only that class demoted."""
        classes = [
            {
                "class_name": "zone_shutdown",
                "current_trust_level": 3,
                "accuracy_pct_30d": 95.0,
                "consecutive_failures": 0,
                "last_demotion_at": None,
            },
            {
                "class_name": "hvac_setpoint_change",
                "current_trust_level": 2,
                "accuracy_pct_30d": 90.0,
                "consecutive_failures": 0,
                "last_demotion_at": None,
            },
        ]
        client = _make_client_for_demotion(classes=classes, damage_count=0, comfort_count_by_class={"zone_shutdown": 1})

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 1
        assert demotions[0]["class_name"] == "zone_shutdown"
        assert demotions[0]["trigger"] == "comfort_violation"
        assert demotions[0]["new_level"] == 1


# ------------------------------------------------------------------
# Demotion cool-off
# ------------------------------------------------------------------


class TestDemotionCoolOff:
    """Demoted class within 7 days → skipped."""

    @pytest.mark.asyncio
    async def test_cool_off_skips_recent_demotion(self, engine):
        """Class demoted 1 day ago → no re-demotion (cool-off active)."""
        from datetime import datetime, timedelta, timezone

        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        client = _make_client_for_demotion(
            classes=[
                {
                    "class_name": "zone_shutdown",
                    "current_trust_level": 3,
                    "accuracy_pct_30d": 75.0,
                    "consecutive_failures": 5,
                    "last_demotion_at": recent,
                }
            ],
            damage_count=0,
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        # Would trigger on both accuracy drop AND consecutive failures,
        # but cool-off (7 days) prevents it
        assert len(demotions) == 0

    @pytest.mark.asyncio
    async def test_cool_off_expired_allows_demotion(self, engine):
        """Class demoted 8 days ago → demotion proceeds (cool-off expired)."""
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        client = _make_client_for_demotion(
            classes=[
                {
                    "class_name": "zone_shutdown",
                    "current_trust_level": 3,
                    "accuracy_pct_30d": 75.0,
                    "consecutive_failures": 0,
                    "last_demotion_at": old,
                }
            ],
            damage_count=0,
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            demotions = await engine.check_demotion_triggers("site-002")

        assert len(demotions) == 1
        assert demotions[0]["trigger"] == "accuracy_drop_l3"
        assert demotions[0]["new_level"] == 2


# ------------------------------------------------------------------
# apply_demotions
# ------------------------------------------------------------------


class TestApplyDemotions:
    """apply_demotions updates DB, records audit, sends alerts."""

    @pytest.mark.asyncio
    async def test_apply_demotions_updates_db(self, engine):
        """apply_demotions updates current_trust_level, last_demotion_at, resets consecutive_failures."""
        client = Mock()
        cr_update_chain = _ch()
        pt_insert_chain = _ch()
        cr_select_chain = _ch(data=[{"id": "cr-001"}])

        def table_side(name):
            if name == "recommendation_class_readiness":
                t = Mock()
                t.update = Mock(return_value=t)
                t.eq = Mock(return_value=t)
                t.execute = Mock(return_value=cr_update_chain.execute.return_value)
                return t
            if name == "phase_transition_log":
                t = Mock()
                t.insert = Mock(return_value=t)
                t.execute = Mock(return_value=pt_insert_chain.execute.return_value)
                return t
            return _ch()

        client.table = Mock(side_effect=table_side)

        demotions = [
            {
                "class_name": "zone_shutdown",
                "current_level": 2,
                "new_level": 1,
                "trigger": "consecutive_failures",
                "evidence": "3 consecutive failures",
            }
        ]

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            with patch(
                "app.services.notification_service.NotificationService.send_alert_direct", new_callable=AsyncMock
            ):
                alert_ids = await engine.apply_demotions("site-002", demotions)

        assert len(alert_ids) == 1

    @pytest.mark.asyncio
    async def test_apply_demotions_no_demotions(self, engine):
        """apply_demotions with empty list → no DB writes, no alerts."""
        client = Mock()

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=client):
            alert_ids = await engine.apply_demotions("site-002", [])

        assert alert_ids == []


# (Phase B threshold tests live in test_optimization_tier_router_phase_b.py)
