"""Recommendation repository write-shape tests."""

import pytest

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
