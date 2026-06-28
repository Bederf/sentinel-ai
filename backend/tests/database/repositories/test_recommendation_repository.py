"""Recommendation repository write-shape tests."""

import pytest

from app.models.recommendation import Recommendation, RecommendationStatus
from app.database.repositories.recommendation_repository import RecommendationRepository


def test_filter_supabase_payload_drops_model_only_fields():
    """Supabase writes should not include fields absent from the live table."""
    repo = RecommendationRepository()

    payload = repo._filter_supabase_payload(
        {
            "id": "rec-1",
            "site_id": "S001",
            "status": "pending",
            "action_type": "setpoint_change",
            "source": "health_alert",
            "source_type": "rule_based",
            "correlation_id": "corr-1",
            "outcome_validated": True,
            "outcome_notes": "validated",
            "reason": "Test recommendation",
        }
    )

    assert payload["id"] == "rec-1"
    assert payload["site_id"] == "S001"
    assert payload["status"] == "pending"
    assert payload["action_type"] == "setpoint_change"
    assert payload["reason"] == "Test recommendation"
    # source and source_type exist in the live table — they should be retained
    assert payload["source"] == "health_alert"
    assert payload["source_type"] == "rule_based"
    # correlation_id is model-only; outcome fields exist in the live table and are retained.
    assert "correlation_id" not in payload
    assert payload["outcome_validated"] is True
    assert payload["outcome_notes"] == "validated"


def test_normalise_source_fields_marks_operating_state_gate_recommendations():
    repo = RecommendationRepository()

    payload = repo._normalise_source_fields(
        {
            "site_id": "site-002",
            "action_type": "ai_optimization",
            "target_equipment": "SITE-002-HVAC-SCHEDULE",
            "metadata": {"rule": "closed_empty_building_hvac_running"},
        }
    )

    assert payload["source"] == "ai_optimizer"
    assert payload["source_type"] == "operating_state_gate"


def test_normalise_source_fields_marks_ai_optimization_default_source_type():
    repo = RecommendationRepository()

    payload = repo._normalise_source_fields(
        {
            "site_id": "site-002",
            "action_type": "ai_optimization",
            "target_equipment": "S002-AHU-B01",
            "metadata": {},
        }
    )

    assert payload["source"] == "ai_optimizer"
    assert payload["source_type"] == "ml_model"


@pytest.mark.asyncio
async def test_resolve_id_prefix_returns_single_db_match():
    """Short tokens should resolve from the canonical DB-backed recommendation set."""
    repo = RecommendationRepository()

    class _Resp:
        data = [
            {"id": "abc12345-0000-0000-0000-000000000000", "timestamp": "2026-03-16T10:00:00Z"},
            {"id": "def67890-0000-0000-0000-000000000000", "timestamp": "2026-03-16T09:00:00Z"},
        ]

    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        async def execute(self):
            return _Resp()

    class _Client:
        def table(self, _name):
            return _Query()

    async def _get_client():
        return _Client()

    repo.get_client = _get_client

    resolved = await repo.resolve_id_prefix("abc12345")
    assert resolved == "abc12345-0000-0000-0000-000000000000"


@pytest.mark.asyncio
async def test_control_dedupe_does_not_query_executed_recommendations():
    """Fresh Telegram advisories must not reuse already-actioned recommendation IDs."""
    repo = RecommendationRepository()
    queried_statuses = []

    class _Resp:
        data = []

    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def in_(self, _column, values):
            queried_statuses.extend(values)
            return self

        def gte(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        async def execute(self):
            return _Resp()

    class _Client:
        def table(self, _name):
            return _Query()

    async def _get_client():
        return _Client()

    repo.get_client = _get_client

    duplicate = await repo._find_recent_duplicate_control_recommendation(
        {
            "site_id": "site-002",
            "target_equipment": "S002-AHU-B01",
            "action_type": "ai_optimization",
            "action": {"point": "damper_position", "value": 100.0},
        }
    )

    assert duplicate is None
    assert queried_statuses == ["pending", "approved"]


@pytest.mark.asyncio
async def test_expire_pending_by_source_rules_supersedes_different_target_family():
    """Logical safety gates must expire stale recs even when target_equipment changes."""
    repo = RecommendationRepository()
    stale = Recommendation(
        id="11111111-1111-1111-1111-111111111111",
        site_id="site-002",
        action_type="ai_optimization",
        target_equipment="SITE-002-HVAC-SCHEDULE",
        status=RecommendationStatus.PENDING,
        reason="Shut down HVAC",
        metadata={"source_metadata": {"rule": "closed_empty_building_hvac_running"}},
    )
    unrelated = Recommendation(
        id="22222222-2222-2222-2222-222222222222",
        site_id="site-002",
        action_type="ai_optimization",
        target_equipment="SITE-002-LIGHTING-SCHEDULE",
        status=RecommendationStatus.PENDING,
        metadata={"source_metadata": {"rule": "closed_empty_building_hvac_running"}},
    )
    updated = []
    audit_events = []

    async def _get_by_status(site_id, status, limit=10):
        assert site_id == "site-002"
        assert status == RecommendationStatus.PENDING
        return [stale, unrelated]

    async def _update(_rec_id, rec):
        updated.append(rec)
        return rec

    async def _record_audit_event(**kwargs):
        audit_events.append(kwargs)

    repo.get_by_status = _get_by_status
    repo.update = _update
    repo._record_audit_event = _record_audit_event

    count = await repo.expire_pending_by_source_rules(
        "site-002",
        {"closed_empty_building_hvac_running"},
        superseded_by_rule="occupancy_conflict_blocks_hvac_shutdown",
        superseded_reason="conflict supersedes shutdown",
        target_prefixes=("SITE-002-HVAC",),
    )

    assert count == 1
    assert updated == [stale]
    assert stale.status == RecommendationStatus.EXPIRED
    assert stale.approval_status == "superseded"
    assert stale.metadata["superseded_by_rule"] == "occupancy_conflict_blocks_hvac_shutdown"
    assert unrelated.status == RecommendationStatus.PENDING
    assert len(audit_events) == 1
